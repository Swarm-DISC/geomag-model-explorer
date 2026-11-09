# geomag-model-explorer — project rules

Development discipline for this repository, for people and coding agents alike.

1. **Commit → push → redeploy.** Commit early and often, and push every commit to
   the remote before moving on — on as many branches as you like; `main` is the
   released state. A pushed change to served code is not done until the running
   service has been restarted on it (for the systemd deploy:
   `systemctl --user restart geomag-model-explorer-web.service`).
2. **Commit authorship.** Commits use the configured default git identity (system-wide
   or repo-set — never hardcoded in tooling); an agent-assisted commit ends with a
   single `Co-Authored-By:` trailer naming the working agent generically (e.g.
   `Co-Authored-By: Claude <noreply@anthropic.com>`) — no model name/version.
3. **Network/render separation.** `fetch.py` is the only module that talks to
   VirES (viresclient lives in the optional `fetch` extra: `uv sync --extra
   fetch`). `serve.py` may *invoke* fetch.py's day-fetch as a background job
   on a cache miss (Phase 2+), but contains no VirES code itself; `export.py`
   and everything under `web/` read only local files.
4. **Data provenance.** Every snapshot fetched into `data/raw/` is recorded in
   `data/MANIFEST.toml` (model spec, grid, radius, time range, sha256, viresclient
   version). `data/raw/` and `web/data/` are gitignored — reproducible from
   `fetch.py` + `export.py`; the MANIFEST is committed.
5. **Browser-tested or it isn't done.** UI changes are verified with Playwright in
   headless Chromium (real interactions, zero `pageerror` / `console.error`) before
   they are merged to `main`. Branch work runs against a local `serve.py` (or a branch
   preview) with real data — never against a production instance, which serves its own
   data dir. Headless WebGL2 works with SwiftShader (see
   `tests/webgl_probe_result.json`); keep test scenes small, SwiftShader is slow. Tests
   that drive the browser carry the `browser` marker (`uv run pytest -m "not browser"`
   is the quick loop).
6. **No build step.** The frontend is plain ES modules + importmap; three.js is
   vendored into `web/vendor/` and committed. Don't introduce bundlers without
   updating PLAN.md first.
7. **PLAN.md is the source of truth** for scope and phasing. Update it when decisions
   change; record completed phases there rather than starting side documents.
8. **Plan refresh & archival.** When a plan's phases are all complete — or PLAN.md
   has drifted into describing history rather than current state — move its content
   into `HISTORY.md` as a new `## v<N> plan (archived <date>)` section (newest
   first) and write a fresh PLAN.md covering current state, live concerns, and next
   steps. HISTORY.md stays out of the AGENTS.md reading list. Ideas not yet
   human-reviewed stay in IDEAS.md and are never promoted to PLAN.md phases without
   that review.
9. **License.** The project is MIT-licensed: a real `LICENSE` file at the root
   (copyright Swarm DISC).
10. **One branch, one worktree — the main checkout holds the data.** Keep the checkout
    that holds `data/raw` + `web/data` on `main`. Do branch work in per-branch git
    worktrees: run `uv sync` first (per-worktree `.venv`); `data/raw` and `web/data`
    there may be symlinks to the main checkout's data — shared, read-mostly; never run
    `fetch.py`/`export.py` from a worktree (replace the symlink with a real dir if a
    branch must regenerate data). Push, browser-test (rule 5), then merge to `main`.
