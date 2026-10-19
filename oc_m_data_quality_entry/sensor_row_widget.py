"""
sensor_row_widget.py
OC_M Project Leader app — one sensor's full grading controls.
Version: 2026.10.19_01

## ChangeLog

2026.10.19_01: Cast-level grade buttons (G/U/Q/B) are now DISABLED, not
just left clickable-then-corrected, whenever that grade is BETTER
(less severe) than the sensor's current dump-level grade (via
context.quality_lookup.severity() against context.dump_grade - falling
back to good_id's own severity when no dump override exists, matching
resolved_cast_grade()'s own "no dump override -> good_id" fallback).
Prevents the PI from ever creating a Dump -> Cast hierarchy violation
through normal use, matching the precedent already set by
_GradePickerDialog's floor logic, which similarly omits (not merely
disables, for THAT dialog's case) any button that would grade a depth
range better than its cast. This is the PROACTIVE half of the fix; the
DETECTIVE half (output_io.py's new validate_submission() hierarchy
checks, same day) catches anything that slips in some other way (e.g.
manual JSON edits), and a read-time clamp in resolved_cast_grade()
neutralizes an illegal value's effect on the cascade regardless of how
it got there - see output_io.py's 2026.10.19_01 changelog entry for
both of those.

2026.10.16_03: Flat-array migration, UI side.
SensorDepthRange and SensorRowContext.existing_depth_ranges/depth_override_count
are commented out (not deleted - left in place as a clearly-marked
reference block in case we need to look back at the old shape; can be
removed for real once the new behavior is confirmed working).
Replaced by a single new field, SensorRowContext.
depths_differing_from_cast: int, computed directly by the caller
(entry_window.py) by comparing CastEntry.depth_quality_ids[sensor][i]
against the cast-level resolved id - there is no longer a list of
range objects for this widget to count. _update_diff_summary() and the
depth-badge logic in refresh() now read this field instead of
len(existing_depth_ranges). This file's _GradePickerDialog/
_on_range_selected floor-and-reset logic is UNCHANGED - it never
touched existing_depth_ranges directly, so nothing there needed to
move (see the flat-array handoff doc's note that this widget never
touches CastEntry directly; the actual array-writing happens in
entry_window.py).

2026.10.16_02: Removed a dead leftover - _existing_depth_overrides was
still being computed in refresh() but nothing reads it anymore (the
overlap-warning dialog that used it was already removed from
_on_range_selected prior to this entry). Also removed the now-unused
depthRangeDeleted signal declaration (nothing emits it as of
2026.10.16_01's list-to-summary replacement).

2026.10.16_01: Replaced the per-range delete-list with a summary count
("N depth ranges differ from the cast grade"), per plan from the
2026.10.15 reset-button work. The old list's per-row delete button no
longer has a clean conceptual home now that "Reset to cast grade" is
the primary corrective action (delete-by-list-position doesn't compose
well with a 5th picker option) - the summary count plus Reset/Clear-All
covers the same real need (undo a mistaken depth grading) without
needing to enumerate and index into individual override entries.
_rebuild_ranges_list()/_range_row_widgets removed; _update_diff_summary()
added.

2026.10.15_01: Added "Reset to cast grade" as a picker option,
alongside the existing worse-than-floor grade choices - first step of
replacing the per-range delete-list UI with a summary-count readout
(see 2026.10.16 entry below for that follow-on piece). New
depthRangeReset(str, int, int) signal, reported via
_GradePickerDialog.result_is_reset rather than chosen_quality_id, since
a reset carries no quality_id. Removed the "nothing worse to grade"
early-return dialog from _on_range_selected - Reset is always a
meaningful option even when no worse grade exists (e.g. clearing a
stale depth override left over from before the cast grade tightened),
so there's no longer a dead-end case requiring an early bailout.

2026.10.14_02: Two fixes from developer testing feedback, backfilled
into this changelog (both were applied to the file without a version
bump at the time - corrected here rather than left undocumented):
  - Tightened the depth-grading floor from "equal-or-worse" to
    "strictly worse": grading a depth range to the SAME value as the
    sensor's current cast-level grade is redundant (looks like an
    action was taken, but changes nothing resolved) and is now
    excluded from the picker the same way better-than-floor options
    already were. Changed severity comparison from `<` to `<=` in
    _GradePickerDialog's button-building loop.
  - Moved the per-range list's delete (\u2715) button from the far
    right of each row (past addStretch()) to immediately after the
    range/grade label, per developer request for better visual
    association between a range and its delete control.

2026.10.14_01: Added a grading floor for depth-range overrides, per
developer request: a sensor's depth-range grade can never be BETTER
than that sensor's current cast-level resolved grade (cast override,
or falling through to dump-level override, or Good) - only equal or
worse is allowed. Enforced by omitting (not merely disabling) any
better-than-floor option from _GradePickerDialog's button row, so nothing
invalid can be clicked. The floor is read from SensorRowContext.resolved_id
at the moment a range is completed - already guaranteed current by the
existing refresh-on-every-grade-change discipline, so no new state
tracking was needed. Deliberately NOT retroactive: an existing depth
override that predates a later, stricter cast/dump grade is left as-is
(same "don't rewrite history" principle already applied to overlapping
depth ranges) - the floor only constrains NEW picker choices going
forward.

2026.10.13_03: Added a visible per-range list under each sensor's depth
strip (one row per existing_depth_ranges entry: "start-end: grade",
each with its own delete button), plus a "Clear all ranges" button -
fixes re-graded/overlapping depth ranges silently accumulating dead,
invisible entries in CastEntry.depth_overrides with no way to remove
them. SensorDepthRange gained a quality_id field, carrying that
specific override's OWN stored grade (not the resolved/winning grade
for those depths - see the dataclass's own docstring on why this
distinction matters: two overlapping entries for the same depths must
show their own different grades in the list, not both show whichever
one happens to currently be winning the "last-applied wins" cascade).
New signals: depthRangeDeleted(str, int), allDepthRangesCleared(str).

2026.10.13_02: Added a depth-override count badge to the row header,
next to the sensor name - the only always-visible indicator that a
sensor has depth-range grading on the current cast. Previously this
was invisible unless the row was manually expanded and the strip's
colored bands inspected by eye; with 9 rows this made it easy to lose
track of which sensors had depth overrides after closing a validation
dialog. SensorRowContext gains depth_override_count (a derived
property, always len(existing_depth_ranges), so it cannot drift out of
sync). Badge is hidden entirely when count is 0, so collapsed rows with
no depth grading look unchanged. Clicking the badge expands the row.

2026.10.13_01: No functional change. Version bump only, to reflect the
single-file architecture pivot in output_io.py/entry_window.py - this
file's caller-builds-a-snapshot contract (SensorRowContext/
SensorDepthRange) already matched the new design with no changes
needed; confirmed during the pivot rather than assumed.

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


# COMMENTED OUT 2026.10.16_03 - superseded by the flat-array model.
# SensorDepthRange mirrored output_io.DepthRangeOverride, which no
# longer exists (output_io.py 2026.10.16_01). Left here, not deleted,
# as a reference for what the old per-range shape looked like - remove
# for real once the depths_differing_from_cast replacement is confirmed
# working.
#
# @dataclass
# class SensorDepthRange:
#     """Plain (start_depth, end_depth, quality_id) for ONE existing
#     depth-range override of THIS sensor on the currently selected cast -
#     a direct, lossless mirror of output_io.DepthRangeOverride's own
#     start_depth/end_depth/quality_id fields (filtered to this sensor;
#     CastEntry.depth_overrides holds all sensors' ranges mixed together,
#     so the caller filters before building this context). Kept as a
#     separate, minimal type here rather than importing
#     DepthRangeOverride directly, so this widget module has no
#     dependency on output_io.py.
#
#     quality_id here is this override's OWN stored grade - NOT the
#     resolved/winning grade for these depths. If a later override
#     shadows this one (see DumpEntry.resolved_depth_grade's "last-
#     applied wins"), that shadowing is invisible at this field's level
#     by design: the per-range list is meant to show the PI exactly what
#     each entry actually says, including ones currently being shadowed,
#     so a duplicate/mistaken override can be identified and deleted
#     rather than silently indistinguishable from the one that's winning.
#     """
#     start_depth: int
#     end_depth: int
#     quality_id: int

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
    # COMMENTED OUT 2026.10.16_03 - flat-array migration. Replaced by
    # depths_differing_from_cast below. Left here as a reference for
    # the old shape; remove for real once the replacement is confirmed
    # working.
    # existing_depth_ranges: list[SensorDepthRange]  # THIS sensor's real depth_overrides on this cast
    depths_differing_from_cast: int
    # Number of depths (not ranges) where THIS sensor's stored
    # depth_quality_ids value differs from the cast-level resolved
    # grade, on the currently selected cast. 0 when none, or when no
    # cast is selected. Computed by the caller (entry_window.py) in
    # _build_context_for_sensor(), since that's where both
    # CastEntry.depth_quality_ids and the cast-level resolved id are
    # already in hand - this widget has no way to compute it itself
    # without reaching into CastEntry directly, which it deliberately
    # never does (see this module's docstring, "Ownership model").
    thresholds: ThresholdBounds | None
    has_cast_selected: bool

    # COMMENTED OUT 2026.10.16_03 - flat-array migration. depth_
    # override_count was always len(existing_depth_ranges); now that
    # existing_depth_ranges is gone, depths_differing_from_cast is
    # passed directly by the caller instead of being derived here.
    # @property
    # def depth_override_count(self) -> int:
    #     """Number of depth-range overrides THIS sensor has on the
    #     currently selected cast. 0 when none, or when no cast is
    #     selected (existing_depth_ranges is always empty in that case).
    #     Deliberately a derived property, not a separately-passed field -
    #     it's always exactly len(existing_depth_ranges), so there is no
    #     way for it to drift out of sync with the list it's counting."""
    #     return len(self.existing_depth_ranges)


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
        depthRangeReset(str, int, int)
            (sensor, start_depth, end_depth) - PI chose "Reset to cast
            grade" instead of an explicit grade for a completed drag.
            The caller removes/clears whatever depth-level override(s)
            cover this range for this sensor, letting it fall back to
            the cast/dump cascade.
        allDepthRangesCleared(str)
            (sensor) - PI clicked "Clear all ranges" for this sensor on
            the currently selected cast. The caller removes every
            depth_overrides entry for this sensor on this cast.
    """

    dumpGradeChanged = pyqtSignal(str, object)
    castGradeChanged = pyqtSignal(str, object)
    depthRangeGraded = pyqtSignal(str, int, int, int)
    depthRangeReset = pyqtSignal(str, int, int)
    # (sensor, start_depth, end_depth) - PI chose "Reset to cast grade"
    # for a completed drag, instead of an explicit worse grade. Distinct
    # from depthRangeGraded since there's no quality_id to carry - the
    # caller is responsible for clearing whatever depth-level state
    # covers this range for this sensor, so it falls back to the
    # cast/dump cascade again.
    allDepthRangesCleared = pyqtSignal(str)
    # (sensor) - PI clicked "Clear all" for this sensor on this cast.
    # NOTE: depthRangeDeleted was removed here (2026.10.16_02) - nothing
    # emits it since the per-range delete buttons were replaced by the
    # summary count in 2026.10.16_01.

    def __init__(self, sensor: str, parent=None):
        super().__init__(parent)
        self.sensor = sensor
        self._context: SensorRowContext | None = None
        self._expanded = False
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

        # Depth-override count badge - the only always-visible indicator
        # that this sensor has ANY depth-range grading on this cast.
        # Needed because the header's "resolved:" label only ever shows
        # the cast-level cascade result (resolved_cast_grade() correctly
        # never resolves to "depth" at this level - see
        # SensorRowContext.resolved_tier's own docstring), so a sensor
        # that's Good at the cast level but has a Bad depth-range
        # override buried inside it would otherwise be completely
        # invisible unless every row is expanded and inspected by eye.
        # Clicking the badge also expands the row, as a shortcut.
        self._btn_depth_badge = QToolButton()
        self._btn_depth_badge.setStyleSheet(
            "QToolButton { background-color: #3b82f6; color: white; "
            "border-radius: 8px; padding: 1px 6px; font-weight: bold; }"
        )
        self._btn_depth_badge.clicked.connect(lambda: self._set_expanded(True))
        self._btn_depth_badge.setVisible(False)
        header.addWidget(self._btn_depth_badge)

        self._btn_clear_all = QPushButton("Clear all ranges")
        self._btn_clear_all.setStyleSheet("padding: 1px 6px;")
        self._btn_clear_all.clicked.connect(self._on_clear_all_clicked)
        self._btn_clear_all.setVisible(False)
        header.addWidget(self._btn_clear_all)

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

        # Summary readout of how many depths currently differ from this
        # sensor's cast-level grade (2026.10.16 - replaces the old
        # per-range delete-list; see refresh()/_rebuild_ranges_list for
        # why a list no longer applies once ranges stop being discrete
        # stored objects).
        self._lbl_diff_summary = QLabel("")
        self._lbl_diff_summary.setStyleSheet("color: #9ca3af; font-style: italic;")
        depth_layout.addWidget(self._lbl_diff_summary)

        root.addWidget(self._depth_area)
        self._depth_area.setVisible(False)

    # ------------------------------------------------------------------
    def set_show_tooltips(self, show: bool) -> None:
        """Passthrough to the embedded DepthStripWidget - keeps
        entry_window.py's Settings-menu handler from reaching into
        self._strip directly, preserving this widget's existing
        encapsulation of its internal DepthStripWidget."""
        self._strip.set_show_tooltips(show)

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
        # Dump -> Cast hierarchy floor (2026.10.19): a cast can never be
        # graded better than its dump. dump_floor_id is the sensor's
        # current dump-level value, or good_id if no dump override is
        # set (matching resolved_cast_grade()'s own fallback - with no
        # dump override, EVERYTHING is legal, since good_id is the best
        # possible grade and nothing can be better than it).
        dump_floor_id = context.dump_grade if context.dump_grade is not None else context.quality_lookup.good_id
        dump_floor_severity = context.quality_lookup.severity(dump_floor_id)
        for qid, btn in self._cast_buttons.items():
            legal = context.quality_lookup.severity(qid) >= dump_floor_severity
            btn.setEnabled(has_cast and legal)
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

        count = context.depths_differing_from_cast
        if count > 0:
            label = "1 depth" if count == 1 else f"{count} depths"
            self._btn_depth_badge.setText(label)
            self._btn_depth_badge.setVisible(True)
            self._btn_clear_all.setVisible(True)
        else:
            self._btn_depth_badge.setVisible(False)
            self._btn_clear_all.setVisible(False)

        self._update_diff_summary(context)

        self._strip.set_data(context.depth_points)
        self._strip.set_thresholds(context.thresholds)
        self._chk_thresholds.setEnabled(context.thresholds is not None)

        if self._expanded and not has_cast:
            self._set_expanded(False)
        self._btn_expand.setEnabled(has_cast)

    def _update_diff_summary(self, context: SensorRowContext) -> None:
        """Updated 2026.10.16_03 for the flat-array model: counts actual
        DEPTHS whose stored depth_quality_ids value differs from the
        cast-level resolved grade, via context.depths_differing_from_cast
        (computed by the caller - see SensorRowContext's field comment).
        This replaces the old range-entry count, which is no longer a
        meaningful concept under the flat-array model."""
        count = context.depths_differing_from_cast
        if count == 0:
            self._lbl_diff_summary.setText("")
        elif count == 1:
            self._lbl_diff_summary.setText("1 depth differs from the cast grade.")
        else:
            self._lbl_diff_summary.setText(f"{count} depths differ from the cast grade.")

    def _on_clear_all_clicked(self):
        if self._context is None:
            return
        reply = QMessageBox.question(
            self,
            "Clear all depth ranges",
            f"Remove ALL depth-range grades for {self.sensor} on this cast? "
            "This cannot be undone (though you can re-grade from scratch).",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self.allDepthRangesCleared.emit(self.sensor)

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

        # Overlap-warning dialog removed 2026.10.16: it existed to warn
        # about range-vs-range ambiguity under the old "last-applied
        # wins" override-list model. With "Reset to cast grade" now
        # available as an explicit action and the per-range list gone
        # (see 2026.10.16_01), re-grading a previously-graded depth is
        # just as unambiguous as grading a fresh one - the new drag's
        # result simply applies to that range, no warning needed.

        floor_quality_id = self._context.resolved_id
        lookup = self._context.quality_lookup
        floor_severity = lookup.severity(floor_quality_id)
        worst_severity = max(lookup.severity(qid) for qid in lookup.ids_sorted_by_severity())
        # Note: even when there's no WORSE grade available, "Reset to
        # cast grade" can still be meaningful (clearing a stale
        # depth-specific override from before the cast grade changed) -
        # so this no longer early-returns; _GradePickerDialog always
        # offers Reset regardless of whether any explicit worse option
        # exists.

        picker = _GradePickerDialog(
            self.sensor, start_depth, end_depth,
            floor_quality_id, lookup, self
        )
        if picker.exec():
            if picker.result_is_reset:
                self.depthRangeReset.emit(self.sensor, start_depth, end_depth)
            else:
                self.depthRangeGraded.emit(self.sensor, start_depth, end_depth, picker.chosen_quality_id)


class _GradePickerDialog(QMessageBox):
    """Grade-choice prompt for a completed depth-range drag.
    Deliberately plain (QMessageBox-derived button row) rather than a
    custom dialog.

    floor_quality_id enforces the "depth grade cannot be BETTER THAN OR
    EQUAL TO the sensor's current cast-level resolved grade" rule
    (2026.10.14, tightened same day to exclude equal-to as redundant) -
    any quality id with severity <= the floor's severity is omitted
    from the button row entirely, not merely disabled, so there's
    nothing to click that would violate the rule. The floor itself is
    always the sensor's CURRENT cast-level resolved grade
    (DumpEntry.resolved_cast_grade's output, threaded through via
    SensorRowContext.resolved_id).

    A "Reset to cast grade" button (2026.10.14) is always offered
    alongside whatever explicit worse-grade options exist, EXCEPT when
    there is nothing to reset FROM in a way that would differ from
    offering an explicit grade - it is always safe to offer regardless
    of whether this depth range currently has an override, since
    resetting a range with no existing override is simply a no-op the
    caller can shrug off. Reports back via result_is_reset instead of
    chosen_quality_id when chosen."""

    def __init__(self, sensor: str, start_depth: int, end_depth: int,
                 floor_quality_id: int, quality_lookup, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grade depth range")
        floor_label = quality_lookup.label(floor_quality_id)
        floor_severity = quality_lookup.severity(floor_quality_id)
        self.setText(
            f"Grade {sensor} for depth {start_depth}m\u2013{end_depth}m:\n\n"
            f"(This sensor is currently graded {floor_label} at the cast/dump "
            f"level - grading a depth range to {floor_label} again would be "
            f"redundant, so only grades WORSE than {floor_label} are offered. "
            f"Choose \"Reset to cast grade\" to remove any depth-specific "
            f"grading for this range.)"
        )
        self.chosen_quality_id: int | None = None
        self.result_is_reset: bool = False

        self._buttons_by_id = {}
        for qid in quality_lookup.ids_sorted_by_severity():
            if quality_lookup.severity(qid) <= floor_severity:
                continue  # equal-to-or-better-than the floor - redundant, not offered
            btn = self.addButton(quality_lookup.label(qid), QMessageBox.ButtonRole.ActionRole)
            self._buttons_by_id[btn] = qid

        self._reset_button = self.addButton("Reset to cast grade", QMessageBox.ButtonRole.ActionRole)
        self.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

    def exec(self) -> int:
        result = super().exec()
        clicked = self.clickedButton()
        if clicked is self._reset_button:
            self.result_is_reset = True
            return 1
        if clicked in self._buttons_by_id:
            self.chosen_quality_id = self._buttons_by_id[clicked]
            return 1
        return 0
