# deploy/Dockerfile — image for the deployment-setup experimental tier.
# Built from the public GitHub source at a pinned ref. Satisfies the contract:
#   - serves HTTP on $PORT            (default 8000)
#   - serves under $URL_PREFIX        (= /experimental/<name>); responds at $URL_PREFIX/
#       (handled by deploy/asgi.py, which strips the prefix from the ASGI path)
# This app uses no websockets, so --allow-websocket-origin is not applicable.
#
# VirES credentials: pass `-e VIRES_TOKEN=<token>` at run time (get one at
# https://vires.services/accounts/tokens/). deploy/entrypoint.sh installs it via
# `viresclient set_token` and then does the initial model-evaluation fetch so the globe
# has data on first load — same credential pattern as Swarm-DISC/SwarmPAL-processor and
# Swarm-DISC/geospacelab-dashboard. Without a token the app still serves, but with no day data.
#
#   docker run --rm -p 8000:8000 \
#     -e PORT=8000 -e URL_PREFIX=/experimental/geomag-model-explorer \
#     -e VIRES_TOKEN=<token> geomag-model-explorer
#
# DATA NOTE: precomputed tiles (web/data/) are gitignored, so they are not in the image; the
# startup fetch populates them at $GEOMAG_MODEL_EXPLORER_DATA (default /data below), shared by
# fetch + export + serve. Mount a volume there to persist the cache across restarts (otherwise
# it lives in the container's writable layer and the fetch re-runs on every start).

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependency layer — cached unless pyproject.toml / uv.lock change. The `fetch` extra
# (viresclient) is included for VirES model fetches; the dev group (pytest/playwright/httpx)
# and the dev-only `assets` extra are omitted.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra fetch

# Application source.
COPY . .
RUN chmod +x deploy/entrypoint.sh

# $PORT and $URL_PREFIX are provided by deployment-setup at run time; defaults match the
# experimental contract. $URL_PREFIX is consumed by deploy/asgi.py. GEOMAG_MODEL_EXPLORER_DATA
# points the whole cache tree at /data so a mounted volume there persists it (see DATA NOTE).
ENV PORT=8000 \
    URL_PREFIX="" \
    GEOMAG_MODEL_EXPLORER_DATA=/data
EXPOSE 8000

# entrypoint.sh: configure VirES creds -> initial model-evaluation fetch -> exec uvicorn on
# $PORT serving the prefix-aware wrapper (uv run keeps the `fetch` venv for fetch.py/export.py).
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
