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

Carried forward — still open, not yet decisions:

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

**None approved.** [`IDEAS.md`](./IDEAS.md) is the candidate backlog; items
are promoted into numbered phases here only on human approval, with the
decision date recorded.

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
