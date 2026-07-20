# geomag-model-explorer — project plan

*Browser-based interactive 3D visualization of Earth's geomagnetic field.*

**Status: v2.12 shipped, merged and published 2026-07-15** (the v2 studies
generation — v2.3 through v2.12 — is complete and archived in
[`HISTORY.md`](./HISTORY.md); the v1 plan and the v2.1/v2.2 governance phases
are earlier sections there). This file describes the *current* state and what
is genuinely live. Per RULES §8 it is refreshed (and the old generation
archived) whenever it drifts into describing history rather than current
state.

## 1. What exists

Geomagnetic field models served by VirES, **evaluated via viresclient only**,
rendered as colormapped (optionally relief-displaced) shells on a three.js
globe. Study selection is two dropdowns: a primary **Field to explore**
(All / Core / Crust / Ionosphere / Magnetosphere — per-source views over the
same globe) and a secondary **Model** that greys out, with the reason, where
the chosen field has no data. The Swarm Comprehensive Inversion chain
(MCO/MLI/MIO/MMA_SHA_2C) is the primary four-field family; **every other
grid-evaluable VirES model** rides as a single-field family (CHAOS, IGRF
5-yearly 1900–2025, MCO/MLI/MIO_SHA_2D, MMA_SHA_2F, LCS-1, MF7; CHAOS-MIO,
AMPS and MLI_SHA_2E deliberately unevaluated, greyed with the reason —
probe: `docs/v211_model_probe.json`). An ⓘ modal (flag `modelinfo`)
documents the served model behind every on-screen layer. Core offers a
B ↔ dB/dt secular-variation toggle; Ionosphere is the seasonal
(fixed-12:00-UT, pose-held) series.

The view: field toggles summed on the GPU, component picker (Northward /
Eastward / Upward / Intensity), altitude/depth shell slider (CMB → mantle
steps → surface → the unified 0–1500 km ladder), colorbar with scale lock
(`vmax=` in permalinks), any-day date picker with on-demand fetch +
permanent cache, bottom-docked time slider (15-min steps, 97/day) with
playback, hover readout (geographic under any frame), day/night **sunlight**
shading (soft terminator, night floor 0.55), **relief** displacement
(hillshaded, sun-lit when both flags are on), and an **ECEF | ECI**
reference-frame switch (mean-solar pose about +Y; the globe spins under a
world-fixed sun). Defaults (v2.12, landing-view tune 2026-07-15): all four
fields + sunlight + relief on, shell h500, component Up, **boot at 08:00 UT**
— ~3/4 of the landing disc lit, terminator on the Atlantic limb, Sq blob on
screen. Permalink state lives in the URL hash (stability contract: unknown
keys ignored, absent key = default); deploy-time feature flags
(`features.json` → `/api/features`) gate every post-v1 module.

```
fetch.py   the ONLY module that talks to VirES (uv --extra fetch)
             → data/raw/*.npz + data/MANIFEST.toml (provenance)
export.py  npz → quantized int16 tiles web/data/<field>/<shell>/<day>/tNN.i16
             + web/data/manifest.json (atomic publish; per-day p99 ranges)
serve.py   starlette on :8212 — static + tiles + day-fetch job API
             (GET /api/days, POST /api/days/<date>; single-job queue)
web/       no-build frontend: ES modules + importmap, three.js vendored
             main.js · globe.js · shaders.js · dataset.js · ui.js
```

Key parameters (rationale in HISTORY.md): tiles are int16 NEC triples,
decoded to RGBA16F textures; storage `qrange` is decoupled from display
`vmax`; colorbar range = sum of enabled fields' per-shell p99 (manifest,
per day); MIO at 2°, MMA at 2°, MCO/MLI at 1°; ~320 MB of tiles per cached
day. Deploy: systemd `--user` unit `geomag-model-explorer-web.service`
(:8212, its own data dir via `GEOMAG_MODEL_EXPLORER_DATA`), portal prefix
`/foundry/geomag-model-explorer/`, redeploy = restart; branch previews on
the Heimdall :8300 portal serve the checkout's exported data via
`.heimdall.toml` data_mounts. Published via Heimdall `mirror` to
`Swarm-DISC/geomag-model-explorer` — merging to `main` publishes.

## 2. Live operational concerns

**Efficiency pass (branch `efficiency`, 2026-07-16)** — measured review in
[`docs/efficiency-review.md`](./docs/efficiency-review.md) (footprint, 4c/8GB
capacity model, per-source sampling analysis vs each model's SH degree and
temporal parameterisation). Landed in this pass:

- **Serving** — tiles now get `.i16.gz` siblings at export (level 9, mtime=0)
  and serve.py's `TileFiles` sends them with `Content-Encoding: gzip` +
  `Cache-Control: immutable` (tile paths are content-immutable; manifest.json
  is `no-cache`). This is ladder rung 3 minus bundling: measured, it lifts the
  playback ceiling from ~30 to ~90–100 concurrent viewers on a 4-core host —
  per-request gzip on the single event loop was the binding constraint, not
  bandwidth or RAM. Fallback gzip runs at level 6 (+47% throughput, +0.04%
  bytes vs the old level-9 default). The manifest parse is cached on stat.
  **One-time activation on the primary checkout after merge** (one block,
  before any new day-fetch POST): re-export every cached day and series from
  raw (`export.py --day <d>` / `--series <id>` — no VirES contact; this
  applies the v5 per-shell qranges below), then
  `uv run python export.py --compress-existing` for anything untouched.
- **Client** — tile cache is byte-budgeted (128 MB GPU) instead of 64 entries,
  so a full-day playback loop (194 tiles) no longer evicts itself each pass;
  slider drags coalesce to one texture pass per frame and abort superseded
  in-flight tile fetches (one hard scrubber could previously saturate the
  server's event loop for every viewer).
- **Raw store** — new raw npz are float32 + deflate (~12× smaller: a core
  bundle 34.5 MB → ~2.9 MB; a new day ~1.3 GB → ~0.11 GB). float32's ~6e-8
  relative error sits 3 orders under the int16 tile quantization. Existing
  float64 raw stays valid (np.load reads both); no retro-pass — MANIFEST.toml
  sha256 provenance of already-fetched snapshots is untouched.
- **Per-shell quantization ranges (manifest v5)** — one CMB-sized qrange
  (3e6 nT) quantized the surface core field to 91.6 nT steps: stored values
  sat flat for years, then jumped one int16 step (plainly visible in the
  timeline charts; ±46 nT in the hover readout). Core/core-sv now carry
  per-shell qranges sized from measured per-shell maxima (~2x headroom):
  surface step 3.66 nT (core) / 0.015 nT/yr (core-sv). Additive manifest
  key (`qrange_nT_shells`); pre-v5 records decode by their scalar exactly
  as quantized. Tile URLs carry a `?v=<qrange-grid>` cache-bust so the
  immutable cache can never descale stale bytes.
- **Timeline exactness** (globe may approximate, charts must not): chart
  assembly snaps the pin to the nearest node of the coarsest charted grid —
  every plotted value is an exact stored evaluation (grids nest: 2° nodes ⊂
  1° ⊂ 0.5°), with the snapped coordinates shown in the panel status line.

Carried forward — still open, not yet decisions:

- **Disk policy** (v1 §9.3): cached days accumulate forever — tiles
  ~320 MB/day; raw npz now ~0.11 GB/day compressed (was ~1.3 GB). Current
  cache: 2.0 GB tiles, 8.2 GB raw (pre-compression corpus; ~52 GB free —
  the v2.13 quarterly-core addendum adds only ~2.6 GB raw + ~0.7 GB tiles
  per data root, ~0.22 GB raw once refetched compressed). Rung 1 (drop
  `data/raw/` after export) was considered with v2.7 and **deferred
  2026-06-12**: raw retains re-export flexibility (qrange/format changes
  without refetching) and the disk has headroom; the float32+deflate change
  extends that headroom ~12×. Policy (efficiency review): tiles stay
  accumulate-forever (they are the product); if disk pressure returns, prune
  *raw only* (it is regenerable per §4 provenance) before reaching for rung 2.
  The scaling ladder, in order, architecture unchanged until the last rung:
  (1) drop `data/raw/` after export; (2) `GEOMAG_MODEL_EXPLORER_DATA` env
  var → big disk; (3) bundle frames per field·shell·day, precompressed —
  **the precompression half landed 2026-07-16**; (4) int8 for MIO/MMA —
  **deprioritized 2026-07-16**: the review's sampling analysis dominates it
  losslessly (see docs/efficiency-review.md Table A) and int8 at fixed qrange
  is ~16 colormap steps of banding; (5) only then a blob store. A future
  Storms study (IDEAS §9.1 `window` kind / §9.4 — demoted from the phase
  ladder 2026-06-12) would add deliberate *multi-day* caching on top.
  Materialized series sit at ~10–100 MB each (mio-seasonal-2020 is now
  ~84 MB on the full ladder).
- **Radial interpolation between shells** (v1 §9.6): deferred — physically
  honest continuation needs per-degree (a/r)^(n+2), i.e. client-side SH
  evaluation. Offer later as explicitly approximate, or never.
- **Model validity ends 2023-11-30** at last check (2026-06-12): re-run
  `fetch.py --validity` periodically (or check at serve start) so new CI
  product releases extend the date picker — the May/October 2024 G5 storms
  are the prize waiting behind this (IDEAS §6.3).
- **Portal/Ansible clobber risk** (pre-existing, all foundry projects): the
  internal portal role's `foundry-stub.html.j2` is stale (knows only
  vizlab) and written with `force: true` — an Ansible re-run would drop the
  geomag-model-explorer card from the live foundry index. Fix belongs in the
  internal portal repo.
- **Day-fetch endpoint is a write surface**: single-job queue + validity
  validation suffice on the trusted portal network; revisit if exposed wider.

## 3. Next phases

Three phases are recorded below: v2.13 and v2.14 (both merged to `main`),
and v2.15 (branch `loading-states`).
[`IDEAS.md`](./IDEAS.md) is the candidate backlog; items are promoted
into numbered phases here only on human approval, with the decision date
recorded.

### Phase v2.13 — Timeline viewer (time series at a pinned location)

**Approved 2026-07-15** (direct user request, so the RULES §8 human-review
gate is satisfied by construction; the nearest prior thinking was IDEAS §4.5's
pinned-probe sparkline). Branch: `timeline-viewer` — **implemented and
browser-verified 2026-07-15**, since merged to `main`.

**Why.** The globe answers *where*; nothing answers *when* at a fixed place.
A pinned point plus three stacked component charts over the active timeline
turns every already-exported day and series into a virtual-observatory
record — assembled from local tiles only, no new VirES traffic.

**Shape.** Feature flag `timeseries` → `web/features/timeseries.js`. A
**Globe | Time series | Combined** view toggle in the header (Combined splits
over/under: globe above, charts below, shared timebar). Pin a point by
clicking the globe (click ≠ drag) or typing coordinates — geocentric
lat/lon/radius or WGS84 geodetic lat/lon/height (`web/geodesy.js`, new pure
module). Three chart panels: shared x = the active timeline's epochs (UT),
independent y per component, crosshair-synced, one x axis aligned across
the stack (labels on the bottom panel; no drag-zoom — see the post-addendum
fixes), a current-time cursor tracking `state.pos`, click-to-seek. A convention toggle relabels and
re-signs the stored NEC sums: **N/E/Up** (N, E, −C) | **R/θ/φ** (−C, −N, E) |
**NEC** (N, E, C). Charts are drawn with **uPlot 1.6.32, vendored** into
`web/vendor/` (ESM + css, importmap key `uplot`, provenance in
`web/vendor/VERSION`) — the RULES §6 no-build/no-CDN pattern, decision
recorded here.

**Contract & invariants.**
- The chart plots exactly what the globe shows: the sum over
  enabled-and-available fields (`hooks.frameSource`) at `state.shell`,
  bilinear at the pin — same tile URLs (`tileURL`/`fieldDay`), same qrange
  descale, full int16 precision, for every epoch of the active timeline.
- No network beyond the app's own `./data/` tiles (RULES §3 untouched).
- Coordinates: native = geocentric (that is what the tiles are). Geodetic
  input converts via WGS84 before sampling; plotted components remain
  geocentric-NEC relabelings (no geodetic NED rotation).
- The pinned point rides the globe's shell: a typed radius/height snaps to
  the nearest available shell and moves the existing shell slider, so the
  globe, hover readout and charts can never disagree. The snapped shell (and
  its geodetic equivalent) is echoed back; geocentric is authoritative.
- Series assembly is texture-LRU-neutral (`dataset.cacheSize()` unchanged),
  cancels stale runs (AbortController + sequence guard), caches results per
  (day|shell|fields|point), renders missing tiles as gaps, and samples
  non-stepped fields once per assembly. Within a day, core/crust plot flat —
  that is the data, not a bug.
- Permalink keys: `view=` (≠ globe), `pt=<lat>,<lon>` (geocentric, 2 dp),
  `ptc=` (≠ neu). Absent = default, unknown values ignored (the existing
  stability contract); a flag-off deploy never writes them.
- Flag off ⇒ byte-identical v2.12 behavior (no toggle, no panel, no keys).

**Verification.** `tests/test_timeseries_browser.py` (stub-server pattern,
zero pageerror/console.error, incl. a flag-off port): view toggle, click-vs-
drag pinning + marker, geodetic snap, charts-match-`lookup()`, convention
sign flips, LRU neutrality + cancellation, permalink round-trip. Then a
real-data pass on the Heimdall :8300 branch preview (diurnal Sq at a
mid-latitude pin; `core-secular` and `mio-seasonal-2020` for multi-epoch
variation) before merge.

*Verified 2026-07-15*: 10/10 new browser tests green (22 s, :8224/:8225);
fast suites 54 green; permalink suite 5 green after fixing a stale
pre-v2.12 expectation (garbage-hash default pos is 32 since the boot-time
tune — it fails on `main` too). Real-data preview pass: Niemegk-ish surface
pin shows the Sq wiggle (N-range 11 nT, mean N 18.6 μT) over flat
core/crust; `core-secular` charts 10 yearly nT/yr epochs at the CMB;
`mio-seasonal-2020` charts 53 weekly epochs; linked x-zoom, click-to-seek
and geodetic snapping all exercised (screenshots
`tests/artifacts/live_v213_*.png`). One layout fix landed en route: the
shared x axis is drawn only on the bottom panel, or combined mode collapses
the plot areas to zero height. Host finding for MAINTENANCE: every
pre-v2.13 browser suite's fixed ports (8213–8223) are now occupied by
unrelated fleet services, so those suites silently probe foreign servers
and time out — port allocation needs a rework (the new suite sits on the
free 8224/8225).

*Updated onto the v2.14 `main`, 2026-07-16*: merged `main` into this branch
(sole conflict: this file's §3 — both phase records kept) and landed the
v2.14-prescribed follow-up — `#globe` and `#series-panel` now live inside a
static `#viewport` (position anchor for the ⓘ overlay), so the button
survives the globe hiding in series view; the panel appends into `#viewport`
and the combined split is 42% of the view pane. Suite repairs along the way,
none v2.13-specific: sun and relief moved off the dead 8213–8223 ports to
8234–8237 and day-pick to 8238 (the host finding above — all three failed on
every branch); day-pick additionally needed the shared foundry token wired in
(stub-server secret + pre-cached localStorage, the deployed shape) — the
REVIEW #6 fail-closed gate had silently broken it while its port was dead,
on `main` too (confirmed against a clean `main` worktree). Full suite green
post-update: 128 passed, 1 skipped. A fresh real-data :8300 preview pass on
the updated branch remains the gate before this branch merges to `main`.

**Scope addendum (approved 2026-07-16, direct user request).** Five pre-merge
refinements to the charts and the Core timeline:

1. The per-chart uPlot legends go away; the component name moves to a rotated
   y-axis label (canvas-drawn in the axis stroke colour — `series[1].label`
   stays, now purely a test seam) and reads as a rate (e.g. `dB_θ/dt`,
   `nT/yr`) whenever the Core B ↔ dB/dt toggle has SV displayed.
2. Span-adaptive single-line UTC x-tick labels: years at year ticks, month
   names carrying the year at January and the first visible tick, day labels
   likewise, HH:MM with the ISO date at the first tick on sub-day spans. The
   axis stays 30 px — two-line labels rejected for the combined-mode vertical
   budget.
3. Hover values move into a compact in-plot readout per chart; one
   bottom-centre time readout below the lowest panel shows the crosshair
   instant, falling back to the transport instant (gold, matching the time
   cursor) when the pointer leaves the charts.
4. **Core sampling densifies — quarterly at 2°**: `core-secular`,
   `core-secular@chaos` and `core-secular@mco2d` switch from yearly/1° to
   3-month epochs on a 2° grid, via a new `SeriesSpec.step_months` and a
   per-series `grid` override (same pattern as `qrange`);
   `core-secular@igrf` stays 5-yearly at 1° (piecewise-linear generations —
   denser epochs would only interpolate). The addendum's first cut was
   monthly at 1° — a real CI fetch verified end-to-end, but the fleet-wide
   fetch clocked ~7 h and the user revised the resolution down the same
   day (2° spatial, once per 3 months). And (user directive, same day)
   `core-secular@chaos` expands to CHAOS-Core's own availability —
   1997-09-01..2023-06-01 — since the Core component is valid far wider
   (1997-02-07..2027-02-06) than the rest of CHAOS; 1997-09-01 is the
   first first-of-month epoch with a whole ±6-mo SV window. Epoch counts:
   37 (CI) / 104 (@chaos) / 13 (@mco2d).
5. Data notes for (4): series raw npz are step-index-keyed (`t{step:03d}`)
   and grid-unaware, so a cadence or grid change invalidates
   `data/raw/series/<id>` wholesale — delete before re-fetch. Cost ~462
   stacked 2° evals (tens of minutes, resumable), ~2.6 GB raw + ~0.7 GB
   tiles per data root — no disk pressure. Old `e=` permalinks survive
   (`nearestEpoch` is instant-based). Pre-merge verification runs against a
   scratch data root (`GEOMAG_MODEL_EXPLORER_DATA`) + local serve on :8240,
   leaving the worktree's symlinked shared data untouched. Post-merge ops,
   per series, in the primary checkout AND the :8212 service root
   (`~/.local/share/geomag-model-explorer-deploy`): delete stale
   `data/raw/series/<id>`, hardlink-copy the scratch raw in, no-op
   `fetch.py --series` (upserts MANIFEST.toml provenance) +
   `export.py --series`, commit MANIFEST.toml, restart the service.

*Addendum verified 2026-07-16.* Suites: 5 new/updated browser tests
(chart chrome, adaptive x labels incl. the year-rollover rule, readouts,
37-epoch quarterly timeline) — timeseries 13, families 18 green on the
quarterly 2° stubs; fetch/export units 55 green (incl. the grid-override
and step_months epoch tests). Real-data passes: (a) :8300 branch preview,
16/16 scripted chrome checks + the weekly `mio-seasonal-2020` month-label
look, zero console errors (`live_v213_addendum_*.png`); (b) a local
scratch-root server on :8240 (`GEOMAG_MODEL_EXPLORER_DATA`, worktree rules
untouched) with freshly fetched quarterly 2° data — 11/11 checks per
family: CI 37 epochs, @chaos 104 (1997–2023, year ticks every 2 years),
@mco2d 13 (`live_v213_quarterly_*.png`). Two real defects were caught by
these passes and fixed en route: series tiles were sized from
`manifest.fields` everywhere (2° tiles threw "49413 values, expected
196023") — fixed by the per-series manifest `grid` map +
`dataset.storageGrid()`; and quarter-spaced ticks rolled the year
silently past Dec → Mar — fixed by the year-on-rollover rule. The whole
quarterly fetch ran 46 min against VirES (vs ~7 h projected for the
monthly/1° first cut, which was verified end-to-end and then superseded).
Full suite: 131 passed, 1 skipped; `test_serve_api::test_queue_orders_
and_reports` flakes under heavy fetch load only (passes on a quiet box —
pre-existing timing sensitivity, not a v2.13 change). Post-merge ops as
recorded in the addendum: propagate the scratch raw (hardlink) + export
into the primary checkout and the :8212 service root, commit
MANIFEST.toml, restart, then `rm -rf /var/tmp/geomag-core-monthly`.

*Post-addendum chart fixes (2026-07-16, direct user request).* Two panel
fixes before merge. (1) The three panels now share one aligned x grid:
uPlot auto-pads the right edge by 25 px only on panels whose bottom axis
has nonzero *size* (`calcPlotRect` counts a side only when
`_size + labelSize > 0`), so the lone labeled bottom panel sat 25 px
narrower — its data and gridlines shifted against the panels above. The
x axis (with its vertical gridlines) is now drawn on all three panels —
labels and tick marks bottom-only, size 0 above, so the combined-mode
flex calibration holds — and the right padding is pinned to the same 25
on all three, since the size-0 axes still don't count toward uPlot's
auto-padding. (2) Drag-select x-zoom is disabled (`cursor.drag.x =
false`) — area-select was a user cut; programmatic `setScale` stays as
the tests' span seam, still propagated across panels by `syncXScale`.
Verified: timeseries 15 green (panel alignment — equal bbox, identical
splits, bottom-only labels — and no-zoom-on-drag added); full suite 135
passed, 1 skipped — the serve_api queue test's one failure was tmpfs
ENOSPC (`/tmp` 4.9G; pytest keeps the last 3 ~1 GB sandbox generations,
two of them stale from a killed session — a second flake cause besides
load, cleaned and green on rerun). Scripted :8300 preview pass 7/7 on
real data (`live_v213_fixes_*.png`; code hot-copied into the running
preview container — a rebuild would drop its fetched data).

**Out of scope** (this phase): per-field traces, radial interpolation between
shells, geodetic NED component rotation, CSV export, multi-day stitching,
plotting at radii off the shell ladder, pausing the hidden globe render.

---

### Phase v2.14 — Interface reorganization (three control layers)

**Approved 2026-07-15** (direct user request; RULES §8 gate satisfied by
construction). Branch: `interface-improve`, from `main`/v2.12 by explicit
user decision — NOT stacked on the unmerged `timeline-viewer`. **Merged to
`main` 2026-07-16**; this branch now builds on it.

**Why.** The header grew one control at a time (v2.9–v2.12): two dropdowns,
four checkbox/radio groups and three display toggles share two
undifferentiated rows, and the primary choice — what to explore — is a
dropdown whose options grey out, so the top-level action can be
un-clickable. Reorganize into three intent layers without changing what any
control does.

**Shape.**
- Layer 1 (header row 1) — *what to explore*: "Explore category" as an
  always-enabled pill group (All / Core / Crust / Ionosphere / Magnetosphere;
  same tab ids) + "Model" (unchanged `<select>`; unavailable models stay
  greyed with the reason). Clicking a category the current model cannot
  serve auto-switches the model (the existing `switchField` fallback) and
  says so: the Model select flashes and a transient `aria-live` note names
  the switch ("Model → Swarm CI — IGRF has no Ionosphere data").
- Layer 2 (header row 2) — *what is in the sum*: "Fields to include"
  checkboxes ("Field to show" + B ↔ dB/dt swap on Core, as today), then a
  vertical separator, then "Visualisation mode" (today's series select,
  relabeled and labeled — entries unchanged this phase; an Ionosphere
  Diurnal|Seasonal pair is the intended future occupant) + the pinned date
  + fetch chip.
- Layer 3 — *how it is drawn*: a floating `#vis-options` box overlaid
  top-left of the globe, annotated in two sections split by a divider —
  "Magnetic field component:" (N/E/Up/Intensity) and "Display options:"
  (Sunlight, Relief, ECEF (earth-fixed) | ECI (inertial)). The hover
  readout moves to top-center (top corners are free: shell slider and
  colorbar are vertically centered).
- The ⓘ button becomes a hard-to-miss 4.4rem overlay at the globe's
  top-right (2.6rem on short windows, clearing the colorbar); the modal
  designates each layer's exact VirES expression as a copyable `<code>`
  line and links the viresclient model catalogue
  (readthedocs `available_parameters.html#models`).
  (Sizes/annotations refined per user review of the live preview,
  2026-07-15.)
- The header and the vis-options box are collapsible (static `.chrome-toggle`
  buttons, wired in ui.js — chrome state only, never in the permalink);
  viewports ≤ 640 px wide boot collapsed, so phones land on a slim title
  bar + ⚙ chip over a full globe. The default camera pulls back to
  (0, 0.3, 3.3) — the whole disc lands centred (the v2.12 pose cropped the
  bottom) — and portrait panes scale the pull-back by 1/aspect at boot;
  explicit cam= permalinks override both. A ⌂ reset chip in the header row,
  just before "Explore category" (kept visible in the collapsed strip, so
  phones retain one-tap reset), resets the WHOLE session to the boot
  defaults — every selection, overlay and the camera — by wiping the
  permalink hash and reloading: the boot path is the definition of the
  default state, so nothing can drift as features grow.
  (Added per user review, 2026-07-15.)
- Structural: header and vis box become explicit static containers/slots in
  index.html; features append into named slots — the `.after()` anchor
  chains (title←field-bar←family-bar←ⓘ; component-radios←relief←sun←frame,
  order = reverse module order) are retired.
- Pills are restyled real radio inputs (new `.pill-radio`, category group
  only — `.comp-radio` groups keep their look by explicit user decision
  2026-07-15; same decision scoped Visualisation to relabel-only).

**Contract & invariants.**
- Zero permalink changes: no key added or removed; every pre-v2.14 link
  restores identically. No new feature flag (the reorg is chrome for
  existing flagged features); flag-off shapes degrade as today — empty
  slots collapse invisibly.
- Category pills are never disabled; the Model select remains the honest
  side (greyed + reason). A model auto-switch is always announced, never
  silent.
- `state.*` keys and all control ids stable except: `#field-select` /
  `#field-bar` are retired → `#field-pills` group + `#field-<tabid>` radios
  (documented breaking id).
- Merge-friendliness with `timeline-viewer`: zero diff on permalink.js /
  ui.js / dataset.js / web/sun.js; style.css edits kept above v2.13's
  EOF-appended block. **Post-merge follow-up (one small commit):** v2.13's
  `body[data-view="series"] #globe{display:none}` would hide the ⓘ — wrap
  `#globe` + `#series-panel` in a `#viewport` and reparent `#model-info-btn`
  there (`#vis-options` staying globe-only is correct: all three of its
  controls are globe-display options). Its view toggle self-parks at row 1's
  right edge via `margin-left:auto` — the correct slot.

**Verification.** Updated `test_studies_browser.py` /
`test_families_browser.py` (pill interactions, never-disabled assertion,
auto-switch + note, modal expression + docs link; new fixtures on ports
≥ 8226 — 8213–8223 are dead on this host, v2.13 finding); then the real
gate: LAN :8300 branch-preview pass with real data (landing layout,
auto-switch feedback, modal expressions verbatim from the manifest,
pre-v2.14 permalink shapes, narrow/short-window stress, keyboard focus),
screenshots to `tests/artifacts/live_v214_*.png`, record here.

**Out of scope:** the timeline-viewer merge itself; Ionosphere
Diurnal|Seasonal entries (future occupant of the Visualisation select);
propagating pill styling to other radio groups; date-picker revival; model
pills; new series exports.

*Verified 2026-07-15*: browser suites green on the moved ports — studies 6,
permalink 5, families 18 (8226–8233; the old 8213–8223 fixtures probed
foreign fleet services and timed out); fast suites 54 green. Becoming
runnable surfaced three latent stale expectations (garbage/refused links
leave the boot default in charge, and boot pos is 32 since the v2.12
landing-view tune — same family as 95eda4c); fixed in place. Real-data pass
on the :8300 `interface-improve` container (scripted Chromium, 39 checks,
zero console errors): three-layer landing, pills never disabled, IGRF →
Ionosphere auto-switch with the verbatim chip text and transient clear,
Model-side grey-out intact, modal expressions byte-equal to
`manifest.models` (MIO_SHA_2C composite, CHAOS-MMA Primary+Secondary sum),
viresclient catalogue link + copy button (secure context), v1 / series /
lens-only permalink shapes restore identically, 700 px wrap clean, arrow
keys walk the pills. One layout fix landed en route: at ≤ 640 px height the
wrapped vis-options row overlapped the shell column — it now starts at
7.5rem with the hover readout dropped below it. Screenshots
`tests/artifacts/live_v214_*.png`.

*Refinement pass, same day* (user review of the live preview): ⓘ to
4.4rem, vis box annotated in two divided sections, frame radios spell out
earth-fixed/inertial, row 2 gains a vertical separator and the
"Visualisation mode" name. Re-verified: suites green, 47 scripted preview
checks, zero console errors. Two short-window regressions caught by the
extended checks and fixed: the ⓘ media override lost to the later base
rule on source order, and the stepped-left ⓘ needed the colorbar column
(~6rem) plus a narrower vis panel to land in clear space.

*Second refinement pass, same day* (user review): collapsible header +
vis box, the camera re-tune, and the ⌂ reset-view chip (bullets above).
Re-verified: studies suite 9 green incl. two collapse tests and the
full-reset round-trip (a non-default session → boot defaults: selections,
camera, pill, hash reload); 58 scripted preview checks, zero console
errors — desktop toggles fold/unfold with the canvas
reflowing, a 390×844 page boots collapsed on a full centred disc
(`live_v214_mobile.png`), 700×500 overlay geometry stays clear. Known
cosmetic limit: the *expanded* vis box on a phone overlays the shell
panel — it is a dismissible translucent overlay, accepted for now.

### Phase v2.15 — Loading states (slow-connection honesty)

**Approved 2026-07-17** (direct user request: the site misleads on slow
connections — the shell mesh moved and the colorbar relabeled while the old
shell's values stayed painted until the tiles arrived). Branch:
`loading-states` — implemented and browser-verified 2026-07-17.

**Why.** `applyTextures` wrote its uniforms (enables, per-shell qrange
descale, `uVmax`) *before* awaiting the tile fetch, so during the gap the
still-bound old tiles were renormalized by the new view's ranges under an
already-relabeled colorbar; a scrubbed-over call could also commit late (its
per-pair AbortError was swallowed, so the superseded `Promise.all` still
resolved). Playback already had the right discipline (freeze until decoded);
the shell/mode/day paths never adopted it. There was no tile-loading
indicator at all.

**Shape.** A pending/target contract in `main.js`: `applySeq` stamps each
`applyTextures` call, `boundSeq` the one on screen; while they differ the
shell dims (`uStale` desaturate in `shaders.js`, bit-identical off path) and
a centered globe overlay (`#load-overlay`, CSS-only spinner, 200 ms grace
delay against flicker; ships visible so it also covers boot) shows until the
**atomic commit**: all uniform writes, texture binds, `uVmax`, and the
colorbar relabel land together after every tile resolves — the four
interaction-time `refreshColorbar()` calls (and the studies/timeseries ones)
are gone. The mesh still follows the slider live (deliberate: responsive
geometry, honestly-dimmed values). Superseded calls never commit; a real
fetch failure keeps the stale dim and turns the overlay into a
click-to-retry (failed tiles self-evict from the cache, so the retry is
real). After each commit an idle timer (1 s) prefetches the ±2 neighbor
rungs of the shell ladder for the enabled fields (~24 tiles worst case,
inside the 128 MB LRU; skipped while playing; a scrub's `abortStaleFetches`
cancels in-flight warms). Deliberate behavior change: binding is atomic —
fields no longer pop in one-by-one on mode switches.

**Contract & invariants.**
- The colorbar and the shader uniforms only ever describe tiles that are
  actually bound; between target and commit the display is visibly stale
  (dim + overlay), never silently wrong.
- Playback never enters pending — `advancePlayback` keeps its own
  freeze-until-decoded discipline untouched.
- Fully-cached scrubs skip the pending UI entirely (no dim/overlay flash).
- Test handle: `pending()` on `window.geomagModelExplorer`.
- Verified by `tests/test_loading_browser.py` (sandboxed :8239, page-side
  tile latency/failure shim): boot overlay, throttled-scrub dim + deferred
  relabel, cached-scrub no-flash, mode-switch pending, playback never
  pends, failure → retry, idle prefetch warms neighbors. Two existing
  assertions updated for the new behavior (families unit relabel now waits
  for commit; timeseries LRU-neutrality measures after the prefetch
  settles; live-suite cache bound restated against the byte budget).

On the slate (IDEAS-only, not approved): Storms tab + indices (the `window`
series kind, `fetch.py --indices` + strip chart, curated storm window
bookmarks — IDEAS §9.1/§9.3/§9.4; demoted from phase v2.4 on 2026-06-12; the
v2.4 and v2.5 numbers stay retired — v2.5 was renumbered to v2.9 the same
day; re-promote on approval). Cross-family comparison series (CHAOS-vs-CI
diurnal, signed-diff display — IDEAS 2.3/2.6 successors), seasonal decade
extension (~100 MB), and the pre-studies slate: quick wins (1.1, 5.1, 4.1,
5.2, 5.3), SH playground satellite page (3.1 + 3.2), sunset review (8.3)
before adding more. Quick wins may interleave with the studies phases on
approval.

## 4. Plan lifecycle

This file stays current-state. When its phases complete or it goes stale,
archive it as a new `## v<N> plan` section in `HISTORY.md` and rewrite (RULES
§8). Unreviewed proposals live in `IDEAS.md`, decisions and status live here,
history lives in `HISTORY.md`.
