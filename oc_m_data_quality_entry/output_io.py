"""
output_io.py
OC_M Project Leader app — output file I/O and validation.
Version: 2026.10.13_01

## ChangeLog

2026.10.13_01: Single-file architecture pivot. REPLACES the two-file
(pre-loader snapshot + PI delta) design with one JSON structure used for
both the pre-loader's output and the PI's save/load. CastEntry now holds
the full per-depth reading series (depths/readings) alongside grade
overrides, not just overrides - this is the structural fix for the
"no graphs showing" bug from the prior session (see handoff doc): there
is no longer a separate raw pre-loader payload for entry_window.py to
keep in sync with OCMSubmission, so that class of desync bug is no
longer representable.

Removed entirely (not deprecated/kept dormant - per explicit developer
decision, the pre-pivot delta-based code was checked into GitHub first
so it remains recoverable there if ever needed):
    - restrict_onto_preload_shell()
    - the old new_from_preload() (merged into load() - see below)
    - the delta-only shape of to_json_payload() (now emits the full
      structure, readings included, so a saved file is fully
      self-contained and re-openable without re-running the
      pre-loader - this is what lets the PI open/save across multiple
      sittings without the Data Manager re-running the pre-loader each
      time)
    - _depth_overrides_from_preload_grades() - this function existed to
      solve a two-file-design-only problem (how does a freshly-loaded
      pre-loader shell initially represent the database's own stored
      grades as editable overrides). Under the single-file design,
      load() always reads an actual saved submission shape (whether
      it's a brand-new pre-loader-emitted file the PI has never graded,
      or a file the PI already saved once) - there is no separate
      "shell" state to seed.

OCMSubmission.load() is now the ONE load path, used both for a fresh
pre-loader-emitted file and for re-opening the PI's own prior save -
there is no longer a meaningful distinction between the two at the
file-shape level, since both are the same JSON shape now. A fresh
pre-loader file simply has every cast's sensor_cast_grades/
depth_overrides empty and comment null, which already resolves
correctly to all-Good via the existing cascade - no special-case
handling needed for "first open."

2026.10.08_02: removed the hardcoded GRADED_SENSORS list and GOOD_ID
constant. Both are now caller-supplied parameters, sourced from the
pre-loader JSON (graded_sensors list; good_id = the id whose
data_quality_code is "0", found in data_quality_ids) rather than
hand-typed copies of facts OC.tbl_data_quality/tbl_oc_cast already own.

Per-sensor, per-depth grading redesign (2026-10-08): this is a
REPLACEMENT of the prior single-value grading model (dump-level default
code/comment, per-cast override, destructive defective-sensor NULL-out),
not an addition alongside it - see oc_m_preloader_service.py's module
docstring for the full rationale. The old CastEntry.quality_code/comment
and DumpEntry.default_quality_code/default_comment/defective_sensors
fields are gone; there is nothing left for them to do once every sensor
has its own grade at three granularities (dump/cast/depth).

Defines the on-disk shape of the PI's saved OC_M submission (the single
file now shared by the pre-loader's output and the PI's save/load - see
2026.10.13_01 above) and the logic to:
    - resolve each sensor's effective grade id, for a given cast and
      optionally a given depth, via a 3-tier override cascade:
          depth-range override (if the depth falls in one)
              -> cast-level override
              -> dump-level override
              -> the Good id (caller-supplied - see good_id parameters
                 below; this module never assumes which id that is).
    - flag problems that must block ingestion on the Data Manager's
      side, without ever blocking the PI's own Save. The 2026-10
      redesign reduces the original THREE validation rules to ONE
      (a cast with any non-Good grade - cast-level or depth-level, any
      sensor - must have a comment); the other two no longer apply
      under per-sensor grading. See the comment directly above
      validate_submission() for the full per-rule rationale.
    - save / load the submission JSON (one shape, full structure,
      readings included - see 2026.10.13_01)

This module has no Qt dependency, so it can be unit tested and reused
verbatim by the Data Manager's ingestion service later. NOTE for that
future work (per handoff doc): the ingestion service should now expect
to receive this same full structure (readings + all resolved grade
values) per cast, not a sparse delta needing reconciliation against a
separate snapshot - the two-file design's premise is gone.

Comments remain UNCHANGED from the original per-cast design, per
explicit developer instruction: the Project Leader confirmed the single
free-text data_quality_comment per cast is sufficient and no additional
per-sensor or per-depth comment fields are needed, even though grading
itself is now per-sensor/per-depth. This file keeps CastEntry.comment
for that purpose; only the grade-code side of the model is replaced.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DepthRangeOverride:
    sensor: str
    start_depth: int
    end_depth: int        # inclusive; a single depth is start == end
    quality_id: int

    def covers(self, depth: int) -> bool:
        return self.start_depth <= depth <= self.end_depth


@dataclass
class CastEntry:
    cast: str
    # UNCHANGED from the original design, per explicit developer
    # instruction - one free-text comment per cast remains sufficient;
    # no per-sensor or per-depth comment fields are being added.
    comment: str | None = None
    # NEW in 2026.10.13_01 (single-file pivot): the full per-depth
    # reading series for this cast, moved here from the old separate
    # pre-loader raw payload dict. depths and each sensor's readings
    # list are kept in parallel (same length, same order) - depths[i]
    # corresponds to readings[sensor][i] for every sensor. A sensor's
    # reading at index i may be None (no reading at that depth for that
    # sensor - instrument gap, not a grading decision).
    depths: list[int] = field(default_factory=list)
    readings: dict[str, list[float | None]] = field(default_factory=dict)
    # Per-sensor cast-level override. Only sensors with an explicit
    # cast-level grade appear here (sparse dict - absence means "falls
    # through to the dump-level grade, or Good").
    sensor_cast_grades: dict[str, int] = field(default_factory=dict)
    # Explicit depth-range overrides for this cast, any sensor. Overlap
    # resolution is "last-applied wins" (see resolved_depth_grade),
    # applied at read time by scanning in list order - ranges are never
    # eagerly merged/split on write, to keep the override list a simple,
    # faithful record of what the PI actually did, in order.
    depth_overrides: list[DepthRangeOverride] = field(default_factory=list)


@dataclass
class DumpEntry:
    dump: str
    ctd: str | None = None
    start_date: str | None = None
    # Per-sensor dump-level override - this single field covers what the
    # OLD design split across "dump default" (generic, all sensors) and
    # "defective_sensors" (destructive NULL-out, 6 of the 9 sensors
    # only). Both collapse into one concept: a dump-wide grade for one
    # sensor. Sparse dict - absence means "falls through to Good".
    sensor_dump_grades: dict[str, int] = field(default_factory=dict)
    analyst_comments: str = ""          # free-text; NOT applied to the database
    casts: dict[str, CastEntry] = field(default_factory=dict)  # cast -> CastEntry

    # ------------------------------------------------------------------
    def resolved_cast_grade(self, sensor: str, cast: str, good_id: int) -> tuple[int, str]:
        """
        Return (quality_id, tier) for one sensor's GENERAL (non-depth-
        specific) grade on one cast. tier is one of "cast", "dump",
        "default" - purely informational, useful for UI display (e.g.
        showing the PI which level a resolved value actually came from).

        good_id is the id whose data_quality_code is "0" (Good) - caller
        supplies it (ultimately sourced from the pre-loader JSON's
        data_quality_ids list), since this module has no DB access of
        its own and must not assume which id that is.
        """
        entry = self.casts.get(cast)
        if entry is not None and sensor in entry.sensor_cast_grades:
            return entry.sensor_cast_grades[sensor], "cast"
        if sensor in self.sensor_dump_grades:
            return self.sensor_dump_grades[sensor], "dump"
        return good_id, "default"

    def resolved_depth_grade(self, sensor: str, cast: str, depth: int, good_id: int) -> tuple[int, str]:
        """
        Return (quality_id, tier) for one sensor's grade at one specific
        depth row of one cast. tier adds "depth" to the possible values
        from resolved_cast_grade(). Overlap resolution: the LAST matching
        depth_overrides entry (in list order) wins, since the list is
        built in the order the PI applied ranges during the session -
        see CastEntry.depth_overrides.
        """
        entry = self.casts.get(cast)
        if entry is not None:
            for override in reversed(entry.depth_overrides):
                if override.sensor == sensor and override.covers(depth):
                    return override.quality_id, "depth"
        return self.resolved_cast_grade(sensor, cast, good_id)


@dataclass
class CruiseYearEntry:
    cruise_year: str
    dumps: dict[str, DumpEntry] = field(default_factory=dict)  # dump -> DumpEntry


class OCMSubmission:
    """
    In-memory representation of the PI's full OC_M submission, spanning
    possibly-multiple cruise years. As of the 2026.10.13_01 single-file
    pivot, this is the ONE in-memory model for both a fresh pre-loader-
    emitted file and a file the PI has already graded and saved - both
    are the same JSON shape, loaded via the same load() classmethod.
    """

    def __init__(self):
        self.cruise_years: dict[str, CruiseYearEntry] = {}

    # ------------------------------------------------------------------
    def to_json_payload(self) -> dict:
        """
        Emits the FULL structure - readings included - not a delta.
        This is what allows a saved file to be reopened directly (by
        the PI, across multiple sittings, or by the Data Manager's
        future ingestion service) without re-running the pre-loader.

        Unlike the old delta-based version, casts are NOT omitted when
        they have nothing graded - every cast's readings/depths must be
        written regardless of grading state, since this file is now the
        only record of that data for this submission. Only comment/
        sensor_cast_grades/depth_overrides vary in how "empty" they look
        (empty dict/list/null), never whether the cast appears at all.
        """
        cruise_years_out = []
        for year, cy in sorted(self.cruise_years.items()):
            dumps_out = []
            for dump, d in sorted(cy.dumps.items()):
                casts_out = {}
                for cast, c in sorted(d.casts.items()):
                    casts_out[cast] = {
                        "depths": list(c.depths),
                        "readings": {s: list(v) for s, v in c.readings.items()},
                        "comment": c.comment,
                        "sensor_cast_grades": dict(c.sensor_cast_grades),
                        "depth_overrides": [
                            {
                                "sensor": o.sensor,
                                "start_depth": o.start_depth,
                                "end_depth": o.end_depth,
                                "quality_id": o.quality_id,
                            }
                            for o in c.depth_overrides
                        ],
                    }
                dumps_out.append({
                    "dump": dump,
                    "ctd": d.ctd,
                    "start_date": d.start_date,
                    "sensor_dump_grades": dict(d.sensor_dump_grades),
                    "analyst_comments": d.analyst_comments,
                    "casts": casts_out,
                })
            cruise_years_out.append({
                "cruise_year": year,
                "dumps": dumps_out,
            })

        return {
            "submitted_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "cruise_years": cruise_years_out,
        }

    def save(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(self.to_json_payload(), fh, indent=2)

    # ------------------------------------------------------------------
    @classmethod
    def from_payload(cls, payload: dict) -> "OCMSubmission":
        """
        The ONE parse path (2026.10.13_01) - used identically whether
        payload came from a fresh pre-loader-emitted file (every cast's
        comment/sensor_cast_grades/depth_overrides empty) or a file the
        PI already graded and saved. Both are the same JSON shape; there
        is no separate "shell" concept or delta-replay step anymore.

        Takes an already-parsed dict rather than a filepath, since
        main.py already loads the JSON into memory before OCMEntryWindow
        is constructed (see main.py's _load_preload_json) - this avoids
        reading the same file twice under two different code paths.
        load() below is a thin convenience wrapper for callers that do
        have a bare filepath (e.g. entry_window.py's Open/Recent Files,
        which only ever have a path from a QFileDialog).
        """
        sub = cls()
        for cy in payload.get("cruise_years", []):
            year = cy["cruise_year"]
            cy_entry = CruiseYearEntry(cruise_year=year)
            for d in cy.get("dumps", []):
                dump_entry = DumpEntry(
                    dump=d["dump"],
                    ctd=d.get("ctd"),
                    start_date=d.get("start_date"),
                    sensor_dump_grades=dict(d.get("sensor_dump_grades", {})),
                    analyst_comments=d.get("analyst_comments", ""),
                )
                for cast, c in d.get("casts", {}).items():
                    dump_entry.casts[cast] = CastEntry(
                        cast=cast,
                        depths=list(c.get("depths", [])),
                        readings={s: list(v) for s, v in c.get("readings", {}).items()},
                        comment=c.get("comment"),
                        sensor_cast_grades=dict(c.get("sensor_cast_grades", {})),
                        depth_overrides=[
                            DepthRangeOverride(
                                sensor=o["sensor"],
                                start_depth=o["start_depth"],
                                end_depth=o["end_depth"],
                                quality_id=o["quality_id"],
                            )
                            for o in c.get("depth_overrides", [])
                        ],
                    )
                cy_entry.dumps[d["dump"]] = dump_entry
            sub.cruise_years[year] = cy_entry
        return sub

    @classmethod
    def load(cls, filepath: str) -> "OCMSubmission":
        """Convenience wrapper around from_payload() for callers that
        only have a bare filepath (entry_window.py's Open and Recent
        Files menu, both of which only ever get a path back from a
        QFileDialog or a previously-recorded recent-files entry)."""
        with open(filepath, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return cls.from_payload(payload)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
# The original design had THREE rules, all defined for a single grade per
# cast. Only one survives the 2026-10 redesign unchanged in spirit; the
# other two are retired as structurally obsolete or newly incorrect under
# per-sensor grading - not a straightforward port. Specifically:
#
#   1. "Cast has no resolved quality code at all" - RETIRED. Every sensor
#      now ALWAYS resolves to something via the dump -> cast -> depth ->
#      Good cascade (see DumpEntry.resolved_cast_grade/resolved_depth_
#      grade). There is no longer an "ungraded" state for this rule to
#      detect - it cannot fire under the new model by construction.
#
#   2. "Resolved code is Good but has a non-empty comment" - RETIRED.
#      The comment field is shared across all 9 sensors on a cast (per
#      explicit developer instruction - no per-sensor/per-depth comment
#      fields). A cast where conductivity is Bad (needs a comment) and
#      temperature is Good would trip this rule on temperature's behalf
#      even though the comment is legitimately explaining conductivity.
#      Porting this rule as-is would produce a false positive on every
#      multi-sensor cast where only some sensors are graded non-Good -
#      not a real problem, just noise.
#
#   3. "Resolved code is non-Good but has an empty comment" - KEPT, but
#      restated at the CAST level rather than per-sensor, for the same
#      shared-comment reason as #2: if ANY sensor's resolved grade is
#      non-Good anywhere on the cast (a cast-level override, OR any
#      depth-range override for any sensor), and the comment is empty,
#      that is still a legitimate "you graded something bad but never
#      explained why" signal. One problem per cast, not one per sensor,
#      since there is one comment to satisfy.
#
# Depth-level non-Good grades count toward this check the same as
# cast-level ones - a depth-range override is still "something graded
# non-Good on this cast" even though it also carries its own quality_id.
@dataclass
class CastProblem:
    cruise_year: str
    dump: str
    cast: str
    kind: str    # "missing_comment" (the only kind currently produced)
    detail: str


# def _good_id_from_payload(preload_payload: dict) -> int:
#     """The id whose data_quality_code is "0" (Good), read from the
#     pre-loader JSON's data_quality_ids list (itself a live
#     OC.tbl_data_quality query - see oc_m_preloader_service.py's
#     _fetch_data_quality_table()). Raises ValueError if no such row is
#     present - there is no safe assumed fallback for this.
#
#     Still used post-pivot: this reads data_quality_ids, which is a
#     structural part of the shared JSON shape regardless of whether the
#     file is a fresh pre-loader emission or the PI's own prior save (the
#     PI app round-trips this key unchanged - it never alters the
#     DB-sourced lookup table embedded in the file)."""
#     for row in preload_payload.get("data_quality_ids", []):
#         if row.get("code") == "0":
#             return row["id"]
#     raise ValueError(
#         "No row with data_quality_code == '0' (Good) found in "
#         "data_quality_ids - cannot determine the Good id."
#     )


def _cast_has_any_non_good_grade(
    dump_entry: DumpEntry, cast: str, graded_sensors: list[str], good_id: int
) -> bool:
    """True if any sensor resolves non-Good anywhere on this cast - a
    cast-level override for any sensor, or a depth-range override for
    any sensor at any depth. Dump-level-only grades do NOT by themselves
    make every cast in the dump "non-Good" for this check's purposes -
    they still resolve non-Good for that sensor on this cast via the
    cascade, so they ARE included; this function simply asks the
    cascade's own resolved_cast_grade(), which already accounts for
    dump-level fallback."""
    for sensor in graded_sensors:
        grade_id, _tier = dump_entry.resolved_cast_grade(sensor, cast, good_id)
        if grade_id != good_id:
            return True
    cast_entry = dump_entry.casts.get(cast)
    if cast_entry is not None and cast_entry.depth_overrides:
        return any(o.quality_id != good_id for o in cast_entry.depth_overrides)
    return False


def validate_submission(
    sub: OCMSubmission, graded_sensors: list[str], good_id: int
) -> list[CastProblem]:
    """
    Never blocks Save. Returns a flat list of problems for display
    (dialog + grid highlighting). The Data Manager's ingestion service
    re-runs an equivalent check as a hard mandatory-error gate.

    graded_sensors and good_id should both come from the same JSON
    payload the submission was loaded from - entry_window.py already
    holds that payload's graded_sensors/data_quality_ids in memory and
    passes these through rather than this module hand-typing either.

    Currently produces only "missing_comment" problems - see the module
    comment above for why the original design's other two rules were
    retired rather than ported.
    """
    problems: list[CastProblem] = []

    for year, cy in sorted(sub.cruise_years.items()):
        for dump, d in sorted(cy.dumps.items()):
            for cast in sorted(d.casts.keys()):
                comment = (d.casts[cast].comment or "").strip()
                if not comment and _cast_has_any_non_good_grade(d, cast, graded_sensors, good_id):
                    problems.append(CastProblem(
                        year, dump, cast, "missing_comment",
                        f"Cast {cast} (dump {dump}, {year}) has at least one "
                        "sensor graded non-Good (cast-level or depth-level) "
                        "but no comment. Non-Good grades require an "
                        "explanatory comment."
                    ))

    return problems
