# AGENTS.md — geomag-model-explorer session primer

Agent-agnostic guide; `CLAUDE.md` is a symlink to this file.

**geomag-model-explorer** is a browser-based interactive 3D visualization of
Earth's geomagnetic field: models served by VirES — the Swarm CI chain as the
primary four-field family (core, crust, ionosphere, magnetosphere) plus every
other grid-evaluable VirES model as single-field families — **evaluated via
viresclient only**, rendered as colormapped shells on a three.js globe with
studies dropdowns, day/night sunlight, relief displacement, and an ECEF | ECI
frame switch. The authoritative current-state description is `PLAN.md` §1 —
keep it there, not here.

Read these first, in order:

1. `PLAN.md` — current state, live concerns, next steps. Superseded plan
   generations are archived in `HISTORY.md` (read only when design archaeology
   is needed); the original seed note is `NOTE.md` (historical).
2. `RULES.md` — workflow rules (commit→push→redeploy, fetch/render separation,
   browser testing, plan refresh & archival). Non-negotiable.
3. `IDEAS.md` — candidate next phases. **Not yet human-reviewed** — treat as
   proposals only, never as commitments.

## Quick facts

- **Port:** 8212 (`geomag-model-explorer-web.service`; portal proxy
  `/foundry/geomag-model-explorer/`).
- **Redeploy:** `systemctl --user restart geomag-model-explorer-web.service` (unit in
  `deploy/`). Note the service serves its **own data dir** (`GEOMAG_MODEL_EXPLORER_DATA`)
  — browser-verify branch work against the branch's Heimdall **:8300 preview** (which
  mounts the checkout's `web/data`), not :8212.
- **Environments:** `uv` project. `uv sync` for dev; `uv sync --extra fetch` only
  when running `fetch.py` (viresclient). Tests: `uv run pytest`.
- **Headless browser:** Playwright + Chromium cached workspace-wide. WebGL2 +
  half-float linear filtering confirmed working headlessly
  (`tests/webgl_probe_result.json`).
- **VirES credentials:** `~/.viresclient.ini` (configured & verified
  2026-06-10). Used only by `fetch.py` — including when `serve.py` invokes it
  for on-demand day fetches. Never commit tokens.
- **Prior art to consult:**
  `/home/ivaldi/foundry/vizlab/projects/geomag-field-globes/` (viresclient
  eval_model pattern, MANIFEST.toml provenance) and
  `/home/ivaldi/foundry/vizlab/projects/fancy-globe/` (field value ranges,
  nio colormap, time interpolation).

## When in doubt

Update `PLAN.md` (decisions/status) rather than starting a side document.
