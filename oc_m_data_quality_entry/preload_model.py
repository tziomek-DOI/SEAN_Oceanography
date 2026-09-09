"""
preload_model.py
OC_M Project Leader app — Qt table model for the per-dump cast grid.
Build: 3

Wraps a single DumpEntry's casts (from output_io.py) as a
QAbstractTableModel so the grid supports built-in sorting via
QTableView.setSortingEnabled(True), without hand-rolling that logic.

Columns: Cast | Quality code override | Comment override
Cast is read-only; the other two are editable in place.

The grid always displays each cast's *resolved* value (override if
set, otherwise the dump-level default) so changing the default is
immediately visible across every row that doesn't have its own
override. Cells showing an inherited default (vs an explicit
per-cast override) are styled in a muted color so the two are
visually distinguishable — otherwise there is no way to tell, just
by looking, whether a value came from the default or was typed in
for that specific cast.

Red-flagging (per spec, only applied after Save/Open, never live while
editing) is driven externally: the window calls set_flagged_casts()
with the set of cast numbers to highlight, and the model re-paints
those rows via data() role handling — no validation logic lives here.
"""

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor

from output_io import DumpEntry

COL_CAST = 0
COL_CODE = 1
COL_COMMENT = 2

CODE_CHOICES = [
    ("", "-- use default --"),
    ("0", "0: Good"),
    ("1", "1: Unknown"),
    ("4", "4: Questionable"),
    ("8", "8: Bad"),
]
CODE_LABELS = dict(CODE_CHOICES)

FLAG_BG = QColor("#fceaea")
FLAG_FG = QColor("#791f1f")
INHERITED_FG = QColor("#8b8067")  # muted - value comes from the dump default, not an override


class DumpCastTableModel(QAbstractTableModel):
    def __init__(self, dump_entry: DumpEntry | None = None, parent=None):
        super().__init__(parent)
        self._dump: DumpEntry | None = None
        self._casts: list[str] = []
        self._flagged: set[str] = set()
        if dump_entry is not None:
            self.set_dump(dump_entry)

    # ------------------------------------------------------------------
    def set_dump(self, dump_entry: DumpEntry):
        self.beginResetModel()
        self._dump = dump_entry
        self._casts = sorted(dump_entry.casts.keys())
        self._flagged = set()
        self.endResetModel()

    def notify_defaults_changed(self):
        """Call after the dump-level default code/comment changes, so
        every row inheriting the default (i.e. with no override of its
        own) repaints to show the new resolved value."""
        if not self._casts:
            return
        top_left = self.index(0, COL_CODE)
        bottom_right = self.index(len(self._casts) - 1, COL_COMMENT)
        self.dataChanged.emit(top_left, bottom_right)

    def set_flagged_casts(self, cast_numbers: set[str]):
        """Called after Save/Open validation. Repaints affected rows only."""
        self._flagged = set(cast_numbers)
        if self._casts:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._casts) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right)

    def clear_flags(self):
        self.set_flagged_casts(set())

    # ------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._casts)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return ["Cast", "Quality code", "Comment"][section]

    def flags(self, index: QModelIndex):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_CAST:
            return base
        return base | Qt.ItemFlag.ItemIsEditable

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._dump is None:
            return None

        cast = self._casts[index.row()]
        entry = self._dump.casts[cast]
        col = index.column()
        is_override = bool(entry.quality_code) if col == COL_CODE else bool(entry.comment)

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_CAST:
                return cast
            if col == COL_CODE:
                code, _ = self._dump.resolved(cast)
                return CODE_LABELS.get(code, "") if code else ""
            if col == COL_COMMENT:
                _, comment = self._dump.resolved(cast)
                return comment or ""

        if role == Qt.ItemDataRole.EditRole:
            # The quality-code dropdown deliberately shows only this
            # cast's own override (blank = "use default") - opening the
            # editor on an inherited numeric code must not silently
            # freeze that cast to whatever the default happened to be.
            #
            # The comment field is different: it's free text, and a
            # user opening an inherited comment almost always wants to
            # see and extend it, not start from blank. So the comment
            # editor seeds from the *resolved* (possibly inherited)
            # text instead.
            if col == COL_CAST:
                return cast
            if col == COL_CODE:
                return entry.quality_code or ""
            if col == COL_COMMENT:
                _, comment = self._dump.resolved(cast)
                return comment or ""

        if role == Qt.ItemDataRole.BackgroundRole and cast in self._flagged:
            return FLAG_BG
        if role == Qt.ItemDataRole.ForegroundRole:
            if cast in self._flagged:
                return FLAG_FG
            if col in (COL_CODE, COL_COMMENT) and not is_override:
                return INHERITED_FG

        if role == Qt.ItemDataRole.ToolTipRole and col in (COL_CODE, COL_COMMENT):
            return "" if is_override else "Inherited from the dump default (not an override)"

        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or self._dump is None:
            return False

        cast = self._casts[index.row()]
        entry = self._dump.casts[cast]
        col = index.column()

        if col == COL_CODE:
            entry.quality_code = value or None
        elif col == COL_COMMENT:
            entry.comment = (value or "").strip() or None
        else:
            return False

        # Editing a cast clears any stale flag on that row until the next
        # explicit Save/Open re-validation, avoiding a misleading red row
        # that no longer reflects current content.
        self._flagged.discard(cast)
        self.dataChanged.emit(index, index)
        return True

    def cast_at_row(self, row: int) -> str:
        return self._casts[row]