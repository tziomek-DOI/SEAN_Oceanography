"""
entry_window.py
OC_M Project Leader app — main window.
Build: 16

Layout:
    Left:  QTreeWidget, top-level items = cruise years, children = dumps.
           Clicking a dump navigates the right side to that dump's form.
           Hover/selection highlighting lives in the shared dm_styles.qss.
    Right: filename label, dump header (read-only CTD/start date,
           defective-sensor checkboxes, dump-level default quality
           code + comment, a data-quality-code reference button) above
           a sortable cast grid, with an Analyst's Comments box beneath.

Menu bar: File -> Open, Save, Save As, Recent Files, Exit.
          Help -> Open SOP, About.
Menu hover styling and the separator beneath the bar live in the
shared dm_styles.qss, not here.

Exit confirmation is deliberately simple rather than a real dirty-flag
check: it always asks "Are you sure you want to exit?" whether or not
anything has actually changed. Wired to both the menu's Exit action
and the window's closeEvent (the X button), so neither path can skip
the prompt.

Save never blocks on validation problems (per spec); it always writes
the file, then shows a summary dialog of any problems found and
highlights the affected rows in the grid for the dump currently
displayed. The validation dialog is a fixed-size, scrollable dialog
(not QMessageBox) so a long list of problems can never grow the
window past the screen and hide its own Close button.

Open reconstitutes a saved file against THIS session's own pre-loader
payload (see output_io.restrict_onto_preload_shell) - a saved file
only records deltas from the pre-loader snapshot (ctd/start_date/full
cast lists are never written to it), so it cannot stand alone as a
complete source of dump/cast structure. Only years/dumps present in
the opened file are kept; every other pre-loader year is dropped
rather than shown present-but-empty.

About reads docs/about.md as a TEMPLATE, not just raw display text:
{app_name}/{version}/{build_date} tokens in the file are substituted
from version.py at display time, so the version number lives in one
place (version.py) while wording/placement is fully editable in the
markdown file.

CTD number and start date are DISPLAY ONLY - sourced from the
pre-loader JSON and never edited or written back into the PI's output
file. Analyst's Comments is a plain multi-line text field, never
applied to the database.
"""

import os
import traceback
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyledItemDelegate,
    QTableView,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from output_io import (
    DumpEntry,
    OCMSubmission,
    validate_submission,
)
from preload_model import CODE_CHOICES, COL_CODE, COL_COMMENT, DumpCastTableModel
from recent_files import RecentFiles
from version import CURRENT_VERSION

DUMP_ROLE = Qt.ItemDataRole.UserRole
YEAR_ROLE = Qt.ItemDataRole.UserRole + 1


# ---------------------------------------------------------------------------
# Delegates
# ---------------------------------------------------------------------------
class QualityCodeDelegate(QStyledItemDelegate):
    """Quality-code column renders as a dropdown while editing."""

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        for value, label in CODE_CHOICES:
            combo.addItem(label, userData=value)
        return combo

    def setEditorData(self, editor: QComboBox, index):
        current = index.data(Qt.ItemDataRole.EditRole) or ""
        pos = editor.findData(current)
        editor.setCurrentIndex(pos if pos >= 0 else 0)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)


class CommentDelegate(QStyledItemDelegate):
    """Comment column: cursor placed at the end of existing text (rather
    than select-all) so appending is the natural action when a cast is
    currently inheriting the dump-level default comment."""

    def setEditorData(self, editor: QLineEdit, index):
        text = index.data(Qt.ItemDataRole.EditRole) or ""
        editor.setText(text)
        editor.deselect()
        editor.setCursorPosition(len(text))


# ---------------------------------------------------------------------------
# Validation results popup - fixed size, scrollable, buttons always visible
# regardless of how many issues are found (QMessageBox has no size cap and
# will grow off-screen with a long enough list).
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
# Data-quality code reference popup
# ---------------------------------------------------------------------------
class DataQualityCodeDialog(QDialog):
    def __init__(self, code_table: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Data quality codes")

        layout = QVBoxLayout(self)

        rows = "".join(
            f"<tr><td style='padding:4px 12px 4px 0;'><b>{c['code']}</b></td>"
            f"<td style='padding:4px 0;'>{c['label']}</td></tr>"
            for c in code_table
        )
        label = QLabel(
            "<table>"
            "<tr><th align='left' style='padding-right:12px;'>Code</th>"
            "<th align='left'>Meaning</th></tr>" + rows + "</table>"
        )
        layout.addWidget(label)

        note = QLabel(
            "Data Quality Comments should not be recorded for casts with "
            "code 0 (Good)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8b8067; font-style: italic;")
        layout.addWidget(note)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class OCMEntryWindow(QMainWindow):
    def __init__(self, preload_payload: dict, default_output_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Oceanographic Survey Data Quality Report (OC-M)")
        self.resize(1000, 700)

        self._preload_payload = preload_payload
        self._default_output_dir = default_output_dir
        self._submission = OCMSubmission.new_from_preload(preload_payload)

        self._current_year: str | None = None
        self._current_dump: str | None = None
        self._current_filename: str | None = None
        self._current_filepath: str | None = None
        self._last_problems: list = []
        self._last_save_dir: str | None = None
        self._cast_model = DumpCastTableModel()

        app_dir = Path(__file__).resolve().parent
        self._sop_path = app_dir / "docs" / "SEAN OC SOP 11 Data Quality Assignment (OC_M Creation) version 3.pdf"
        self._about_md_path = app_dir / "docs" / "about.md"
        self._recent_files = RecentFiles(app_dir / "data" / "recent_files.json")

        self._build_ui()
        self._build_menu_bar()
        self._populate_tree()

    # ------------------------------------------------------------------
    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: tree ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Cruise year / dump")
        self._tree.itemClicked.connect(self._on_tree_item_clicked)
        splitter.addWidget(self._tree)

        # --- Right: dump form ---
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._lbl_open_file = QLabel("Open file: (unsaved - using pre-load snapshot)")
        self._lbl_open_file.setStyleSheet("color: #8b8067; font-size: 9pt;")
        right_layout.addWidget(self._lbl_open_file)

        title_row = QHBoxLayout()
        self._lbl_dump_title = QLabel("Select a dump from the list on the left.")
        self._lbl_dump_title.setStyleSheet("font-weight: bold; color: #556b2f;")
        title_row.addWidget(self._lbl_dump_title)
        title_row.addStretch()

        self._btn_code_help = QToolButton()
        self._btn_code_help.setText("Data quality codes \u24d8")
        self._btn_code_help.clicked.connect(self._on_show_code_help)
        title_row.addWidget(self._btn_code_help)
        right_layout.addLayout(title_row)

        meta_row = QHBoxLayout()
        self._lbl_ctd = QLabel("CTD: \u2014")
        self._lbl_start_date = QLabel("Start date: \u2014")
        meta_row.addWidget(self._lbl_ctd)
        meta_row.addWidget(self._lbl_start_date)
        meta_row.addStretch()
        right_layout.addLayout(meta_row)

        self._lbl_change_status = QLabel("")
        self._lbl_change_status.setStyleSheet("color: #556b2f; font-style: italic;")
        right_layout.addWidget(self._lbl_change_status)

        sensor_group = QGroupBox("Defective / absent sensors (whole dump)")
        sensor_layout = QHBoxLayout(sensor_group)
        self._sensor_checks: dict[str, QCheckBox] = {}
        for name in self._preload_payload.get(
            "defective_sensor_columns", ["Cond", "Temp", "Fluo", "OBS", "PAR", "O2"]
        ):
            cb = QCheckBox(name)
            cb.stateChanged.connect(self._on_sensor_check_changed)
            self._sensor_checks[name] = cb
            sensor_layout.addWidget(cb)
        right_layout.addWidget(sensor_group)

        default_group = QGroupBox("Default quality code / comment (applies to all casts unless overridden)")
        default_layout = QHBoxLayout(default_group)
        default_layout.addWidget(QLabel("Default code:"))
        self._cmb_default_code = QComboBox()
        for value, label in CODE_CHOICES:
            self._cmb_default_code.addItem(label, userData=value)
        self._cmb_default_code.currentIndexChanged.connect(self._on_default_changed)
        default_layout.addWidget(self._cmb_default_code)

        default_layout.addWidget(QLabel("Default comment:"))
        self._txt_default_comment = QLineEdit()
        self._txt_default_comment.editingFinished.connect(self._on_default_changed)
        default_layout.addWidget(self._txt_default_comment, stretch=1)
        right_layout.addWidget(default_group)

        self._table = QTableView()
        self._table.setModel(self._cast_model)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(
            QTableView.EditTrigger.CurrentChanged
            | QTableView.EditTrigger.AnyKeyPressed
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.setItemDelegateForColumn(COL_CODE, QualityCodeDelegate(self._table))
        self._table.setItemDelegateForColumn(COL_COMMENT, CommentDelegate(self._table))
        right_layout.addWidget(self._table, stretch=2)

        comments_group = QGroupBox("Analyst's comments (not applied to the database)")
        comments_layout = QVBoxLayout(comments_group)
        self._txt_analyst_comments = QPlainTextEdit()
        self._txt_analyst_comments.setMinimumHeight(90)
        self._txt_analyst_comments.textChanged.connect(self._on_analyst_comments_changed)
        comments_layout.addWidget(self._txt_analyst_comments)
        right_layout.addWidget(comments_group, stretch=1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

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

        help_menu = menu_bar.addMenu("&Help")

        act_sop = QAction("Open SOP\u2026", self)
        act_sop.triggered.connect(self._on_open_sop)
        help_menu.addAction(act_sop)

        act_about = QAction("&About", self)
        act_about.triggered.connect(self._on_show_about)
        help_menu.addAction(act_about)

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
        """File -> Save. Uses the currently open filepath if one exists
        (i.e. this file was opened or already saved once this session);
        otherwise behaves like Save As, since there is nothing yet to
        save back over."""
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
            # A stray/mistyped { } in the markdown shouldn't crash the
            # dialog - fall back to showing the raw, unsubstituted text.
            body = template

        # Rendered plain, not as parsed Markdown - about.md is meant to
        # be a short editable blurb, not a document requiring a real
        # Markdown renderer. QLabel wraps it in <pre> so line breaks in
        # the file are preserved as written.
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
    def _on_show_code_help(self):
        codes = self._preload_payload.get("data_quality_codes", [])
        dlg = DataQualityCodeDialog(codes, self)
        dlg.exec()

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

        # Immediately show real content from whatever was just loaded,
        # rather than leaving the right-hand panel showing the previous
        # file's dump (or the initial placeholder) with nothing on
        # screen to indicate a new file actually opened.
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
        self._lbl_dump_title.setText("Select a dump from the list on the left.")
        self._lbl_change_status.setText("")
        self._lbl_ctd.setText("CTD: \u2014")
        self._lbl_start_date.setText("Start date: \u2014")
        self._txt_default_comment.blockSignals(True)
        self._txt_default_comment.clear()
        self._txt_default_comment.blockSignals(False)
        self._cmb_default_code.blockSignals(True)
        self._cmb_default_code.setCurrentIndex(0)
        self._cmb_default_code.blockSignals(False)
        for cb in self._sensor_checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._txt_analyst_comments.blockSignals(True)
        self._txt_analyst_comments.clear()
        self._txt_analyst_comments.blockSignals(False)
        self._cast_model.set_dump(DumpEntry(dump=""))

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
        dump_entry = self._submission.cruise_years[year].dumps[dump]

        self._lbl_dump_title.setText(f"Cruise year {year} \u2014 Dump {dump}")
        self._lbl_change_status.setText("")
        self._lbl_ctd.setText(f"CTD: {dump_entry.ctd or '\u2014'}")
        self._lbl_start_date.setText(f"Start date: {dump_entry.start_date or '\u2014'}")

        self._cmb_default_code.blockSignals(True)
        pos = self._cmb_default_code.findData(dump_entry.default_quality_code or "")
        self._cmb_default_code.setCurrentIndex(pos if pos >= 0 else 0)
        self._cmb_default_code.blockSignals(False)

        self._txt_default_comment.blockSignals(True)
        self._txt_default_comment.setText(dump_entry.default_comment or "")
        self._txt_default_comment.blockSignals(False)

        for name, cb in self._sensor_checks.items():
            cb.blockSignals(True)
            cb.setChecked(name in dump_entry.defective_sensors)
            cb.blockSignals(False)

        self._txt_analyst_comments.blockSignals(True)
        self._txt_analyst_comments.setPlainText(dump_entry.analyst_comments or "")
        self._txt_analyst_comments.blockSignals(False)

        self._cast_model.set_dump(dump_entry)
        self._apply_flags_for_current_dump()

    # ------------------------------------------------------------------
    def _current_dump_entry(self) -> DumpEntry | None:
        if self._current_year is None or self._current_dump is None:
            return None
        return self._submission.cruise_years[self._current_year].dumps[self._current_dump]

    def _on_sensor_check_changed(self, _state):
        d = self._current_dump_entry()
        if d is None:
            return
        d.defective_sensors = [name for name, cb in self._sensor_checks.items() if cb.isChecked()]
        self._show_change_confirmed(f"Defective sensors updated for dump {self._current_dump}.")

    def _on_default_changed(self):
        d = self._current_dump_entry()
        if d is None:
            return
        d.default_quality_code = self._cmb_default_code.currentData() or None
        comment = self._txt_default_comment.text().strip()
        d.default_comment = comment or None
        self._cast_model.notify_defaults_changed()
        self._show_change_confirmed(
            f"Default applied to all casts in dump {self._current_dump} without an override."
        )

    def _on_analyst_comments_changed(self):
        d = self._current_dump_entry()
        if d is None:
            return
        d.analyst_comments = self._txt_analyst_comments.toPlainText()

    def _show_change_confirmed(self, message: str):
        self._lbl_change_status.setText(message)

    # ------------------------------------------------------------------
    def _apply_flags_for_current_dump(self):
        """Re-derive which casts in the on-screen dump should be
        highlighted, based on the last full-submission validation run.
        Called after Save/Open and whenever the tree selection changes,
        so switching dumps always reflects the most recent check."""
        d = self._current_dump_entry()
        if d is None:
            return
        flagged = {
            p.cast for p in self._last_problems
            if p.cruise_year == self._current_year and p.dump == self._current_dump
        }
        self._cast_model.set_flagged_casts(flagged)

    # ------------------------------------------------------------------
    def _run_validation_and_report(self):
        self._last_problems = validate_submission(self._submission)
        self._apply_flags_for_current_dump()

        if not self._last_problems:
            QMessageBox.information(
                self, "Validation",
                "No issues found \u2014 every cast has a resolved quality code, "
                "and comment rules are satisfied."
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
            # Reconstitute the file against THIS session's own pre-loader
            # payload - not a no-op, not a "keep every year" merge. See
            # output_io.restrict_onto_preload_shell for why a saved file
            # cannot stand alone (it only records deltas: ctd, start_date,
            # and any ungraded cast are never written to the file at all).
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
        """Shows every exception in full - type, message, and complete
        traceback via 'Show Details' - so a failure can never look like
        silent inaction. Catches Exception broadly (not a narrow
        allow-list of expected error types) so nothing slips through
        unreported."""
        details = traceback.format_exc()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(f"{title}:\n{filepath}\n\n{type(exc).__name__}: {exc}")
        box.setDetailedText(details)
        box.exec()
