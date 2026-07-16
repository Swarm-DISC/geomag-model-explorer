# Efficiency review — 2026-07-16 (branch `efficiency`)

Measured review of storage, network, server capacity, growth, and model
sampling. Empirical numbers come from decimation/cadence/compression
experiments on the real tiles in `web/data` and gzip timing on this host;
sampling recommendations are grounded in each model's spherical-harmonic
degree and temporal parameterisation (product handbooks; Sabaka et al. 2013;
Finlay et al. 2020 CHAOS-7; Olsen et al. 2017 LCS-1; IGRF-13 Alken et al.).
Items marked **landed** shipped on this branch; the rest are recommendations.

## Footprint (measured)

- `web/data` tiles 2.0 GB (13,387 files): magneto 607M, iono 470M, core 438M,
  core-sv 413M, crust 43M. `data/raw` 8.2 GB (float64 uncompressed npz,
  pre-dating this branch's float32+deflate change).
- A new cached day: ~1.2 GB raw (~0.11 GB after this branch) + ~315 MB tiles
  (magneto+iono 306 MB of that); 195 stacked VirES evals = 396 HTTP requests.
- Wire: first load ≈ 1.4 MB gz (three.js ~420 KB of it); shell change 6 tiles
  ≈ 0.75 MB gz; playback speed 4 ≈ 6.5 tiles/s ≈ 0.44 MB/s gz per viewer.

## Server capacity (4 cores / 8 GB)

The binding constraint was **per-request gzip level 9 on the single uvicorn
event loop** (measured 23.7 MB/s single-core: 2.9 ms per 99 KB tile, 11.5 ms
per 392 KB). Egress (~130 Mbps peak), RAM (~2.5 GB incl. an export job) and
the portal rate limit (POST /api/days only) never bind.

| Scenario | Viewers before p95 > 1 s (pre-branch) | After precompression |
|---|---|---|
| Exploring (shell change / ~10 s) | ~150 | request-overhead-bound, several hundred |
| Playback speed 4 | ~30 | ~90–100 |
| One hard scrubber, no abort | 1 — saturated everyone | tens (abort + coalesce landed) |

Slow links: 3G (0.75 Mbps) cannot sustain playback (needs 3.5 Mbps) and first
paint is ~15–25 s (three.js dominated); 4 Mbps is usable, playback marginal;
25 Mbps comfortable. Immutable tile caching (landed) makes revisits and
playback loops free; the remaining 3G first-visit cost is the vendor bundle
(see "not recommended now" below).

## What landed on this branch

- **Precompressed tiles + HTTP caching** (PLAN ladder rung 3, minus bundling):
  export emits deterministic `.i16.gz` siblings (level 9, mtime=0);
  `serve.TileFiles` serves them with `Content-Encoding: gzip`,
  `Cache-Control: public, max-age=1y, immutable` on tiles, `no-cache` on
  manifest.json. Fallback gzip level 6 (+47% throughput, +0.04% bytes).
  Activation on an existing corpus: `uv run python export.py
  --compress-existing` (idempotent, ~84 s for 2 GB) — run from the primary
  checkout, never a worktree (RULES §10).
- **Manifest parse cache** keyed on stat (the 2 s /api/days poll re-parsed
  85 KB JSON on the event loop).
- **Scrub hygiene**: slider drags coalesce to one texture pass per frame and
  abort superseded in-flight tile fetches (`dataset.abortStaleFetches`).
- **Byte-budget tile LRU** (128 MB GPU, was 64 entries ≈ 26 MB): a one-day
  playback working set (194 small tiles) now stays resident across loops.
- **Raw npz float32 + deflate** (~12×: core bundle 34.5 → 2.9 MB). float32
  error ~6e-8 relative ≪ int16 tile quantization (~3e-5 of qrange). Old
  float64 raw remains readable; provenance of existing snapshots untouched.
- **Timeline exactness** (principle: the globe may approximate, charts must
  not): assembly snaps the pin to the nearest node of the coarsest charted
  grid — node values are exact stored evaluations, and the grids nest
  (2° ⊂ 1° ⊂ 0.5°), so one point is exact for every summed field. Snapped
  coordinates are surfaced in the panel status.

## Addendum (same day): core-field staircase — root cause + fix (landed)

User-reported: core values flat for years, then a jump. Measured: with the
single CMB-sized qrange (3,000,000 nT), the int16 step is 91.56 nT at every
shell; surface SV is 10–90 nT/yr, so stored surface values advanced one code
every ~1–9 years (verified on the quarterly series: node codes
`247×8 246×7 245×7 244×7 243×8`). The pin-snap exactness change exposed it —
bilinear sampling had been blending four staircases into a pseudo-smooth
wobble that was equally wrong (±46 nT). Fix (manifest v5): per-shell qranges
for core (surface ladder 120,000 → 3.66 nT steps; graded d-shells; CMB keeps
the scalar so family overrides still work) and core-sv (surface 500 →
0.015 nT/yr steps), threaded through `storageQrange(field, day, shell)`,
uScale, hover, and `samplePoint`; tile URLs gain a `?v=<qrange-grid>`
cache-bust making the immutable cache safe across re-exports. Requires the
post-merge re-export from raw (no VirES) — see PLAN §2 activation.

## Table A — sampling recommendations (not yet implemented)

Anchor: the colormap resolves ~256 steps ≈ 0.39% of vmax; errors well under
that are invisible on the globe. Errors below are measured (decimate →
bilinear-reconstruct → compare on real tiles), not estimated.

| # | Source · dimension | Current → suggested | Saving | Measured impact / grounding |
|---|---|---|---|---|
| A1 | magneto spatial | 2° → **4°** | −74.6%/tile, −453 MB corpus | rms 0.028% vmax, max 0.12% — 14× under a colormap step. MMA is external deg ≤1–2 (induced ≤5): Nyquist 36–180°. Whole-field grid change — the format already supports it |
| A2 | magneto temporal | 15 min → **1 h** | −74% | rms 0.26% vmax. Measured frame-diffs sit at the quantization floor between coefficient knots every 45/90 min (6 h cycle) — 15-min tiles re-sample straight lines. MMA_SHA_2C deg-1 is estimated in 1.5 h bins (Sabaka 2013) |
| A3 | magneto shells | 16 → **4** (surface, h500, h1000, h1500) | −75% | surface vs h500 measured near-identical (far degree-1 source). With A1+A2: 153 → ~2.5 MB/day |
| A4 | iono temporal | 15 min → **30 min** | −49.5% (−233 MB) | rms 0.21% vmax, worst 2.5% localized in the polar electrojet. **1 h visibly degrades** (max 10%) — do not. MIO is continuous (24/12/8/6 h harmonics); the client already lerps (uMix) |
| A5 | iono spatial | **keep 2°** | — | 4° already visible (max 15.9% vmax in electrojets); MIO deg 60 → 3° Nyquist |
| A6 | core spatial, surface+h-shells | 1° → **3°** on 16/22 shells | −88.7%/tile, −283 MB | rms 0.05% vmax; relief grad err 7%. MCO deg 18/CHAOS deg 20 → Nyquist 9–10°; 3° keeps 3× margin. Needs per-shell grids (below) |
| A7 | core spatial, cmb+d-shells | **keep 1°** (2° floor) | — | CMB k=2 already rms 0.61% / max 2.3% of qrange; CMB flux patches are the payload. Measured band-limit: grids coarser than ~7.5° alias |
| A8 | core-sv spatial | quarterly series ship 2° — acceptable for globe; optionally restore 1° at cmb+d-shells via per-shell grids | — | surface 2° rms 0.43% vmax (at the colormap step); CMB rms 334 nT/yr, worst 2.4 kNT/yr. Charts stay exact regardless via pin-snap |
| A9 | crust spatial, surface | 1° → **0.5°** (user directive: utility-first) | costs +8 MB, +1.3 MB gz per surface visit | LCS-1 (deg 185, Nyquist 0.97°) becomes properly resolved instead of marginal. Hillshade benefits fully; relief displacement is mesh-bound (256×128) — densify at surface to exploit it |
| A10 | crust spatial, altitude | h100–h400 keep 1° (unmeasured); **≥h500 → 2°** | net crust 43 → ~30 MB incl. A9 | 2° at h500: rms ≤0.15% vmax, relief-safe (grad err 14%); crust there is ≤3.8 nT of a 100 nT vmax |
| A11 | core+iono shell ladders | **keep** | — | core deg-18 terms change ~27% per 100 km; iono surface↔h500 amplitudes differ ~2.5× |
| A12 | core/crust per-day snapshots | resolve picked days to the nearest secular epoch (lerp optional) instead of materializing per-day core tiles; disclose with a caption ("core from epoch YYYY-MM") | ~8.6 MB tiles + 34.5 MB raw + 1 VirES eval per day | core drifts ~80 nT/yr → ≤40 nT (0.06% vmax) at yearly epochs, ≤10 nT at quarterly. MCO/CHAOS are order-6 B-splines, 6-month knots — nothing sub-monthly exists to display |
| A13 | secular epoch density | **done on main** (v2.13 quarterly@2°) | — | 3-month steps sample the 6-month spline knots at 2× — Nyquist-adequate |
| A14 | day-boundary tiles | export 96 steps; resolve step 96 to next day's t00 when cached | ~1%/day | t96 ≡ next day's t00, verified byte-identical |

A1–A4 + A6 + A9/A10 belong to **one coordinated manifest-v5 rev**: per-shell
grid metadata (extend the shipped per-series `storageGrid` pattern with a
shell key) + per-field cadence (de-hardcode `stepped === '15min'`, per-field
step mapping on the shared timebar). Combined effect: tile corpus 2.0 →
~0.9 GB, a cached day 315 → ~80 MB, VirES points down proportionally.
Coarser-grid re-exports decimate from existing raw (no refetch); only crust
0.5° needs a one-time VirES fetch (~2 chunks per crust family).

## Table B — remaining infrastructure recommendations

| # | Area | Recommendation |
|---|---|---|
| B3 | Static offload | nginx (gzip_static/sendfile/HTTP-2) in front of tiles moves the ceiling to the NIC. Cross-repo: portal nginx (internal portal repo) must mount the data tree, or a sidecar joins deploy/Dockerfile. Previews keep the pure-Python path |
| B9 | int8 for MIO/MMA (ladder rung 4) | **deprioritized**: Table A dominates it losslessly; int8 at fixed qrange = ~16 colormap steps of banding |
| B10 | Vendor bundle | not recommended now: immutable-caching vendor files is unsafe until paths are versioned (they don't change on upgrade); a tree-shaken three.js (−50–60%) would need a PLAN amendment (RULES §6 no-build-step) |
| B11 | Local SH evaluation (chaosmagpy/ppigrf) | strategic option only — "evaluated via viresclient only" is a project premise (PLAN §1); would need an explicit PLAN amendment + A/B numeric diff vs eval_model. Motivating datapoint: the monthly@1° secular plan projected ~7 h of VirES fetch; quarterly@2° measured 46 min |

## VirES / numpy assessment

Fetch is already efficient: shell-stacked batched requests (all shells of one
field-timestep per `eval_stacked`, 200k-point chunks), fully vectorized numpy
(no per-point loops), static crust fetched once, idempotent raw cache.
Remaining nits (make_grid recomputed twice per snapshot, duplicate
snapshot-complete check, two-pass quantize) are micro — the real levers are
fewer sampled points (Table A) and, strategically, B11.

## Method note

Review ran as a staged agent workflow: exploration (pipeline / serving /
branch-interaction), measurement (spatial decimation, temporal cadence,
compression + gzip timing on real tiles), literature (model parameterisation,
VirES practice), a 4c/8GB capacity model, and a 3-lens adversarial verify
(arithmetic, physics/utility, ops/deploy) whose corrections are folded in.
