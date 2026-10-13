"""
entry_window.py
OC_M Project Leader app — main window.
Version: 2026.10.08_01

## ChangeLog

2026.10.08_01: Per-sensor, per-depth grading redesign. REPLACES the old
single-code-per-cast grid (Cast | Quality code | Comment) and the
dump-level default-code/comment group with a stack of 9 SensorRowWidget
instances (see sensor_row_widget.py) - one per graded sensor, each with
its own dump-level grade buttons, cast-level grade buttons, resolved-
value readout, and a collapsible depth-strip for depth-range grading.
Defective-sensor checkboxes are also retired - per developer decision,
"sensor X defective for this dump" and "sensor X graded Bad for this
dump" are the same action now, both expressed through the new
dump-level grade buttons on that sensor's row.

preload_model.py's DumpCastTableModel/QualityCodeDelegate/
CommentDelegate are no longer imported anywhere in this file as of this
version - preload_model.py can now be safely deleted (nothing else in
this app imports it either; it was only ever used by the grid this
version replaces).

Ownership/refresh model: this window owns the live OCMSubmission and
the current cast selection. Each SensorRowWidget is a stateless view;
this window builds a fresh SensorRowContext for a given sensor/cast and
calls that row's refresh() whenever (a) the cast selection changes (all
9 rows refresh), or (b) that ONE sensor's grade changed via its own
row's signal (only that row refreshes - a grade change on one sensor's
dump/cast/depth override cannot affect another sensor's resolved value,
since each sensor's cascade is entirely independent).

QualityLookup and the graded-sensor list are built ONCE at window
construction, from the pre-loader JSON payload (preload_payload[
"graded_sensors"], preload_payload["data_quality_ids"]) - never
hand-typed here. validate_submission() now requires graded_sensors and
good_id as explicit arguments (see output_io.py's 2026-10-08 fix); both
are threaded through from the same source.

Layout: sized for a maximized 14-15" laptop at minimum (per developer
confirmation - the PI is expected to run this maximized, same as the
Excel-driven predecessor), not a small fixed dialog. All 9 sensor rows
are shown stacked, wrapped in a QScrollArea as a safety net for smaller
displays/higher DPI settings, not as the primary interaction model.

Everything else (tree, Analyst's Comments, menu bar, Open/Save/Recent
Files, exit confirmation, SOP/About dialogs) is UNCHANGED from the
original design.
"""

import os
import traceback
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from depth_strip_widget import QualityLookup, ResolvedDepthPoint, ThresholdBounds
from output_io import (
    CastEntry,
    DepthRangeOverride,
    DumpEntry,
    OCMSubmission,
    validate_submission,
)
from recent_files import RecentFiles
from sensor_row_widget import SensorDepthRange, SensorRowContext, SensorRowWidget
from app_settings import AppSettings, STYLE_MODE_CUSTOM, STYLE_MODE_SHARED
from version import CURRENT_VERSION

_SHARED_STYLES_PATH = Path(__file__).resolve().parent.parent / "styles" / "dm_styles.qss"

DUMP_ROLE = Qt.ItemDataRole.UserRole
YEAR_ROLE = Qt.ItemDataRole.UserRole + 1


# ---------------------------------------------------------------------------
# Validation results popup - UNCHANGED from the original design.
# ---------------------------------------------------------------------------
class ValidationResultsDialog(QDialog):
    def __init__(self, problems: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Validation issues found")
        self.resize(640, 420)
        self.setMinimumSize(420, 260)

        layout = QVBoxLayout(self)

        header = QLabel(
            f"{len(problems)} issue(s) found. These will be rejected when this "
            "file is submitted for loading and must be corrected:"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText("\n".join(f"\u2022 {p.detail}" for p in problems))
        layout.addWidget(body, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.setDefault(True)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class OCMEntryWindow(QMainWindow):
    def __init__(self, preload_payload: dict, default_output_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Oceanographic Survey Data Quality Report (OC-M)")
        self.resize(1400, 900)  # sized for a maximized 14-15" laptop; fully resizable

        self._preload_payload = preload_payload
        self._default_output_dir = default_output_dir

        self._quality_lookup = QualityLookup.from_preload_payload(preload_payload)
        self._graded_sensors: list[str] = preload_payload.get("graded_sensors", [])

        self._submission = OCMSubmission.new_from_preload(preload_payload)

        self._current_year: str | None = None
        self._current_dump: str | None = None
        self._current_cast: str | None = None
        self._current_filename: str | None = None
        self._current_filepath: str | None = None
        self._last_problems: list = []
        self._last_save_dir: str | None = None

        app_dir = Path(__file__).resolve().parent
        self._sop_path = app_dir / "docs" / "SEAN OC SOP 11 Data Quality Assignment (OC_M Creation) version 3.pdf"
        self._about_md_path = app_dir / "docs" / "about.md"
        self._recent_files = RecentFiles(app_dir / "data" / "recent_files.json")
        self._app_settings = AppSettings(app_dir / "data" / "app_settings.json")

        self._sensor_rows: dict[str, SensorRowWidget] = {}

        self._build_ui()
        self._build_menu_bar()
        self._apply_saved_style_preference()
        self._populate_tree()

    # ------------------------------------------------------------------
    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: tree (cruise year / dump) ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Cruise year / dump")
        self._tree.setMinimumWidth(220)
        self._tree.itemClicked.connect(self._on_tree_item_clicked)
        splitter.addWidget(self._tree)

        # --- Middle: cast list for the selected dump ---
        cast_panel = QWidget()
        cast_layout = QVBoxLayout(cast_panel)
        cast_layout.addWidget(QLabel("Casts in dump:"))
        self._cast_tree = QTreeWidget()
        self._cast_tree.setHeaderHidden(True)
        self._cast_tree.setMinimumWidth(140)
        self._cast_tree.setMaximumWidth(220)
        self._cast_tree.itemClicked.connect(self._on_cast_item_clicked)
        cast_layout.addWidget(self._cast_tree)
        splitter.addWidget(cast_panel)

        # --- Right: dump/cast header + 9 sensor rows + comments ---
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._lbl_open_file = QLabel("Open file: (unsaved - using pre-load snapshot)")
        self._lbl_open_file.setStyleSheet("color: #8b8067; font-size: 9pt;")
        right_layout.addWidget(self._lbl_open_file)

        self._lbl_dump_title = QLabel("Select a dump from the list on the left.")
        self._lbl_dump_title.setStyleSheet("font-weight: bold; color: #556b2f;")
        right_layout.addWidget(self._lbl_dump_title)

        meta_row = QHBoxLayout()
        self._lbl_ctd = QLabel("CTD: \u2014")
        self._lbl_start_date = QLabel("Start date: \u2014")
        meta_row.addWidget(self._lbl_ctd)
        meta_row.addWidget(self._lbl_start_date)
        meta_row.addStretch()
        right_layout.addLayout(meta_row)

        # Scroll area wrapping all 9 sensor rows - safety net for smaller
        # displays/higher DPI, not the primary interaction model (a
        # maximized 14-15" laptop should show all 9 without scrolling).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setSpacing(2)

        for sensor in self._graded_sensors:
            row = SensorRowWidget(sensor)
            row.dumpGradeChanged.connect(
                lambda qid, s=sensor: self._on_dump_grade_changed(s, qid)
            )
            row.castGradeChanged.connect(
                lambda qid, s=sensor: self._on_cast_grade_changed(s, qid)
            )
            row.depthRangeGraded.connect(
                lambda s, start, end, qid: self._on_depth_range_graded(s, start, end, qid)
            )
            self._sensor_rows[sensor] = row
            rows_layout.addWidget(row)

        rows_layout.addStretch()
        scroll.setWidget(rows_container)
        right_layout.addWidget(scroll, stretch=2)

        comments_group = QWidget()
        comments_layout = QVBoxLayout(comments_group)
        comments_layout.addWidget(QLabel("Analyst's comments (not applied to the database):"))
        self._txt_analyst_comments = QPlainTextEdit()
        self._txt_analyst_comments.setMinimumHeight(70)
        self._txt_analyst_comments.textChanged.connect(self._on_analyst_comments_changed)
        comments_layout.addWidget(self._txt_analyst_comments)
        right_layout.addWidget(comments_group, stretch=0)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)

        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------
    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        act_open = QAction("&Open\u2026", self)
        act_open.triggered.connect(self._on_open)
        file_menu.addAction(act_open)

        act_save = QAction("&Save", self)
        act_save.triggered.connect(self._on_save_current)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save &As\u2026", self)
        act_save_as.triggered.connect(self._on_save)
        file_menu.addAction(act_save_as)

        self._recent_menu = file_menu.addMenu("Recent Files")
        self._refresh_recent_menu()

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        settings_menu = menu_bar.addMenu("&Settings")

        self._act_use_shared_style = QAction("Use shared style sheet (dm_tools)", self)
        self._act_use_shared_style.setCheckable(True)
        self._act_use_shared_style.triggered.connect(self._on_toggle_shared_style)
        settings_menu.addAction(self._act_use_shared_style)

        act_load_custom_style = QAction("Load custom style sheet\u2026", self)
        act_load_custom_style.triggered.connect(self._on_load_custom_style)
        settings_menu.addAction(act_load_custom_style)

        help_menu = menu_bar.addMenu("&Help")

        act_sop = QAction("Open SOP\u2026", self)
        act_sop.triggered.connect(self._on_open_sop)
        help_menu.addAction(act_sop)

        act_about = QAction("&About", self)
        act_about.triggered.connect(self._on_show_about)
        help_menu.addAction(act_about)

    def _apply_saved_style_preference(self):
        """Called once at startup, after the menu exists (so the
        checkable action's state can be set to match). Applies whatever
        style_mode was persisted from a prior session - defaults to
        STYLE_MODE_NONE (no stylesheet, Qt native/OS theme) on a
        genuinely first-ever launch, per explicit developer
        instruction."""
        mode = self._app_settings.style_mode
        if mode == STYLE_MODE_SHARED:
            self._set_stylesheet_from_path(_SHARED_STYLES_PATH, persist=False)
            self._act_use_shared_style.setChecked(True)
        elif mode == STYLE_MODE_CUSTOM and self._app_settings.custom_style_path:
            self._set_stylesheet_from_path(Path(self._app_settings.custom_style_path), persist=False)
        else:
            self._clear_stylesheet(persist=False)

    def _set_stylesheet_from_path(self, path: Path, persist: bool) -> bool:
        if not path.is_file():
            QMessageBox.warning(
                self, "Style sheet not found",
                f"Could not find the style sheet file:\n{path}"
            )
            return False
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self, "Could not read style sheet",
                f"Could not read:\n{path}\n\n{exc}"
            )
            return False

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(text)
        return True

    def _clear_stylesheet(self, persist: bool):
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet("")
        if persist:
            self._app_settings.set_none()

    def _on_toggle_shared_style(self, checked: bool):
        if checked:
            if self._set_stylesheet_from_path(_SHARED_STYLES_PATH, persist=True):
                self._app_settings.set_shared()
            else:
                self._act_use_shared_style.setChecked(False)
        else:
            self._clear_stylesheet(persist=True)

    def _on_load_custom_style(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load custom style sheet", "", "Qt Style Sheets (*.qss);;All files (*.*)"
        )
        if not filepath:
            return
        if self._set_stylesheet_from_path(Path(filepath), persist=True):
            self._app_settings.set_custom(filepath)
            self._act_use_shared_style.blockSignals(True)
            self._act_use_shared_style.setChecked(False)
            self._act_use_shared_style.blockSignals(False)

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        paths = self._recent_files.get_all()
        if not paths:
            empty_act = QAction("(no recent files)", self)
            empty_act.setEnabled(False)
            self._recent_menu.addAction(empty_act)
            return
        for path in paths:
            act = QAction(os.path.basename(path), self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked=False, p=path: self._open_filepath(p))
            self._recent_menu.addAction(act)

    def _on_save_current(self):
        if self._current_filepath:
            self._save_to_path(self._current_filepath)
        else:
            self._on_save()

    def _on_open_sop(self):
        if not self._sop_path.is_file():
            QMessageBox.warning(
                self, "SOP not found",
                f"Expected the SOP document at:\n{self._sop_path}\n\n"
                "Contact the Data Manager if this file is missing."
            )
            return
        webbrowser.open(self._sop_path.as_uri())

    def _on_show_about(self):
        if self._about_md_path.is_file():
            try:
                template = self._about_md_path.read_text(encoding="utf-8")
            except OSError as exc:
                template = f"(Could not read about.md: {exc})"
        else:
            template = "(docs/about.md not found)"

        try:
            body = template.format(
                app_name=CURRENT_VERSION.app_name,
                version=CURRENT_VERSION.version,
                build_date=CURRENT_VERSION.build_date,
            )
        except (KeyError, IndexError):
            body = template

        html_body = f"<pre style='white-space: pre-wrap; font-family: inherit;'>{body}</pre>"
        QMessageBox.about(self, "About", html_body)

    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent):
        reply = QMessageBox.question(
            self, "Confirm exit",
            "Are you sure you want to exit? Click 'Cancel' to return to "
            "the app to save your work.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    def _populate_tree(self):
        self._tree.clear()
        first_dump_item = None
        for year in sorted(self._submission.cruise_years.keys(), reverse=True):
            year_item = QTreeWidgetItem([year])
            year_item.setData(0, YEAR_ROLE, year)
            for dump in sorted(self._submission.cruise_years[year].dumps.keys()):
                dump_item = QTreeWidgetItem([f"Dump {dump}"])
                dump_item.setData(0, YEAR_ROLE, year)
                dump_item.setData(0, DUMP_ROLE, dump)
                year_item.addChild(dump_item)
                if first_dump_item is None:
                    first_dump_item = dump_item
            self._tree.addTopLevelItem(year_item)
        self._tree.expandAll()

        if first_dump_item is not None:
            self._tree.setCurrentItem(first_dump_item)
            year = first_dump_item.data(0, YEAR_ROLE)
            dump = first_dump_item.data(0, DUMP_ROLE)
            self._load_dump_into_form(year, dump)
        else:
            self._clear_form_to_empty_state()

    def _clear_form_to_empty_state(self):
        self._current_year = None
        self._current_dump = None
        self._current_cast = None
        self._lbl_dump_title.setText("Select a dump from the list on the left.")
        self._lbl_ctd.setText("CTD: \u2014")
        self._lbl_start_date.setText("Start date: \u2014")
        self._cast_tree.clear()
        self._txt_analyst_comments.blockSignals(True)
        self._txt_analyst_comments.clear()
        self._txt_analyst_comments.blockSignals(False)
        self._refresh_all_sensor_rows()

    # ------------------------------------------------------------------
    def _on_tree_item_clicked(self, item: QTreeWidgetItem, _col: int):
        dump = item.data(0, DUMP_ROLE)
        year = item.data(0, YEAR_ROLE)
        if dump is None:
            return  # a cruise-year row was clicked, not a dump
        self._load_dump_into_form(year, dump)

    def _load_dump_into_form(self, year: str, dump: str):
        self._current_year = year
        self._current_dump = dump
        self._current_cast = None
        dump_entry = self._submission.cruise_years[year].dumps[dump]

        self._lbl_dump_title.setText(f"Cruise year {year} \u2014 Dump {dump}")
        self._lbl_ctd.setText(f"CTD: {dump_entry.ctd or '\u2014'}")
        self._lbl_start_date.setText(f"Start date: {dump_entry.start_date or '\u2014'}")

        self._txt_analyst_comments.blockSignals(True)
        self._txt_analyst_comments.setPlainText(dump_entry.analyst_comments or "")
        self._txt_analyst_comments.blockSignals(False)

        self._cast_tree.clear()
        first_cast_item = None
        for cast in sorted(dump_entry.casts.keys()):
            item = QTreeWidgetItem([f"Cast {cast}"])
            item.setData(0, Qt.ItemDataRole.UserRole, cast)
            self._cast_tree.addTopLevelItem(item)
            if first_cast_item is None:
                first_cast_item = item

        if first_cast_item is not None:
            self._cast_tree.setCurrentItem(first_cast_item)
            self._current_cast = first_cast_item.data(0, Qt.ItemDataRole.UserRole)

        self._refresh_all_sensor_rows()

    def _on_cast_item_clicked(self, item: QTreeWidgetItem, _col: int):
        self._current_cast = item.data(0, Qt.ItemDataRole.UserRole)
        self._refresh_all_sensor_rows()

    # ------------------------------------------------------------------
    def _current_dump_entry(self) -> DumpEntry | None:
        if self._current_year is None or self._current_dump is None:
            return None
        return self._submission.cruise_years[self._current_year].dumps[self._current_dump]

    def _current_cast_entry(self) -> CastEntry | None:
        dump_entry = self._current_dump_entry()
        if dump_entry is None or self._current_cast is None:
            return None
        return dump_entry.casts.get(self._current_cast)

    def _build_context_for_sensor(self, sensor: str) -> SensorRowContext:
        dump_entry = self._current_dump_entry()
        has_cast = self._current_cast is not None and dump_entry is not None

        if dump_entry is None:
            return SensorRowContext(
                sensor=sensor,
                quality_lookup=self._quality_lookup,
                dump_grade=None,
                cast_grade=None,
                resolved_id=self._quality_lookup.good_id,
                resolved_tier="default",
                depth_points=[],
                existing_depth_ranges=[],
                thresholds=ThresholdBounds.from_preload_payload(self._preload_payload, sensor),
                has_cast_selected=False,
            )

        dump_grade = dump_entry.sensor_dump_grades.get(sensor)

        cast_grade = None
        existing_ranges: list[SensorDepthRange] = []
        depth_points: list[ResolvedDepthPoint] = []
        resolved_id = self._quality_lookup.good_id
        resolved_tier = "default"

        if has_cast:
            cast_entry = dump_entry.casts.get(self._current_cast)
            if cast_entry is not None:
                cast_grade = cast_entry.sensor_cast_grades.get(sensor)
                existing_ranges = [
                    SensorDepthRange(start_depth=o.start_depth, end_depth=o.end_depth)
                    for o in cast_entry.depth_overrides
                    if o.sensor == sensor
                ]
            resolved_id, resolved_tier = dump_entry.resolved_cast_grade(
                sensor, self._current_cast, self._quality_lookup.good_id
            )
            depth_points = self._build_depth_points(sensor, dump_entry, self._current_cast)

        return SensorRowContext(
            sensor=sensor,
            quality_lookup=self._quality_lookup,
            dump_grade=dump_grade,
            cast_grade=cast_grade,
            resolved_id=resolved_id,
            resolved_tier=resolved_tier,
            depth_points=depth_points,
            existing_depth_ranges=existing_ranges,
            thresholds=ThresholdBounds.from_preload_payload(self._preload_payload, sensor),
            has_cast_selected=has_cast,
        )

    def _build_depth_points(self, sensor: str, dump_entry: DumpEntry, cast: str) -> list[ResolvedDepthPoint]:
        """Builds the resolved per-depth series for one sensor/cast,
        combining the ORIGINAL readings from the pre-load payload (this
        window's only source for the raw trace - output_io.py's
        CastEntry never stores readings, only grade overrides) with the
        CURRENT resolved grade from the submission's live override
        cascade (which may differ from the payload's original
        general_grades/depth_grades if the PI has made changes this
        session)."""
        # TODO: Remove debug print statements after fix(es).
        print(f"DEBUG: self._current_year={self._current_year!r} (type {type(self._current_year)})")
        print(f"DEBUG: self._current_dump={self._current_dump!r} (type {type(self._current_dump)})")
        cast_payload = self._find_cast_payload(cast)
        print(
            f"DEBUG: year={self._current_year!r} dump={self._current_dump!r} cast={cast!r} -> found: {cast_payload is not None}")
        if cast_payload is None:
            for cy in self._preload_payload.get("cruise_years", []):
                print(
                    f"DEBUG: comparing cy['cruise_year']={cy['cruise_year']!r} to self._current_year={self._current_year!r} -> equal: {cy['cruise_year'] == self._current_year}")
                for d in cy.get("dumps", []):
                    print(f"DEBUG:     payload has dump={d['dump']!r}, cast keys={list(d.get('casts', {}).keys())!r}")
            return []

        depths = cast_payload.get("depths", [])
        readings = cast_payload.get("readings", {}).get(sensor, [])

        points = []
        for i, depth in enumerate(depths):
            reading = readings[i] if i < len(readings) else None
            quality_id, tier = dump_entry.resolved_depth_grade(
                sensor, cast, depth, self._quality_lookup.good_id
            )
            points.append(ResolvedDepthPoint(
                depth=depth, reading=reading, quality_id=quality_id, tier=tier
            ))
        return points

    def _find_cast_payload(self, cast: str) -> dict | None:
        # TODO: Remove debug prints after fix
        print(f"DEBUG: preload_payload has {len(self._preload_payload.get('cruise_years', []))} cruise_year entries")

        for cy in self._preload_payload.get("cruise_years", []):
            print(f"DEBUG: cy keys = {list(cy.keys())}, cy['cruise_year'] = {cy.get('cruise_year')!r}")
            if cy["cruise_year"] != self._current_year:
                continue
            for d in cy.get("dumps", []):
                if d["dump"] != self._current_dump:
                    continue
                return d.get("casts", {}).get(cast)
        return None

    def _refresh_all_sensor_rows(self):
        for sensor, row in self._sensor_rows.items():
            row.refresh(self._build_context_for_sensor(sensor))

    def _refresh_one_sensor_row(self, sensor: str):
        self._sensor_rows[sensor].refresh(self._build_context_for_sensor(sensor))

    # ------------------------------------------------------------------
    def _on_dump_grade_changed(self, sensor: str, quality_id: int | None):
        dump_entry = self._current_dump_entry()
        if dump_entry is None:
            return
        if quality_id is None:
            dump_entry.sensor_dump_grades.pop(sensor, None)
        else:
            dump_entry.sensor_dump_grades[sensor] = quality_id
        self._refresh_one_sensor_row(sensor)

    def _on_cast_grade_changed(self, sensor: str, quality_id: int | None):
        cast_entry = self._current_cast_entry()
        if cast_entry is None:
            return
        if quality_id is None:
            cast_entry.sensor_cast_grades.pop(sensor, None)
        else:
            cast_entry.sensor_cast_grades[sensor] = quality_id
        self._refresh_one_sensor_row(sensor)

    def _on_depth_range_graded(self, sensor: str, start_depth: int, end_depth: int, quality_id: int):
        cast_entry = self._current_cast_entry()
        if cast_entry is None:
            return
        cast_entry.depth_overrides.append(
            DepthRangeOverride(
                sensor=sensor, start_depth=start_depth, end_depth=end_depth, quality_id=quality_id
            )
        )
        self._refresh_one_sensor_row(sensor)

    def _on_analyst_comments_changed(self):
        d = self._current_dump_entry()
        if d is None:
            return
        d.analyst_comments = self._txt_analyst_comments.toPlainText()

    # ------------------------------------------------------------------
    def _run_validation_and_report(self):
        self._last_problems = validate_submission(
            self._submission, self._graded_sensors, self._quality_lookup.good_id
        )

        if not self._last_problems:
            QMessageBox.information(
                self, "Validation",
                "No issues found \u2014 every graded cast has a comment where required."
            )
            return

        dlg = ValidationResultsDialog(self._last_problems, self)
        dlg.exec()

    # ------------------------------------------------------------------
    def _on_save(self):
        if self._last_save_dir is None:
            os.makedirs(self._default_output_dir, exist_ok=True)
            start_path = os.path.join(self._default_output_dir, "oc_m_submission.json")
        else:
            start_path = ""

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save OC_M submission", start_path, "JSON files (*.json)"
        )
        if not filepath:
            return

        self._save_to_path(filepath)

    def _save_to_path(self, filepath: str):
        try:
            self._submission.save(filepath)
        except OSError as exc:
            self._show_error_dialog("Save failed", filepath, exc)
            return

        self._last_save_dir = os.path.dirname(filepath)
        self._current_filepath = filepath
        self._current_filename = os.path.basename(filepath)
        self._lbl_open_file.setText(f"Open file: {self._current_filename}")
        self._recent_files.add(filepath)
        self._refresh_recent_menu()
        self._run_validation_and_report()

    def _on_open(self):
        start_path = self._last_save_dir or ""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open OC_M submission", start_path, "JSON files (*.json)"
        )
        if not filepath:
            return
        self._open_filepath(filepath)

    def _open_filepath(self, filepath: str):
        try:
            loaded = OCMSubmission.load(filepath)
            restricted = loaded.restrict_onto_preload_shell(self._preload_payload)
        except Exception as exc:
            self._show_error_dialog("Open failed", filepath, exc)
            return

        self._last_save_dir = os.path.dirname(filepath)
        self._submission = restricted
        self._current_filepath = filepath
        self._current_filename = os.path.basename(filepath)
        self._lbl_open_file.setText(f"Open file: {self._current_filename}")
        self._recent_files.add(filepath)
        self._refresh_recent_menu()
        self._populate_tree()
        self._run_validation_and_report()

    def _show_error_dialog(self, title: str, filepath: str, exc: Exception):
        details = traceback.format_exc()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(f"{title}:\n{filepath}\n\n{type(exc).__name__}: {exc}")
        box.setDetailedText(details)
        box.exec()
