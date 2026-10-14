# `oc_m_data_quality_entry` — Architecture

Last updated: 2026-10-13, reflecting the single-file architecture pivot
and depth-range deletion work. Standalone PI-facing
app, separate repo from `dm_tools` (see "Repo location" below). Shares
vendored libraries and (optionally) a stylesheet with sibling apps, but
is deployed independently.

**If this document and the actual code disagree, trust the code.**
Version headers inside each file are the source of truth for what's
actually been built; this document is a map, not the territory.

## Repo location

```
File_Processing/                    <- parent folder (confirmed)
├── libs/                           <- vendored PyQt6 etc., SHARED across sibling apps
├── styles/
│   └── dm_styles.qss               <- shared stylesheet, optional (see app_settings.py)
└── oc_m_data_quality_entry/        <- this app's own files live here
    ├── main.py
    ├── entry_window.py
    ├── output_io.py
    ├── depth_strip_widget.py
    ├── sensor_row_widget.py
    ├── app_settings.py
    ├── recent_files.py
    ├── version.py
    └── data/
        ├── recent_files.json           <- auto-created at runtime
        ├── app_settings.json           <- auto-created at runtime
        └── oc_m_preload_sample.json    <- dev-default fixture, PyCharm no-arg launch only
```

`libs/` is referenced as one level up from this app's own folder
(`_APP_DIR.parent / "libs"`) in both `main.py` and
`depth_strip_widget.py`'s standalone test harness. **Not independently
verified this session**: the exact folder structure *above*
`File_Processing/` (e.g. whether it's the repo root or nested further).
Treat anything above `File_Processing/` in this diagram as unconfirmed.

`preload_model.py` **no longer exists** — confirmed deleted. It held
`DumpCastTableModel`/`QualityCodeDelegate`/`CommentDelegate` for the old
single-code-per-cast grid, fully superseded by the per-sensor/per-depth
redesign (see below). Safe to stop looking for it in any future file
listing.

## What this app does

OC_M is SOP 11: a Project Leader (PI) reviews CTD cast data already
loaded into `OC.tbl_oc_cast` (by `dm_tools`'s OC_D process) and assigns
data-quality grades. This app is the PI's own grading tool — it has
**no database connection and no network dependency at all**. It reads
one JSON file, lets the PI grade, and writes the same JSON structure
back out.

A separate, not-yet-built ingestion service (living in `dm_tools`,
outside this app entirely) will eventually read the PI's saved file and
write the real grades into `OC.tbl_oc_cast`. That service does not
exist yet as of this document.

## Architecture: single-file (current)

As of this iteration, there is **one JSON shape**, used both for what the
Data Manager's pre-loader (`dm_tools/services/oc_m_preloader_service.py`
— outside this app, not shown in the tree above) emits, and for what
the PI saves. The PI opens a file, grades it, and saves — overwriting
the original or choosing Save As — and the result is itself a complete,
re-openable file. There is no separate "shell" or "delta" concept.

This replaced an earlier two-file design (pre-loader snapshot + PI
delta, requiring delta-replay onto a fresh shell to reconstitute full
structure) that was pivoted away from mid-session after it caused a
real bug: `entry_window.py` kept cast readings in a separate raw payload
dict that could silently fall out of sync with the in-memory
`OCMSubmission`, leading to blank depth-strip graphs with no error. See
individual file version headers for the detailed changelog of that
pivot (`output_io.py` / `entry_window.py`, both `2026.10.13_01`).

## Files

### `main.py`
*(Not touched this session beyond the stylesheet-ownership change
already reflected in its own comments.)* Entry point. Parses
`--preload`/`--outdir` CLI args (used by the real `.bat`-file launch);
falls back to hard-coded dev-default paths for a bare PyCharm run.
Loads the pre-loader/submission JSON into a dict via
`_load_preload_json()`, then constructs `OCMEntryWindow(preload_payload,
outdir)` — note the constructor still takes an **already-parsed dict**,
not a filepath, since `main.py` loads the JSON itself before the window
exists.

### `entry_window.py` — Version `2026.10.13_04`
Main window. Owns the live `OCMSubmission` and the current cruise-year /
dump / cast selection. Builds `OCMSubmission` via `from_payload()` at
construction (not the old, now-removed `new_from_preload()`). Stores
`self._preload_payload` for exactly the payload-level (non-per-cast)
facts: `QualityLookup`, `graded_sensors`, and per-sensor
`ThresholdBounds` lookups — **not** for cast readings, which live
entirely on each `CastEntry` now.

Owns:
- Cruise-year/dump tree (left) and cast list (middle) — unchanged from
  the original design.
- Per-cast comment box (`CastEntry.comment`) — **added this session**;
  this is the field `validate_submission()` actually checks. Sits
  between the dump header (CTD/start date) and the sensor-row stack.
  Distinct from, and not to be confused with, the dump-level "Analyst's
  comments" box further down (`DumpEntry.analyst_comments`, explicitly
  *not* applied to the database, *not* checked by the validator).
- A stack of 9 `SensorRowWidget` instances, one per graded sensor,
  wrapped in a `QScrollArea` (safety net for small/high-DPI displays;
  the PI is expected to run this maximized on a 14–15" laptop minimum).
- Settings menu (stylesheet toggle: shared / custom / none — defaults
  to none/native-Qt on first-ever launch).
- Open / Save / Save As / Recent Files, exit confirmation, SOP/About
  dialogs — unchanged from the original design.

`_build_depth_points()` now reads `depths`/`readings` directly off the
current `CastEntry` — no more reaching into a separate raw payload dict
by year/dump/cast (that lookup, `_find_cast_payload()`, is gone; it was
the root cause of the pre-pivot sync bug described above).

### `output_io.py` — Version `2026.10.13_01`
No Qt dependency — reusable by the future ingestion service. Defines
the on-disk JSON shape and the grading logic:

- `DepthRangeOverride` — one sensor's grade for a depth range on one
  cast. `covers(depth)` is the only cascade-relevant method.
- `CastEntry` — `comment`, `depths`, `readings` (per-sensor lists,
  **added this session** — previously readings lived only in a raw
  payload dict, now they're part of this dataclass so there's a single
  source of truth), `sensor_cast_grades`, `depth_overrides`.
- `DumpEntry` — `sensor_dump_grades`, `analyst_comments`, `casts`.
  `resolved_cast_grade()` / `resolved_depth_grade()` implement the
  3-tier cascade: **depth-range override → cast-level override →
  dump-level override → Good** (the Good id is always caller-supplied,
  never hardcoded — see `_good_id_from_payload()`).
- `OCMSubmission` — `from_payload(dict)` is the one parse path (used
  for both a fresh pre-loader file and a reopened PI save — there's no
  longer a meaningful difference between the two at the file-shape
  level). `load(filepath)` is a thin wrapper around it.
  `to_json_payload()` emits the **full** structure, readings included,
  every cast always present (never omitted for having nothing graded)
  — this is what makes a saved file self-contained and re-openable
  without re-running the pre-loader.
- `validate_submission()` — one surviving rule (of an original three):
  a cast with any non-Good grade anywhere (cast-level or depth-level,
  any sensor) must have a non-empty `comment`. Never blocks Save; shown
  as an informational dialog after Save/Open.

**Removed this session** (not deprecated — checked into GitHub first,
per explicit decision, so recoverable there if ever needed):
`restrict_onto_preload_shell()`, the old `new_from_preload()`,
`_depth_overrides_from_preload_grades()`.

### `depth_strip_widget.py` — Version `2026.10.08_04`
*(Not modified this session — listed here because it was previously
missing from this document entirely, not because anything changed.)*
No Qt-independent logic lives here that output_io.py also needs; this
is a pure view component. Has NO knowledge of overrides or cascades —
it only paints already-resolved `ResolvedDepthPoint` values handed to
it via `set_data()`, and reports click-drag gestures back via the
`rangeSelected` signal. Also defines:
- `QUALITY_COLORS` — UI-only id→color map (no DB column backs this).
- `QualityLookup` — id→label and the Good-id, built once from the
  payload's `data_quality_ids` (a live `OC.tbl_data_quality` query done
  by the pre-loader, embedded in the JSON — never hardcoded here).
- `ThresholdBounds` — one sensor's mandatory/optional bounds, from the
  payload's `thresholds` list (a live `OC.tbl_threshold` query). `None`
  bounds are legitimately open-ended (e.g. a missing-signal sentinel)
  and are never drawn, never defaulted to a guessed number.
- Standalone test harness (`python depth_strip_widget.py`) with
  synthetic data — dev/review only, not imported by the real app.

Mandatory/optional threshold bands use two distinct hues (amber /
blue), not one hue at two opacities — the original same-hue approach
was confirmed visually indistinguishable against a dark background.

### `sensor_row_widget.py` — Version `2026.10.13_03`
*(Previously missing from this document entirely.)* One reusable
`QWidget` per sensor: dump-level grade buttons, cast-level grade
buttons, a resolved-value readout, and a collapsible
`DepthStripWidget` area for depth-range grading. Holds **no grading
data of its own** — it's a stateless view over a `SensorRowContext`
snapshot the caller (`entry_window.py`) builds fresh on every relevant
change, passed via `refresh()`.

Added this session:
- A depth-override **count badge** in the row header (e.g. "2 depth
  ranges") — the only always-visible indicator that a sensor has
  depth-range grading on the current cast, since the resolved-value
  label at the header level can never itself say "depth" (it answers a
  cast-level question, not a per-depth one). Clicking the badge expands
  the row.
- A visible **per-range list** under the depth strip, one row per
  existing override (`start–end: grade`), each with its own delete
  (✕) button — fixes re-graded/overlapping ranges silently
  accumulating dead entries with no way to remove them. Each row shows
  that override's **own** stored grade, not the resolved/winning grade
  for those depths (important when two overlapping entries exist for
  the same depths — they must show their own different grades, not
  both show whichever one currently wins the "last-applied wins"
  cascade).
- A **"Clear all ranges"** button (visible whenever any exist) for
  starting over on one sensor/cast in one action, with confirmation.

Signals: `dumpGradeChanged`, `castGradeChanged`, `depthRangeGraded`,
`depthRangeDeleted`, `allDepthRangesCleared` — every grading action is
emitted as a signal; the widget never mutates `output_io.py`'s
dataclasses directly.

### `app_settings.py`
*(Previously missing from this document entirely — added this
session, now complete.)* Small persisted-settings class (mirrors
`recent_files.py`'s restraint) holding the stylesheet preference
(shared / custom path / none). First-ever launch (no settings file yet)
defaults to **no stylesheet** — native Qt/OS theming — per explicit
developer instruction, so e.g. Windows dark mode shows through.

### `recent_files.py`
Unchanged. Not touched this session.

### `version.py`
Unchanged. Already a structured `VersionInfo` dataclass holding
`app_name` / `version` / `build_date`, used by the About dialog.

## Known open items (carried from the handoff doc, not yet verified this session)

- The not-yet-built **ingestion service** (in `dm_tools`) needs to
  expect the full single-file structure per cast now, not a delta — its
  design hasn't been started.
- `DEFECTIVE_SENSOR_COLUMNS`/`SENSOR_TO_DB_COLUMN` in
  `oc_m_preloader_service.py` (outside this app) — still a hand-typed
  6-of-9 sensor subset, deferred pending a possible future
  `OC.tbl_oc_sensors` consolidation table. Not touched this session.
- Cast-list is currently a plain `QTreeWidget`; an earlier prototype
  used a colored mini-strip overview per cast. Revisit if the PI misses
  the at-a-glance view.
- Per-range **comments** (distinct from the one comment-per-cast) were
  discussed this session as a real but unconfirmed need — e.g. grading
  one sensor Questionable for an unrelated reason, then a specific
  depth range Bad for a known cause, with no way to attach the second
  explanation separately. Deliberately **not built** — flagged to
  revisit with the PI only if this proves to be a recurring pain point
  during real testing, not a hypothetical one.
- Handoff-doc verification items (GitHub check-in of pre-pivot code,
  `preload_model.py` deletion) — **both confirmed done** this session.

## Known limitations (by design, not bugs)

- A depth-range override is scoped to one sensor on one specific cast
  only. Selecting the same depth range on a different sensor, or
  viewing a different cast, has no effect on it.
- The per-cast comment is a single free-text field shared by all 9
  sensors and all granularities (cast-level and depth-level alike) —
  confirmed sufficient directly with the PI; see "Per-range comments"
  above for the one open question about this.
