"""
output_io.py
OC_M Project Leader app — output file I/O and validation.
Version: 2026.10.20_02

## ChangeLog

2026.10.20_02: No functional change to this module. Version bump only,
to reflect entry_window.py's new sensor-grade-propagation feature
(conductivity/temperature grades propagating to salinity/sigma_t) -
propagation is entirely a UI-layer decision about WHICH sensors to
apply an already-existing action to, and reuses every mechanism this
module already provides (resolved_cast_grade/resolved_depth_grade's
independent per-sensor cascades, the Dump -> Cast -> Depth clamp) with
no changes needed here. See entry_window.py's matching changelog entry
for the full feature.

2026.10.19_02: Full-file structural parity fix. OCMSubmission was
claimed, across several prior changelog entries (2026.10.13_01,
2026.10.16_01), to share "one JSON structure" with the pre-loader's own
output - that claim was only ever true for the PER-CAST shape
(sensor_cast_grades/depth_quality_ids); it was never actually true for
the file as a whole, and nobody verified the payload-level keys before
writing that claim down. Confirmed via direct diff against a real
pre-loader file and a real PI-saved file (both supplied by the
developer) that to_json_payload() silently dropped SEVEN top-level
keys the pre-loader emits (generated_date, start_year, end_year,
data_quality_ids, thresholds, graded_sensors,
defective_sensor_columns) plus one dump-level key (defective_sensors) -
none of these were ever modeled on OCMSubmission/DumpEntry at all, so
a PI save followed by a reopen would have silently and permanently
lost all of them.

Fixed by adding these as plain pass-through fields:
  - OCMSubmission gains: extraction_date (renamed from the pre-
    loader's "generated_date" on read - the PI app's own save-time
    concept keeps its own name, saved_date, so the two timestamps
    stay distinct: WHEN THE SNAPSHOT WAS QUERIED vs WHEN THE PI LAST
    SAVED), start_year, end_year, data_quality_ids, thresholds,
    graded_sensors, defective_sensor_columns.
  - DumpEntry gains: defective_sensors (per-dump list of sensor names
    the pre-loader's own NULL-column inference flagged - distinct
    from the similarly-named top-level defective_sensor_columns,
    which is the fixed 6-of-9 candidate list, not a per-dump result).
  - "submitted_date" (the PI app's own save timestamp) is renamed to
    saved_date for clarity, per explicit developer request, now that
    it sits alongside extraction_date and the two names being
    confusingly similar ("generated"/"submitted") was part of how this
    went unnoticed for two sessions.

As of 2026.10.20_01, oc_m_preloader_service.py also emits
"extraction_date" natively (was "generated_date") and this module's
from_payload() reads ONLY the new key names (extraction_date,
saved_date) - no backward-compatibility fallback is kept for the old
key names, per explicit developer instruction that already-saved files
are not a concern right now.

None of this changes the per-cast/per-dump GRADING shape, which was
already correct - this is purely restoring the payload-level facts
that were always supposed to round-trip and never did.

2026.10.20_01 (CastEntry.cast_dirty): Added CastEntry.cast_dirty: bool,
to support a streamlined UPDATE process in the Data Manager's future
ingestion service (discussed and designed in the companion ingestion-
service chat, brought here for implementation). Starts False; set to
True by entry_window.py at every point that mutates a cast's grades,
comment, or depth array - six call sites, not the four originally
proposed, since _on_depth_range_reset/_on_all_depth_ranges_cleared were
missed in the first pass. Once dirty, always dirty for the life of the
file - no "un-dirty" path, since a redundant write costs nothing and
there is no feedback loop telling the PI app ingestion already happened
for a given save. Persisted in the saved JSON (round-tripped by
to_json_payload()/from_payload()) rather than kept in-memory-only,
since multi-sitting grading is an explicitly supported workflow.

A finer-grained per-depth-index dirty tracking scheme was considered
and REJECTED as unnecessary complexity: once cast_dirty is True, the
ingestion service is expected to rewrite every depth row in that cast
regardless (cast-level grades and the comment already apply uniformly
to every row in the cast, so there is no scenario where ingestion would
want cast-level granularity finer than "this whole cast changed or it
didn't").

This module does not itself set or read cast_dirty beyond round-
tripping it - it is pure pass-through data, same treatment as station.

2026.10.16_01: Single-shape unification. REPLACES CastEntry.
depth_overrides (a list of DepthRangeOverride range-objects needing
overlap/"last-applied-wins" resolution) with CastEntry.
depth_quality_ids (dict[str, list[int]]) - one resolved quality_id per
depth, per sensor, parallel-indexed with depths/readings[sensor]
exactly like a reading itself. sensor_cast_grades is also now ALWAYS
fully populated (every graded sensor, every cast - no sparseness, no
omission for "nothing graded"), matching oc_m_preloader_service.py's
own output shape exactly for the per-cast portion. This removes the
entire "two overlapping depth overrides for the same depth" bug class
by construction (there is only ever one slot per depth, nothing to
overlap) and eliminates the translation step that previously had to
exist between what the preloader emitted and what the PI app's save
format expected - both ends now read and write the identical per-cast
shape. DepthRangeOverride is removed entirely. resolved_depth_grade()
is now a direct array-index lookup instead of a reverse-order range
scan.

2026.10.13_02: Added CastEntry.station (read-only, DB-sourced) -
round-tripped through to_json_payload()/from_payload() the same way
depths/readings are. Needed so entry_window.py's cast list can show
the station alongside the cast number.

2026.10.13_01: Single-file architecture pivot. REPLACES the two-file
(pre-loader snapshot + PI delta) design with one JSON structure used for
both the pre-loader's output and the PI's save/load. CastEntry now holds
the full per-depth reading series (depths/readings) alongside grade
data, not just overrides - this is the structural fix for the
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
depth_quality_ids fully populated at Good, which already resolves
correctly via the existing cascade - no special-case handling needed
for "first open."

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
has its own grade at three granularities (dump/cast/depth). NOTE
(2026.10.19): DumpEntry.defective_sensors is RE-ADDED as of that
session's fix, but with a DIFFERENT meaning than the old, removed
field - the old one was a destructive NULL-out mechanism; the new one
is a read-only, pass-through copy of the pre-loader's own inference
result, never written to or acted on by this module, kept only so the
PI's saved file doesn't silently lose that information.

Defines the on-disk shape of the PI's saved OC_M submission (the single
file now shared by the pre-loader's output and the PI's save/load) and
the logic to:
- resolve each sensor's effective grade id, for a given cast and
      optionally a given depth, via a 3-tier cascade:
          depth-specific stored value (CastEntry.depth_quality_ids - a
          direct per-depth array lookup, not a range scan; "depth" tier
          applies whenever the stored value differs from the cast-level
          resolved grade)
              -> cast-level grade (CastEntry.sensor_cast_grades)
              -> dump-level override (DumpEntry.sensor_dump_grades)
              -> the Good id (caller-supplied; this module never
                 assumes which id that is).
    - flag problems that must block ingestion on the Data Manager's
      side, without ever blocking the PI's own Save. The 2026-10
      redesign reduces the original THREE validation rules to ONE
      (a cast with any non-Good grade - cast-level or depth-level, any
      sensor - must have a comment); the other two no longer apply
      under per-sensor grading. As of 2026.10.19, two more rules were
      ADDED (not retired) - the dump_vs_cast/cast_vs_depth hierarchy
      checks - see that function's docstring.
    - save / load the submission JSON (one shape, full structure,
      readings included)

This module has no Qt dependency, so it can be unit tested and reused
verbatim by the Data Manager's ingestion service later. As of
2026.10.19, severity_by_id (a plain dict, not a Qt-adjacent object) is
also needed by several functions here - the ingestion service will need
to supply its own copy of the same {quality_id: severity_order} mapping,
sourced from the same OC.tbl_data_quality table this module has always
assumed a caller-supplied good_id/graded_sensors would come from (now
also directly available as OCMSubmission.data_quality_ids/
graded_sensors after loading a file).

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
class CastEntry:
    cast: str
    # Read-only, DB-sourced - never edited by the PI, never written
    # back with a different value than what was loaded.
    station: str | None = None
    # UNCHANGED from the original design, per explicit developer
    # instruction - one free-text comment per cast remains sufficient;
    # no per-sensor or per-depth comment fields are being added.
    comment: str | None = None
    # The full per-depth reading series for this cast. depths and each
    # sensor's readings list are kept in parallel (same length, same
    # order) - depths[i] corresponds to readings[sensor][i] for every
    # sensor. A sensor's reading at index i may be None (no reading at
    # that depth for that sensor - instrument gap, not a grading
    # decision).
    depths: list[int] = field(default_factory=list)
    readings: dict[str, list[float | None]] = field(default_factory=dict)
    # sensor_cast_grades is ALWAYS fully populated - one quality_id per
    # graded sensor, every cast, no sparseness, no omission for
    # "nothing graded." Matches oc_m_preloader_service.py's own output
    # shape exactly for the per-cast portion.
    sensor_cast_grades: dict[str, int] = field(default_factory=dict)
    # One resolved quality_id PER DEPTH, parallel-indexed with
    # depths/readings[sensor] exactly like a reading itself. There is
    # only ever one slot per depth, so there is nothing to overlap.
    # Writing a new grade for a depth range is a direct slot
    # assignment, not an append; "reset to cast grade" is a direct slot
    # assignment back to sensor_cast_grades[sensor], not a filter.
    depth_quality_ids: dict[str, list[int]] = field(default_factory=dict)
    # Added 2026.10.20_01 for the Data Manager's future ingestion
    # service. Starts False; set True by entry_window.py at every
    # grade/comment/depth mutation site. Once True, stays True for the
    # life of the file - no "un-dirty" path. This module only
    # round-trips it; it never sets or reads it for any decision of its
    # own.
    cast_dirty: bool = False


@dataclass
class DumpEntry:
    dump: str
    ctd: str | None = None
    start_date: str | None = None
    # Per-sensor dump-level override. Sparse dict - absence means
    # "falls through to Good".
    sensor_dump_grades: dict[str, int] = field(default_factory=dict)
    analyst_comments: str = ""          # free-text; NOT applied to the database
    # Read-only, pass-through copy of the pre-loader's own defective-
    # sensor inference for this dump (a sensor whose reading column is
    # NULL for every row in the dump). This module never writes to or
    # acts on this field. NOT the same concept as the top-level, fixed
    # candidate list defective_sensor_columns - this is the per-dump
    # RESULT of applying that inference, specific to this one dump.
    defective_sensors: list[str] = field(default_factory=list)
    casts: dict[str, CastEntry] = field(default_factory=dict)  # cast -> CastEntry

    # ------------------------------------------------------------------
    def resolved_cast_grade(
        self, sensor: str, cast: str, good_id: int, severity_by_id: dict[int, int]
    ) -> tuple[int, str]:
        """
        Return (quality_id, tier) for one sensor's GENERAL (non-depth-
        specific) grade on one cast. tier is one of "cast", "dump",
        "default" - purely informational, useful for UI display.

        good_id is the id whose data_quality_code is "0" (Good) - caller
        supplies it, since this module has no DB access of its own.

        severity_by_id maps quality_id -> severity_order, lower = better
        - same convention as depth_strip_widget.QualityLookup.
        severity_by_id, passed as a plain dict rather than that
        Qt-adjacent object so this module stays free of any Qt
        dependency. Used to enforce the Dump -> Cast -> Depth invariant
        (nothing downstream may be BETTER than upstream) at read time:
        if a cast-level override exists but is better than the
        dump-level value, it is ignored and the dump's own resolved
        value/tier is returned instead. The illegal stored override
        itself is never mutated or removed here - this is a pure
        read-time clamp, so a stray illegal value left over from a
        manual JSON edit (or any future bug) is rendered harmless
        everywhere this cascade is consulted, without needing to repair
        the underlying data.
        """
        dump_value = self.sensor_dump_grades.get(sensor, good_id)
        dump_tier = "dump" if sensor in self.sensor_dump_grades else "default"

        entry = self.casts.get(cast)
        if entry is not None and sensor in entry.sensor_cast_grades:
            cast_value = entry.sensor_cast_grades[sensor]
            if severity_by_id[cast_value] < severity_by_id[dump_value]:
                # Illegal: cast is better than dump. Clamp - ignore the
                # stored cast override, fall through to the dump's own
                # resolved value instead.
                return dump_value, dump_tier
            return cast_value, "cast"

        return dump_value, dump_tier

    def resolved_depth_grade(
        self, sensor: str, cast: str, depth: int, good_id: int, severity_by_id: dict[int, int]
    ) -> tuple[int, str]:
        """
        Return (quality_id, tier) for one sensor's grade at one specific
        depth row of one cast. depth_quality_ids[sensor] is a flat
        array, parallel-indexed with CastEntry.depths - the depth-level
        grade is a direct slot lookup, not a range scan.

        tier is "depth" whenever the stored value differs from the
        cast-level resolved grade, else falls through to resolved_
        cast_grade()'s own tier ("cast"/"dump"/"default").

        severity_by_id is forwarded to resolved_cast_grade() for its
        own cast-vs-dump clamp, AND used here for a second, symmetric
        clamp: if the stored depth value is BETTER than the cast-level
        resolved value, it is ignored and the cast-level value/tier is
        returned instead - same pattern as resolved_cast_grade()'s
        cast-vs-dump clamp, one level down. A depth re-stamped with the
        SAME value as the cast level still resolves as "cast" tier, not
        "depth." validate_submission()'s cast_vs_depth check still
        separately reports the underlying bad stored value - the clamp
        fixes the LIVE SESSION's displayed/computed values; validation
        is what tells the PI something in the file needs fixing.
        """
        cast_level_id, cast_level_tier = self.resolved_cast_grade(sensor, cast, good_id, severity_by_id)
        entry = self.casts.get(cast)
        if entry is not None:
            depth_ids = entry.depth_quality_ids.get(sensor)
            if depth_ids is not None and depth in entry.depths:
                idx = entry.depths.index(depth)
                if idx < len(depth_ids):
                    stored = depth_ids[idx]
                    if severity_by_id[stored] < severity_by_id[cast_level_id]:
                        # Illegal: depth is better than its cast's
                        # resolved value. Clamp - ignore the stored
                        # depth value, fall through to the cast-level
                        # tier instead.
                        return cast_level_id, cast_level_tier
                    if stored != cast_level_id:
                        return stored, "depth"
        return cast_level_id, cast_level_tier


@dataclass
class CruiseYearEntry:
    cruise_year: str
    dumps: dict[str, DumpEntry] = field(default_factory=dict)  # dump -> DumpEntry


class OCMSubmission:
    """
    In-memory representation of the PI's full OC_M submission, spanning
    possibly-multiple cruise years. This is the ONE in-memory model for
    both a fresh pre-loader-emitted file and a file the PI has already
    graded and saved - both are the same JSON shape, loaded via the
    same load() classmethod.

    Also holds the pre-loader's PAYLOAD-LEVEL facts (extraction_date,
    start_year, end_year, data_quality_ids, thresholds, graded_sensors,
    defective_sensor_columns) as plain pass-through fields, plus its own
    saved_date.
    """

    def __init__(self):
        self.cruise_years: dict[str, CruiseYearEntry] = {}
        # Payload-level pass-through facts. None of these are read or
        # interpreted by this module beyond storing and round-tripping
        # them - entry_window.py is the consumer.
        self.extraction_date: str | None = None
        self.start_year: str | None = None
        self.end_year: str | None = None
        self.data_quality_ids: list[dict] = []
        self.thresholds: list[dict] = []
        self.graded_sensors: list[str] = []
        self.defective_sensor_columns: list[str] = []
        self.saved_date: str | None = None

    # ------------------------------------------------------------------
    def to_json_payload(self) -> dict:
        """
        Emits the FULL structure - readings included - not a delta.
        This is what allows a saved file to be reopened directly without
        re-running the pre-loader.

        Also emits every payload-level fact this instance was
        constructed with or loaded from, and the PI app's own
        saved_date (this save's timestamp, freshly generated every call
        - distinct from extraction_date, which is carried through
        UNCHANGED from whenever the pre-loader actually queried the
        database). Always writes the current key names (extraction_date/
        saved_date); does not preserve any older on-disk key names - per
        explicit developer instruction, backward compatibility with
        files saved before the 2026.10.19 fix is not a concern.

        Casts are NOT omitted when they have nothing graded - every
        cast's readings/depths must be written regardless of grading
        state, since this file is now the only record of that data for
        this submission.
        """
        cruise_years_out = []
        for year, cy in sorted(self.cruise_years.items()):
            dumps_out = []
            for dump, d in sorted(cy.dumps.items()):
                casts_out = {}
                for cast, c in sorted(d.casts.items()):
                    casts_out[cast] = {
                        "station": c.station,
                        "depths": list(c.depths),
                        "readings": {s: list(v) for s, v in c.readings.items()},
                        "comment": c.comment,
                        "sensor_cast_grades": dict(c.sensor_cast_grades),
                        "depth_quality_ids": {s: list(v) for s, v in c.depth_quality_ids.items()},
                        "cast_dirty": c.cast_dirty,
                    }
                dumps_out.append({
                    "dump": dump,
                    "ctd": d.ctd,
                    "start_date": d.start_date,
                    "sensor_dump_grades": dict(d.sensor_dump_grades),
                    "analyst_comments": d.analyst_comments,
                    "defective_sensors": list(d.defective_sensors),
                    "casts": casts_out,
                })
            cruise_years_out.append({
                "cruise_year": year,
                "dumps": dumps_out,
            })

        return {
            "extraction_date": self.extraction_date,
            "saved_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "start_year": self.start_year,
            "end_year": self.end_year,
            "data_quality_ids": self.data_quality_ids,
            "thresholds": self.thresholds,
            "graded_sensors": self.graded_sensors,
            "defective_sensor_columns": self.defective_sensor_columns,
            "cruise_years": cruise_years_out,
        }

    def save(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(self.to_json_payload(), fh, indent=2)

    # ------------------------------------------------------------------
    @classmethod
    def from_payload(cls, payload: dict) -> "OCMSubmission":
        """
        The ONE parse path - used identically whether payload came from
        a fresh pre-loader-emitted file or a file the PI already graded
        and saved.

        Reads extraction_date/saved_date directly under their current
        names only - no fallback to older key names is kept, per
        explicit developer instruction.

        Takes an already-parsed dict rather than a filepath, since
        main.py already loads the JSON into memory before OCMEntryWindow
        is constructed - this avoids reading the same file twice under
        two different code paths. load() below is a thin convenience
        wrapper for callers that only have a bare filepath.
        """
        sub = cls()

        sub.extraction_date = payload.get("extraction_date")
        sub.saved_date = payload.get("saved_date")
        sub.start_year = payload.get("start_year")
        sub.end_year = payload.get("end_year")
        sub.data_quality_ids = payload.get("data_quality_ids", [])
        sub.thresholds = payload.get("thresholds", [])
        sub.graded_sensors = payload.get("graded_sensors", [])
        sub.defective_sensor_columns = payload.get("defective_sensor_columns", [])

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
                    defective_sensors=list(d.get("defective_sensors", [])),
                )
                for cast, c in d.get("casts", {}).items():
                    dump_entry.casts[cast] = CastEntry(
                        cast=cast,
                        station=c.get("station"),
                        depths=list(c.get("depths", [])),
                        readings={s: list(v) for s, v in c.get("readings", {}).items()},
                        comment=c.get("comment"),
                        sensor_cast_grades=dict(c.get("sensor_cast_grades", {})),
                        depth_quality_ids={s: list(v) for s, v in c.get("depth_quality_ids", {}).items()},
                        cast_dirty=c.get("cast_dirty", False),
                    )
                cy_entry.dumps[d["dump"]] = dump_entry
            sub.cruise_years[year] = cy_entry
        return sub

    @classmethod
    def load(cls, filepath: str) -> "OCMSubmission":
        """Convenience wrapper around from_payload() for callers that
        only have a bare filepath (entry_window.py's Open and Recent
        Files menu)."""
        with open(filepath, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return cls.from_payload(payload)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
# The original design had THREE rules, all defined for a single grade per
# cast. Only one survives the 2026-10 redesign unchanged in spirit:
#
#   1. "Cast has no resolved quality code at all" - RETIRED. Every sensor
#      now ALWAYS resolves to something via the dump -> cast -> depth ->
#      Good cascade.
#
#   2. "Resolved code is Good but has a non-empty comment" - RETIRED.
#      The comment field is shared across all 9 sensors on a cast. A
#      cast where conductivity is Bad (needs a comment) and temperature
#      is Good would trip this rule on temperature's behalf even though
#      the comment is legitimately explaining conductivity.
#
#   3. "Resolved code is non-Good but has an empty comment" - KEPT, but
#      restated at the CAST level rather than per-sensor: if ANY
#      sensor's resolved grade is non-Good anywhere on the cast, and the
#      comment is empty, that's still a legitimate signal. One problem
#      per cast, not one per sensor.
#
# As of 2026.10.19, TWO MORE RULES were ADDED - see
# _hierarchy_problems_for_cast() below. These detect Dump -> Cast ->
# Depth hierarchy violations already present in STORED data (most likely
# cause: a manually edited JSON file, or a file predating these fixes).
# Like the existing missing_comment rule, these are informational only
# and never block Save.
@dataclass
class CastProblem:
    cruise_year: str
    dump: str
    cast: str
    kind: str    # "missing_comment" | "dump_vs_cast" | "cast_vs_depth"
    detail: str


def _cast_has_any_non_good_grade(
    dump_entry: DumpEntry, cast: str, graded_sensors: list[str], good_id: int,
    severity_by_id: dict[int, int]
) -> bool:
    """True if any sensor resolves non-Good anywhere on this cast - a
    cast-level grade for any sensor, or a depth-specific grade for any
    sensor at any depth."""
    for sensor in graded_sensors:
        grade_id, _tier = dump_entry.resolved_cast_grade(sensor, cast, good_id, severity_by_id)
        if grade_id != good_id:
            return True
    cast_entry = dump_entry.casts.get(cast)
    if cast_entry is not None:
        for sensor, depth_ids in cast_entry.depth_quality_ids.items():
            if any(v != good_id for v in depth_ids):
                return True
    return False


def _hierarchy_problems_for_cast(
    dump_entry: DumpEntry, cast: str, graded_sensors: list[str], good_id: int,
    severity_by_id: dict[int, int]
) -> list[tuple[str, str]]:
    """Returns (kind, detail) pairs for every Dump -> Cast -> Depth
    invariant violation found on this one cast, across all graded
    sensors - the DETECTIVE counterpart to resolved_cast_grade()'s/
    resolved_depth_grade()'s read-time clamps.

    dump_vs_cast: compares the RAW stored cast-level override against
    the RAW stored dump-level value.

    cast_vs_depth: compares each stored depth_quality_ids value against
    the EFFECTIVE (already-clamped) cast-level resolved value, not the
    raw one - avoids flooding redundant violations when the raw cast
    value is itself already illegal. Summarized as one entry per
    (cast, sensor) with an affected-depth count."""
    out: list[tuple[str, str]] = []
    cast_entry = dump_entry.casts.get(cast)
    if cast_entry is None:
        return out

    for sensor in graded_sensors:
        raw_cast_value = cast_entry.sensor_cast_grades.get(sensor)
        raw_dump_value = dump_entry.sensor_dump_grades.get(sensor, good_id)

        if raw_cast_value is not None and severity_by_id[raw_cast_value] < severity_by_id[raw_dump_value]:
            out.append((
                "dump_vs_cast",
                f"sensor {sensor}: cast is graded better than its dump "
                f"(cast={raw_cast_value}, dump={raw_dump_value})."
            ))

        effective_cast_value, _tier = dump_entry.resolved_cast_grade(
            sensor, cast, good_id, severity_by_id
        )
        depth_ids = cast_entry.depth_quality_ids.get(sensor, [])
        worse_count = sum(
            1 for v in depth_ids if severity_by_id[v] < severity_by_id[effective_cast_value]
        )
        if worse_count > 0:
            label = "1 depth is" if worse_count == 1 else f"{worse_count} depths are"
            out.append((
                "cast_vs_depth",
                f"sensor {sensor}: {label} graded better than the cast's "
                f"resolved grade (id={effective_cast_value})."
            ))

    return out


def validate_submission(
    sub: OCMSubmission, graded_sensors: list[str], good_id: int, severity_by_id: dict[int, int]
) -> list[CastProblem]:
    """
    Never blocks Save. Returns a flat list of problems for display
    (dialog + grid highlighting). The Data Manager's ingestion service
    re-runs an equivalent check as a hard mandatory-error gate.

    Produces "missing_comment" problems and "dump_vs_cast"/
    "cast_vs_depth" problems - see _hierarchy_problems_for_cast() for
    what these detect and why. All three kinds are non-blocking.
    """
    problems: list[CastProblem] = []

    for year, cy in sorted(sub.cruise_years.items()):
        for dump, d in sorted(cy.dumps.items()):
            for cast in sorted(d.casts.keys()):
                comment = (d.casts[cast].comment or "").strip()
                if not comment and _cast_has_any_non_good_grade(d, cast, graded_sensors, good_id, severity_by_id):
                    problems.append(CastProblem(
                        year, dump, cast, "missing_comment",
                        f"Cast {cast} (dump {dump}, {year}) has at least one "
                        "sensor graded non-Good (cast-level or depth-level) "
                        "but no comment. Non-Good grades require an "
                        "explanatory comment."
                    ))

                for kind, detail in _hierarchy_problems_for_cast(d, cast, graded_sensors, good_id, severity_by_id):
                    problems.append(CastProblem(
                        year, dump, cast, kind,
                        f"Cast {cast} (dump {dump}, {year}): {detail}"
                    ))

    return problems
