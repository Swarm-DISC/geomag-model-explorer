# geomag-model-explorer — project plan

*Browser-based interactive 3D visualization of Earth's geomagnetic field.*

**Status: v1 shipped 2026-06-11** (phases 0–6 complete). This file describes
the *current* state and what is genuinely live. The full v1 working plan —
decisions, rationale, phase checklists, prerequisite probes — is archived in
[`HISTORY.md`](./HISTORY.md); the original seed note is `NOTE.md`. Per RULES
§8, this file is refreshed (and the old generation archived) whenever it
drifts into describing history rather than current state.

## 1. What exists

The four contributions to Earth's magnetic field — core (MCO_SHA_2C), crust
(MLI_SHA_2C), ionosphere (MIO_SHA_2C), magnetosphere (MMA_SHA_2C), the Swarm
Level-2 Comprehensive Inversion chain, evaluated via viresclient only —
rendered as colormapped shells on a three.js globe. Field toggles (summed on
the GPU), component picker (N / E / Up / F), shell slider (CMB through
500 km mantle steps to the surface, then the unified 0–1500 km altitude
ladder at 100 km steps shared by every model — v2.7), colorbar scale lock (freezes the colour range so
magnitude changes across shells/days stay visible; persisted in permalinks
as `vmax=`), any-day date picker with on-demand fetch + permanent cache
(default 2020-01-01 pre-fetched), bottom-docked time slider (00:00–24:00,
15-min steps, 97 timesteps/day) with playback, hover readout, attribution.
Governance shipped in v2.1/v2.2 (write-ups archived in HISTORY.md): a
deploy-time feature-flag registry (`features.json` → `/api/features`,
dynamically imported modules in `web/features/`), permalink state in the URL
hash (stability contract: garbage ignored), and the colorbar scale lock.
v2.6 added the sun overlay (subsolar glyph + terminator from the displayed
UT, flag `sun`) and relief mode (the displayed scalar displaces the shell,
hillshaded — lit by the actual sun when both flags are on; flag `relief`).
v2.9 (flag `families`) put a page-level "Model series" selector (Swarm CI /
CHAOS) over per-source tabs — Combined models (≡ Daily; under CHAOS a
curated 15-min diurnal series), Core with a B ↔ dB/dt toggle (derived
secular variation in nT/yr, yearly 2014–2023 series per family), and
Ionosphere (the Seasons tab) — with missing layers greyed out with the
reason (CHAOS deliberately has no ionospheric layer).

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

Key parameters (rationale in HISTORY.md §§2–4): tiles are int16 NEC triples,
decoded to RGBA16F textures; storage `qrange` is decoupled from display
`vmax`; colorbar range = sum of enabled fields' per-shell p99 (manifest,
per day); MIO at 2°, MMA at 2°, MCO/MLI at 1°; ~320 MB of tiles per cached
day on the v2.7 ladder. Deploy: systemd `--user` unit
`geomag-model-explorer-web.service`, portal prefix `/foundry/geomag-model-explorer/`, redeploy =
restart.

## 2. Live operational concerns

Carried forward from the v1 plan — still open, not yet decisions:

- **Disk policy** (v1 §9.3): cached days accumulate forever — on the v2.7
  ladder ~320 MB/day tiles + ~1.3 GB/day raw npz (current cache: 1.2 GB
  tiles, 4.7 GB raw after the v2.9 series; ~93 GB free). Rung 1 (drop `data/raw/` after export)
  was considered with v2.7 and **deferred 2026-06-12**: raw retains
  re-export flexibility (qrange/format changes without refetching) and the
  disk has headroom. The scaling ladder, in order, architecture unchanged
  until the last rung: (1) drop `data/raw/` after export; (2)
  `GEOMAG_MODEL_EXPLORER_DATA` env var → big disk; (3) bundle frames per
  field·shell·day, precompressed; (4) int8 for MIO/MMA; (5) only then a
  blob store. A future Storms study (IDEAS §9.1 `window` kind / §9.4 —
  demoted from the phase ladder 2026-06-12) would add deliberate
  *multi-day* caching on top. Materialized series sit at ~10–100 MB each
  (mio-seasonal-2020 is now ~84 MB on the full ladder).
- **Radial interpolation between shells** (v1 §9.6): deferred — physically
  honest continuation needs per-degree (a/r)^(n+2), i.e. client-side SH
  evaluation. Offer later as explicitly approximate, or never.
- **Model validity ends 2023-11-30** at last check: re-run `fetch.py
  --validity` periodically (or check at serve start) so new CI product
  releases extend the date picker — the May/October 2024 G5 storms are the
  prize waiting behind this (IDEAS §6.3).
- **Portal/Ansible clobber risk** (pre-existing, all foundry projects): the
  internal portal role's `foundry-stub.html.j2` is stale (knows only
  vizlab) and written with `force: true` — an Ansible re-run would drop the
  geomag-model-explorer card from the live foundry index. Fix belongs in the
  internal portal repo.
- **Day-fetch endpoint is a write surface**: single-job queue + validity
  validation suffice on the trusted portal network; revisit if exposed wider.

## 3. Next phases

[`IDEAS.md`](./IDEAS.md) is the candidate backlog (~35 ideas collected
2026-06-11, plus the §9 studies design). Items are promoted into numbered
phases here only on human approval, with the decision date recorded.
Completed phases v2.1 (feature registry + permalinks) and v2.2 (mantle
shells + colorbar lock) are archived in HISTORY.md.

### Scope decision — multi-timescale, multi-model studies (human-directed 2026-06-11)

Widen the app to **studies on different time regimes** — century-scale core
secular variation, seasonal/decadal MIO, storm-vs-quiet MIO+MMA with
activity indices — and **multiple VirES model families** (CI / IGRF / CHAOS /
WDMAM-if-served), presented as a **single-page tab strip** (Daily ≡ today's
v1, Seasons, Storms, Secular). The seasonal MIO study proves the new
generalized time axis ("series") first. Full design: IDEAS §9. The *scope*
is approved; each phase below still gets per-phase sign-off before
implementation, and each ships with the IDEAS §8.3 definition of done
(flag + demo permalink + Playwright scenario + README line). The Storms
study was demoted back to IDEAS on 2026-06-12 (the scope decision stands;
only its phase slot is withdrawn — see "Beyond").

### Phase v2.3 — series foundation + Seasons tab ✅ (approved & shipped 2026-06-11)

Step A (own commit): `state.minutes` → `state.pos` (float epoch index over
an explicit timeline descriptor); Daily bit-identical. Step B: manifest v2
optional `series` map; curated `SERIES` catalog in `fetch.py`;
`fetch.py --series` / `export.py --series`; materialized
`mio-seasonal-2020` (weekly × 53 through the leap year at 12:00 UT, iono,
~10 MB, −50..50 nT); `frameSource()` in dataset.js as the one availability
rule; tab strip behind flag `studies` (Daily ≡ v1 + Seasons with series
picker, per-tab state snapshots, control budget held); permalink encodes
`tab=`/`series=`/`e=<ISO epoch>` (nearest-epoch restore, garbage ignored,
flag-off ignores series links). CI-only — the family axis is untouched.
Demo:
`/#tab=seasons&series=mio-seasonal-2020&e=2020-07-01T12:00&f=iono&c=Up&s=surface`.
*Verify:* `tests/test_studies_browser.py` (tab strip, Seasons playback +
scrub, permalink roundtrip, garbage, flag-off = v1) + the live demo
permalink.

### Phase v2.6 — sunlight + relief mode ✅ (approved & shipped 2026-06-11)

Two features built back-to-back in one session as designed (full design
write-up: HISTORY.md once this entry is archived; the code is the
authoritative sketch now). Their only integration surface is the one shader
uniform `uLightDir`, decided up front.

**Step A — sun overlay (flag `sun`, IDEAS 1.1).** `web/sun.js` (analytic
subsolar point from the displayed UT; series epochs parsed explicitly as UT)
+ `web/features/sun.js` (terminator LineLoop + subsolar glyph posed by one
quaternion, own Sun checkbox, permalink `sun=1`). While the relief flag is
also on, each update writes the world→view sun direction into `uLightDir`.
Demo: `/#f=iono&c=Up&s=surface&t=12:00&sun=1`.
*Verified:* `tests/test_sun_browser.py` + live pass
(`tests/artifacts/live_sun_demo.png`).

**Step B — relief mode (flag `relief`).** The displayed scalar displaces the
shell radially in the vertex shader (shared `FIELD_CHUNK` GLSL, signed,
fixed ±0.15 radii at the colorbar's `uVmax`, so relief and colors always
agree incl. under lock; F all-outward); FS hillshade from `dFdx/dFdy` of the
displaced view position, floored at 0.55 so the night side stays readable,
lit by `uLightDir` (headlight default, the sun when both flags are on);
`uRelief == 0` is bit-identical (phase screenshots reproduced byte-identical
across the refactor). 256×128 mesh swapped in only while relief is on;
hover/playback/tab snapshots untouched (raycast hits the undisplaced CPU
sphere). Relief checkbox next to the component picker — a display mode, not
a tab. Demos: `/#f=crust&c=Up&s=surface&r=1`;
`/#f=iono&c=Up&s=surface&t=12:00&sun=1&r=1` (the Sq bulge lit by the actual
sun). *Verified:* `tests/test_relief_browser.py` (incl. exact-restore
bit-identity and the uLightDir handoff) + live pass
(`tests/artifacts/live_relief_crust.png`,
`live_relief_sunlit_iono.png`).

### Phase v2.7 — unified shell ladder ✅ (approved 2026-06-12, shipped 2026-06-12)

Shipped as designed: one shared `LADDER` in `fetch.py` (surface,
h100…h1500 — the 0 km slug stays `surface` for permalink stability) for
every model; core alone keeps its below-surface descent (cmb −2891 km,
d2500…d500; 22 shells). MMA dropped h2000/re1. As predicted, everything
downstream (export, manifest, slider union, permalinks, serve day-fetch)
is spec/manifest-driven and needed no code change. Cache regenerated:
static, both cached days, and mio-seasonal-2020 — re-materialized on the
**full 16-shell ladder** (decision 2026-06-12, ~84 MB) so the Seasons tab
slider matches Daily. No quantization clipping anywhere: iono peaks
~115 nT at h100 (10 km below the MIO sheet current, which the 100 km
steps dodge by construction), inside qrange 200. Test sandboxes shrank to
fit the host's small tmpfs (float32 synthetic npz, raw pruned before
serving). Demo: `/#f=core,iono,magneto&c=Up&s=h300&t=12:00` — three
fields summed at a shared altitude, impossible before.
*Verified:* `test_fetch_unit.py::test_unified_shell_ladder`, full suite
(65 passed) + live pass (`tests/artifacts/live_v27_h300_sum.png`).

### Phase v2.8 — Seasons terminator: hold the fixed time-of-day ✅ (approved 2026-06-12, shipped 2026-06-12)

The Seasons sun overlay/terminator spun once per weekly interval during
playback: `displayedUT()` (`web/sun.js`) interpolated *absolute time*
linearly between epochs. Fixed as designed: new exported `seriesUT()`
snaps the interpolated offset to whole days whenever consecutive epochs
are a whole number of days apart (any fixed-time-of-day series), so the
displayed UT keeps the series' clock time — subsolar longitude holds
(± equation of time), declination steps daily. Daily tab untouched;
relief lighting fixed automatically (`uLightDir` derives from the same
UT). The Seasons timeline label in `web/features/studies.js` now derives
from the same `seriesUT()` instant (also fixing its latent local-time
`Date.parse`), so label and sun always agree. Demo:
`/#tab=seasons&series=mio-seasonal-2020&f=iono&c=Up&s=surface&sun=1`.
*Verified:* `tests/test_sun_browser.py::test_seasons_terminator_holds_clock`
(UTC-noon stability, terminator longitude < 5°, label/sun agreement) +
live pass (`tests/artifacts/live_v28_seasons_sun.png`).

### Phase v2.9 — model families + core SV + interface rethink ✅ (approved 2026-06-12, shipped 2026-06-12)

*Renumbered from v2.5 on 2026-06-12 (human-directed) so the phase ladder
reads chronologically — v2.6–v2.8 shipped while this one was queued. The
v2.4 and v2.5 numbers are both retired.*

Human direction 2026-06-12 widens this phase from "family axis + Secular
tab" to **all three** of the following, together, as one phase — they are
interlocking, not optional pieces (full designs: IDEAS §9.2, §9.6, §9.7):

- **Model family axis** (IDEAS §9.2): probe `available_models()` first and
  record results (exact names/validities for IGRF, CHAOS-Core/-Static/
  -MMA, LCS-1/MF7; whether WDMAM exists in VirES — likely not). Then the
  `FAMILIES` table in `fetch.py`. **Decision (human, 2026-06-12): the
  CHAOS family ships without an ionospheric layer — skip "CHAOS-MIO"
  entirely, no substitute model;** the iono toggle/tab is simply
  unavailable under CHAOS (grey vs hide is an interface-discussion item).
- **Core secular variation as a derived field** (IDEAS §9.6): SV in
  **nT/yr** is computable from VirES outputs by centered finite difference
  of two MCO evaluations at t ± 6 months — honest given the model's
  B-spline time basis (confirm MCO_SHA_2C's parameterization in the
  product doc first); pipeline unchanged (two evals instead of one, Ḃ as
  NEC tiles; `core-sv` pseudo-field with probed qrange/vmax; manifest
  `units` key for the colorbar/hover). Units make SV non-summable with nT
  fields — solved by tab gating, never by a fifth checkbox.
- **Top-level interface rethink** (IDEAS §9.7): per-source tabs under a
  page-level model-series selector — e.g. "Daily" → "Combined models", a
  "Core" tab with a B ↔ dB/dt display toggle, and a "Model series"
  dropdown above the tab strip starting with Swarm-CI and CHAOS.

**Mandatory checkpoint (human-directed):** implementation of this phase
must *begin* with an interface design discussion with the human — options
for the tab strip, the family selector, the B/dB/dt toggle, and the IDEAS
§9.7 open questions (families missing a layer, permalink mapping) — before
any code is written. The §9.7 sketch is direction, not a settled design.

**Checkpoint outcome (held 2026-06-12, all four open questions settled):**

1. Tabs: **Combined models** (id `daily`, renamed) · **Core** (new, id
   `core`) · **Ionosphere** (id `seasons`, relabeled). Ids never change
   (permalink stability).
2. **"Model series" dropdown** above the tab strip: Swarm-CI (default) +
   CHAOS — a page-level lens.
3. **CHAOS on Combined = curated diurnal series**
   (`daily-2020-01-01@chaos`); under CHAOS the date picker swaps to a
   series select. No family dimension in the day cache — family rides
   inside the series id slug (IDEAS §9.2 storage design unchanged).
4. Missing layers **grey out + tooltip** ("not part of the CHAOS model
   series") — both the iono toggle on Combined and the Ionosphere tab.
5. Core tab timeline = **yearly series 2014–2023** with a B ↔ dB/dt
   two-way toggle (one displayed field at a time: `core` or `core-sv`;
   SV never sums with nT fields by construction). Full 22-shell core
   ladder (v2.7 precedent).

**Probe record (2026-06-12, `docs/v29_model_probe.py` →
`docs/v29_model_probe.json`; FAMILIES copies from here, not from guesses):**

- Served models confirmed (name → expression, validity):
  `IGRF` (deg 1–13; 1900-01-01 → 2030-01-01), `'CHAOS-Core'` (deg 1–20;
  1997-02-07 → 2026-08-08), `'CHAOS-Static'` (deg 21–185; unbounded),
  `'CHAOS-MMA'` ≡ served composite `'CHAOS-MMA-Primary' +
  'CHAOS-MMA-Secondary'` (deg 1–2; 2000-01-01 → rolling now), `'LCS-1'`
  (deg 1–185; unbounded), `MF7` (deg 16–133; unbounded). **WDMAM: not
  served** (zero matches in `available_models()`, 30 models total) — the
  crust family alternative is LCS-1/MF7, as IDEAS §9.2 predicted.
  `CHAOS-MIO` *is* served but is skipped per the 2026-06-12 decision (no
  ionospheric layer in the CHAOS family).
- Composed two-model expression evaluates fine via `eval_model`
  (probe: surface |B| median ≈ 29 nT) — but `'CHAOS-MMA'` is served
  directly, so FAMILIES uses the alias.
- SV magnitudes (centered diff at 2018-06-01 ± 6 mo, 1° at CMB):
  |Ḃ| max ≈ 59 k nT/yr (MCO_SHA_2C), ≈ 71.5 k nT/yr (CHAOS-Core, more
  small-scale power); surface max ≈ 224, p99 ≈ 196 nT/yr (both models
  agree at the surface). 1° ≈ 5° values at the CMB — SV is smooth at
  these degrees. ⇒ **core-sv qrange = 100 000 nT/yr** (1.4× headroom over
  the strongest case), **vmax = 200 nT/yr** (surface p99). int16 step =
  3.05 nT/yr ⇒ ~64 display levels at the surface — acceptable; revisit
  per-shell qrange only if banding offends at live verify.
- MCO_SHA_2C time basis (CIY4, Sabaka et al. 2018, PMC6425495): core SV
  on SH degrees 1–16 as **order-4 (cubic) B-splines, 6-month knots**;
  degrees 17+ static. Not the piecewise-linear basis IDEAS §9.6 guessed —
  the ±6-month centered difference is therefore a *smoothed* (still
  honest, O(Δ²)) SV estimate, not an exact knot slope. CHAOS-Core is
  order-6 splines; IGRF SV would be a 5-year staircase (century series is
  a later phase anyway).

**Shipped (2026-06-12), all behind flag `families`:** `FAMILIES` table in
fetch.py ((family, layer) → probe-recorded model spec, aliases stable so
`B_NEC_<alias>` never changes; the day pipeline never consults it — family
rides inside curated series ids, `…@chaos`). Derived `core-sv` field
(centered ±6-mo difference in `_save_snapshot`, `sv_window` clamps to
per-model validity from validity.json; nT/yr via a manifest `units` key
that drives colorbar + hover; **no checkbox by construction** — ui.js only
builds toggles for nT fields; F of SV = |Ḃ|, tooltipped). `SeriesSpec`
grew `family`, `step_minutes`, `step_years` (calendar stepping),
`single_step` (one middle-epoch tile — the diurnal series would otherwise
duplicate core/crust ×97) and `qrange` (per-series storage override:
**CHAOS-Core reaches degree 20 and peaks 8.41M nT at the CMB**, 2.8× the
CI-sized core qrange — caught by the export clipping check, stored at 10M
via `storageQrange()` on both descale paths; CI tiles keep full
precision). Manifest v3, all additive. Frontend: shader grew a 5th field
slot (uEnable/uScale became float arrays — Vector4 would have crashed on
index 4), series membership outranks the static shortcut in fieldDay +
frameSource (the chaos series' CHAOS-Static crust must never read the MLI
static tiles), day availability requires per-day stats. studies.js:
Combined models · Core · Ionosphere (ids unchanged) under `#family-select`;
per-(tab,family) snapshots; Core tab B ↔ dB/dt radio clears the colorbar
lock on unit change; grey-outs say *why* ("not part of the CHAOS model
series"); attribution swaps per family. permalink: `family=` (ci = key
absent ⇒ old links bit-identical; series wins over family), kind→flag
gates (annual ⇒ studies, secular/diurnal ⇒ families) so a families-off
deploy degrades gated links to v1. Materialized: `core-secular`,
`core-secular@chaos` (yearly ×10, 2014–2023, 22 shells, B + Ḃ),
`daily-2020-01-01@chaos` (97 × 15-min, single-step core/crust) — tiles now
1.2 GB, raw 4.7 GB. Demos:
`/#tab=core&series=core-secular&f=core-sv&c=Up&s=cmb` (SV flux patches at
the CMB),
`/#family=chaos&tab=daily&series=daily-2020-01-01@chaos&e=2020-01-01T12:00&f=core,crust,magneto&c=Up&s=h300`,
`/#tab=core&series=core-secular@chaos&f=core-sv&c=Up&s=cmb`.
*Verified:* `tests/test_families_browser.py` (12 scenarios, flag on + off,
zero console errors) + full suite (90 passed) + live pass
(`tests/artifacts/live_v29_*.png`).

### Beyond (IDEAS-only, not approved)

Storms tab + indices (the `window` series kind, `fetch.py --indices` +
strip chart, curated storm window bookmarks — IDEAS §9.1/§9.3/§9.4;
demoted from phase v2.4 on 2026-06-12; the v2.4 and v2.5 numbers stay
retired (v2.5 was renumbered to v2.9 the same day);
re-promote on approval). Cross-family comparison series (CHAOS-vs-CI
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
