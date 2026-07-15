# AGENTS.md — geomag-model-explorer session primer

Agent-agnostic guide; `CLAUDE.md` is a symlink to this file.

**geomag-model-explorer** is a browser-based interactive 3D visualization of geomagnetic fields:
core, crust, ionosphere, and magnetosphere — geomagnetic models served by VirES,
primarily the CI chain (MCO_SHA_2C, MLI_SHA_2C, MIO_SHA_2C, MMA_SHA_2C), plus every
other grid-evaluable VirES model as single-field families (v2.11: CHAOS, IGRF
1900–2025, MCO/MLI/MIO_SHA_2D, MMA_SHA_2F, LCS-1, MF7; CHAOS-MIO/AMPS/MLI_SHA_2E
deliberately unevaluated, greyed with the reason) —
**evaluated via viresclient only** — rendered on a three.js globe with
field toggles (summable), a component picker, an altitude/depth shell slider, an
any-day date picker (default 2020-01-01; days fetched on demand and cached), and a
bottom-docked time slider with playback. Study selection is two dropdowns
(v2.10/v2.11): a primary "Field to explore" (All / Core / Crust / Ionosphere /
Magnetosphere — per-source views over the same globe) and a secondary "Model"
that greys out where a field has no data (PLAN §3; Storms demoted to IDEAS §9,
Secular folded into Core). An ⓘ modal (flag `modelinfo`) documents the served
model behind each on-screen layer.

Read these first, in order:

1. `PLAN.md` — current state, live concerns, next steps. Superseded plan
   generations are archived in `HISTORY.md` (read only when design archaeology
   is needed); the original seed note is `NOTE.md` (historical).
2. `RULES.md` — workflow rules (commit→push→redeploy, fetch/render separation,
   browser testing, plan refresh & archival). Non-negotiable.
3. `IDEAS.md` — candidate next phases. **Not yet human-reviewed** — treat as
   proposals only, never as commitments.

## Quick facts

- **Port:** 8212 (reserved; portal proxy `/foundry/geomag-model-explorer/` once served).
- **Redeploy:** `systemctl --user restart geomag-model-explorer-web.service` (Phase 1+; unit
  in `deploy/` once it exists).
- **Environments:** `uv` project. `uv sync` for dev; `uv sync --extra fetch` only
  when running `fetch.py` (viresclient). Tests: `uv run pytest`.
- **Headless browser:** Playwright + Chromium cached workspace-wide. WebGL2 +
  half-float linear filtering confirmed working headlessly
  (`tests/webgl_probe_result.json`).
- **VirES credentials:** `~/.viresclient.ini` (configured & verified
  2026-06-10). Used only by `fetch.py` — including when `serve.py` invokes it
  for on-demand day fetches (Phase 2+). Never commit tokens.
- **Prior art to consult:**
  `/home/ivaldi/foundry/vizlab/projects/geomag-field-globes/` (viresclient
  eval_model pattern, MANIFEST.toml provenance) and
  `/home/ivaldi/foundry/vizlab/projects/fancy-globe/` (field value ranges,
  nio colormap, time interpolation).

## When in doubt

Update `PLAN.md` (decisions/status) rather than starting a side document.
