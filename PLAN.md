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

One phase approved below. [`IDEAS.md`](./IDEAS.md) is the candidate backlog;
items are promoted into numbered phases here only on human approval, with the
decision date recorded. (v2.13, the timeline viewer, is approved and verified
on its own branch `timeline-viewer`, not yet merged — its spec lives in that
branch's PLAN.md; the number stays claimed.)

### Phase v2.14 — Interface reorganization (three control layers)

**Approved 2026-07-15** (direct user request; RULES §8 gate satisfied by
construction). Branch: `interface-improve`, from `main`/v2.12 by explicit
user decision — NOT stacked on the unmerged `timeline-viewer`.

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
