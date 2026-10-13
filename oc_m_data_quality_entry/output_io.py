"""
output_io.py
OC_M Project Leader app — output file I/O and validation.
Version: 2026.10.08_02 (supersedes original version 2026.09.08_1)

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

Defines the on-disk shape of the PI's saved OC_M submission (the file
handed back to the Data Manager for ingestion) and the logic to:
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
    - save / load the submission JSON
    - reconcile an opened file against a fresh pre-loader snapshot
      (restrict_onto_preload_shell), unchanged in spirit from the
      original version: a saved file only ever records DELTAS from the
      pre-loader's cast list, so it cannot stand alone as a complete
      source of dump/cast/depth structure.

This module has no Qt dependency, so it can be unit tested and reused
verbatim by the Data Manager's ingestion service later.

Comments remain UNCHANGED from the original per-cast design, per
explicit developer instruction: the Project Leader confirmed the single
free-text data_quality_comment per cast is sufficient and no additional
per-sensor or per-depth comment fields are needed, even though grading
itself is now per-sensor/per-depth. This file keeps CastEntry.comment
for that purpose; only the grade-code side of the model is replaced.

OPEN DESIGN QUESTION, resolved provisionally below - see
_depth_overrides_from_preload_grades() docstring for detail and an
explicit flag for the developer to confirm or override: how literal
non-Good per-depth-row facts from the pre-loader JSON (which are real,
already-stored database values, not inferred patterns) get represented
as the PI's editable depth-range overrides when a submission shell is
first built from a pre-loader payload.
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
    # NEW: per-sensor cast-level override. Only sensors with an explicit
    # cast-level grade appear here (sparse dict - absence means "falls
    # through to the dump-level grade, or Good").
    sensor_cast_grades: dict[str, int] = field(default_factory=dict)
    # NEW: explicit depth-range overrides for this cast, any sensor.
    # Overlap resolution is "last-applied wins" (see resolved_depth_grade),
    # applied at read time by scanning in list order - ranges are never
    # eagerly merged/split on write, to keep the override list a simple,
    # faithful record of what the PI actually did, in order.
    depth_overrides: list[DepthRangeOverride] = field(default_factory=list)


@dataclass
class DumpEntry:
    dump: str
    ctd: str | None = None
    start_date: str | None = None
    # NEW: per-sensor dump-level override - this single field now covers
    # what the OLD design split across "dump default" (generic, all
    # sensors) and "defective_sensors" (destructive NULL-out, 6 of the
    # 9 sensors only). Both collapse into one concept: a dump-wide grade
    # for one sensor. Sparse dict - absence means "falls through to Good".
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


# ---------------------------------------------------------------------------
# Resolved provisionally - see module docstring's "OPEN DESIGN QUESTION".
# ---------------------------------------------------------------------------
def _depth_overrides_from_preload_grades(
    cast_payload: dict,
    graded_sensors: list[str],
    good_id: int,
) -> list[DepthRangeOverride]:
    """
    Build this cast's initial depth_overrides list directly from the
    pre-loader JSON's literal per-depth-row general_grades/depth_grades
    arrays (real, already-stored database facts - NOT an inference step
    in the sense the developer ruled out for oc_m_preloader_service.py;
    there is no dump/cast-level pattern being guessed at here, only a
    straightforward grouping of literal per-row values that must be
    represented SOMEWHERE in the PI's editable model, since
    depth_overrides is the only place this structure has for a
    depth-level fact).

    For each sensor, walks depth_grades[sensor] (falling back to
    general_grades[sensor] if depth_grades is absent for that sensor -
    both arrays are omitted by the pre-loader when uniformly Good, so
    "absent" always means "nothing non-Good to represent here") and
    collapses contiguous equal non-Good runs into one DepthRangeOverride
    each. This is a literal grouping of adjacent identical values, not
    a judgment call about PI intent - unlike the retired dump/cast-level
    reverse-inference, there's no ambiguity about what "contiguous equal
    values" means at the single-sensor, single-cast, per-depth level.

    FLAGGED FOR DEVELOPER REVIEW: this function's output becomes the
    PI's starting depth_overrides for every previously-graded cast. If
    this is NOT the desired initial presentation (e.g. if the real
    preference is to show these as read-only/separately-labeled facts
    rather than editable overrides indistinguishable from ones the PI
    creates this session), this is the one function to change - nothing
    else in this module depends on how this collapsing is done, only
    that SOME list of DepthRangeOverride comes out the other end.
    """
    overrides: list[DepthRangeOverride] = []
    depths = cast_payload.get("depths", [])
    depth_grades = cast_payload.get("depth_grades", {})
    general_grades = cast_payload.get("general_grades", {})

    for sensor in graded_sensors:
        grade_list = depth_grades.get(sensor) or general_grades.get(sensor)
        if not grade_list:
            continue  # uniformly Good - pre-loader omitted this array entirely

        run_start_idx = None
        run_value = None
        for i, value in enumerate(grade_list):
            if value != run_value:
                if run_value is not None and run_value != good_id:
                    overrides.append(DepthRangeOverride(
                        sensor=sensor,
                        start_depth=depths[run_start_idx],
                        end_depth=depths[i - 1],
                        quality_id=run_value,
                    ))
                run_start_idx = i
                run_value = value
        # flush the final run
        if run_value is not None and run_value != good_id:
            overrides.append(DepthRangeOverride(
                sensor=sensor,
                start_depth=depths[run_start_idx],
                end_depth=depths[-1],
                quality_id=run_value,
            ))

    return overrides


class OCMSubmission:
    """
    In-memory representation of the PI's full OC_M submission, spanning
    possibly-multiple cruise years (mirrors the pre-loader JSON's scope).
    """

    def __init__(self):
        self.cruise_years: dict[str, CruiseYearEntry] = {}

    # ------------------------------------------------------------------
    @classmethod
    def new_from_preload(cls, preload_payload: dict) -> "OCMSubmission":
        """Build a submission shell from the pre-loader JSON. Casts start
        pre-populated with whatever grades already exist in the database,
        represented as depth-range overrides per
        _depth_overrides_from_preload_grades() - see that function's
        docstring for the one open design question in this redesign.
        A fresh, never-graded cast comes in with every sensor's cast/
        dump grade absent (resolves to Good) and no depth overrides.

        The sensor list and the Good id are both read from the pre-loader
        JSON (graded_sensors; good_id derived from data_quality_ids where
        code == "0") - the pre-loader derives both live from the database
        (see oc_m_preloader_service.py); this module never hand-types
        either as a constant."""
        sub = cls()
        graded_sensors = preload_payload.get("graded_sensors", [])
        good_id = _good_id_from_preload_payload(preload_payload)
        for cy in preload_payload.get("cruise_years", []):
            year = cy["cruise_year"]
            cy_entry = CruiseYearEntry(cruise_year=year)
            for d in cy.get("dumps", []):
                dump_entry = DumpEntry(
                    dump=d["dump"],
                    ctd=d.get("ctd"),
                    start_date=d.get("start_date"),
                )
                for cast, cast_payload in d.get("casts", {}).items():
                    dump_entry.casts[cast] = CastEntry(
                        cast=cast,
                        depth_overrides=_depth_overrides_from_preload_grades(
                            cast_payload, graded_sensors, good_id
                        ),
                    )
                cy_entry.dumps[d["dump"]] = dump_entry
            sub.cruise_years[year] = cy_entry
        return sub

    # ------------------------------------------------------------------
    def to_json_payload(self) -> dict:
        cruise_years_out = []
        for year, cy in sorted(self.cruise_years.items()):
            dumps_out = []
            for dump, d in sorted(cy.dumps.items()):
                casts_out = {}
                for cast, c in sorted(d.casts.items()):
                    if not c.sensor_cast_grades and not c.depth_overrides and not c.comment:
                        continue  # nothing to say about this cast - omit entirely
                    casts_out[cast] = {
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
    def load(cls, filepath: str) -> "OCMSubmission":
        with open(filepath, "r", encoding="utf-8") as fh:
            payload = json.load(fh)

        sub = cls()
        for cy in payload.get("cruise_years", []):
            year = cy["cruise_year"]
            cy_entry = CruiseYearEntry(cruise_year=year)
            for d in cy.get("dumps", []):
                dump_entry = DumpEntry(
                    dump=d["dump"],
                    sensor_dump_grades=dict(d.get("sensor_dump_grades", {})),
                    analyst_comments=d.get("analyst_comments", ""),
                )
                for cast, c in d.get("casts", {}).items():
                    dump_entry.casts[cast] = CastEntry(
                        cast=cast,
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

    def restrict_onto_preload_shell(self, preload_payload: dict) -> "OCMSubmission":
        """
        Used by Open. The opened file (self) only ever records DELTAS
        from the pre-loader's cast list: casts with nothing to say
        (no sensor_cast_grades, no depth_overrides, no comment) are
        never written to the output JSON (see to_json_payload), and
        read-only fields like ctd/start_date are never written at all,
        since they're sourced from the database, not authored by the PI.

        This means a saved file can never be treated as a complete,
        standalone source of dump/cast/depth structure - it must be
        replayed on top of a pre-loader shell to reconstitute the full
        cast list, CTD, start date, and (per the open design question
        above) each cast's baseline depth-range overrides from the
        database. This method keeps ONLY the years/dumps that actually
        exist in self (the opened file) - any other pre-loader year is
        dropped entirely, rather than kept present-but-empty, since it
        has nothing to do with the file the Project Leader actually
        asked to open.

        For a cast present in the opened file, the file's own
        sensor_cast_grades/depth_overrides/comment REPLACE the shell's
        baseline entirely (not merged) - the saved file is the PI's
        authoritative state for whatever it chose to record, including
        the baseline depth facts the shell would otherwise have
        supplied. This mirrors the original design's treatment of
        defective_sensors (an explicitly-saved empty/different state
        always wins over re-deriving from the database).
        """
        full_shell = OCMSubmission.new_from_preload(preload_payload)
        restricted = OCMSubmission()

        for year, cy in self.cruise_years.items():
            shell_cy = full_shell.cruise_years.get(year)
            if shell_cy is None:
                # Year isn't in the current pre-loader payload at all
                # (e.g. an older file from before this session's DB
                # snapshot). Keep the file's own data as-is rather than
                # silently dropping it.
                restricted.cruise_years[year] = cy
                continue

            restricted_cy = CruiseYearEntry(cruise_year=year)
            for dump, d in cy.dumps.items():
                shell_dump = shell_cy.dumps.get(dump)
                if shell_dump is None:
                    restricted_cy.dumps[dump] = d
                    continue

                target = DumpEntry(
                    dump=dump,
                    ctd=shell_dump.ctd,
                    start_date=shell_dump.start_date,
                    sensor_dump_grades=dict(d.sensor_dump_grades),
                    analyst_comments=d.analyst_comments,
                )
                # Every cast the shell knows about starts from the shell's
                # own baseline (DB-sourced depth facts); the opened file's
                # own cast entries then replace that baseline outright
                # wherever the file actually has something recorded for
                # that cast.
                for cast, shell_cast in shell_dump.casts.items():
                    if cast in d.casts:
                        target.casts[cast] = d.casts[cast]
                    else:
                        target.casts[cast] = shell_cast
                # A cast present in the file but no longer in the shell
                # (e.g. removed from the DB range) is kept as-is rather
                # than silently dropped.
                for cast, file_cast in d.casts.items():
                    if cast not in target.casts:
                        target.casts[cast] = file_cast

                restricted_cy.dumps[dump] = target

            restricted.cruise_years[year] = restricted_cy

        return restricted


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


def _good_id_from_preload_payload(preload_payload: dict) -> int:
    """The id whose data_quality_code is "0" (Good), read from the
    pre-loader JSON's data_quality_ids list (itself a live
    OC.tbl_data_quality query - see oc_m_preloader_service.py's
    _fetch_data_quality_table()). Raises ValueError if no such row is
    present - there is no safe assumed fallback for this."""
    for row in preload_payload.get("data_quality_ids", []):
        if row.get("code") == "0":
            return row["id"]
    raise ValueError(
        "No row with data_quality_code == '0' (Good) found in "
        "data_quality_ids - cannot determine the Good id."
    )


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

    graded_sensors and good_id should both come from the same pre-loader
    JSON the submission was built against - entry_window.py already
    holds that payload in memory and passes these through rather than
    this module hand-typing either.

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
