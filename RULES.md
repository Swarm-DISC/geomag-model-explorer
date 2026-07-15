# geomag-model-explorer — project rules

These follow Heimdall's recommended project rules (its `RULES.md` §11 and the adopted
starter `RULES.md`). Where they overlap, this file wins for project specifics.

1. **Commit → push → redeploy.** Commit early and often, and push every commit to
   the `internal` remote before moving on — on as many branches as you like; merging
   to `main` is what publishes. A pushed change to served code is not done until
   `systemctl --user restart geomag-model-explorer-web.service` has run.
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
5. **Browser-tested or it isn't done.** UI changes are verified with Playwright
   (real interactions, zero `pageerror` / `console.error`), per Heimdall's
   browser-test rule (RULES §11). Branch work runs against the branch's Heimdall
   :8300 preview (which mounts the checkout's `web/data`) or a local `serve.py`
   with real data — never against :8212, which serves its own data dir. Headless
   WebGL2 works here (SwiftShader — see `tests/webgl_probe_result.json`); keep
   test scenes small, SwiftShader is slow.
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
   (copyright Swarm DISC), matched and enforced by the gate
   (`[gate] require_license = true`, `license = "MIT"` in `.heimdall.toml`).
