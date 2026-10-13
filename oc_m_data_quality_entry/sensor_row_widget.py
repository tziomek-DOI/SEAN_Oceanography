"""
sensor_row_widget.py
OC_M Project Leader app — one sensor's full grading controls.
Version: 2026.10.08_02

## ChangeLog

2026.10.08_02: SensorRowContext now carries the sensor's real existing
depth-range overrides (new SensorDepthRange, mirroring output_io.
DepthRangeOverride's start_depth/end_depth) instead of approximating
ranges from individual resolved depth_points. Overlap checking in
_on_range_selected() is unchanged in logic, now operates on accurate
range boundaries.

2026.10.08_01: Initial version. One reusable QWidget encapsulating a
single sensor's dump-level grade buttons, cast-level grade buttons, a
resolved-value readout, and a collapsible DepthStripWidget (with its
own threshold-band toggle) for depth-range grading. Nine of these are
stacked by entry_window.py to build the full sensor panel - see that
file for the assembly.

Ownership model: this widget holds NO grading data of its own. It is a
thin view over whatever DumpEntry/CastEntry the caller (entry_window.py)
currently has selected, re-rendered via refresh() - the same
set-don't-merge pattern DepthStripWidget already uses for its own data.
This widget never mutates output_io.py's dataclasses by reaching into
them directly from a click handler without telling the caller; instead,
every grading action emits a signal, and the caller is responsible for
applying the change to its own DumpEntry/CastEntry and then calling
refresh() on every affected row (a dump-level grade change can affect
the RESOLVED value shown on every cast in that dump - this widget has
no way to know that on its own, since it only ever sees one cast at a
time).

Overlap warning for depth-range grading: when the PI completes a
drag on the embedded DepthStripWidget, this widget checks the
CURRENTLY SELECTED cast's existing depth_overrides for this sensor
and, if the new range overlaps any of them, shows a simple Ok/Cancel
confirmation before proceeding - per explicit developer instruction,
"last-applied wins" on overlap, with the PI warned first rather than
silently resolved.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from depth_strip_widget import (
    DepthStripWidget,
    QUALITY_COLORS,
    DEFAULT_QUALITY_COLOR,
    QualityLookup,
    ResolvedDepthPoint,
    ThresholdBounds,
)


@dataclass
class SensorDepthRange:
    """Plain (start_depth, end_depth) pair for ONE existing depth-range
    override of THIS sensor on the currently selected cast - a direct,
    lossless mirror of output_io.DepthRangeOverride's own start_depth/
    end_depth fields (filtered to this sensor; CastEntry.depth_overrides
    holds all sensors' ranges mixed together, so the caller filters
    before building this context). Kept as a separate, minimal type
    here rather than importing DepthRangeOverride directly, so this
    widget module has no dependency on output_io.py - it only needs
    the two depth values, nothing else DepthRangeOverride carries."""
    start_depth: int
    end_depth: int


@dataclass
class SensorRowContext:
    """Everything this widget needs to render one sensor's row for the
    currently selected cast - built fresh by the caller on every
    selection change (cast switch, dump switch, or a grade change
    anywhere that could affect this sensor's resolved value). This is
    NOT a reference into output_io.py's own dataclasses; it is a plain
    snapshot the caller computes and hands over, so this widget never
    needs to know how DumpEntry/CastEntry work internally."""
    sensor: str
    quality_lookup: QualityLookup
    dump_grade: int | None          # None = no dump-level override set
    cast_grade: int | None          # None = no cast-level override set (ignored if no cast selected)
    resolved_id: int                # the cascade's resolved value for this cast
    resolved_tier: str              # "cast" | "dump" | "default"
    depth_points: list[ResolvedDepthPoint]  # already-resolved per-depth state, for the strip
    existing_depth_ranges: list[SensorDepthRange]  # THIS sensor's real depth_overrides on this cast
    thresholds: ThresholdBounds | None
    has_cast_selected: bool


class SensorRowWidget(QWidget):
    """
    Emits:
        dumpGradeChanged(str, object)
            (sensor, quality_id_or_None) - None means "clear the
            dump-level override for this sensor" (PI clicked the
            already-active button again to toggle it off).
        castGradeChanged(str, object)
            (sensor, quality_id_or_None) - same None-means-clear
            convention, for the CURRENTLY SELECTED cast. The caller
            knows which cast that is; this widget does not track it.
        depthRangeGraded(str, int, int, int)
            (sensor, start_depth, end_depth, quality_id) - emitted only
            AFTER any overlap-confirmation dialog this widget itself
            shows has been accepted (or no overlap existed). The caller
            applies this to the submission and calls refresh() on every
            row whose resolved value could have changed.
    """

    dumpGradeChanged = pyqtSignal(str, object)
    castGradeChanged = pyqtSignal(str, object)
    depthRangeGraded = pyqtSignal(str, int, int, int)

    def __init__(self, sensor: str, parent=None):
        super().__init__(parent)
        self.sensor = sensor
        self._context: SensorRowContext | None = None
        self._expanded = False
        self._existing_depth_overrides: list[tuple[int, int]] = []  # (start, end) pairs, for overlap checks
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        header = QHBoxLayout()

        self._btn_expand = QToolButton()
        self._btn_expand.setText("\u25b8")
        self._btn_expand.setFixedWidth(20)
        self._btn_expand.clicked.connect(self._on_toggle_expand)
        header.addWidget(self._btn_expand)

        lbl_name = QLabel(self.sensor)
        lbl_name.setFixedWidth(110)
        lbl_name.setStyleSheet("font-family: monospace;")
        header.addWidget(lbl_name)

        header.addWidget(QLabel("dump:"))
        self._dump_buttons: dict[int, QPushButton] = {}
        for qid in (1, 2, 3, 4):
            btn = QPushButton()
            btn.setFixedWidth(26)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, q=qid: self._on_dump_button(q))
            self._dump_buttons[qid] = btn
            header.addWidget(btn)

        self._arrow_label = QLabel("\u2192")
        header.addWidget(self._arrow_label)

        header.addWidget(QLabel("cast:"))
        self._cast_buttons: dict[int, QPushButton] = {}
        for qid in (1, 2, 3, 4):
            btn = QPushButton()
            btn.setFixedWidth(26)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, q=qid: self._on_cast_button(q))
            self._cast_buttons[qid] = btn
            header.addWidget(btn)

        self._lbl_resolved = QLabel("")
        self._lbl_resolved.setMinimumWidth(140)
        header.addWidget(self._lbl_resolved)

        header.addStretch()
        root.addLayout(header)

        # --- collapsible depth-strip area ---
        self._depth_area = QWidget()
        depth_layout = QVBoxLayout(self._depth_area)
        depth_layout.setContentsMargins(24, 2, 0, 4)

        controls_row = QHBoxLayout()
        self._chk_thresholds = QCheckBox("Show threshold bands")
        self._chk_thresholds.stateChanged.connect(
            lambda state: self._strip.set_show_thresholds(state != 0)
        )
        controls_row.addWidget(self._chk_thresholds)
        self._lbl_hover = QLabel("")
        controls_row.addWidget(self._lbl_hover)
        controls_row.addStretch()
        depth_layout.addLayout(controls_row)

        self._strip = DepthStripWidget()
        self._strip.rangeSelected.connect(self._on_range_selected)
        self._strip.hoverDepthChanged.connect(self._on_hover_changed)
        depth_layout.addWidget(self._strip)

        root.addWidget(self._depth_area)
        self._depth_area.setVisible(False)

    # ------------------------------------------------------------------
    def refresh(self, context: SensorRowContext) -> None:
        """Re-render this row from a fresh snapshot. Called by the
        caller any time this sensor's displayed state could have
        changed - cast selection changed, or a grade changed anywhere
        that could affect this row's resolved value."""
        self._context = context

        for qid, btn in self._dump_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(context.dump_grade == qid)
            btn.setText(self._short_label(qid))
            btn.setStyleSheet(self._button_style(qid, active=(context.dump_grade == qid)))
            btn.blockSignals(False)

        has_cast = context.has_cast_selected
        for qid, btn in self._cast_buttons.items():
            btn.setEnabled(has_cast)
            btn.blockSignals(True)
            btn.setChecked(has_cast and context.cast_grade == qid)
            btn.setText(self._short_label(qid))
            btn.setStyleSheet(self._button_style(qid, active=(has_cast and context.cast_grade == qid)))
            btn.blockSignals(False)
        self._arrow_label.setVisible(has_cast)
        for w in (self._cast_buttons[1], self._cast_buttons[2], self._cast_buttons[3], self._cast_buttons[4]):
            pass  # enabled state already set above

        if has_cast:
            label = context.quality_lookup.label(context.resolved_id)
            color = QUALITY_COLORS.get(context.resolved_id, DEFAULT_QUALITY_COLOR)
            self._lbl_resolved.setText(f"resolved: {label} ({context.resolved_tier})")
            self._lbl_resolved.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            self._lbl_resolved.setText("")

        self._existing_depth_overrides = [
            (r.start_depth, r.end_depth) for r in context.existing_depth_ranges
        ]

        self._strip.set_data(context.depth_points)
        self._strip.set_thresholds(context.thresholds)
        self._chk_thresholds.setEnabled(context.thresholds is not None)

        if self._expanded and not has_cast:
            self._set_expanded(False)
        self._btn_expand.setEnabled(has_cast)

    @staticmethod
    def _short_label(qid: int) -> str:
        return {1: "G", 2: "U", 3: "Q", 4: "B"}.get(qid, "?")

    @staticmethod
    def _button_style(qid: int, active: bool) -> str:
        color = QUALITY_COLORS.get(qid, DEFAULT_QUALITY_COLOR)
        if active:
            return f"background-color: {color}; color: white; font-weight: bold;"
        return f"border: 1px solid {color}; color: {color};"

    # ------------------------------------------------------------------
    def _on_toggle_expand(self):
        self._set_expanded(not self._expanded)

    def _set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._btn_expand.setText("\u25be" if expanded else "\u25b8")
        self._depth_area.setVisible(expanded)

    # ------------------------------------------------------------------
    def _on_dump_button(self, quality_id: int):
        if self._context is None:
            return
        # Toggle off if clicking the already-active button.
        new_value = None if self._context.dump_grade == quality_id else quality_id
        self.dumpGradeChanged.emit(self.sensor, new_value)

    def _on_cast_button(self, quality_id: int):
        if self._context is None or not self._context.has_cast_selected:
            return
        new_value = None if self._context.cast_grade == quality_id else quality_id
        self.castGradeChanged.emit(self.sensor, new_value)

    def _on_hover_changed(self, depth):
        if depth is None:
            self._lbl_hover.setText("")
            return
        point = next((p for p in self._context.depth_points if p.depth == depth), None)
        if point is None:
            return
        reading_str = f"{point.reading:.3f}" if point.reading is not None else "(no reading)"
        label = self._context.quality_lookup.label(point.quality_id)
        self._lbl_hover.setText(f"{depth}m \u2014 {reading_str} \u2014 {label} ({point.tier})")

    def _on_range_selected(self, start_depth: int, end_depth: int):
        if self._context is None or not self._context.has_cast_selected:
            return

        overlap = any(
            not (end_depth < lo or start_depth > hi)
            for lo, hi in self._existing_depth_overrides
        )
        if overlap:
            reply = QMessageBox.question(
                self,
                "Overlapping depth range",
                f"This range ({start_depth}m\u2013{end_depth}m) overlaps an "
                f"existing graded range for {self.sensor} on this cast. "
                "The new grade will take precedence wherever the ranges "
                "overlap (last-applied wins).\n\nApply anyway?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return

        picker = _GradePickerDialog(self.sensor, start_depth, end_depth, self)
        if picker.exec():
            self.depthRangeGraded.emit(self.sensor, start_depth, end_depth, picker.chosen_quality_id)


class _GradePickerDialog(QMessageBox):
    """Minimal grade-choice prompt for a completed depth-range drag.
    Deliberately plain (QMessageBox-derived button row) rather than a
    custom dialog - four buttons, no other content needed."""

    def __init__(self, sensor: str, start_depth: int, end_depth: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grade depth range")
        self.setText(f"Grade {sensor} for depth {start_depth}m\u2013{end_depth}m:")
        self.chosen_quality_id: int | None = None

        self._buttons_by_id = {}
        for qid, label in ((1, "Good"), (2, "Unknown"), (3, "Questionable"), (4, "Bad")):
            btn = self.addButton(label, QMessageBox.ButtonRole.ActionRole)
            self._buttons_by_id[btn] = qid
        self.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

    def exec(self) -> int:
        result = super().exec()
        clicked = self.clickedButton()
        if clicked in self._buttons_by_id:
            self.chosen_quality_id = self._buttons_by_id[clicked]
            return 1
        return 0
