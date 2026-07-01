# HISTORY.md — superseded plan generations

Newest first. Each section is a complete working plan as it stood when it was
archived per RULES §8; the current plan is [`PLAN.md`](./PLAN.md). Not part of
the default session reading list — consult only for design archaeology.

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
