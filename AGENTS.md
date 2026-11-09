# AGENTS.md — geomag-model-explorer contributor guide

Agent-agnostic guide for anyone (human or coding agent) working on this repository;
`CLAUDE.md` is a symlink to this file.

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

- **Layout:** `fetch.py` is the only module that talks to VirES (→ `data/raw/` +
  `data/MANIFEST.toml`); `export.py` turns raw npz into quantized tiles under
  `web/data/` + `web/data/manifest.json`; `serve.py` (starlette) serves the static
  frontend, the tiles and the day-fetch job API; `web/` is the no-build frontend
  (ES modules + importmap, three.js vendored). See `README.md` → Layout.
- **Environments:** `uv` project. `uv sync` for dev (serve, export, tests);
  `uv sync --extra fetch` (or `uv run --extra fetch …`) when running `fetch.py`
  (viresclient). The `assets` extra is only needed to regenerate committed textures.
  In a fresh git worktree run `uv sync` first.
- **Tests:** `uv run pytest`. `uv run pytest -m "not browser"` is the quick loop (unit
  + API). The `browser` suites drive the app in headless Chromium via Playwright
  (`uv run playwright install chromium` once); most start their own sandboxed server
  on free ports with synthetic data, while `tests/test_browser.py` targets a live
  service on :8212. WebGL2 + half-float linear filtering work headlessly under
  SwiftShader (`tests/webgl_probe_result.json`) — keep scenes small and timeouts
  generous.
- **Port:** 8212 by default (`uv run uvicorn serve:app --port 8212`).
- **Data location:** `GEOMAG_MODEL_EXPLORER_DATA=<dir>` relocates the data cache
  (raw + tiles) off the checkout; the layout under it mirrors `data/` + `web/data/`.
  A running service serves its own data dir, so verify branch work against a local
  server on the branch's data, not a production instance.
- **VirES credentials:** `~/.viresclient.ini` (see the viresclient docs). Used only by
  `fetch.py` — including when `serve.py` invokes it for on-demand day fetches. Never
  commit tokens or credentials.
- **Day-fetch API token:** `POST /api/days/<date>` is gated by a shared secret from
  `GEOMAG_API_TOKEN` (or the file named by `GEOMAG_API_TOKEN_FILE`), sent as
  `X-API-Token`; with neither set the route fails closed.
- **Deploy:** an example systemd `--user` unit in
  `deploy/geomag-model-explorer-web.service`, and a Docker image
  (`deploy/Dockerfile`, `deploy/entrypoint.sh`, `deploy/asgi.py` for serving under
  `$URL_PREFIX`). The frontend uses only relative URLs, so it works behind a
  reverse proxy under any path prefix.

## When in doubt

Update `PLAN.md` (decisions/status) rather than starting a side document.
