"""
output_io.py
OC_M Project Leader app — output file I/O and validation.
Build: 4

Defines the on-disk shape of the PI's saved OC_M submission (the file
handed back to the Data Manager for ingestion) and the logic to:
    - resolve each cast's effective quality code / comment
      (per-cast override wins; falls back to the dump-level default)
    - flag problems that must block ingestion on the Data Manager's
      side, without ever blocking the PI's own Save:
        1. cast has no resolved quality code at all
        2. resolved code is '0' (Good) but has a non-empty comment
        3. resolved code is non-'0' but has an empty comment
    - save / load the submission JSON

This module has no Qt dependency, so it can be unit tested and reused
verbatim by the Data Manager's ingestion service later.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime

GOOD_CODE = "0"


@dataclass
class CastEntry:
    cast: str
    quality_code: str | None = None   # None = no override; inherits dump default
    comment: str | None = None        # None = no override; inherits dump default


@dataclass
class DumpEntry:
    dump: str
    ctd: str | None = None
    start_date: str | None = None
    defective_sensors: list[str] = field(default_factory=list)
    default_quality_code: str | None = None
    default_comment: str | None = None
    analyst_comments: str = ""          # free-text; NOT applied to the database
    casts: dict[str, CastEntry] = field(default_factory=dict)  # cast -> CastEntry

    def resolved(self, cast: str) -> tuple[str | None, str | None]:
        """Return (effective_code, effective_comment) for one cast."""
        entry = self.casts.get(cast)
        code = (entry.quality_code if entry and entry.quality_code else None) or self.default_quality_code
        comment = (entry.comment if entry and entry.comment else None) or self.default_comment
        return code, comment


@dataclass
class CruiseYearEntry:
    cruise_year: str
    dumps: dict[str, DumpEntry] = field(default_factory=dict)  # dump -> DumpEntry


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
        pre-populated with whatever grades already exist in the database
        (a previously-graded year comes in fully populated; a fresh
        survey year comes in ungraded, since data_quality is NULL until
        an OC_M has actually been applied)."""
        sub = cls()
        for cy in preload_payload.get("cruise_years", []):
            year = cy["cruise_year"]
            cy_entry = CruiseYearEntry(cruise_year=year)
            for d in cy.get("dumps", []):
                dump_entry = DumpEntry(
                    dump=d["dump"],
                    ctd=d.get("ctd"),
                    start_date=d.get("start_date"),
                    defective_sensors=list(d.get("defective_sensors", [])),
                )
                for cast in d.get("casts", []):
                    dump_entry.casts[cast] = CastEntry(cast=cast)
                for co in d.get("cast_overrides", []):
                    cast = co["cast"]
                    if cast not in dump_entry.casts:
                        dump_entry.casts[cast] = CastEntry(cast=cast)
                    dump_entry.casts[cast].quality_code = co.get("quality_code")
                    dump_entry.casts[cast].comment = co.get("comment")
                cy_entry.dumps[d["dump"]] = dump_entry
            sub.cruise_years[year] = cy_entry
        return sub

    # ------------------------------------------------------------------
    def to_json_payload(self) -> dict:
        cruise_years_out = []
        for year, cy in sorted(self.cruise_years.items()):
            dumps_out = []
            for dump, d in sorted(cy.dumps.items()):
                cast_overrides = []
                for cast, c in sorted(d.casts.items()):
                    if c.quality_code or c.comment:
                        cast_overrides.append({
                            "cast": cast,
                            "quality_code": c.quality_code,
                            "comment": c.comment,
                        })
                dumps_out.append({
                    "dump": dump,
                    "defective_sensors": list(d.defective_sensors),
                    "default_quality_code": d.default_quality_code,
                    "default_comment": d.default_comment,
                    "analyst_comments": d.analyst_comments,
                    "cast_overrides": cast_overrides,
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
                    defective_sensors=list(d.get("defective_sensors", [])),
                    default_quality_code=d.get("default_quality_code"),
                    default_comment=d.get("default_comment"),
                    analyst_comments=d.get("analyst_comments", ""),
                )
                for co in d.get("cast_overrides", []):
                    dump_entry.casts[co["cast"]] = CastEntry(
                        cast=co["cast"],
                        quality_code=co.get("quality_code"),
                        comment=co.get("comment"),
                    )
                cy_entry.dumps[d["dump"]] = dump_entry
            sub.cruise_years[year] = cy_entry
        return sub

    def merge_onto_preload_shell(self, preload_payload: dict) -> "OCMSubmission":
        """
        DEPRECATED for use by Open - kept for a possible future "refresh
        my in-progress save against the latest snapshot of the SAME
        scope" action, which is a different operation from Open.

        Builds a shell containing EVERY year in preload_payload (not just
        the ones in self), so it is only correct when self and
        preload_payload are understood to cover the same intended scope -
        e.g. re-syncing your own prior save to pick up newly-added casts.
        It is NOT correct for opening an unrelated, differently-scoped
        file, since every pre-loader year absent from that file would
        still appear, empty - see restrict_onto_preload_shell() instead.
        """
        shell = OCMSubmission.new_from_preload(preload_payload)
        for year, cy in self.cruise_years.items():
            if year not in shell.cruise_years:
                continue
            for dump, d in cy.dumps.items():
                if dump not in shell.cruise_years[year].dumps:
                    continue
                target = shell.cruise_years[year].dumps[dump]
                target.defective_sensors = list(d.defective_sensors)
                target.default_quality_code = d.default_quality_code
                target.default_comment = d.default_comment
                target.analyst_comments = d.analyst_comments
                for cast, c in d.casts.items():
                    if cast in target.casts:
                        target.casts[cast].quality_code = c.quality_code
                        target.casts[cast].comment = c.comment
        return shell

    def restrict_onto_preload_shell(self, preload_payload: dict) -> "OCMSubmission":
        """
        Used by Open. The opened file (self) only ever records DELTAS
        from the pre-loader's cast list: casts with no override at all
        are never written to the output JSON (see to_json_payload), and
        read-only fields like ctd/start_date/full cast lists are never
        written at all, since they're sourced from the database, not
        authored by the PI.

        This means a saved file can never be treated as a complete,
        standalone source of dump/cast structure - it must be replayed
        on top of a pre-loader shell to reconstitute the full grid, CTD,
        and start date. Unlike merge_onto_preload_shell, this method
        keeps ONLY the years/dumps that actually exist in self (the
        opened file) - any other pre-loader year is dropped entirely,
        rather than kept present-but-empty, since it has nothing to do
        with the file the Project Leader actually asked to open.
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

                # Start from the shell (full cast list, ctd, start_date,
                # any DB-sourced defective_sensors/grades from the
                # ORIGINAL pre-loader snapshot), then let the opened
                # file's own fields win outright wherever the file
                # represents a completed round of the PI's editing.
                # defective_sensors in particular must never fall back to
                # the shell once a save exists: in the real workflow, a
                # saved file IS the PI's authoritative current state for
                # its own scope, never re-queried mid-cycle, so an
                # explicitly emptied list means "PI unchecked this," not
                # "nothing was ever recorded here."
                target = DumpEntry(
                    dump=dump,
                    ctd=shell_dump.ctd,
                    start_date=shell_dump.start_date,
                    defective_sensors=list(d.defective_sensors),
                    default_quality_code=d.default_quality_code,
                    default_comment=d.default_comment,
                    analyst_comments=d.analyst_comments,
                    casts={cast: CastEntry(cast=cast, quality_code=c.quality_code, comment=c.comment)
                           for cast, c in shell_dump.casts.items()},
                )
                # Overlay the opened file's own per-cast overrides on top
                # of whatever the shell already had (e.g. DB-sourced
                # grades), so the file's explicit choices win.
                for cast, c in d.casts.items():
                    if cast not in target.casts:
                        target.casts[cast] = CastEntry(cast=cast)
                    if c.quality_code:
                        target.casts[cast].quality_code = c.quality_code
                    if c.comment:
                        target.casts[cast].comment = c.comment

                restricted_cy.dumps[dump] = target

            restricted.cruise_years[year] = restricted_cy

        return restricted


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class CastProblem:
    cruise_year: str
    dump: str
    cast: str
    kind: str    # "ungraded" | "good_with_comment" | "missing_comment"
    detail: str


def validate_submission(sub: OCMSubmission) -> list[CastProblem]:
    """
    Never blocks Save. Returns a flat list of problems for display
    (dialog + grid highlighting). The Data Manager's ingestion service
    re-runs equivalent checks as hard mandatory-error gates.
    """
    problems: list[CastProblem] = []

    for year, cy in sorted(sub.cruise_years.items()):
        for dump, d in sorted(cy.dumps.items()):
            for cast, _ in sorted(d.casts.items()):
                code, comment = d.resolved(cast)
                comment = (comment or "").strip()

                if not code:
                    problems.append(CastProblem(
                        year, dump, cast, "ungraded",
                        f"Cast {cast} (dump {dump}, {year}) has no quality code "
                        "(no dump default and no per-cast override)."
                    ))
                    continue

                if code == GOOD_CODE and comment:
                    problems.append(CastProblem(
                        year, dump, cast, "good_with_comment",
                        f"Cast {cast} (dump {dump}, {year}) is marked Good but has "
                        "a comment. Comments should not be recorded for Good casts."
                    ))
                elif code != GOOD_CODE and not comment:
                    problems.append(CastProblem(
                        year, dump, cast, "missing_comment",
                        f"Cast {cast} (dump {dump}, {year}) has quality code {code} "
                        "but no comment. Non-Good casts require an explanatory comment."
                    ))

    return problems
