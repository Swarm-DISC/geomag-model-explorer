# HISTORY.md — superseded plan generations

Newest first. Each section is a complete working plan as it stood when it was
archived per RULES §8; the current plan is [`PLAN.md`](./PLAN.md). Not part of
the default session reading list — consult only for design archaeology.

## v2 studies plan (archived 2026-07-15 — v2.3–v2.12 all shipped)

The multi-timescale, multi-model studies generation: from the 2026-06-11 scope
decision through v2.12 (reference frames + surface sunlight + defaults refresh
+ landing-view tune), merged to `main` and published 2026-07-15. Archived
verbatim below, each phase with its verification record. The v2.1/v2.2
governance phases that preceded this generation are the next section down.

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

### Phase v2.10 — selector inversion (Field to explore → Model) ✅ (shipped 2026-07-01)

Human-directed UI change: choose the study first. The v2.9 lineup (a "Model
series" dropdown over a per-source tab strip) becomes two dropdowns — a
**primary "Field to explore"** select (All / Core / Ionosphere; "All" ≡ the
former "Combined models") and a **secondary "Model"** select (Swarm CI /
CHAOS). Field is primary: the Model options grey out where the chosen field
has no data (e.g. Ionosphere × CHAOS — CHAOS has no ionospheric layer), and
picking such a field falls the model back to one that has it (`switchField`
mirrors the old `switchFamily`→`bestField` fallback). Presentation-only: study
ids (`daily`/`core`/`seasons`) and `state.family` are unchanged, so
`permalink.js` is untouched and every v2.3–v2.9 link (incl.
`tab=`/`series=`/`family=`) round-trips bit-identically. The whole change lives
in `web/features/studies.js` (+ `web/style.css`, an `index.html` comment).
Demos unchanged from v2.9. *Verified:* `tests/test_families_browser.py` /
`test_studies_browser.py` rewired to drive `#field-select` (incl. the
field-primary model fallback + grey-out) + full suite + live browser pass.

### Phase v2.11 — all VirES models + model-info ⓘ ✅ (shipped 2026-07-01)

Every grid-evaluable model VirES serves (probe: `docs/v211_model_probe.json`,
30 catalog names) is now selectable. **ci and chaos stay the only multi-field
lenses**; each remaining model is a **single-field family** riding one
curated series: core — MCO_SHA_2D (`core-secular@mco2d`, yearly 2014–2017,
its full frozen validity) and IGRF (`core-secular@igrf`, 5-yearly
**1900–2025**, the full-range century study; core-sv stored at ±150k — the
1900s CMB |Bdot| tops the 100k default); crust — LCS-1 (±2000 nT storage),
MF7, MLI_SHA_2D (timeless: the new `kind="static"` 1-epoch/single-step
series `crust-static@*`, incl. ci/chaos twins); iono — MIO_SHA_2D
(`mio-seasonal-2020@mio2d`); magneto — MMA_SHA_2F (`daily-2020-01-01@mma2f`).
The "Field to explore" dropdown gains **Crust** (kind `static`; timebar
hidden — single epoch) and **Magnetosphere** (kind-less like All, gated to
its field, so it *reuses* the day cache / the CHAOS day's magneto layer —
no duplicate data). **Unevaluated by decision, greyed in the dropdown with
the reason** (2026-07-01): CHAOS-MIO (the 2026-06-12 decision stands), AMPS
(polar current climatology, not a global field), MLI_SHA_2E (degree 600 ≫
the 1° grid). Aliases (MCO_SHA_2X, CHAOS, SwarmCI, -Primary/-Secondary
halves) are covered indirectly. Manifest **v4** (additive): per-field
`model`/`sv`, per-series `models`, top-level `models` (validity + served
expression from `--validity`). The **ⓘ model-info modal** (flag `modelinfo`,
`web/features/model-info.js`, IDEAS §6.2) opens a native `<dialog>` naming
the served model behind each on-screen layer with degree range, validity,
grid/cadence/storage, an honest caveat paragraph, and the
unevaluated/alias footer. `tab=` permalink key is now functional (kind-less
tabs are indistinguishable from data alone); `fieldVmax` fixed so a series'
crust uses its own stats, not MLI's; `#timebar[hidden]` CSS fixed; playback
guards the zero-span single-epoch timeline. Follow-up (user report
2026-07-03): the grey-out is now **symmetric** — fields the chosen model
can't serve disable in the Field dropdown (previously picking one silently
swapped the model back, e.g. All × MMA_SHA_2F offered Crust → Swarm CI).
Demos:
`/#tab=core&series=core-secular@igrf&e=1950-06-01T12:00&f=core-sv&c=Up&s=cmb`,
`/#tab=crust&series=crust-static@lcs1&f=crust&c=Up&s=surface`,
`/#tab=magneto&series=daily-2020-01-01@mma2f&f=magneto&c=Up&s=h500`.
*Verified:* fast suites (48) green; live :8212 browser pass 46/46 checks,
zero console errors (`tests/artifacts/live_v211_*.png`);
`test_families_browser.py` extended (Crust/Magnetosphere studies,
unevaluated entries, modal, magneto tab= round-trip).

### Phase v2.12 — reference frames + surface sunlight + defaults refresh ✅ (approved 2026-07-08, implemented 2026-07-08 on branch `frames-and-sunlight`)

IDEAS §1.4 promoted as its two-way subset (human-directed): a global
**ECEF | ECI** reference-frame control — plain radios, no disclosure nesting,
no sun-fixed mode yet, though `web/features/frame.js` keeps a FRAMES table +
one `frameAngle()` so the third mode is a table row when wanted
(`(180 − subsolarPoint(ut).lon) · DEG`). ECI poses the globe group by the
mean-solar hour angle from the displayed UT (+Y polar axis, 15°/hr; one
quaternion poses the globe and the sun lighting — IDEAS §1.4's contract), so
Daily playback shows the Earth spinning eastward under a sun that holds still
up to the equation of time (±4°). Permalink `frame=<id>`, written only when
≠ ecef; unknown ids degrade to ecef (stability contract). Hover picking
applies the inverse earth quaternion so the readout stays geographic.

Bundled in the same approval:

- **Sun → Sunlight** (flag `sun`, key `sun=`, `#sun-toggle` id all kept): the
  v2.6 overlay (terminator ring + subsolar glyph) is retired; the toggle now
  shades the globe surface itself by day/night — object-space `uSunDir` +
  `uSunlight` uniforms in the field *and* coast fragments (soft ~±5°
  terminator band, 0.35 night floor), so the terminator reads as a lighting
  boundary and, being object-space, is rotation-proof under ECI for free.
  The v2.6 uLightDir handoff (relief hillshade follows the sun while both
  flags are on) is unchanged in logic, now frame-aware (world sun =
  earth quaternion × ecef sun).
- **Defaults refresh**: all four fields on, relief on, sunlight on; shell
  stays h500, component Up. Permalink learns the off forms `sun=0` / `r=0`
  (key absent = the new on default; old explicit `=1` links still parse;
  `f=` already round-trips the full list incl. empty).
- **Labels/footer**: component radios + hover readout display Northward /
  Eastward / Upward / Intensity (`N`/`E`/`Up`/`F` stay the architectural keys
  in `c=`, COMPONENT_MASK, radio values/ids); the attribution line reads
  "An ESA Swarm project via VirES — …".

v2.6 bit-identity is preserved via the all-off path (`sun=0&r=0`:
`uSunlight == 0 && uRelief == 0` leaves color untouched); the *default* look
changes by design. Pre-v2.12 links that never carried `sun=`/`r=` now render
with both on — absent-means-default is the contract and the defaults moved.

Demos: ECI playback `/#day=2020-01-01&t=00:00&f=iono&c=Up&s=h100&frame=eci`
(press play: the globe spins, the Sq blob and the night shading hold still);
v1 look `/#f=crust&c=Up&s=surface&sun=0&r=0`.
*Verified:* fast suites green (54); browser suites rewritten/re-anchored
in-tree (`test_frame_browser.py` new; sun suite re-targeted from the retired
overlay to the uniforms) but not run on this host (SwiftShader sandbox
timeouts — known); real-data smoke against a checkout serve on :8230 —
17/17 checks (boot defaults, uniforms, hash normalization with no
sun=/r=/frame= keys, frame=eci → exactly 90° about +Y at 06:00 UT and back,
sun=0&r=0 off-forms, zero console errors) + eyeballed screenshots (midnight
night-side, noon lit, ECI 06:00 with the Americas rotated into view,
night-dimmed).

**Landing-view tune (2026-07-15, human-directed):** booting at t=00:00 faced
the viewer at the midnight side — a near-black landing globe. The boot time
moved to **08:00 UT** (subsolar ~60°E: ~3/4 of the landing disc lit,
terminator on the Atlantic limb, Sq blob on screen) and the night floor rose
**0.35 → 0.55** in both fragments so the night side stays clearly readable,
just darker (worst-case night × relief hillshade 0.30, was 0.19). Fast
suites stayed green (54); no test pinned either constant.

**:8300 branch-preview browser pass (2026-07-15) — the remaining-before-merge
list, all green: 28/28 checks, zero pageerror/console.error** across every
section, real interactions throughout. Boot (t=08:00 hash-normalized, night
quarter visible & darker than day); ECI playback (timePos advances, pose
tracks UT at 15°/h with <1° deviation spread, world-space sun drift <0.03
while the globe spins); relief × night floor (night pixels readable with
relief on and off); hover under ECI (readout stays geographic — same pixel
reads 156.2°E under eci vs 0.1°E under ecef); Seasons pose-hold (weekly
12:00 UT steps: earth angle spread 0°, subsolar-lon spread 0.46°); studies ×
frame interplay (all five tabs cycled under eci, CHAOS greys the iono
toggle, back to CI clean); narrow width (420 px: no horizontal scroll, all
controls visible). Eyeballed: default 3/4-lit landing, ECI mid-play
world-fixed lighting, Seasons night face at the new floor, narrow layout.



## v2 governance phases (archived 2026-06-11 — both shipped)

Phase write-ups moved verbatim from PLAN.md §3 when the plan was refreshed
for the multi-timescale studies scope (IDEAS §9); PLAN §1 keeps one-line
mentions.

### Phase v2.1 — governance: feature registry + permalinks ✅ (approved & shipped 2026-06-11)

Deploy-time feature flags — `features.json` → `GET /api/features`; the
frontend dynamically `import()`s only enabled modules from `web/features/`,
each implementing `restore(ctx)` (pre-UI, may mutate state + camera) and
`attach(ctx)` (post-boot; `onChange` fires from the render loop). First
flagged feature: **permalink state** —
`#day=…&t=HH:MM&f=core,iono&c=N&s=cmb&cam=x,y,z`, restored on load
(uncached days go through the day-fetch job), written back debounced via
`history.replaceState`. Unknown/invalid hash values are ignored (stability
contract). Demo:
`/#day=2020-01-01&t=12:00&f=core&c=N&s=cmb&cam=0.000,0.000,2.500`.
*Verify:* `tests/test_permalink_browser.py` (flag-on stub server: restore,
write-back, garbage degradation, flag-off = v1) + live demo permalink.

### Phase v2.2 — mantle shells + colorbar scale lock ✅ (approved & shipped 2026-06-11)

Human-requested (not from IDEAS). Five mantle shells for the core field
(d2500…d500, every 500 km of depth) so the slider transitions smoothly from
the CMB; `fetch.py` snapshot skipping is now shell-aware
(`snapshot_complete`), so re-fetching a cached day self-heals it with shells
added later — only incomplete snapshots re-run. Colorbar lock button
(`#colorbar-lock`): freezes `state.vmaxLock` at the displayed range until
unlocked; permalink gains an optional `vmax=` key (stability contract:
garbage ignored). *Verify:* `test_browser.py::test_colorbar_lock`,
`test_permalink_browser.py::test_vmax_lock_roundtrip`.

## v1 plan (archived 2026-06-11 — all phases 0–6 shipped)

Preserved verbatim (headings demoted one level).

*Browser-based interactive 3D visualization of Earth's geomagnetic field.*

This is the working plan grown from `NOTE.md`, informed by the vizlab prior art
(`geomag-field-globes`, `fancy-globe`) and the old ESA VirES web client
(an internal web-client framework). It is meant to be discussed and iterated on —
see **Open questions** at the end. Status: **all phases (0–6) complete;
shipped 2026-06-11.** Revised 2026-06-10: CI model chain only (no ppigrf), any-day picking
with on-demand fetch, bottom-docked time slider. Revised 2026-06-11 (Phase 1–2
implementation): MIO at 2° (§9.1 → resolved), 97 timesteps per day (t96 =
next-day 00:00 so the 23:45–24:00 slider segment interpolates), components
shown as **N / E / Up / F** with Up = −C (§9.4 → resolved; tiles store native
NEC), async day-fetch UX (§9.2 → resolved), storage quantization range
decoupled from display range (see §3), MANIFEST.toml granularity per
field·day.

### 1. Goal & scope

An interactive web app showing the four contributions to Earth's magnetic field
as colormapped values on a 3D globe. All field values come from **viresclient
only**, using the Swarm Level-2 Comprehensive Inversion (CI) model chain:

| Field | Model | Time behaviour |
|---|---|---|
| Core | MCO_SHA_2C | continuous (secular variation; ~constant within a day) |
| Crust | MLI_SHA_2C | static |
| Ionosphere | MIO_SHA_2C (primary + secondary summed) | daily cycle (15-min cadence) |
| Magnetosphere | MMA_SHA_2C (primary + secondary summed) | fast (15-min cadence) |

Interactions:

- **Field toggles** — any subset of the four; enabled fields are **summed** on the GPU.
- **Component picker** — N, E, C (or magnitude F).
- **Altitude/depth slider** — translucent shells at discrete precomputed radii,
  including below the surface (core–mantle boundary).
- **Date picker — any day** within the models' validity range, **default
  2020-01-01**; the day's data is fetched on demand and cached (§5).
- **Time slider docked at the bottom of the page** — full-width, spanning the
  picked day 00:00–24:00 in 15-min steps, with play/pause and speed control.

```
┌──────────────────────────────────────────────────────┐
│  controls: field toggles · component · shell · date  │
│                                                      │
│                      3D globe                        │
│                                                      │
├──────────────────────────────────────────────────────┤
│ ⏵ ──────●──────────────── 00:00–24:00 · speed ▾      │  ← bottom time bar
└──────────────────────────────────────────────────────┘
```

Explicitly deferred: field lines, mobile polish.

### 2. Decisions & rationale

| # | Decision | Rationale |
|---|---|---|
| 1 | **three.js** (vendored ES module + OrbitControls, custom `ShaderMaterial`) | Shells at arbitrary radii — including the CMB at r=3480 km — are just spheres; Cesium is built around the WGS84 ellipsoid + terrain and fights sub-surface shells; custom fragment shaders give GPU-side summation, component selection, and colormapping. globe.gl/deck.gl target point/arc layers. The old WebClient-Framework (Backbone + Cesium 1.20 + plotty) confirms the raster-grid-on-globe pattern but is reference-only. |
| 2 | **viresclient only** — all four fields from the CI chain (MCO/MLI/MIO/MMA_SHA_2C); no ppigrf/chaosmagpy model evaluation | One consistent, co-estimated model family; one fetch path; the VirES token is configured and verified (§7). chaosmagpy remains a dev-time dependency solely for exporting the nio colormap LUT — it never evaluates fields. |
| 3 | **Quantized int16 binary tiles** — one tile per field·shell·timestep, shape `[nlat, nlon, 3]`, N/E/C interleaved, little-endian — plus `manifest.json` (dims, qrange/vmax, radius, times per field) | int16 with per-field scale; gzips well; all three components in one texture makes component selection / |F| a shader-side `dot()`/`length()`. Decoded in JS to half-float, uploaded as **RGBA16F** textures (alpha unused) — linear filtering confirmed working headlessly (§7). **Storage `qrange` ≠ display `vmax`** (learned at first export): real data exceeds the prior-art display ranges — MLI surface anomalies hit ±875 nT (Kursk), MCO at the CMB ~10⁶ nT — so qrange is sized per field's strongest shell (core 1.5e6, crust 1500, iono 200, magneto 500 nT) while vmax keeps the prior-art display defaults (65000/100/25/25). int16 resolution stays far below colormap steps. |
| 4 | **Each field keeps its native grid** — no resampling at export | Every enabled field's texture is sampled at the same normalized UV in the shader, so summation needs no common grid. CI models are low-degree (MCO ≤ deg ~18, MLI ≤ deg ~80, MIO/MMA lower still) — 1° grids suffice everywhere, 2° for MMA. |
| 5 | **Discrete precomputed shells; slider snaps to available radii** | On-GPU radial interpolation is physically wrong for potential fields (power-law decay, not linear). Snap-to-shell is honest and simple. |
| 6 | **Any-day picking via on-demand fetch + permanent cache** (§5); default day 2020-01-01 pre-fetched at deploy | The only way to satisfy both "precomputed and stored" (no live per-frame evaluation) and an open date picker. A day is fetched once, in a background job with progress UI, then served from cache forever. |
| 7 | **Serving:** static frontend + tiles + a small day-fetch API via starlette/uvicorn, `uv run`, as systemd `--user` unit `geomag-model-explorer-web.service` on **:8212** | Matches the muninn/huginn pure-uv pattern: redeploy = `systemctl --user restart geomag-model-explorer-web.service`. App must work behind `/foundry/geomag-model-explorer/` (relative URLs only). |
| 8 | **No build step** — plain ES modules + importmap; three.js vendored into `web/vendor/` and committed | Few modules, one page; keeps redeploy restart-only with no node in the deploy path. Vite is the fallback if module count grows. |

### 3. Architecture

```
fetch.py   (the ONLY module that talks to VirES; viresclient in the `fetch` extra)
   ├─ fetch_day(date)    → per-day tiles: MCO (1/day), MIO+MMA (96×15 min)
   ├─ fetch_static()     → MLI tiles (once)
   └─ model validity ranges via viresclient (constrain the date picker)
        └─▶ data/raw/*.npz + data/MANIFEST.toml   (provenance: model spec, grid,
                                                   radius, times, sha256, version)
export.py  (offline) npz → web/data/<field>/<shell>/<YYYY-MM-DD>/t##.i16
                          + web/data/manifest.json (+ nio LUT at build time)

serve.py   starlette on 0.0.0.0:8212
   ├─ StaticFiles: web/ + cached tiles (gzip)
   ├─ GET /api/days            → cached days + model validity range
   └─ POST /api/days/<date>    → background fetch_day + export job; progress
                                  polled by the UI ("fetching 2021-03-17 … 42%")

browser
   dataset.js — fetch + decode tiles → RGBA16F textures, LRU cache, prefetch
   globe.js   — three.js scene: field shell(s), coastline reference sphere
   shaders.js — the fragment shader (below)
   ui.js      — toggles, component radios, shell slider, date picker,
                bottom-docked time bar (slider + play/pause/speed)
```

**Shader contract.** For each enabled field: sample its texture at the fragment's
UV — for MIO/MMA sample the two adjacent timestep textures and `mix()` by the
time fraction — then:

```
vec3 B = Σ_i  enable_i * sample_i(uv).xyz          // N, E, C in nT (descaled)
float v = dot(B, componentMask)  or  length(B)     // component or |F|
color   = texture(lut, 0.5 * (v / vmax) + 0.5)     // diverging nio colormap
```

`vmax` defaults to the sum of enabled fields' vmaxes (open question §9).
Per-field ranges from prior art (to be confirmed against CI models at fetch
time): core ±65000 nT, crust ±100 nT, magnetosphere/ionosphere ±25 nT.

**fetch.py** extends the proven pattern in
`vizlab/projects/geomag-field-globes/fetch.py` (`SwarmRequest.eval_model()` on
lat/lon meshgrids) to full B_NEC × multiple radii × time series. To keep request
counts sane it **stacks all shells of a field into one evaluation per timestep**
(`radius` is per-point) and chunks large point sets; resumable per snapshot.

### 4. Data scope

**Shells** (radii per field; MIO never evaluated at the ~110 km sheet current —
singular there; primary+secondary summed at fetch time):

| Field | Shells | Grid |
|---|---|---|
| Core (MCO) | CMB (r = 3480 km), surface, 110 km, 450 km, 1000 km, 2000 km alt | 361×181 (1°) |
| Crust (MLI) | surface, 110 km, 450 km | 361×181 (1°) |
| Ionosphere (MIO) | surface, 450 km | 181×91 (2°; §9.1 resolved) |
| Magnetosphere (MMA) | surface, 450 km, 2000 km, ~1 R_E alt | 181×91 (2°) |

**Time:** everything keys off the **picked day**. MLI static (fetched once);
MCO evaluated once per picked day at 12:00 UT (secular variation is invisible
within a day); MIO/MMA at 15-min cadence — **97 snapshots t00..t96**, with t96
= next-day 00:00 so the 23:45–24:00 slider segment interpolates instead of
clamping. No separate epoch slider — secular variation is explored by picking
different days.

**Volume per picked day** (int16 × 3 components):

| Field | Bytes/tile | Shells | Steps/day | Per day |
|---|---|---|---|---|
| Core (MCO) | 0.39 MB | 6 | 1 | 2.4 MB |
| Crust (MLI) | 0.39 MB | 3 | static | 1.2 MB (once) |
| Magnetosphere (MMA) | 0.10 MB | 4 | 97 | 38.3 MB |
| Ionosphere (MIO) | 0.10 MB | 2 | 97 | 19.2 MB |
| | | | **per day** | **≈60 MB** |

All lazily loaded by the browser (initial page load is one tile, ≤0.4 MB; a
full view streams as needed). Gzip gets int16 grids to roughly 50–70%. Cached
days accumulate on disk (~115 MB/day) — `data/raw/` and `web/data/` are
gitignored; `MANIFEST.toml` records provenance per fetched day.

### 5. Any-day picking: on-demand fetch + cache

Arbitrary dates with precomputed-only data means the archive is built lazily:

- The date picker accepts any day inside the **intersection of the four models'
  validity ranges** (reported by VirES at fetch time, refreshed periodically;
  Swarm-era products, so roughly 2013-11 onward). Default: **2020-01-01**,
  pre-fetched at deploy so the first visit is instant.
- Picking an uncached day POSTs `/api/days/<date>`; serve.py runs
  `fetch_day` + export as a **background job** and the UI shows progress.
  A day at 1° MIO is several hundred grid evaluations even with shell-stacking
  — expect **minutes, not seconds**, for first fetch of a new day (the main
  argument for MIO at 2°, §9). Once cached, switching to that day is instant.
- One fetch job at a time; concurrent picks queue. Fetched days are kept
  forever (revisit if disk becomes a concern).

**Cache storage (initial scheme).** Plain files in the checkout, no database:
`data/raw/` holds the float64 `.npz` masters per fetched day (provenance in the
committed `MANIFEST.toml`); `web/data/<field>/<shell>/<YYYY-MM-DD>/t##.i16`
holds the int16 tiles the browser consumes, indexed by `web/data/manifest.json`.
A day is cached iff its tiles are complete **and** listed in the manifest — the
index doubles as the atomic-publish mechanism. ~115 MB/day in tiles (1° MIO),
~2× if raw npz is retained; a year of days ≈ 80 GB retained / 42 GB tiles-only.

**Scaling ladder (rethink path for larger volume, in order — architecture
unchanged until the last rung):**
1. Drop `data/raw/` after export (re-fetchable; MANIFEST keeps provenance) — ~50%.
2. Externalize the cache dir (`GEOMAG_MODEL_EXPLORER_DATA` env var → big disk; default
   stays in-checkout).
3. Bundle: one binary per field·shell·day (96 frames + header), precompressed
   gzip/zstd at rest — 96× fewer files and HTTP round-trips; browser slices
   frames from one fetch.
4. Shrink payload: MIO at 2° (÷4) + int8 for MIO/MMA (±25 nT → ~0.2 nT/step,
   below colormap resolution) — a year of days ≈ 7 GB.
5. Only if a filesystem tree truly stops scaling: LMDB/SQLite blob store or
   object storage.

### 6. Repo layout

```
geomag-model-explorer/
├── PLAN.md  NOTE.md  README.md  RULES.md  AGENTS.md  CLAUDE.md→AGENTS.md
├── pyproject.toml  uv.lock        # dev: pytest, pytest-playwright; fetch: viresclient
├── fetch.py                       # network ONLY → data/raw/ + MANIFEST.toml
├── export.py                      # npz → web/data tiles + manifest.json + LUT
├── serve.py                       # starlette: static + day-fetch API, :8212
├── deploy/geomag-model-explorer-web.service   # systemd --user unit (Phase 1)
├── deploy/PORTAL_HANDOFF.md
├── data/raw/                      # gitignored; MANIFEST.toml committed
├── web/
│   ├── index.html  style.css  main.js  globe.js  shaders.js  dataset.js  ui.js
│   ├── vendor/                    # three.module.js, OrbitControls.js (committed)
│   ├── textures/                  # coastlines.png, colormap_nio.png (committed)
│   └── data/                      # gitignored cached tiles + manifest.json
└── tests/                         # webgl probe, export round-trip, browser tests
```

### 7. Prerequisite check results (Phase 0, 2026-06-10)

- **Headless WebGL2: PASS** with default headless Chromium (no special launch
  args). Renderer: `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)
  (0x0000C0DE)), SwiftShader driver)`. RGBA16F half-float texture upload +
  LINEAR filtering verified by readback (midpoint of a 2-texel ramp read 143 ≈
  0.56×255 — bilinear, not NEAREST). `MAX_TEXTURE_SIZE` 8192 (largest grid
  721×361). Probe: `tests/test_webgl_probe.py`, results:
  `tests/webgl_probe_result.json`. SwiftShader is software GL — keep test
  scenes small and timeouts generous.
- **VirES token: CONFIGURED & VERIFIED** — user set up `~/.viresclient.ini`
  (2026-06-10); confirmed with a minimal `eval_model(models=["IGRF"])` call
  (two points, surface) returning physically sensible B_NEC. viresclient
  0.16.0 in the `fetch` extra. Nothing blocks the data pipeline.
- **Port 8212: free** (`ss -ltn`), reserved for geomag-model-explorer; next-free in the
  portal 82xx map.
- **npm registry: reachable** (HTTP 200) for the one-time three.js vendoring.

### 8. Phases

Each phase is independently shippable: **commit → push → redeploy →
browser-test** (zero `pageerror`/`console.error`, real interactions).

All phases shipped 2026-06-11 (commit history is the detailed record):

- **Phase 0 — repo + plan + prerequisite checks. ✅ done.**
- ✅ **Phase 1 — MVP globe.** `fetch.py` minimal: MLI_SHA_2C surface grid (one
  small fetch — token already verified); `export.py` minimal: that tile +
  manifest + nio LUT (chaosmagpy, dev-time only) + coastlines texture.
  three.js scene with one shell + OrbitControls; vendored three.js.
  `serve.py` (static only) + `deploy/geomag-model-explorer-web.service` installed; portal
  nginx block + link-card go live. *Verify:* Playwright against `:8212`
  **and** through the portal prefix; canvas non-blank (pixel readback);
  drag-rotate changes the view; screenshot for human review.
- ✅ **Phase 2 — full data pipeline.** `fetch_day`/`fetch_static` per §4
  (shell-stacked, chunked, resumable); export of all four fields; pre-fetch
  default day 2020-01-01; model validity ranges. *Verify:* export round-trip
  test (int16 ↔ float within quantization error); tile sizes match §4; values
  sanity-checked against prior-art ranges; MVP still renders.
- ✅ **Phase 3 — multi-field summation + component picker.** Four samplers,
  per-field enable/vmax uniforms, component mask / `length()`; checkboxes +
  radios; colorbar; fields without data at the current shell greyed out.
  *Verify:* Playwright toggles each control, asserts canvas pixels change.
- ✅ **Phase 4 — altitude/depth shells.** Slider snapping to the union of enabled
  fields' radii (intersection when summing); translucent coastline reference
  sphere when off-surface; CMB interior view. *Verify:* slider sweep in
  browser test; CMB screenshot.
- ✅ **Phase 5 — time: bottom bar + any-day picking.** Bottom-docked full-width
  time slider (00:00–24:00, 15-min steps) with play/pause/speed; `mix()`
  between adjacent timesteps; background prefetch + LRU texture cache. Date
  picker (default 2020-01-01) wired to `/api/days`: cached days load
  instantly, new days trigger the background fetch job with progress UI.
  *Verify:* playback advances ≥k distinct frames without errors; cache stays
  bounded; picking an uncached day shows progress and (in a test with a
  stubbed fetcher) completes and renders.
- ✅ **Phase 6 — polish.** Hover readout (lat/lon + nT via raycast + CPU tile
  lookup), attribution (ESA Swarm/VirES, CI models — DTU/IPGP et al.),
  colorbar refinement, README, portal card screenshot, PLAN.md
  reconciliation.

### 9. Open questions (to discuss before/during Phase 2)

1. ~~**MIO resolution**~~ — **resolved 2026-06-11: 2°** (19 MB/day, ~4× faster
   first-fetch; MIO is a smooth low-degree field).
2. ~~**Day-fetch UX**~~ — **resolved 2026-06-11: async** — the user keeps
   exploring the current day; a progress chip near the date picker polls
   `GET /api/days`.
3. **Disk policy** — cached days accumulate ~60 MB/day. Keep forever
   vs LRU-evict on disk too? See the scaling ladder in §5 — flagged for a
   deliberate rethink before the cache grows large; rungs 1–2 are cheap.
4. ~~**Component naming**~~ — **resolved 2026-06-11: N / E / Up / F** with
   Up = −C (sign flip in the shader mask; tiles store native NEC).
5. ~~**Colorbar policy when summing**~~ — **resolved 2026-06-11 (forced by
   the CMB view, which saturated the fixed range 37×): colorbar range = sum
   of the enabled fields' per-shell p99 of |components|** (computed per day
   at export, stored in manifest.json). p99 reproduces the prior-art
   surface defaults (core 62k, crust 113, iono 30 nT) and stays usable at
   every shell; the static defaults remain the fallback.
6. **Radial interpolation between shells** — offer later as explicitly
   approximate, or never?

### 10. Portal plan

- Phase 0 (done): static stub `portal/web/foundry/geomag-model-explorer/index.html`
  ("in planning") + link-card on the foundry index — satisfies the root
  minimum-visibility rule before anything is served.
- Phase 1: nginx location `/foundry/geomag-model-explorer/` → `:8212` (modeled on existing
  blocks, `X-Forwarded-Prefix`, 502/503 fallback to the stub), then
  `systemctl --user restart portal.service`. Handoff doc in
  `deploy/PORTAL_HANDOFF.md`.
- **Caveat (pre-existing, affects all foundry projects):** `/home/ivaldi/portal`
  is not a git repo — it is deployed by an internal Ansible role
  (`roles/portal`), whose `foundry-stub.html.j2` template is **stale** (knows
  only vizlab) and is written with `force: true`. An Ansible re-run would
  clobber the live foundry index, dropping the geomag-model-explorer card along with
  bragi/huginn/muninn/urd/jupyterlab. Static-file edits go live without a
  restart (bind-mounted dir); only `nginx.conf` changes need
  `systemctl --user restart portal.service`.

### 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| SwiftShader WebGL limits/perf | Probed up front (§7, PASS). Keep browser-test scenes small; generous timeouts. Fallbacks if a device lacks WebGL2: WebGL1 + half-float extensions, or NEAREST + shader-side bilinear. |
| First-fetch latency for a new day (minutes) | Shell-stacked, chunked evaluations; background job + progress UI; default day pre-fetched; MIO at 2° (§9.1) cuts the dominant cost ~4×. |
| Day-fetch endpoint is a write surface (triggers VirES traffic + disk writes) | Single-job queue, per-day dedup, validity-range validation of the date; portal is on a trusted network (same posture as muninn's digest box) — revisit if exposed wider. |
| VirES rate limits / service hiccups mid-day-fetch | Resumable per-snapshot fetching; job retries; partial days never published to the manifest. |
| Data size growth (~115 MB per cached day) | Gitignored; disk policy open question §9.3; MIO 2° reduces to ~19 MB/day. |
| MIO physics (primary/secondary, 110 km sheet) | Sum primary+secondary at fetch time; never evaluate at the sheet; only surface + 450 km shells. |
| CI model validity ranges bound the picker | Ranges queried from VirES and enforced server-side; picker greys out out-of-range dates. |
