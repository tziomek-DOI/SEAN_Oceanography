"""
entry_window.py
OC_M Project Leader app — main window.
Version: 2026.10.22_03

## ChangeLog

2026.10.22_02: Fixed initial-open pane collapse. _fit_tree_width()
previously measured ONLY item content (sizeHintForColumn), which
returns near-zero width before anything is populated into a tree -
on first launch, both left panes rendered far narrower than their own
header text ("Cruise year / dump", "Casts in dump:"). Now takes the
max of content width and header/label width (via QFontMetrics) as a
floor. _dump_tree's own header text is used automatically (its header
isn't hidden); _cast_tree's header IS hidden, so a new
self._lbl_casts_in_dump reference was kept and passed in explicitly,
since "Casts in dump:" lives in a separate QLabel above the tree, not
in the tree's own header.

2026.10.22_01: Replaced hardcoded pixel widths for the two left-side
panes (dump tree, cast tree) with content-driven sizing. Added
_fit_tree_width(), which uses resizeColumnToContents(0) +
sizeHintForColumn(0) to measure each tree's actual content width, plus
a single small _TREE_WIDTH_PADDING constant for scrollbar/frame slop
(not a per-pane guessed total). _dump_tree is fitted once in
_populate_tree() since its content (cruise years/dumps) is static per
file. _cast_tree is RE-fitted every time _load_dump_into_form()
repopulates it, since cast labels ("Cast xx - Station yy") vary in
length per dump. splitter.setSizes([...]) is now recalculated from
these measured widths instead of hardcoded numbers, at both initial
populate and every dump-change. Removed the old fixed setMinimumWidth/
setMaximumWidth values entirely - minimum width is now also derived
from measured content (via the same helper) so the user can still
drag narrower if they want, but nothing is hardcoded. Also renamed
self._tree -> self._dump_tree throughout (no longer adequately
descriptive now that there are two tree widgets).

2026.10.20_03: Sensor-grade propagation. Per explicit PI instruction:
grading conductivity or temperature (at ANY granularity - dump, cast,
or depth-range, including reset/clear-all) now ALSO applies the
identical action to salinity and sigma_t, since those two are
physically derived from conductivity/temperature in CTD oceanography.
Propagation is NON-TRANSITIVE and ONE-TIME: salinity/sigma_t are never
themselves propagation sources, and propagation re-fires fresh every
time the source sensor's grade changes again - there is no persistent
"linked" state, so the PI can freely override a propagated grade on
salinity/sigma_t afterward, and it will simply be overwritten again the
next time conductivity or temperature is re-graded (per explicit PI
confirmation - this is intentional, not a bug to fix later).

PROPAGATION_TARGETS (module-level dict) is the single source of truth:
conductivity -> [salinity, sigma_t], temperature -> [salinity, sigma_t].
Fluorescence/OBS/pressure/oxygen/par have no entry (no propagation).
Pressure was explicitly EXCLUDED per PI instruction - a bad pressure
reading implies the cast's entire DEPTH AXIS may be suspect, which is a
cast/dump-level concern this app has no mechanism to represent (depths
is a flat index, not a gradeable quantity) and is explicitly NOT handled
by this feature.

All five grade-mutating handlers (_on_dump_grade_changed,
_on_cast_grade_changed, _on_depth_range_graded, _on_depth_range_reset,
_on_all_depth_ranges_cleared) now determine the full list of affected
sensors (source + propagation targets) up front, collect clobber/
downgrade info for ALL of them, and show ONE combined confirmation
dialog covering the source sensor's own effects AND each target
sensor's resulting change - per explicit PI instruction: "warn, then
override" - propagation never silently no-ops or partially applies on a
target sensor; if propagating would downgrade salinity's existing Q to
match conductivity's new B, the dialog says so explicitly, and on
confirmation it is applied in full, the same unconditional-overwrite
(Option C) semantics already used elsewhere in this file. Declining the
dialog is a true no-op for ALL affected sensors, including the source
sensor's own grade change - consistent with the existing clobber-dialog
contract.

_confirm_clobber() gained a third, optional parameter (sensor_changes)
for the new "sensor X will also be graded Y -> Z" dialog section,
distinct from the existing cast/depth sections.

Comments (_on_cast_comment_changed, the dump-comment-copy button) are
NOT propagated - nothing in the PI's instructions covers comments, and
a comment isn't a graded quantity each sensor cascades independently
over.

2026.10.20_02: Added a "Copy to all casts in dump" button next to the
per-cast comment box, to reduce the tedium of a dump-level grade change
requiring an identical comment on every cast in that dump. Clicking it
takes the CURRENTLY DISPLAYED cast's comment text and appends it
(separated by a visual divider, not overwritten/concatenated with no
boundary) to every OTHER cast's comment in the same dump - existing
comments are preserved, never silently overwritten. No confirmation
dialog, since this is reversible by just editing the text afterward.

Button is enabled only when at least one graded sensor has a non-Good
dump-level grade set on the CURRENTLY SELECTED dump. Refreshed via
_refresh_copy_comment_button(), called alongside the existing
_refresh_cast_comment_box() at every point the selected dump/cast
changes or a dump-level grade changes. Also explicitly disabled in
_clear_form_to_empty_state() (a real gap in the first pass of this
feature - that function clears/disables the comment box inline without
calling _refresh_cast_comment_box(), so the new button would have been
left stale/enabled otherwise).

2026.10.20_01: Sets CastEntry.cast_dirty = True at every site that
mutates a cast's grades, comment, or depth array - supports the Data
Manager's future ingestion service doing a streamlined UPDATE instead
of rewriting every row of every cast in the file. Six call sites:
_on_cast_grade_changed, _on_depth_range_graded, _on_cast_comment_
changed, _on_depth_range_reset, _on_all_depth_ranges_cleared, and
_on_dump_grade_changed (set INSIDE its per-cast loop, on every cast
actually touched by either the cast-override-overwrite branch or the
depth-invariant-enforcement branch).

2026.10.19_02: Reads graded_sensors/data_quality_ids/thresholds from
self._submission (now populated correctly after output_io.py's
2026.10.19_02 structural-parity fix) instead of only ever trusting the
one-time preload_payload dict passed in at construction. This means a
REOPENED file now correctly restores these facts from the file itself.
self._preload_payload is retained only as a thin wrapper
({"thresholds": self._submission.thresholds}) for ThresholdBounds.
from_preload_payload()'s existing call signature.

2026.10.19_01: Threads severity_by_id through to output_io.py's
resolved_cast_grade()/resolved_depth_grade()/validate_submission().

2026.10.16_04: Hierarchy-invariant enforcement + clobber warning.
Establishes, as an invariant actively enforced on every grade change,
the rule: Dump -> Cast -> Depth, and nothing downstream may ever be a
BETTER (less severe) grade than whatever is immediately upstream of it.
Before any SET (not clear) runs, a Yes/No warning dialog
(_confirm_clobber()) lists every cast/depth that WILL be downgraded.
Choosing No, or closing the dialog, makes this a true no-op.

2026.10.13_05: Cast list now shows "Cast xx - Station yy" instead of
just "Cast xx", using CastEntry.station. Falls back to just "Cast xx"
if station is missing.

2026.10.13_04: Wired up depth-range deletion (superseded by the
2026.10.16 flat-array migration).

2026.10.13_03: Fixed validator false-positive: CastEntry.comment had no
UI control anywhere. Added a per-cast comment box, wired to
CastEntry.comment via _on_cast_comment_changed(), populated/cleared on
cast selection via _refresh_cast_comment_box().

2026.10.13_02: Fixed KeyError crash on dump-level and cast-level grade
button clicks - lambda connections declared only one parameter against
signals that emit two arguments.

2026.10.13_01: Single-file architecture pivot. This window no longer
keeps a separate self._preload_payload dict around as a second source
of truth for cast readings - OCMSubmission.load() is now the only load
path, and CastEntry itself holds depths/readings directly.

2026.10.08_01: Per-sensor, per-depth grading redesign. REPLACES the old
single-code-per-cast grid with a stack of 9 SensorRowWidget instances -
one per graded sensor, each with its own dump-level grade buttons,
cast-level grade buttons, resolved-value readout, and a collapsible
depth-strip for depth-range grading.

Ownership/refresh model: this window owns the live OCMSubmission and
the current cast selection. Each SensorRowWidget is a stateless view;
this window builds a fresh SensorRowContext for a given sensor/cast and
calls that row's refresh() whenever the cast selection changes (all 9
rows refresh) or that ONE sensor's grade changed via its own row's
signal (only that row refreshes - EXCEPT as of 2026.10.20_03, where a
propagating sensor change must also refresh every TARGET sensor's row,
since propagation changes their resolved values too).

Layout: sized for a maximized 14-15" laptop at minimum. All 9 sensor
rows are shown stacked, wrapped in a QScrollArea as a safety net for
smaller displays/higher DPI settings.

Everything else (tree, Analyst's Comments, menu bar, Open/Save/Recent
Files, exit confirmation, SOP/About dialogs) is UNCHANGED from the
original design.
"""

import os
import traceback
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
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
    DumpEntry,
    OCMSubmission,
    validate_submission,
)
from recent_files import RecentFiles
from sensor_row_widget import SensorRowContext, SensorRowWidget
from app_settings import AppSettings, STYLE_MODE_CUSTOM, STYLE_MODE_SHARED
from version import CURRENT_VERSION

_SHARED_STYLES_PATH = Path(__file__).resolve().parent.parent / "styles" / "dm_styles.qss"

DUMP_ROLE = Qt.ItemDataRole.UserRole
YEAR_ROLE = Qt.ItemDataRole.UserRole + 1

# Fixed padding added to a tree's measured content width to account for
# scrollbar/frame slop that resizeColumnToContents()/sizeHintForColumn()
# don't fully capture pre-render. This is a small, stable constant - NOT
# a per-pane guessed total width (see 2026.10.22_01 changelog).
_TREE_WIDTH_PADDING = 32

# Sensor-grade propagation (2026.10.20_03) - per explicit PI
# instruction: grading conductivity or temperature at ANY granularity
# also applies the identical action to salinity and sigma_t. This is
# the SINGLE SOURCE OF TRUTH for which sensors propagate to which -
# non-transitive (salinity/sigma_t are never keys here) and deliberately
# does NOT include pressure (a bad pressure reading implies the cast's
# depth axis itself may be suspect - a cast/dump-level concern this app
# has no mechanism to represent, explicitly out of scope per the PI).
PROPAGATION_TARGETS: dict[str, list[str]] = {
    "conductivity": ["salinity", "sigma_t"],
    "temperature": ["salinity", "sigma_t"],
}


def _affected_sensors(sensor: str) -> list[str]:
    """Returns [sensor] + whatever it propagates to, per
    PROPAGATION_TARGETS. The source sensor is always first."""
    return [sensor] + PROPAGATION_TARGETS.get(sensor, [])


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

        self._default_output_dir = default_output_dir

        self._submission = OCMSubmission.from_payload(preload_payload)

        self._quality_lookup = QualityLookup.from_preload_payload({
            "data_quality_ids": self._submission.data_quality_ids
        })
        self._graded_sensors: list[str] = self._submission.graded_sensors

        self._preload_payload = {"thresholds": self._submission.thresholds}

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
        for row in self._sensor_rows.values():
            row.set_show_tooltips(self._app_settings.show_depth_tooltips)
        self._populate_tree()

# ------------------------------------------------------------------
    def _build_ui(self):
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: tree (cruise year / dump) ---
        self._dump_tree = QTreeWidget()
        self._dump_tree.setHeaderLabel("Cruise year / dump")
        self._dump_tree.itemClicked.connect(self._on_tree_item_clicked)
        self._splitter.addWidget(self._dump_tree)

        # --- Middle: cast list for the selected dump ---
        cast_panel = QWidget()
        cast_layout = QVBoxLayout(cast_panel)
        self._lbl_casts_in_dump = QLabel("Casts in dump:")
        cast_layout.addWidget(self._lbl_casts_in_dump)
        self._cast_tree = QTreeWidget()
        self._cast_tree.setHeaderHidden(True)
        self._cast_tree.itemClicked.connect(self._on_cast_item_clicked)
        cast_layout.addWidget(self._cast_tree)
        self._splitter.addWidget(cast_panel)

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

        # Per-CAST comment (distinct from the per-DUMP "Analyst's
        # comments" box further down). This is the field
        # validate_submission() actually checks.
        cast_comment_group = QWidget()
        cast_comment_layout = QVBoxLayout(cast_comment_group)
        cast_comment_layout.setContentsMargins(0, 0, 0, 0)

        comment_header_row = QHBoxLayout()
        comment_header_row.addWidget(
            QLabel("Cast comment (required if any sensor is graded non-Good):")
        )
        comment_header_row.addStretch()
        self._btn_copy_comment_to_dump = QPushButton("Copy to all casts in dump")
        self._btn_copy_comment_to_dump.setEnabled(False)
        self._btn_copy_comment_to_dump.clicked.connect(self._on_copy_comment_to_dump_clicked)
        comment_header_row.addWidget(self._btn_copy_comment_to_dump)
        cast_comment_layout.addLayout(comment_header_row)

        self._txt_cast_comment = QPlainTextEdit()
        self._txt_cast_comment.setMaximumHeight(50)
        self._txt_cast_comment.textChanged.connect(self._on_cast_comment_changed)
        cast_comment_layout.addWidget(self._txt_cast_comment)
        right_layout.addWidget(cast_comment_group)

        # Scroll area wrapping all 9 sensor rows.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setSpacing(2)

        for sensor in self._graded_sensors:
            row = SensorRowWidget(sensor)
            row.dumpGradeChanged.connect(
                lambda _sensor_arg, qid, s=sensor: self._on_dump_grade_changed(s, qid)
            )
            row.castGradeChanged.connect(
                lambda _sensor_arg, qid, s=sensor: self._on_cast_grade_changed(s, qid)
            )
            row.depthRangeGraded.connect(
                lambda s, start, end, qid: self._on_depth_range_graded(s, start, end, qid)
            )
            row.depthRangeReset.connect(
                lambda s, start, end: self._on_depth_range_reset(s, start, end)
            )
            row.allDepthRangesCleared.connect(
                lambda s: self._on_all_depth_ranges_cleared(s)
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

        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setStretchFactor(2, 1)

        self.setCentralWidget(self._splitter)

    # ------------------------------------------------------------------
    def _fit_tree_width(self, tree: QTreeWidget, header_label: QLabel | None = None) -> int:
        """Measures a QTreeWidget's actual content width (column 0) and
        returns max(content width, header/label width) + padding. Also
        applies that same value as the tree's minimum width, so the
        splitter can't be dragged narrower than the content needs while
        still allowing the user to drag it WIDER if they want. Replaces
        the old hardcoded setMinimumWidth/setMaximumWidth pixel values
        (2026.10.22_01) - this is entirely content-driven, no guessed
        numbers.

        header_label (2026.10.22_02): when the tree has no items yet
        (e.g. on initial open before anything is populated),
        sizeHintForColumn() alone can return a near-zero width, making
        the pane collapse below its own header text. Pass in whichever
        QLabel/header text should set a floor on the width - for
        _dump_tree that's its own setHeaderLabel() text; for _cast_tree
        (header hidden) that's the separate "Casts in dump:" QLabel
        above it."""
        tree.resizeColumnToContents(0)
        content_width = tree.sizeHintForColumn(0)

        label_width = 0
        if header_label is not None:
            metrics = QFontMetrics(header_label.font())
            label_width = metrics.horizontalAdvance(header_label.text())
        elif tree.headerItem() is not None and not tree.isHeaderHidden():
            metrics = QFontMetrics(tree.font())
            label_width = metrics.horizontalAdvance(tree.headerItem().text(0))

        width = max(content_width, label_width) + _TREE_WIDTH_PADDING
        tree.setMinimumWidth(width)
        return width

    def _apply_splitter_sizes(self):
        """Recomputes all three splitter pane widths from the two left
        trees' CURRENT measured content, giving every remaining pixel
        to the grading pane (index 2). Safe to call repeatedly - e.g.
        once after _populate_tree() and again every time
        _load_dump_into_form() repopulates _cast_tree with
        differently-sized labels."""
        dump_width = self._fit_tree_width(self._dump_tree)
        cast_width = self._fit_tree_width(self._cast_tree, header_label=self._lbl_casts_in_dump)
        total = self._splitter.width() or self.width()
        right_width = max(total - dump_width - cast_width, 0)
        self._splitter.setSizes([dump_width, cast_width, right_width])

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

        settings_menu.addSeparator()

        self._act_show_tooltips = QAction("Show depth hover tooltip", self)
        self._act_show_tooltips.setCheckable(True)
        self._act_show_tooltips.setChecked(self._app_settings.show_depth_tooltips)
        self._act_show_tooltips.triggered.connect(self._on_toggle_tooltips)
        settings_menu.addAction(self._act_show_tooltips)

        help_menu = menu_bar.addMenu("&Help")

        act_sop = QAction("Open SOP\u2026", self)
        act_sop.triggered.connect(self._on_open_sop)
        help_menu.addAction(act_sop)

        act_about = QAction("&About", self)
        act_about.triggered.connect(self._on_show_about)
        help_menu.addAction(act_about)

    def _apply_saved_style_preference(self):
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

    def _on_toggle_tooltips(self, checked: bool):
        self._app_settings.set_show_depth_tooltips(checked)
        for row in self._sensor_rows.values():
            row.set_show_tooltips(checked)

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
        self._dump_tree.clear()
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
            self._dump_tree.addTopLevelItem(year_item)
        self._dump_tree.expandAll()

        if first_dump_item is not None:
            self._dump_tree.setCurrentItem(first_dump_item)
            year = first_dump_item.data(0, YEAR_ROLE)
            dump = first_dump_item.data(0, DUMP_ROLE)
            self._load_dump_into_form(year, dump)
        else:
            self._clear_form_to_empty_state()
            self._apply_splitter_sizes()

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
        self._txt_cast_comment.blockSignals(True)
        self._txt_cast_comment.clear()
        self._txt_cast_comment.setEnabled(False)
        self._txt_cast_comment.blockSignals(False)
        self._btn_copy_comment_to_dump.setEnabled(False)
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
            cast_entry = dump_entry.casts[cast]
            label = f"Cast {cast}"
            if cast_entry.station:
                label += f" - Station {cast_entry.station}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, cast)
            self._cast_tree.addTopLevelItem(item)
            if first_cast_item is None:
                first_cast_item = item

        if first_cast_item is not None:
            self._cast_tree.setCurrentItem(first_cast_item)
            self._current_cast = first_cast_item.data(0, Qt.ItemDataRole.UserRole)

        self._refresh_cast_comment_box()
        self._refresh_all_sensor_rows()
        self._apply_splitter_sizes()

    def _on_cast_item_clicked(self, item: QTreeWidgetItem, _col: int):
        self._current_cast = item.data(0, Qt.ItemDataRole.UserRole)
        self._refresh_cast_comment_box()
        self._refresh_all_sensor_rows()

    def _refresh_cast_comment_box(self):
        cast_entry = self._current_cast_entry()
        self._txt_cast_comment.blockSignals(True)
        self._txt_cast_comment.setPlainText(cast_entry.comment if cast_entry and cast_entry.comment else "")
        self._txt_cast_comment.setEnabled(cast_entry is not None)
        self._txt_cast_comment.blockSignals(False)
        self._refresh_copy_comment_button()

    def _refresh_copy_comment_button(self):
        """Enabled only when the CURRENTLY SELECTED dump has at least
        one graded sensor with a non-Good dump-level grade - the
        condition under which validate_submission()'s missing_comment
        rule is likely to require a comment on every cast in this dump.
        Disabled when no dump is selected, or when every sensor's
        dump-level grade is Good/unset."""
        dump_entry = self._current_dump_entry()
        if dump_entry is None or self._current_cast is None:
            self._btn_copy_comment_to_dump.setEnabled(False)
            return

        any_non_good_dump_grade = any(
            dump_entry.sensor_dump_grades.get(sensor) not in (None, self._quality_lookup.good_id)
            for sensor in self._graded_sensors
        )
        self._btn_copy_comment_to_dump.setEnabled(any_non_good_dump_grade)

    def _on_cast_comment_changed(self):
        cast_entry = self._current_cast_entry()
        if cast_entry is None:
            return
        cast_entry.comment = self._txt_cast_comment.toPlainText()
        cast_entry.cast_dirty = True

    def _on_copy_comment_to_dump_clicked(self):
        """Appends the CURRENTLY DISPLAYED cast's comment text to every
        OTHER cast's comment in the same dump, separated by a visual
        divider - never overwrites an existing comment outright. The
        source cast itself is left untouched."""
        dump_entry = self._current_dump_entry()
        source_cast_entry = self._current_cast_entry()
        if dump_entry is None or source_cast_entry is None:
            return

        source_text = (source_cast_entry.comment or "").strip()
        if not source_text:
            return

        for cast, cast_entry in dump_entry.casts.items():
            if cast == self._current_cast:
                continue
            existing = (cast_entry.comment or "").strip()
            if existing:
                cast_entry.comment = f"{existing}\n---\n{source_text}"
            else:
                cast_entry.comment = source_text
            cast_entry.cast_dirty = True

        self._refresh_cast_comment_box()

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
                depths_differing_from_cast=0,
                thresholds=ThresholdBounds.from_preload_payload(self._preload_payload, sensor),
                has_cast_selected=False,
            )

        dump_grade = dump_entry.sensor_dump_grades.get(sensor)

        cast_grade = None
        depths_differing = 0
        depth_points: list[ResolvedDepthPoint] = []
        resolved_id = self._quality_lookup.good_id
        resolved_tier = "default"

        if has_cast:
            cast_entry = dump_entry.casts.get(self._current_cast)
            if cast_entry is not None:
                cast_grade = cast_entry.sensor_cast_grades.get(sensor)
            resolved_id, resolved_tier = dump_entry.resolved_cast_grade(
                sensor, self._current_cast, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
            )
            if cast_entry is not None:
                depth_ids = cast_entry.depth_quality_ids.get(sensor, [])
                depths_differing = sum(1 for v in depth_ids if v != resolved_id)
            depth_points = self._build_depth_points(sensor, cast_entry)

        return SensorRowContext(
            sensor=sensor,
            quality_lookup=self._quality_lookup,
            dump_grade=dump_grade,
            cast_grade=cast_grade,
            resolved_id=resolved_id,
            resolved_tier=resolved_tier,
            depth_points=depth_points,
            depths_differing_from_cast=depths_differing,
            thresholds=ThresholdBounds.from_preload_payload(self._preload_payload, sensor),
            has_cast_selected=has_cast,
        )

    def _build_depth_points(self, sensor: str, cast_entry: CastEntry | None) -> list[ResolvedDepthPoint]:
        if cast_entry is None:
            return []

        dump_entry = self._current_dump_entry()
        depths = cast_entry.depths
        readings = cast_entry.readings.get(sensor, [])

        points = []
        for i, depth in enumerate(depths):
            reading = readings[i] if i < len(readings) else None
            quality_id, tier = dump_entry.resolved_depth_grade(
                sensor, self._current_cast, depth, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
            )
            points.append(ResolvedDepthPoint(
                depth=depth, reading=reading, quality_id=quality_id, tier=tier
            ))
        return points

    def _refresh_all_sensor_rows(self):
        for sensor, row in self._sensor_rows.items():
            row.refresh(self._build_context_for_sensor(sensor))

    def _refresh_one_sensor_row(self, sensor: str):
        self._sensor_rows[sensor].refresh(self._build_context_for_sensor(sensor))

    def _refresh_sensor_rows(self, sensors: list[str]):
        """Refreshes exactly the given sensor rows. Added 2026.10.20_03
        for propagation - a propagating sensor change affects its own
        row AND every target sensor's row, which the pre-existing
        _refresh_one_sensor_row() (singular) couldn't express."""
        for sensor in sensors:
            if sensor in self._sensor_rows:
                self._refresh_one_sensor_row(sensor)

    # ------------------------------------------------------------------
    def _collect_clobbered_depths(
            self, cast_entry: CastEntry, sensor: str, new_cast_level_id: int, station: str | None, cast: str
    ) -> list[tuple[str, str | None, int, str]]:
        """Returns (cast, station, depth, sensor) tuples for every depth
        under cast_entry whose stored depth_quality_ids[sensor] value is
        BETTER (less severe) than new_cast_level_id. The sensor field
        (2026.10.20_04) was added when propagation first merged MULTIPLE
        sensors' results into one list - before propagation, every
        caller only ever dealt with one sensor at a time, so the sensor
        name was implicit and never needed to travel with the tuple.
        Without it, three propagated sensors sharing the same bad depth
        rendered as three identical, unlabeled "0m" lines in
        _confirm_clobber()'s detail list."""
        depth_ids = cast_entry.depth_quality_ids.get(sensor, [])
        new_severity = self._quality_lookup.severity(new_cast_level_id)
        out = []
        for i, depth in enumerate(cast_entry.depths):
            if i < len(depth_ids) and self._quality_lookup.severity(depth_ids[i]) < new_severity:
                out.append((cast, station, depth, sensor))
        return out

    def _collect_downgraded_casts_and_depths(
            self, dump_entry: DumpEntry, sensor: str, new_dump_grade: int
    ) -> tuple[list[str], list[tuple[str, str | None, int, str]]]:
        """Dump-level scan: returns (cast_names, depth_tuples) where
        cast_names lists every cast whose OWN sensor_cast_grades
        override is better than new_dump_grade, and depth_tuples lists
        every depth that would additionally need bumping."""
        new_dump_severity = self._quality_lookup.severity(new_dump_grade)
        downgraded_casts = []
        depth_tuples = []
        for cast, cast_entry in sorted(dump_entry.casts.items()):
            existing_cast_grade = cast_entry.sensor_cast_grades.get(sensor)
            if existing_cast_grade is not None and self._quality_lookup.severity(existing_cast_grade) < new_dump_severity:
                downgraded_casts.append(cast)
                effective_cast_level_id = new_dump_grade
            else:
                effective_cast_level_id = existing_cast_grade if existing_cast_grade is not None else new_dump_grade
            depth_tuples.extend(
                self._collect_clobbered_depths(
                    cast_entry, sensor, effective_cast_level_id, cast_entry.station, cast
                )
            )
        return downgraded_casts, depth_tuples

    def _confirm_clobber(
            self,
            downgraded_casts: list[str],
            affected_depths: list[tuple[str, str | None, int, str]],
            sensor_changes: list[tuple[str, int | None, int]] | None = None,
    ) -> bool:
        """Shows a Yes/No warning listing every cast and/or depth that
        WILL be downgraded, PLUS (2026.10.20_03) any propagation-target
        sensor whose own grade will also change. Returns True iff the
        PI chose to proceed; returns True with no dialog at all if
        nothing would actually be affected. No/cancelled means a TRUE
        no-op for everything the caller was about to do, including
        propagation.

        sensor_changes (new, 2026.10.20_03): list of
        (sensor_name, old_value_or_None, new_value) tuples for
        propagation targets whose CAST-LEVEL resolved value will change
        as a result of this action - distinct from the existing cast/
        depth sections, since propagation is the first scenario where
        one action changes a DIFFERENT sensor's grade directly, not just
        cascading within the same sensor's own hierarchy."""
        sensor_changes = sensor_changes or []
        if not downgraded_casts and not affected_depths and not sensor_changes:
            return True

        lines = []

        if sensor_changes:
            lines.append("Sensors that will also be graded (propagation):")
            for sensor, old_value, new_value in sensor_changes:
                old_label = self._quality_lookup.label(old_value) if old_value is not None else "(none)"
                new_label = self._quality_lookup.label(new_value)
                lines.append(f"    {sensor}: {old_label} -> {new_label}")
            lines.append("")

        if downgraded_casts:
            lines.append("Casts with their own grade that will be overwritten:")
            for cast in downgraded_casts:
                lines.append(f"    Cast {cast}")
            lines.append("")

        if affected_depths:
            lines.append("Depths that will be overwritten:")
            last_cast = None
            for cast, station, depth, sensor_name in sorted(affected_depths):
                if cast != last_cast:
                    label = f"Cast {cast}" + (f" - Station {station}" if station else "")
                    lines.append(label + ":")
                    last_cast = cast
                lines.append(f"    {depth}m ({sensor_name})")

        summary_parts = []
        if sensor_changes:
            summary_parts.append(f"{len(sensor_changes)} other sensor(s) will also be graded")
        if downgraded_casts:
            summary_parts.append(f"{len(downgraded_casts)} cast(s)")
        if affected_depths:
            summary_parts.append(f"{len(affected_depths)} depth(s)")
        summary = ", ".join(summary_parts)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Lower-level grades will be overwritten")
        box.setText(
            f"{summary} currently have a grade that is BETTER than the one "
            "you are about to set, or will be changed by propagation to a "
            "related sensor. A cast or depth can never be graded better "
            "than the level above it.\n\n"
            "No changes have been made yet. Proceed?"
        )
        box.setDetailedText("\n".join(lines))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    def _on_dump_grade_changed(self, sensor: str, quality_id: int | None):
        dump_entry = self._current_dump_entry()
        if dump_entry is None:
            return

        affected_sensors = _affected_sensors(sensor)

        if quality_id is not None:
            all_downgraded_casts: list[str] = []
            all_affected_depths: list[tuple[str, str | None, int, str]] = []
            sensor_changes: list[tuple[str, int | None, int]] = []

            for s in affected_sensors:
                downgraded_casts, affected_depths = self._collect_downgraded_casts_and_depths(
                    dump_entry, s, quality_id
                )
                all_downgraded_casts.extend(f"{c} ({s})" for c in downgraded_casts)
                all_affected_depths.extend(affected_depths)
                if s != sensor:
                    old_value = dump_entry.sensor_dump_grades.get(s)
                    if old_value != quality_id:
                        sensor_changes.append((s, old_value, quality_id))

            if not self._confirm_clobber(all_downgraded_casts, all_affected_depths, sensor_changes):
                return  # true no-op - nothing applied, including propagation

        for s in affected_sensors:
            if quality_id is None:
                dump_entry.sensor_dump_grades.pop(s, None)
            else:
                dump_entry.sensor_dump_grades[s] = quality_id
                for cast, cast_entry in dump_entry.casts.items():
                    existing_cast_grade = cast_entry.sensor_cast_grades.get(s)
                    if existing_cast_grade is not None and self._quality_lookup.severity(existing_cast_grade) < self._quality_lookup.severity(quality_id):
                        cast_entry.sensor_cast_grades[s] = quality_id
                        cast_entry.cast_dirty = True

            # Whether or not a cast-level override was just overwritten
            # above, every cast's depth array must satisfy the invariant
            # against its own (possibly-updated) resolved value.
            for cast, cast_entry in dump_entry.casts.items():
                resolved_id, _tier = dump_entry.resolved_cast_grade(
                    s, cast, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
                )
                depth_ids = cast_entry.depth_quality_ids.get(s)
                if depth_ids is None:
                    cast_entry.depth_quality_ids[s] = [resolved_id] * len(cast_entry.depths)
                    cast_entry.cast_dirty = True
                else:
                    resolved_severity = self._quality_lookup.severity(resolved_id)
                    for i, v in enumerate(depth_ids):
                        if self._quality_lookup.severity(v) < resolved_severity:
                            depth_ids[i] = resolved_id
                            cast_entry.cast_dirty = True

        self._refresh_sensor_rows(affected_sensors)
        self._refresh_copy_comment_button()

    def _on_cast_grade_changed(self, sensor: str, quality_id: int | None):
        cast_entry = self._current_cast_entry()
        dump_entry = self._current_dump_entry()
        if cast_entry is None or dump_entry is None:
            return

        affected_sensors = _affected_sensors(sensor)

        if quality_id is not None:
            all_affected_depths: list[tuple[str, str | None, int, str]] = []
            sensor_changes: list[tuple[str, int | None, int]] = []

            for s in affected_sensors:
                affected_depths = self._collect_clobbered_depths(
                    cast_entry, s, quality_id, cast_entry.station, self._current_cast
                )
                all_affected_depths.extend(affected_depths)
                if s != sensor:
                    old_value = cast_entry.sensor_cast_grades.get(s)
                    if old_value != quality_id:
                        sensor_changes.append((s, old_value, quality_id))

            if not self._confirm_clobber([], all_affected_depths, sensor_changes):
                return  # true no-op - nothing applied, including propagation

        for s in affected_sensors:
            if quality_id is None:
                cast_entry.sensor_cast_grades.pop(s, None)
            else:
                cast_entry.sensor_cast_grades[s] = quality_id
            cast_entry.cast_dirty = True

            resolved_id, _tier = dump_entry.resolved_cast_grade(
                s, self._current_cast, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
            )
            depth_ids = cast_entry.depth_quality_ids.get(s)
            if depth_ids is None:
                cast_entry.depth_quality_ids[s] = [resolved_id] * len(cast_entry.depths)
            else:
                resolved_severity = self._quality_lookup.severity(resolved_id)
                for i, v in enumerate(depth_ids):
                    if self._quality_lookup.severity(v) < resolved_severity:
                        depth_ids[i] = resolved_id

        self._refresh_sensor_rows(affected_sensors)
        self._refresh_copy_comment_button()

    def _on_depth_range_graded(self, sensor: str, start_depth: int, end_depth: int, quality_id: int):
        """Direct slot assignment into cast_entry.depth_quality_ids[s]
        for every depth index in [start_depth, end_depth], for the
        source sensor AND (2026.10.20_03) every propagation target.
        Defensively initializes a sensor's array to its CURRENT
        cast-level resolved value if it isn't present yet."""
        cast_entry = self._current_cast_entry()
        if cast_entry is None:
            return
        dump_entry = self._current_dump_entry()
        if dump_entry is None:
            return

        affected_sensors = _affected_sensors(sensor)

        all_affected_depths: list[tuple[str, str | None, int, str]] = []
        for s in affected_sensors:
            if s not in cast_entry.depth_quality_ids:
                cast_level_id, _tier = dump_entry.resolved_cast_grade(
                    s, self._current_cast, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
                )
                cast_entry.depth_quality_ids[s] = [cast_level_id] * len(cast_entry.depths)
            depth_ids = cast_entry.depth_quality_ids[s]
            indices = self._depth_index_range(cast_entry, start_depth, end_depth)
            new_severity = self._quality_lookup.severity(quality_id)
            for i in indices:
                if i < len(depth_ids) and self._quality_lookup.severity(depth_ids[i]) < new_severity:
                    all_affected_depths.append((self._current_cast, cast_entry.station, cast_entry.depths[i], s))

        if not self._confirm_clobber([], all_affected_depths):
            return  # true no-op - nothing applied, including propagation

        for s in affected_sensors:
            depth_ids = cast_entry.depth_quality_ids[s]
            for i in self._depth_index_range(cast_entry, start_depth, end_depth):
                if i < len(depth_ids):
                    depth_ids[i] = quality_id
            cast_entry.cast_dirty = True

        self._refresh_sensor_rows(affected_sensors)

    def _on_depth_range_reset(self, sensor: str, start_depth: int, end_depth: int):
        """PI chose "Reset to cast grade" for a completed drag.
        Overwrites these slots with the sensor's current cast-level
        resolved value, for the source sensor AND (2026.10.20_03) every
        propagation target - each reset to ITS OWN cast-level resolved
        value, not the source sensor's."""
        cast_entry = self._current_cast_entry()
        if cast_entry is None:
            return
        dump_entry = self._current_dump_entry()
        if dump_entry is None:
            return

        affected_sensors = _affected_sensors(sensor)

        for s in affected_sensors:
            cast_level_id, _tier = dump_entry.resolved_cast_grade(
                s, self._current_cast, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
            )
            if s not in cast_entry.depth_quality_ids:
                cast_entry.depth_quality_ids[s] = [self._quality_lookup.good_id] * len(cast_entry.depths)
            depth_ids = cast_entry.depth_quality_ids[s]
            for i in self._depth_index_range(cast_entry, start_depth, end_depth):
                if i < len(depth_ids):
                    depth_ids[i] = cast_level_id
            cast_entry.cast_dirty = True

        self._refresh_sensor_rows(affected_sensors)

    def _on_all_depth_ranges_cleared(self, sensor: str):
        """Overwrites the ENTIRE depth_quality_ids[s] array back to each
        sensor's own cast-level resolved value, for the source sensor
        AND (2026.10.20_03) every propagation target."""
        cast_entry = self._current_cast_entry()
        if cast_entry is None:
            return
        dump_entry = self._current_dump_entry()
        if dump_entry is None:
            return

        affected_sensors = _affected_sensors(sensor)

        for s in affected_sensors:
            cast_level_id, _tier = dump_entry.resolved_cast_grade(
                s, self._current_cast, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
            )
            cast_entry.depth_quality_ids[s] = [cast_level_id] * len(cast_entry.depths)
            cast_entry.cast_dirty = True

        self._refresh_sensor_rows(affected_sensors)

    @staticmethod
    def _depth_index_range(cast_entry: CastEntry, start_depth: int, end_depth: int) -> list[int]:
        """Returns the list of indices into cast_entry.depths whose
        depth value falls within [start_depth, end_depth] inclusive."""
        return [
            i for i, d in enumerate(cast_entry.depths)
            if start_depth <= d <= end_depth
        ]

    def _on_analyst_comments_changed(self):
        d = self._current_dump_entry()
        if d is None:
            return
        d.analyst_comments = self._txt_analyst_comments.toPlainText()

    # ------------------------------------------------------------------
    def _run_validation_and_report(self):
        self._last_problems = validate_submission(
            self._submission, self._graded_sensors, self._quality_lookup.good_id, self._quality_lookup.severity_by_id
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
        except Exception as exc:
            self._show_error_dialog("Open failed", filepath, exc)
            return

        self._last_save_dir = os.path.dirname(filepath)
        self._submission = loaded

        self._quality_lookup = QualityLookup.from_preload_payload({
            "data_quality_ids": self._submission.data_quality_ids
        })
        self._graded_sensors = self._submission.graded_sensors
        self._preload_payload = {"thresholds": self._submission.thresholds}

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
