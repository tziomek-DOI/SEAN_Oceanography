"""
depth_strip_widget.py
OC_M Project Leader app — depth-strip widget.
Version: 2026.10.08_04

2026.10.08_02: QUALITY_COLORS/QualityLookup split out - labels and the
Good-id now come from the pre-loader JSON's real OC.tbl_data_quality
query, not a hardcoded literal.

2026.10.08_03: Added ThresholdBounds + depth-strip threshold-band
painting (mandatory/optional reference bands, sourced from the
pre-loader JSON's "thresholds" list - itself a live OC.tbl_threshold
query, no hardcoded bounds anywhere in this file). Toggle is exposed
via set_show_thresholds(); the toggle CONTROL (checkbox/menu item)
belongs to the caller (entry_window.py), not this widget. Standalone
test harness extended with a toggle checkbox and synthetic bounds so
this can be reviewed in isolation before being wired into the full app.

2026.10.08_04: Developer-reported the two threshold bands (same hue,
two alpha levels) were not visually distinguishable against the dark
background - confirmed via screenshot. Switched to two genuinely
distinct colors (amber for mandatory, blue for optional) at higher,
more separated opacity instead of relying on subtle alpha differences.

A single reusable QWidget: draws one sensor's reading trace for one cast,
depth-indexed left-to-right, with grade-colored background bands behind
the trace. Supports click-drag depth-range selection, emitted as a Qt
signal for the caller to act on (show a grade-picker popup, run an
overlap check, etc.) — this widget has NO knowledge of overrides,
cascades, or grading logic. It only knows how to paint a trace +
grade-colored bands from data handed to it, and how to report a
click-drag gesture back to its caller.

This separation matches output_io.py's own design: DumpEntry.
resolved_depth_grade() computes the (quality_id, tier) cascade result;
this widget only ever receives already-resolved values to paint, via
set_data(). It never calls into output_io.py itself.

Null readings (gaps in the sensor's recorded values — e.g. an SBE error
sentinel nulled out upstream in oc_d_service.py) are rendered as a break
in the trace line, not interpolated across — interpolating would draw a
reading that was never actually recorded.

Build/usage note: this file can be run directly (`python
depth_strip_widget.py`) for a standalone interactive test harness with
synthetic data, independent of the rest of the OC_M app — see
`if __name__ == "__main__":` at the bottom. This is for development
review only; the harness code is not imported or used by the real app.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Shared vendored dependencies (PyQt6, etc.) live one level up from this
# app's own folder, in File_Processing/libs - same layout main.py already
# assumes. Needed here too since this file can be run standalone (see the
# __main__ block at the bottom) without going through main.py's own
# sys.path setup first.
_APP_DIR = Path(__file__).resolve().parent
_LIBS_DIR = _APP_DIR.parent / "libs"
sys.path.insert(0, str(_LIBS_DIR))

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

# UI-only styling - no database column says what color represents Bad.
QUALITY_COLORS: dict[int, str] = {
    1: "#4a7c3f",   # Good
    2: "#9a9a3f",   # Unknown
    3: "#c98a2b",   # Questionable
    4: "#b33f3f",   # Bad
}
DEFAULT_QUALITY_COLOR = "#777777"  # fallback if an id has no color entry


@dataclass
class QualityLookup:
    """Id -> label, and which id means "Good" - both read from the
    pre-loader JSON's "data_quality_ids" list (a live OC.tbl_data_quality
    query; see oc_m_preloader_service._fetch_data_quality_table()).
    Built once by the caller (entry_window.py) and shared wherever a
    label or the Good-id is needed."""
    label_by_id: dict[int, str]
    good_id: int

    @classmethod
    def from_preload_payload(cls, preload_payload: dict) -> "QualityLookup":
        rows = preload_payload.get("data_quality_ids", [])
        label_by_id = {r["id"]: r["label"] for r in rows}
        good_rows = [r["id"] for r in rows if r.get("code") == "0"]
        if not good_rows:
            raise ValueError(
                "No row with data_quality_code == '0' (Good) found in "
                "data_quality_ids - cannot determine the Good id."
            )
        return cls(label_by_id=label_by_id, good_id=good_rows[0])

    def label(self, quality_id: int) -> str:
        return self.label_by_id.get(quality_id, f"Unknown (id={quality_id})")


@dataclass
class ThresholdBounds:
    """One sensor's validation bounds, sourced from OC.tbl_threshold
    (read live by the pre-loader, embedded in the pre-load JSON - see
    oc_m_preloader_service.py). Any bound may be None, meaning that side
    is unconstrained (e.g. fluorescence.mand_min is NULL because a
    negative reading there means "missing signal," not "out of range" -
    see tbl_threshold's own notes column). None bounds are simply not
    drawn, never defaulted to a guessed numeric value."""
    mand_min: float | None
    mand_max: float | None
    opt_min: float | None
    opt_max: float | None

    @classmethod
    def from_preload_payload(cls, preload_payload: dict, sensor: str) -> "ThresholdBounds | None":
        """Look up one sensor's row from the pre-load JSON's
        "thresholds" list (keyed by the tbl_threshold.parameter column).
        Returns None if no row exists for this sensor - some
        tbl_threshold rows (cast, date_gmt, fathometer_depth,
        cast_target_depth) are not sensors at all and never have one."""
        for row in preload_payload.get("thresholds", []):
            if row.get("parameter") == sensor:
                return cls(
                    mand_min=row.get("mand_min"),
                    mand_max=row.get("mand_max"),
                    opt_min=row.get("opt_min"),
                    opt_max=row.get("opt_max"),
                )
        return None


@dataclass
class ResolvedDepthPoint:
    """One depth row's full state, as already resolved by the caller via
    DumpEntry.resolved_depth_grade() — this widget performs no cascade
    logic of its own."""
    depth: int
    reading: float | None
    quality_id: int
    tier: str   # "depth" | "cast" | "dump" | "default" — drives opacity only


class DepthStripWidget(QWidget):
    """
    Emits:
        rangeSelected(int, int)   — a completed click-drag, start/end
                                     depth inclusive, start <= end always.
        hoverDepthChanged(object) — the depth under the cursor (int), or
                                     None when the cursor leaves the strip.
    """

    rangeSelected = pyqtSignal(int, int)
    hoverDepthChanged = pyqtSignal(object)

    CELL_WIDTH = 7
    STRIP_HEIGHT = 56
    TOP_MARGIN = 4
    BOTTOM_MARGIN = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[ResolvedDepthPoint] = []
        self._drag_start_idx: int | None = None
        self._drag_end_idx: int | None = None
        self._hover_idx: int | None = None
        self._thresholds: ThresholdBounds | None = None
        self._show_thresholds: bool = False
        self.setMouseTracking(True)
        self.setMinimumHeight(self.STRIP_HEIGHT)

    # ------------------------------------------------------------------
    def set_thresholds(self, thresholds: ThresholdBounds | None) -> None:
        """Called whenever the selected sensor changes. None means this
        sensor has no tbl_threshold row (e.g. not a validated parameter) -
        the toggle will simply have nothing to show."""
        self._thresholds = thresholds
        self.update()

    def set_show_thresholds(self, show: bool) -> None:
        """Toggled by the caller's own checkbox/menu action - this widget
        owns no UI control for the toggle itself, only the on/off state
        and the resulting paint behavior."""
        self._show_thresholds = show
        self.update()

    # ------------------------------------------------------------------
    def set_data(self, points: list[ResolvedDepthPoint]) -> None:
        """Replace the displayed series entirely. Called whenever the
        selected cast or sensor changes."""
        self._points = points
        self._drag_start_idx = None
        self._drag_end_idx = None
        self._hover_idx = None
        self._recompute_geometry()
        self.update()

    def _recompute_geometry(self) -> None:
        n = len(self._points)
        width = max(1, n * self.CELL_WIDTH)
        self.setFixedWidth(width)

        values = [p.reading for p in self._points if p.reading is not None]
        if values:
            self._min_v = min(values)
            self._max_v = max(values)
            if self._min_v == self._max_v:
                # Flat series — avoid a zero-span division later.
                self._min_v -= 0.5
                self._max_v += 0.5
        else:
            self._min_v, self._max_v = 0.0, 1.0

    # ------------------------------------------------------------------
    def _idx_from_x(self, x: float) -> int:
        idx = int(x // self.CELL_WIDTH)
        return max(0, min(len(self._points) - 1, idx))

    def _y_for_value(self, v: float) -> float:
        span = self._max_v - self._min_v
        usable = self.STRIP_HEIGHT - self.TOP_MARGIN - self.BOTTOM_MARGIN
        frac = (v - self._min_v) / span
        return self.STRIP_HEIGHT - self.BOTTOM_MARGIN - frac * usable

    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if not self._points:
            painter.fillRect(self.rect(), QColor("#0f172a"))
            return

        sel_lo, sel_hi = self._current_selection_range()

        # --- threshold reference bands (drawn first, so grade-colored
        # bands and the trace sit on top and remain visually dominant) ---
        if self._show_thresholds and self._thresholds is not None:
            self._paint_threshold_bands(painter)

        # --- grade-colored background bands ---
        for i, p in enumerate(self._points):
            x = i * self.CELL_WIDTH
            color_hex = QUALITY_COLORS.get(p.quality_id, DEFAULT_QUALITY_COLOR)
            color = QColor(color_hex)
            color.setAlphaF(0.12 if p.tier == "default" else 0.38)
            painter.fillRect(QRectF(x, 0, self.CELL_WIDTH, self.STRIP_HEIGHT), color)

            if sel_lo is not None and sel_lo <= i <= sel_hi:
                painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
                painter.drawRect(QRectF(x + 0.5, 0.5, self.CELL_WIDTH - 1, self.STRIP_HEIGHT - 1))

        # --- reading trace, broken at None gaps ---
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#cbd5e1"))
        pen.setWidthF(1.25)
        painter.setPen(pen)

        path = QPainterPath()
        drawing = False
        for i, p in enumerate(self._points):
            x = i * self.CELL_WIDTH + self.CELL_WIDTH / 2
            if p.reading is None:
                drawing = False
                continue
            y = self._y_for_value(p.reading)
            if not drawing:
                path.moveTo(QPointF(x, y))
                drawing = True
            else:
                path.lineTo(QPointF(x, y))
        painter.drawPath(path)

        # --- hover guide line ---
        if self._hover_idx is not None:
            x = self._hover_idx * self.CELL_WIDTH + self.CELL_WIDTH / 2
            hover_pen = QPen(QColor("#60a5fa"))
            hover_pen.setStyle(Qt.PenStyle.DashLine)
            hover_pen.setWidthF(1.0)
            painter.setPen(hover_pen)
            painter.drawLine(QPointF(x, 0), QPointF(x, self.STRIP_HEIGHT))

    def _paint_threshold_bands(self, painter: QPainter) -> None:
        """Draws the mandatory range and the optional range as two
        DISTINCT colors (not the same hue at two opacities - that proved
        too subtle to read against a dark background in practice) so the
        PI can tell "within optional" from "within mandatory but outside
        optional" from "outside mandatory entirely" at a glance. The
        optional band is drawn on top of (inside) the mandatory band,
        since optional bounds are always the tighter, nested range. Any
        None bound is simply not drawn (no edge line / no fill on that
        side) rather than defaulted to a guessed value - see
        ThresholdBounds' own docstring for why some bounds are
        legitimately open-ended (e.g. a missing-signal sentinel)."""
        t = self._thresholds
        width = len(self._points) * self.CELL_WIDTH

        MAND_COLOR = QColor("#c98a2b")  # amber - "acceptable but outer limit"
        OPT_COLOR = QColor("#3b82f6")  # distinct blue - "preferred/tighter range"

        if t.mand_min is not None or t.mand_max is not None:
            y_top = self._y_for_value(t.mand_max) if t.mand_max is not None else 0
            y_bot = self._y_for_value(t.mand_min) if t.mand_min is not None else self.STRIP_HEIGHT
            fill = QColor(MAND_COLOR)
            fill.setAlphaF(0.30)
            painter.fillRect(QRectF(0, y_top, width, y_bot - y_top), fill)

        if t.opt_min is not None or t.opt_max is not None:
            y_top = self._y_for_value(t.opt_max) if t.opt_max is not None else 0
            y_bot = self._y_for_value(t.opt_min) if t.opt_min is not None else self.STRIP_HEIGHT
            fill = QColor(OPT_COLOR)
            fill.setAlphaF(0.35)
            painter.fillRect(QRectF(0, y_top, width, y_bot - y_top), fill)

    def _current_selection_range(self) -> tuple[int | None, int | None]:
        if self._drag_start_idx is None or self._drag_end_idx is None:
            return None, None
        lo = min(self._drag_start_idx, self._drag_end_idx)
        hi = max(self._drag_start_idx, self._drag_end_idx)
        return lo, hi

    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._points or event.button() != Qt.MouseButton.LeftButton:
            return
        idx = self._idx_from_x(event.position().x())
        self._drag_start_idx = idx
        self._drag_end_idx = idx
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._points:
            return
        idx = self._idx_from_x(event.position().x())

        if self._hover_idx != idx:
            self._hover_idx = idx
            self.hoverDepthChanged.emit(self._points[idx].depth)

        if self._drag_start_idx is not None:
            self._drag_end_idx = idx
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start_idx is None or event.button() != Qt.MouseButton.LeftButton:
            return
        lo, hi = self._current_selection_range()
        self._drag_start_idx = None
        self._drag_end_idx = None
        self.update()
        if lo is not None:
            start_depth = self._points[lo].depth
            end_depth = self._points[hi].depth
            self.rangeSelected.emit(start_depth, end_depth)

    def leaveEvent(self, event) -> None:
        self._hover_idx = None
        self.hoverDepthChanged.emit(None)
        self.update()

    # ------------------------------------------------------------------
    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(max(1, len(self._points) * self.CELL_WIDTH), self.STRIP_HEIGHT)


# ---------------------------------------------------------------------------
# Standalone test harness — development/review only, not part of the app.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import random

    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QLabel,
        QMainWindow,
        QVBoxLayout,
        QWidget as QW,
    )

    def make_synthetic(max_depth: int, spike_at: int | None) -> list[ResolvedDepthPoint]:
        # Synthetic-test-only stand-in for the real Good id, which in the
        # actual app comes from QualityLookup.good_id (itself sourced from
        # the pre-loader JSON). This harness has no real JSON to load, so
        # it hardcodes 1 here deliberately, for test data only - this is
        # NOT the pattern entry_window.py should follow.
        _TEST_GOOD_ID = 1
        rand = random.Random(42)
        points = []
        v = 10.0
        for d in range(max_depth + 1):
            v += (rand.random() - 0.5) * 0.4
            reading = v
            if spike_at is not None and abs(d - spike_at) < 6:
                falloff = 1 - abs(d - spike_at) / 6
                reading += 18 * falloff * (0.6 + rand.random() * 0.8)
            quality_id = _TEST_GOOD_ID
            tier = "default"
            points.append(ResolvedDepthPoint(depth=d, reading=round(reading, 3),
                                              quality_id=quality_id, tier=tier))
        # Punch a couple of null gaps, like a real SBE sentinel dropout.
        for d in (15, 16, 17):
            if d <= max_depth:
                points[d].reading = None
        return points

    # Synthetic threshold bounds for this test only - in the real app,
    # these come from ThresholdBounds.from_preload_payload(). Chosen here
    # so the synthetic trace (base ~10, spike to ~28) crosses both the
    # optional and mandatory bands at the spike, for a visible test.
    _TEST_THRESHOLDS = ThresholdBounds(
        mand_min=0.0, mand_max=25.0, opt_min=5.0, opt_max=18.0,
    )

    class TestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("DepthStripWidget — standalone test")
            central = QW()
            layout = QVBoxLayout(central)

            self.strip = DepthStripWidget()
            self.strip.set_data(make_synthetic(70, spike_at=40))
            self.strip.set_thresholds(_TEST_THRESHOLDS)
            layout.addWidget(self.strip)

            self.chk_thresholds = QCheckBox("Show mandatory/optional threshold bands")
            self.chk_thresholds.stateChanged.connect(
                lambda state: self.strip.set_show_thresholds(state != 0)
            )
            layout.addWidget(self.chk_thresholds)

            self.status = QLabel("Click-drag a range on the strip above.")
            layout.addWidget(self.status)

            self.strip.rangeSelected.connect(self._on_range)
            self.strip.hoverDepthChanged.connect(self._on_hover)

            self.setCentralWidget(central)
            self.resize(560, 200)

        def _on_range(self, start, end):
            self.status.setText(f"Range selected: {start}m to {end}m "
                                 f"({end - start + 1} depth rows)")
            # Simulate applying a grade, just to see the bands update.
            for p in self.strip._points:
                if start <= p.depth <= end:
                    p.quality_id = 4
                    p.tier = "depth"
            self.strip.update()

        def _on_hover(self, depth):
            if depth is None:
                return
            p = self.strip._points[depth]
            reading_str = f"{p.reading:.3f}" if p.reading is not None else "(no reading)"
            self.status.setText(f"Depth {depth}m — {reading_str}")

    app = QApplication(sys.argv)
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
