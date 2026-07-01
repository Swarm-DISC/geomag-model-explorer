#!/usr/bin/env bash
# Container entrypoint for the deployment-setup experimental tier.
#
#   1. Configure VirES credentials from $VIRES_TOKEN (same pattern as
#      Swarm-DISC/SwarmPAL-processor and Swarm-DISC/geospacelab-dashboard:
#      `viresclient set_token https://vires.services/ows <token>`).
#   2. Kick off the model-evaluation fetch on container creation so the globe gains data
#      (validity range + static crust + the default day). This runs in the BACKGROUND so the
#      server is responsive immediately (viresclient retries server errors with a long backoff,
#      so a blocking fetch could stall startup) — data appears once the fetch completes.
#   3. Serve on $PORT under $URL_PREFIX (deploy/asgi.py strips the prefix).
#
# Steps 1-2 are best-effort: a missing/invalid token or a failed fetch is logged, never fatal.
# Env knobs: GEOMAG_MODEL_EXPLORER_SKIP_FETCH=1 skips the startup fetch (e.g. with a
# pre-populated GEOMAG_MODEL_EXPLORER_DATA volume); GEOMAG_MODEL_EXPLORER_DEFAULT_DAY overrides
# the fetched day (defaults to export.DEFAULT_DAY).
set -uo pipefail

run() { uv run --frozen --no-dev --extra fetch "$@"; }
log() { echo "[entrypoint] $*"; }

VIRES_URL="https://vires.services/ows"

# The server serves web/data via StaticFiles; create the cache dirs up front so early requests
# get a clean 404 instead of an error before the fetch has written anything. Honor
# GEOMAG_MODEL_EXPLORER_DATA — a mounted volume relocates the whole cache tree there.
DATA_DIR="${GEOMAG_MODEL_EXPLORER_DATA:-$PWD}"
mkdir -p "$DATA_DIR/web/data" "$DATA_DIR/data/raw"

# 1. VirES credentials -------------------------------------------------------------------
if [ -n "${VIRES_TOKEN:-}" ]; then
  log "configuring viresclient token for $VIRES_URL"
  run viresclient set_token "$VIRES_URL" "$VIRES_TOKEN" || log "WARN: set_token failed"
  run viresclient set_default_server "$VIRES_URL"       || true
else
  log "WARN: VIRES_TOKEN not set — skipping startup fetch; the globe will have no day data until one is fetched"
fi

# 2. Initial model-evaluation fetch (background) -----------------------------------------
# The full UI needs three things: the default day (core/iono/magneto), the static crust, AND
# the curated series (annual/secular/diurnal — including the CHAOS family). The series drive the
# page's "Model series" selector and the study tabs; export none and familiesPresent() collapses
# to {ci}, degrading the UI to the v1 single-model (Swarm CI) view — crust + one day only.
# fetch.py skips VirES calls whose raw npz already exists, so with a persistent data volume only
# the first launch pays the network cost; data_complete() then short-circuits the whole fetch.
data_complete() {
  run python -c 'import json,sys
from export import WEB_DATA
from fetch import SERIES
m = WEB_DATA / "manifest.json"
d = json.loads(m.read_text()) if m.exists() else {}
sys.exit(0 if d.get("days") and set(d.get("series") or {}) >= set(SERIES) else 1)' 2>/dev/null
}

initial_fetch() {
  local day s
  day="${GEOMAG_MODEL_EXPLORER_DEFAULT_DAY:-$(run python -c 'import export; print(export.DEFAULT_DAY)' 2>/dev/null || echo 2020-01-01)}"
  if data_complete; then
    log "cache already complete (day + all series present) — skipping startup fetch"
    return
  fi
  log "background model-evaluation fetch: validity + static crust + day $day + curated series"
  run python fetch.py --validity                                       || log "WARN: validity fetch failed"
  run python fetch.py --static && run python export.py --static        || log "WARN: static/crust fetch failed"
  run python fetch.py --day "$day" && run python export.py --day "$day" || log "WARN: day $day fetch/export failed"
  for s in $(run python -c 'import fetch; print(" ".join(sorted(fetch.SERIES)))' 2>/dev/null); do
    run python fetch.py --series "$s" && run python export.py --series "$s" || log "WARN: series $s fetch/export failed"
  done
  log "background fetch finished"
}
if [ -n "${VIRES_TOKEN:-}" ] && [ -z "${GEOMAG_MODEL_EXPLORER_SKIP_FETCH:-}" ]; then
  initial_fetch &
fi

# 3. Serve (foreground; forward signals so `docker stop` is clean) -----------------------
log "starting server on :${PORT:-8000} (URL_PREFIX='${URL_PREFIX:-}')"
run uvicorn deploy.asgi:app --host 0.0.0.0 --port "${PORT:-8000}" &
server=$!
trap 'kill -TERM "$server" 2>/dev/null' TERM INT
wait "$server"
