# IDEAS.md — candidate features beyond the shipped v1

Suggestions for growing geomag-model-explorer into a tool that helps people *understand* the
geomagnetic field — its four sources, their driving forces, their wildly
different time and spatial scales — and the spherical-harmonic machinery behind
all of it. Collected 2026-06-11 from a code review, a hands-on browser session
against the live app, and web research into prior art and the science context
(sources at the end). These are proposals to discuss, not commitments; PLAN.md
remains the authority on what is actually being built.

**Guiding observations** from playing with v1:

- Each source has a different "axis of interest": **crust** is all spatial
  detail (static), **MMA** is all time domain (spatially just degree ≤ 3),
  **MIO** is a sun-synchronous daily cycle, **core** is spatial at one instant
  but fascinating across years. Features should play to each source's axis
  rather than treating them uniformly.
- The ionospheric Sq pattern and the equatorial electrojet are clearly visible
  in playback today — but nothing on screen shows *why* they sit where they
  sit (the Sun, and magnetic rather than geographic coordinates).
- With all four fields summed, the core swamps everything; |F| wastes half of
  the diverging colormap; nothing currently teaches spherical harmonics even
  though every pixel comes from them.
- A cautionary lesson from prior art: EOX (operators of the VirES web client)
  publicly noted that piling features into their UI made it too complicated,
  pushing advanced use into notebooks. Stay small and opinionated; prefer a
  few flagship ideas done well over feature breadth — §8 proposes the
  mechanisms (flags, modes, lenses, safe layering) to hold that line.

Effort tags: **(S)** small — hours-to-a-day; **(M)** medium — a phase-sized
chunk; **(L)** large — multi-phase.

---

## 1. Make the invisible drivers visible (context overlays)

**1.1 Subsolar marker + day/night terminator (S).** The single
highest-value/lowest-cost addition. The Sq vortices and the equatorial
electrojet follow local noon; today the user sees a blob migrating westward
with no explanation. Solar position is a few lines of analytic astronomy from
the displayed UT; draw the terminator as a great-circle line and the subsolar
point as a sun glyph (shader term or line mesh). Suddenly playback *reads as*
"the ionospheric dynamo follows the Sun".

**1.2 Magnetic-coordinate overlays (M).** Dip equator (I = 0), geomagnetic and
dip poles, optionally a faint quasi-dipole graticule. MIO is *parameterized*
in quasi-dipole coordinates — overlaying the very coordinate system the model
lives in explains why the EEJ hugs the dip equator (which visibly diverges
from the geographic equator over South America). Data path: viresclient
returns `QDLat`/`QDLon`/`MLT` as auxiliaries; export iso-QDLat polylines once
per epoch alongside the tiles. The dip equator can also be contoured
client-side from the existing NEC tiles (where I = 0).

**1.3 Geographic graticule + a few place labels (S).** Orientation aid,
especially on interior (CMB) and high-altitude shells where coastlines are
faint or absent. A 30° lat/lon grid plus labels for the handful of named
features the tool wants to talk about (Kursk, Bangui, South Atlantic
Anomaly).

**1.4 Reference-frame switch: ECEF / ECI / sun-fixed (M).** *(generalized
2026-06-12 from the original "follow the sun" mode; ECEF/ECI subset promoted
to PLAN v2.12 on 2026-07-08 as a plain global toggle — sun-fixed remains the
candidate follow-on, and the FRAMES table in `web/features/frame.js` is built
for it)* A camera-or-globe
rotation mode, surfaced as a three-way reference-frame switch rather than a
bare "spin" toggle:

- **ECEF** (Earth-fixed) — today's behavior; the globe stands still.
- **ECI** (inertial) — the globe rotates with the hour angle during playback,
  so Earth's rotation is *visible* rather than implied: the missing intuition
  that the diurnal cycle IS rotation under the Sun.
- **Sun-fixed** — local time held fixed while the day plays: the Sq current
  system stands still and the *Earth rotates beneath it* — the single most
  direct way to convey that the daily variation is a fixed sun-synchronous
  pattern, not a travelling wave.

Cheap: rotate the globe group by hour angle from the displayed UT — the
solar-position math has existed in `web/sun.js` since v2.6; pose the globe
and the sun overlay (terminator + subsolar glyph, which stays fixed in
ECI/sun-fixed and rotates in ECEF) from one quaternion. Most meaningful on
the **Daily** tab (and Storms windows); a 3-way frame control replaces
nothing, so per §8.2's control budget it should nest under a disclosure or
live only in the Daily lens, with other tabs pinned to ECEF.

## 2. Storms, quiet days, and the time axis

**2.1 Geomagnetic-index strip chart under the time slider (M).** *(absorbed
into §9.3: the indices pipeline serves the Storms tab and lights up the Daily
view for free)* A small
Dst/Hp30 (or SYM-H) trace for the picked day, playhead synced to the time
slider. Watching the MMA shell deepen *exactly as the Dst trace dives* is the
storm story told in one glance — ring current strengthening IS the Dst
depression. Path of least resistance: viresclient co-fetches `Dst`, `Kp`,
`F107` as auxiliaries, so `fetch_day` can grab the day's index series in the
same job at negligible cost; alternatives are GFZ's Kp/Hp30 JSON API and WDC
Kyoto Dst.

**2.2 Event bookmarks / curated day gallery (S).** *(absorbed into §9.4: the
candidate list below becomes the Storms tab's curated window bookmarks)* A
"try these" list next to
the date picker, each with one sentence of why. In-validity candidates
(validity currently ends 2023-11-30):

- **2015-03-17** — St. Patrick's Day storm, first superstorm of cycle 24
  (Dst min −223 nT); two-step main phase.
- **2017-09-07/08** — the X9.3-flare storm period (Dst ≈ −150 nT).
- **2018-08-25/26** — surprise intense storm in a quiet cycle (Dst ≈ −176 nT).
- **2017-08-21** — total solar eclipse over the USA: a deliberately *honest*
  bookmark — MIO is a quiet-time climatology and does **not** contain the
  eclipse signature (see 6.2).
- Quietest day of any month, machine-readable from GFZ's published Q-days
  list — a one-click "quiet vs disturbed" contrast.

The May and October 2024 G5 storms (Gannon storm Dst ≈ −412 nT, the biggest
since 2003) are currently *outside* model validity — worth listing greyed-out
("awaiting model update") and re-checking whenever `--validity` refreshes.

**2.3 A/B day comparison (M).** *(deferred by §9: multi-day window playback
with an indices strip covers the storm-vs-quiet story first; a signed-diff
display mode over series epochs is a candidate later layer)* Pick two days
(storm vs quiet), play them in
sync — either split-screen globes or a signed-difference mode. The shader
already binds two textures per field (floor/ceil timestep); a difference mode
is mostly plumbing plus a colorbar policy.

**2.4 Primary vs induced toggle for MIO and MMA (M).** Both models come in
primary (external/E-region current) + secondary (Earth-induced) parts; VirES
serves the split, the pipeline currently sums them at fetch time. Storing
them separately and adding a toggle turns the app into a demonstration of
**electromagnetic induction in the conducting planet**: the induced part of
MMA lags and decays after a storm onset; the induced part of MIO is the
"ghost" image of Sq from currents induced in the mantle and oceans. No other
public visualization shows this split interactively.

**2.5 Year-lapse / secular-variation playlist (M–L).** *(subsumed by §9's
`secular` series kind)* A second time scale:
one snapshot per month or year across 2014–2023, played as a sequence. Shows
the South Atlantic Anomaly deepening and growing its second minimum southwest
of Africa (developing since ~2015), the north dip pole sprinting toward
Siberia (~35–55 km/yr in the Swarm era), and — on the CMB shell — westward
drift of flux patches (~17 km/yr at the equator). Implementation: the
any-day pipeline already fetches arbitrary days; this is a curated list of
pre-fetched dates plus a playlist UI (and the core field is only 2.4 MB/day,
so a decade of Januaries is ~30 MB).

**2.6 Date-difference / dB/dt mode for the core (M).** *(subsumed by §9's
`secular` series kind; a per-year-normalized diff is a candidate display mode
on such a series)* Render
field(day A) − field(day B), normalized per year. Multi-year baselines make
secular variation directly visible, and slope changes across 2014 / mid-2017
/ 2019–2020 are the Swarm-era **geomagnetic jerks**. Pairs naturally with 2.5.

## 3. Spherical-harmonics playground (the flagship educational idea)

The models *are* spherical-harmonic coefficient sets; the app currently hides
that entirely. Research found interactive SH globes for gravity (ICGEM vis3d)
but **no interactive web tool for the geomagnetic Lowes–Mauersberger
spectrum** — this niche is genuinely open.

**3.1 Degree-truncation / band-pass slider (L).** Render core and crust
through "degrees 1..n only" (or a band). VirES model expressions accept
degree limits (e.g. `MCO_SHA_2C(max_degree=13)` — verify exact syntax against
viresclient docs), so the existing tile pipeline can fetch a ladder of
truncations *without any new evaluation machinery*: it's just more model
strings. Pre-fetch a ladder for one static epoch; the slider sweeps it.
Watching the tilted dipole emerge, then flux lobes, then crustal speckle is
the best available intuition for "what degree n means".

**3.2 Live Lowes–Mauersberger spectrum panel (M).** R_n vs n for core +
crust, with the (a/r)^(2n+4) factor applied live as the shell slider moves.
This single plot explains two things the app already shows but doesn't
explain: why core and crust can be separated at all (the knee at n ≈ 13–15,
known since Langel & Estes 1982), and why crustal anomalies collapse with
altitude while the core barely fades (degree-dependent attenuation — Bangui
goes from ~−1000 nT at ground to ~−22 nT at 400 km). Needs the Gauss
coefficients shipped to the browser — a few kB for core, ~100 kB-scale for
crust — and ~20 lines of JS. Clicking a degree could band-pass the globe
(ties into 3.1).

**3.3 Single-harmonic explorer (M).** Pick (n, m), see Y_n^m on the globe —
ICGEM's gravity idiom transplanted to geomagnetism — and, better, see that
term's actual g_n^m/h_n^m-weighted contribution to the real field. Pure
client-side math (associated Legendre functions), zero data fetch; could
live on a separate "learn" page to keep the main UI lean.

**3.4 "Build the field" animation (S, given 3.1).** Auto-play cumulative
degrees 1 → n_max as an intro/attract mode.

**3.5 Dipole-only mode + moment/tilt readout (S–M).** A "n = 1" preset
showing the tilted dipole with a numeric readout of dipole moment and tilt
for the picked epoch. Across epochs (2.5) it shows the ~5%/century moment
decay — the number behind every "is the field reversing?" headline.

## 4. Vector nature & derived quantities

**4.1 D / I / H display options (S).** The tiles already store native NEC
vectors, so declination `atan2(E, N)`, inclination, and horizontal intensity
are one shader function each — no new data. Declination is the bridge to
everyday experience ("where does a compass point, and why is it wrong?").

**4.2 Isoline overlays (M).** Agonic/isogonic lines (D contours), the dip
equator (I = 0), and an |F| threshold contour outlining the South Atlantic
Anomaly (e.g. F < 24,000 nT). Marching squares in JS over the CPU-side int16
tiles the hover readout already keeps. The NOAA historical-declination
viewer shows how readable isogonics + pole markers are.

**4.3 Horizontal-vector glyphs or streamlines (M).** An arrow/streamline
layer for the horizontal (N, E) component on the current shell. The Sq
"vortices" become actual visible vortices instead of color blobs; over the
crust it shows anomaly-scale compass deflection. Prior art: SuperMAG's
station vectors, nullschool's flow rendering.

**4.4 Field-line tracing (L — the deferred classic).** Click to seed a field
line, integrate through the core (+ optionally crust) field, drawn in 3D
between shells. Feasible client-side: ship the MCO Gauss coefficients (low
degree) and evaluate B(r, θ, φ) in JS — RK4 over a degree-≤20 SH sum is
microseconds per step. Unlocks the *between-shells* space the shell slider
skips over, shows conjugate points and the asymmetry of the real field vs a
dipole, and visually explains the SAA as the place field lines sag closest
to Earth. VirES does region-seeded tracing; a click-to-trace globe is more
playful.

**4.5 Hover readout upgrades (S).** Per-field breakdown (the CPU lookup
already computes each field separately before summing), all components +
D/I at once, and pinnable probes; a pinned probe could sparkline its value
over the day from tiles already in cache.

## 5. Display & UX polish (friction found while playing)

- **5.1 Sequential colormap for F (S).** |F| is always positive; the
  diverging nio map wastes half its range and renders the surface field as
  undifferentiated red. Switch to a sequential ramp when component = F.
- **5.2 Smarter disabled field toggles (S).** A field's checkbox is disabled
  whenever the current shell lacks its data, and nothing says why; clicking
  a disabled toggle should jump to that field's nearest shell (this tripped
  up scripted interaction twice during review).
- **5.3 Camera adapts to shell radius (S).** At the 1 R_E magnetosphere
  shell the camera stays at ~2.8 R_E and the shell fills the screen; pull
  back when the shell grows, and add a "go inside" preset for the CMB (the
  from-inside mantle view of core flux patches is spectacular and currently
  undiscoverable).
- **5.4 Permalink state (S).** *(promoted to PLAN v2.1, shipped 2026-06-11)*
  Encode day/time/fields/component/shell/camera
  in the URL hash. Makes every bookmark in 2.2 a shareable link and costs
  almost nothing.
- **5.5 Keyboard time-stepping (S).** nullschool's j/k idiom, plus
  space = play/pause.
- **5.6 Colorbar histogram + scale options (M).** A value histogram behind
  the colorbar, draggable vmax, and an asinh/log option for shells (CMB)
  whose dynamic range defeats a linear map even at p99.
- **5.7 Small-multiples view (M–L).** Two or four synced globes, one per
  field — the honest answer to "core swamps the sum" and the clearest way to
  show four sources with four different characters at the same instant.
- **5.8 Animation export (M).** Render playback to WebM/GIF for sharing;
  pairs with 2.2's storm days.

## 6. Honesty & guidance

**6.1 "What am I looking at?" guided tour (M).** A handful of narrative
steps that drive the existing controls: surface crust → shell slider up
(anomalies fade — why?) → CMB (the field's true face) → iono day-cycle with
terminator on → storm-day MMA with the Dst trace. Prior art: VirES's
embedded tutorial, NCEI's story map. This converts the feature set into the
*understanding* the project aims for, and it's mostly writing, not code.

**6.2 Model-caveat panel (S). ✅ Shipped v2.11** (flag `modelinfo`,
`web/features/model-info.js`): One honest paragraph per source, surfaced
from an "ⓘ": MIO is a quiet-time climatology (no storms, no eclipse
signatures — the 2017-08-21 eclipse bookmark demonstrates the gap), MMA is
degree ≤ 3 (no substorm structure, no auroral electrojets), MLI is truncated
(no short-wavelength anomalies), MCO stops at the jerk-resolution limit.
Educational tools earn trust by showing their seams.

**6.3 Validity-refresh nudge (S).** The picker currently tops out at
2023-11-30; periodically re-run `--validity` (or check at serve start) so
new CI product releases automatically extend the range — the 2024 G5 storms
are the biggest prize waiting behind this.

## 7. Bigger swings (flagged, probably out of scope)

- **Century mode** via IGRF: *(moved into scope 2026-06-11 — see §9.2; the
  `sv-century@igrf` secular series is the planned vehicle)*. The original
  hesitation — a second model family and its validity logic — is now handled
  by §9's family-inside-the-series design. NOAA's 1590–2020 declination
  viewer still owns the deep-history niche (gufm1 is not in VirES).
- **Other model families** (CHAOS, WDMAM, LCS-1, MF7): *(moved into scope
  2026-06-11 — see §9.2)*. Requires the `available_models()` probe first;
  WDMAM is likely not served by VirES at all, in which case the crust
  alternatives are LCS-1/MF7.
- **Sonification** of storm playback or secular variation (ESA/DTU prior
  art); charming, low educational density.
- **Observatory / Swarm-track residual overlays**: powerful (it is how the
  models are *made*) but this is VirES web client territory — the complexity
  trap EOX warned about.
- **Aurora oval overlay** (NOAA OVATION JSON): visually appealing, but a
  different data family with a different cadence and no model link to the
  CI chain.
- **Volumetric/cross-section rendering** between shells: physically honest
  radial interpolation needs per-degree (a/r)^(n+2) continuation, i.e.
  client-side SH evaluation — if 4.4 ships, a meridional slice plane becomes
  feasible and would be genuinely novel.

## 8. Wrangling feature creep: modularity, modes, and safe layering

This document is itself a hazard: ~35 ideas pointed at a codebase whose charm
is that it's ~900 lines of frontend with one shader and one state object. Two
distinct costs grow if features land naively — **engineering coupling** (every
feature touching `main.js`/`ui.js`/the shader makes the next feature harder)
and **review burden** (every knob multiplies the interactions a human must
perform to test, and the combinations a browser test must cover). Proposals,
in increasing order of ambition:

### 8.1 Engineering: keep the core small, make the seams explicit

- **A feature registry with deploy-time flags.** *(promoted to PLAN v2.1,
  shipped 2026-06-11)* One `features` config
  (served by `serve.py` alongside `/api/days`, sourced from a config file or
  env) listing which features this deployment enables. The frontend loads
  feature modules via dynamic `import()` only when enabled — consistent with
  the no-build rule, and the core stays exactly as fast and small as v1 when
  everything is off. Disabling a misbehaving feature becomes a config edit +
  restart, not a revert.
- **An overlay contract.** Most ideas in §1 and §4 are *overlays* (terminator,
  graticule, isolines, markers, vectors, strip chart): give them one narrow
  interface — roughly *attach(scene/ui), update(state), dispose()* — and
  forbid them from touching the field shader or each other. Overlays then
  compose freely and can be deleted freely; coupling is structurally capped.
- **Two cost classes, budgeted separately.** *Cheap class:* pure client-side
  math or reuse of existing tiles (D/I/H, isolines, SH explorer, hover
  upgrades, permalinks). *Expensive class:* anything adding a shader term or
  a **new tile axis** (primary/induced split, degree ladders, day-pair
  diffs — each multiplies storage, manifest schema, fetch time, and test
  surface). Rule of thumb: at most one new data axis in flight at a time, and
  every axis must be optional in the manifest so its absence degrades to v1
  behavior.
- **Satellite pages over a mega-app.** The SH playground (§3.3) and guided
  tour (§6.1) work better as separate pages sharing `vendor/`, `dataset.js`
  and the textures, not as panels in the main UI. Multi-page keeps each page
  reviewable in isolation and is the strongest anti-coupling move available —
  the main globe never learns the features exist.

### 8.2 User-facing: modes and lenses instead of more knobs

- **Viewer modes as named flag-presets, not codepaths.** *Simple* (surface,
  one field at a time, terminator on, play button — for the visitor with 90
  seconds), *Explorer* (≈ today's v1), *Expert* (everything enabled). A mode
  is literally a saved set of feature flags + initial state, so there is one
  codebase and zero mode-specific logic; the mode switch is itself just a
  permalink.
- **Thematic lenses.** Curated control-subsets around one story each: *Storm*
  (MMA + Dst strip + event bookmarks), *Dynamo* (CMB + year-lapse + SV
  diff), *Compass* (D/I + isogonics + pole markers), *Harmonics* (degree
  tools + spectrum). A lens shows only its relevant controls. This converts N
  independent features into a handful of coherent destinations — and each
  lens doubles as the unit of documentation, testing, and feedback ("the
  Storm lens feels wrong" beats "checkbox #14 confused me"). *(Concretized
  2026-06-11: lenses ship as the study tabs of §9.4 — a tab is a lens plus a
  time-axis binding.)*
- **A hard control budget.** Cap visible top-level controls (today: 4
  toggles, 4 radios, 2 sliders, picker, time bar — already near the limit).
  Any new control must nest under a disclosure, live in a lens, or replace
  something. The EOX precedent is what failure looks like.

### 8.3 Layering features in safely over time

- **Ship dark, enable deliberately.** Every feature lands behind its flag,
  **default off**, in its own commit — the existing
  commit → push → redeploy → browser-test cadence (RULES) is unchanged, but
  "deployed" and "enabled" decouple. A feature is enabled in the deploy
  config only after its browser test passes against the live service; if it
  misbehaves in real use, it's flipped off without touching git history.
- **A definition of done per feature.** Each feature ships with four things:
  its flag, a *permalink demo state* showing it off, one Playwright scenario
  exercising it, and a one-line entry in README/the gallery (8.4). No
  exceptions — this is what keeps the system reviewable at feature 20.
- **Additive-only data evolution.** New tile axes and manifest keys are only
  ever added, never repurposed; `manifest.json` already carries a `version`
  field — bump it on schema growth and have the frontend treat unknown keys
  as ignorable and missing optional axes as "feature unavailable". Old cached
  days stay valid forever, rollback is a `git revert` + restart, and a v1
  frontend pointed at v5 data still works.
- **Permalink stability as a public contract.** Once §5.4 ships, shared URLs
  are the product's memory: unknown params are ignored, removed features
  degrade to defaults rather than erroring. This is also what makes flags
  safe to retire.
- **An experimental tier + sunset reviews.** Features can be marked
  *experimental* (visible only via something like `?labs=1`) to gather
  feedback without commitment. Periodically cull: a feature that complicates
  a refactor and has no champion gets deleted — flags and the overlay
  contract make deletion a small diff, and git remembers.

### 8.4 Keeping review and feedback cheap

- **A permalink gallery as the review surface.** Auto-generate (from the
  registry) one page of links: each enabled feature's demo state, each
  lens, each event bookmark. Human review of a release = click through one
  page; "play about with it" stops scaling with the number of knobs.
- **Bound the test combinatorics the same way.** The browser suite walks that
  same permalink list — load, assert zero console errors, screenshot, one
  interaction each — plus the existing v1 core tests. Per-feature isolation
  tests + lens-preset combinations *instead of* the full cross-product of
  fields × components × shells × overlays × time, which is already
  untestable at ~10 features.
- **Feedback built into sharing.** A "share this view" button (state-encoded
  URL, §5.4) doubles as the feedback channel: a reported issue arrives as the
  exact reproducible view, not a prose description.

## 9. Studies: multi-timescale & multi-model (scope widened 2026-06-11)

**Human-directed scope decision (2026-06-11):** the app should show model
behaviours that live on *incompatible time regimes* — century-scale core
secular variation (sparse sampling, fixed time of day), daily/seasonal/decadal
MIO change (seasonal/decadal sampled at a fixed time of day), storm-vs-quiet
MIO+MMA response alongside activity indices — and compare different model
series (CI / CHAOS / IGRF / WDMAM-if-available). The *scope* is sanctioned;
the designs below remain proposals refined per-phase. Two further decisions
taken the same day: the **seasonal MIO study proves the new axis first**, and
the richer interface is a **single-page tab strip** (satellite pages stay
reserved for the SH playground and guided tour, per §8.1).

The reconciliation problem: today's data axis is exactly one time regime —
(field, shell, **day**, 97 × 15-min steps). Each study needs a different
sampling rule, but none needs new rendering machinery: the shader already
interpolates between two epoch textures by `uMix`, and that works for *any*
ordered epoch list. So the design generalizes the time axis once, and hangs
everything else off it.

### 9.1 The `series` abstraction — the one new data axis

A **series** is an ordered, monotone list of ISO epochs with an id, a kind, a
field set, an optional per-field shell subset, and a model family (default
`CI`). Today's day is retroactively a series of kind `diurnal`. Kinds:

| kind      | epochs                                  | example (proposed)                     | storage |
|-----------|-----------------------------------------|----------------------------------------|---------|
| `diurnal` | 97 × 15 min within one day (legacy)     | `2020-01-01`                           | existing day layout, untouched |
| `annual`  | fixed time-of-day, weekly over a year   | `mio-seasonal-2020` (52 × 12:00 UT, iono ×2 shells, **~10 MB**) | materialized |
| `secular` | fixed time-of-day, yearly over decades  | `sv-century@igrf` (×126, core {cmb, surface}, **~100 MB**)      | materialized |
| `window`  | concatenated 15-min steps, N consecutive days | `storm-2015-03-17` (4 days)      | **virtual** — zero new tiles |

Two storage strategies, and this is the key economy:

- **Materialized** series get new tiles at
  `web/data/<field>/<shell>/<series-id>/tNNN.i16` (3-digit step; the legacy
  2-digit day layout is untouched — additive only, per §8.3). Series ids are
  filesystem-safe slugs.
- **Virtual** (`window`) series derive their epochs from member days already
  in the day cache: day *k*'s t96 ≡ day *k+1*'s t00, so the seam is exact and
  the storm study — the data-heavy one — costs only the already-budgeted
  ~60 MB/day.

Pipeline: a curated `SERIES` catalog in `fetch.py` next to `FIELDS` (mirrors
the existing pattern, unit-testable; *not* user-generated — keeps the
day-fetch write surface tiny). `fetch.py --series <id>` expands the epoch
rule and reuses `eval_stacked` per epoch (resumable via `snapshot_complete`;
raw under `data/raw/series/<id>/<field>/tNNN.npz`; MANIFEST.toml provenance
per series·field). `export.py --series <id>` reuses the quantize/stats
machinery and adds an optional `series` map to `manifest.json` (version → 2;
unknown keys ignorable; absence degrades to v1):

```
"series": { "<id>": { "kind", "fields": [...], "epochs": [ISO...],
                      "fixed_time", "shells": {field: [slugs]},
                      "days": [...],          # window kind only
                      "stats": {field: {shell: {min,max,p99}}},
                      "exported_at" } }
```

A series may restrict shells per field (the century series wants
{cmb, surface}, not all 11 core shells). A field absent from a series is
simply unavailable on that tab (toggle disabled); static crust is timeless
and available everywhere.

Frontend: the one real core change is generalizing `state.minutes` (0..1440)
to `state.pos` (float epoch index) — `applyTextures`/playback only ever need
floor/ceil indices plus `uMix`, and linear interpolation is honest for all
these smooth series (15-min iono, weekly Sq climatology, yearly SV). **This
refactor lands first, alone, with Daily behavior bit-identical and the suite
green** (Daily: `pos = minutes/15`; permalink `t=HH:MM` preserved).
`dataset.js` gains a series-aware `tileURL` (window kind resolves to existing
day paths); the time bar's label format and playback speed become per-kind.

### 9.2 Model family — a parameter of a series, not a path axis

`FieldSpec.model` is currently hard-coded per field. Evolution: a `FAMILIES`
table in `fetch.py` mapping (family, layer) → VirES model spec — `CI`
(today's four), `IGRF` (core, ~1900–2030: the century enabler, since
MCO_SHA_2C validity is only 2013-11→2023-11), `CHAOS` (CHAOS-Core /
CHAOS-Static / CHAOS-MMA), crust alternatives (LCS-1, MF7). The family lives
*inside* the series entry and its slug (`sv-century@igrf`); since the series
id is already the path key, **no new tile-path dimension appears**. This
honors §8.1's one-axis-at-a-time rule: the series axis is *the* axis; family
rides inside it and ships only after the series infrastructure is proven.
"CHAOS vs CI on the same day" is then just another materialized diurnal
series; a signed-diff display mode over two series (cf. 2.3/2.6) is a
candidate later layer.

**Probe first, don't assume:** run `SwarmRequest.available_models()` /
`get_model_info()` to confirm exact model names and validities for IGRF,
CHAOS-Core, LCS-1, MF7 — and whether WDMAM is served at all (likely **not**;
if absent, the crust family substitutes LCS-1/MF7 and the docs say so). The
"viresclient only" rule (RULES §3) is unchanged throughout.

### 9.3 Indices pipeline (cheap cost class)

`fetch.py --indices <start> [end]` → viresclient auxiliaries (`Dst`, `Kp`,
`F107`) at coarse sampling (e.g. PT5M) → `web/data/indices/<day>.json`
(~15 KB/day; window tabs concatenate client-side). The day-fetch job in
`serve.py` appends an indices step, non-fatal on failure; manifest day/series
entries gain an optional `indices` key. Consumed by
`web/features/indices.js` — an overlay-contract strip chart above the time
slider, playhead-synced, behind flag `indices`. This *is* 2.1, so the Daily
tab gets the Dst strip for free. Honest caveat: auxiliaries ride the Swarm
collections, so no strip on the century tab (pre-2013 epochs).

### 9.4 The interface: study tabs on a single page

A **tab** is a declarative binding `{id, label, series-kind filter, visible
controls, defaults, overlays}` — §8.2's thematic lenses made concrete, behind
flag `studies` (flag off = exactly v1).

- **Daily** (default; ≡ v1): date picker + 97-step bar. A hash with only v1
  keys ⇒ Daily tab, so every existing permalink keeps working.
- **Seasons**: annual-series select; slider labelled in weeks/dates; iono
  (+crust).
- **Secular**: secular-series select; slider in years; core (+crust);
  defaults to colorbar lock at the series-wide p99 — secular change is
  invisible under auto-ranging, which is exactly what the v2.2 lock was
  built for.
- **Storms**: window select from curated bookmarks (the 2.2 list:
  2015-03-17, 2017-09-07/08, 2018-08-25/26, …); multi-day bar + indices
  strip.

Control budget (§8.2) is *gated by the tab*: each tab shows at most the v1
control count — outside Daily, a series/window `<select>` replaces the date
picker. Permalink gains `tab=` and `e=<ISO epoch>` (mapped to the nearest
epoch — robust to series edits; garbage ignored per the stability contract).
Tests: one demo permalink + one Playwright scenario per tab; the permalink
gallery (§8.4) lists tabs × series.

*2026-06-12:* a per-source rethink of this tab strip is proposed in §9.7 —
the declarative tab binding survives; the labels, gating and a new
page-level family selector are what change.

### 9.5 Storage & sequencing

Tile = nlon·nlat·3·2 B (core 1°: ~392 KB; iono/MMA 2°: ~99 KB). Materialized
series are small (~10–100 MB each, see the table); storm windows reuse the
~60 MB/day cache but make *multi-day* caching deliberate — scaling-ladder
rung 1 (drop `data/raw/` after export) becomes timely (PLAN §2). Fetch cost
is equally modest: the weekly seasonal series is 52 evaluations, a quarter of
one day's 195.

Sequencing (the phase ladder lives in PLAN §3): series axis first via the
cheapest study (Seasons, CI-only — proves fetch → export → manifest → tabs →
permalink → tests end-to-end for ~10 MB), then the virtual window kind +
indices (Storms — demoted from the PLAN phase ladder 2026-06-12, a proposal
here again), then the family axis (Secular, after the probe). One new
data axis in flight at a time, per §8.1.

### 9.6 Core secular variation as a derived field (proposed 2026-06-12)

SV is itself a spherical-harmonic field: all time dependence of the
internal field lives in the Gauss coefficients g(t), h(t), so
Ḃ = −∇(∂V/∂t) is the same expansion evaluated with ġ, ḣ — same
(a/r)^(n+2) continuation per degree, same NEC components, same shell
ladder. Units **nT/yr**.

viresclient's `eval_model` has no time-derivative operator and no served
SV product, but the models' time bases make a **centered finite
difference honest**: Ḃ(t₀) ≈ [B(t₀+6 mo) − B(t₀−6 mo)] / 1 yr.
MCO_SHA_2C parameterizes coefficients with low-order B-splines at
~6-month knots (believed piecewise-linear — *confirm in the product doc
before building*), so the difference is the exact knot-to-knot slope
averaged over at most two segments; for CHAOS-Core (order-6 splines) the
O(Δ²) error is far below display resolution; IGRF's derivative is a
5-year staircase. Differencing MCO alone keeps external/induced fields
out of the estimate. Implementation cost is trivial and stays inside the
"viresclient only" rule (RULES §3): two `eval_stacked` calls instead of
one (core is 1 eval per cached day today), Ḃ stored as NEC triples →
int16 tiles → manifest, pipeline untouched; a `core-sv` pseudo-field with
its own qrange/vmax.

Cautions and probes:

- **Units rule:** nT/yr must never sum with nT — the field toggles sum on
  the GPU, so SV cannot be a fifth checkbox. Tab gating (the Seasons
  mechanism, §9.4) solves it by construction. The manifest field record
  gains a `units` key so the colorbar and hover readout print nT/yr.
- **F component** of SV tiles shows |Ḃ| (magnitude of the SV vector) —
  which is *not* dF/dt (that is B·Ḃ/|B| and needs both fields in the
  shader). Label honestly.
- **Magnitudes** (probe empirically before fixing qrange): surface |Ḃ|
  peaks ~100–150 nT/yr today; at the CMB the SV spectrum is blue (power
  rises with degree n), so downward continuation amplifies it into
  10³–10⁴ nT/yr small-scale flux patches — the spectacular view.
- **Validity edges:** t₀ ± 6 mo must stay inside model validity
  (2013-11‥2023-11 at last check); clamp or fall back to a one-sided
  difference near the ends.
- Follow-on someday: secular *acceleration* (nT/yr², second difference) —
  the geomagnetic-jerk quantity, same machinery again.

A yearly SV series 2014→2023 (CI-only, {cmb, surface} + a ladder subset)
gives a Secular/Core tab its content without waiting for the family axis
(§9.2); the IGRF century series then extends the same view back to ~1900.
This also subsumes the dB/dt half of 2.6.

### 9.7 Interface rethink: per-source tabs under a model-series selector (human-directed 2026-06-12)

Direction from the human — sketched here, **to be settled in a design
discussion with the human at implementation time** (recorded as a
mandatory checkpoint in PLAN v2.9), not decided unilaterally:

- Rethink the top level so tabs read as **per-source studies** rather
  than per-time-regime: e.g. rename "Daily" → **"Combined models"**; add
  a **"Core"** tab whose display toggles between **B and dB/dt** (§9.6);
  by extension an "Ionosphere" tab could absorb today's Seasons.
- **Above** the tab strip, a **"Model series" dropdown** selects the
  model family for the whole page — start with **Swarm-CI** and
  **CHAOS** — making family a page-level lens. This refines §9.2 (there,
  family rides inside the series id): the storage/path design is
  unchanged; only the control surface moves up a level.
- Tab gating still enforces the control budget (§8.2) and the units rule
  (§9.6).

Open questions for that discussion: what becomes of the Seasons label and
the per-tab date/series pickers; whether "Combined models" can show SV at
all or it stays Core-tab-only; how the dropdown composes with permalinks
(a `family=` key?); how families missing a layer present (decided 2026-06-12:
CHAOS ships with **no ionospheric layer — skip "CHAOS-MIO", no substitute**;
whether the iono tab/toggle greys out or hides under CHAOS is still for the
discussion); and how existing v1 permalinks map onto the renamed tabs (the
stability contract must hold).

## Suggested ordering

1. **Governance first (S):** the feature-flag registry + permalink state
   (5.4) — every later idea assumes these exist; they are an afternoon now
   and a rewrite later.
2. **Quick wins, one afternoon each (S):** terminator + sun marker (1.1),
   sequential F colormap (5.1), D/I/H components (4.1),
   event bookmarks (2.2), camera/shell fixes (5.2, 5.3).
3. **One temporal flagship (M):** index strip chart (2.1) — it upgrades the
   already-working storm playback into a cause-and-effect story.
4. **One structural flagship (M–L):** the SH playground (3.1 + 3.2) — unique
   on the open web, directly serves the "understand spherical harmonics"
   goal, and reuses the existing tile pipeline — as a satellite page (8.1).
5. Then a sunset review (8.3) before adding more.

**Studies ladder (appended 2026-06-11, scope-approved — see §9 and PLAN §3):**
the series foundation + Seasons tab first (proves the axis at minimum cost),
then Storms + indices (absorbs items 2.1/2.2 and the temporal flagship above —
demoted from the PLAN phase ladder 2026-06-12, a proposal again), then the
model-family axis + Secular tab. The studies ladder interleaves with, rather
than replaces, the quick wins above.

---

## Research sources (verified 2026-06-11)

Prior art: [VirES for Swarm](https://vires.services/) ([EOX 2015](https://eox.at/2015/11/vires-swarm-and-magnetic-model-data-visualization/),
[2021 update](https://eox.at/2021/09/vires-services-update-2021/)) ·
[NCEI Historical Declination Viewer](https://www.ncei.noaa.gov/maps/historical-declination/) ·
[earth.nullschool.net](https://earth.nullschool.net/about) ·
[NASA CCMC visualization / iSWA](https://ccmc.gsfc.nasa.gov/visualization/) ·
[SuperMAG](https://supermag.jhuapl.edu/) · [AMPERE](http://ampere.jhuapl.edu) ·
[ICGEM 3D SH visualizer](https://icgem.gfz-potsdam.de/vis3d/tutorial) ·
[Exploring our Magnetic Earth (Swarm DISC)](https://book.magneticearth.org/) ·
[ESA "sounds of the magnetic field"](https://www.esa.int/Applications/Observing_the_Earth/FutureEO/Swarm/The_scary_sound_of_Earth_s_magnetic_field) ·
[NOAA CrowdMag](https://www.ncei.noaa.gov/products/crowdmag-magnetic-data)

Science: [Swarm-era jerks (EPS 2021)](https://earth-planets-space.springeropen.com/articles/10.1186/s40623-021-01504-2) ·
[SAA weakening/splitting (ESA 2020)](https://www.esa.int/Applications/Observing_the_Earth/FutureEO/Swarm/Swarm_probes_weakening_of_Earth_s_magnetic_field) ·
[pole drift (Livermore et al.)](https://arxiv.org/pdf/2010.11033) ·
[St. Patrick's Day storm (EPS)](https://earth-planets-space.springeropen.com/articles/10.1186/s40623-016-0525-y) ·
[Gannon storm (Geosci. Commun.)](https://gc.copernicus.org/articles/7/297/2024/) ·
[Langel & Estes 1982 spectrum knee](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/GL009i004p00250) ·
[CM6 parameterization (Sabaka et al. 2020)](https://ntrs.nasa.gov/api/citations/20205002861/downloads/Sabaka%20EPSP-D-20-00051_REV1.pdf) ·
[MIO product handbook](https://swarmhandbook.earth.esa.int/catalogue/SW_MIO_SHA_2C)

Indices: [GFZ Kp/Hp30 + Q-days](https://kp.gfz.de/en/data) ·
[WDC Kyoto Dst](https://wdc.kugi.kyoto-u.ac.jp/dstdir/) ·
[DTU RC index](http://www.spacecenter.dk/files/magnetic-models/RC/) ·
[NOAA SWPC JSON products](https://services.swpc.noaa.gov/products/) ·
[viresclient auxiliaries (Dst, Kp, F10.7, QDLat, MLT)](https://viresclient.readthedocs.io/en/latest/available_parameters.html)
