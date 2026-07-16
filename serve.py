"""geomag-model-explorer web service: static frontend + tiles + day-fetch API on :8212.

Contains no VirES code (RULES §3) — day fetches run fetch.py and export.py as
subprocesses (overridable via GEOMAG_MODEL_EXPLORER_FETCH_CMD / GEOMAG_MODEL_EXPLORER_EXPORT_CMD, the
test seam). One fetch job at a time; concurrent picks queue; a day exists for
clients iff it appears in web/data/manifest.json (export publishes it last,
atomically).

Behind the portal at /foundry/geomag-model-explorer/ (the frontend uses only relative
URLs, so no prefix handling is needed here).

    uv run --extra fetch uvicorn serve:app --host 0.0.0.0 --port 8212

GEOMAG_MODEL_EXPLORER_DATA relocates the cache tree (default: the checkout) — see PLAN §5.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import shlex
import subprocess
import threading
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from _auth import RateLimiter, check_token

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA_ROOT = Path(os.environ.get("GEOMAG_MODEL_EXPLORER_DATA", str(ROOT)))
WEB_DATA = DATA_ROOT / "web" / "data"
MANIFEST_JSON = WEB_DATA / "manifest.json"
VALIDITY_PATH = DATA_ROOT / "data" / "validity.json"
RAW = DATA_ROOT / "data" / "raw"
FEATURES_PATH = Path(os.environ.get("GEOMAG_MODEL_EXPLORER_FEATURES",
                                    str(ROOT / "features.json")))

DEFAULT_FETCH_CMD = "uv run --extra fetch python fetch.py"
DEFAULT_EXPORT_CMD = "uv run --extra fetch python export.py"


_manifest_cache: tuple[tuple[int, int], dict] | None = None  # ((mtime_ns, size), parsed)


def read_manifest() -> dict:
    """Parsed manifest, cached on (mtime_ns, size). The manifest is rewritten
    atomically by export.py (tmp + os.replace), so a stat change is the exact
    publish signal; the frontend polls /api/days every 2 s during a fetch and
    each poll otherwise re-reads + re-parses 85 KB on the event loop."""
    global _manifest_cache
    try:
        st = MANIFEST_JSON.stat()
    except OSError:
        return {"default_day": None, "validity": None, "days": {}}
    key = (st.st_mtime_ns, st.st_size)
    if _manifest_cache is None or _manifest_cache[0] != key:
        _manifest_cache = (key, json.loads(MANIFEST_JSON.read_text()))
    return _manifest_cache[1]


def read_validity() -> dict | None:
    if VALIDITY_PATH.exists():
        return json.loads(VALIDITY_PATH.read_text())
    return None


def read_features() -> dict:
    """Deploy-time feature flags (RULES §8 governance; IDEAS §8.1). A missing
    or broken config means every feature is off — i.e. v1 behavior."""
    try:
        flags = json.loads(FEATURES_PATH.read_text())
        return flags if isinstance(flags, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


class TileFiles(StaticFiles):
    """StaticFiles + the tile-serving policy (PLAN §2 scaling ladder, rung 3):

    - `<tile>.i16.gz` siblings (export.py emits them) are served with
      `Content-Encoding: gzip` when the client accepts it, so tiles skip the
      per-request gzip pass that otherwise runs on the single event loop —
      that pass, not bandwidth or RAM, is the serving bottleneck.
    - Tile paths are content-immutable (same raw + qrange re-exports
      byte-identical; a format change bumps the path) → immutable max-age.
    - manifest.json is the mutable atomic-publish point → no-cache, so
      clients always revalidate (ETag keeps that a 304).
    """

    async def get_response(self, path: str, scope):
        response = None
        if (path.endswith(".i16")
                and "gzip" in Headers(scope=scope).get("accept-encoding", "")):
            try:
                response = await super().get_response(path + ".gz", scope)
                response.headers["content-encoding"] = "gzip"
                response.headers["content-type"] = "application/octet-stream"
                response.headers["vary"] = "Accept-Encoding"
            except HTTPException as exc:
                if exc.status_code != 404:   # no sibling: fall through
                    raise
        if response is None:
            response = await super().get_response(path, scope)
        if path.endswith(".i16"):
            response.headers["cache-control"] = ("public, max-age=31536000, "
                                                 "immutable")
        elif path.endswith("manifest.json"):
            response.headers["cache-control"] = "no-cache"
        return response


class JobRunner:
    """Single background worker; FIFO queue of dates; in-memory state.
    A service restart loses the queue — acceptable: fetches are resumable
    per snapshot and re-POSTing a date is cheap."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.pending: collections.deque[str] = collections.deque()
        self.current: dict | None = None    # {date, state}
        self.last_error: dict | None = None
        self.thread: threading.Thread | None = None

    def submit(self, date: str) -> str:
        with self.lock:
            if self.current and self.current["date"] == date:
                return "running"
            if date in self.pending:
                return "queued"
            self.pending.append(date)
            self.last_error = None
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._worker, daemon=True)
                self.thread.start()
            self.cond.notify_all()
            return "queued"

    def snapshot(self) -> tuple[dict | None, list[str]]:
        with self.lock:
            job = None
            if self.current:
                job = dict(self.current, done=0,
                           total=None, message=None, error=None)
                progress = self._progress_file(self.current["date"])
                if progress.exists():
                    try:
                        p = json.loads(progress.read_text())
                        job.update(done=p.get("done", 0),
                                   total=p.get("total"),
                                   message=p.get("message"))
                    except (json.JSONDecodeError, OSError):
                        pass
                if job["state"] == "exporting":
                    job["message"] = "exporting tiles"
            elif self.last_error:
                job = dict(self.last_error)
            return job, list(self.pending)

    @staticmethod
    def _progress_file(date: str) -> Path:
        return RAW / date / "progress.json"

    def _run(self, cmd_env: str, default: str, args: list[str]) -> None:
        cmd = shlex.split(os.environ.get(cmd_env, default)) + args
        subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True,
                       text=True)

    def _worker(self) -> None:
        while True:
            with self.lock:
                while not self.pending:
                    if not self.cond.wait(timeout=60):
                        return          # idle: let the thread retire
                date = self.pending.popleft()
                self.current = {"date": date, "state": "fetching"}
            try:
                progress = self._progress_file(date)
                progress.parent.mkdir(parents=True, exist_ok=True)
                self._run("GEOMAG_MODEL_EXPLORER_FETCH_CMD", DEFAULT_FETCH_CMD,
                          ["--day", date, "--progress-file", str(progress)])
                with self.lock:
                    self.current = {"date": date, "state": "exporting"}
                self._run("GEOMAG_MODEL_EXPLORER_EXPORT_CMD", DEFAULT_EXPORT_CMD,
                          ["--day", date])
                with self.lock:
                    self.current = None
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or "").strip()[-400:]
                with self.lock:
                    self.last_error = {"date": date, "state": "error",
                                       "error": f"exit {exc.returncode}: "
                                                f"{detail}"}
                    self.current = None


runner = JobRunner()
_limiter = RateLimiter()


async def api_features(request):
    return JSONResponse(read_features())


async def api_days(request):
    manifest = read_manifest()
    job, queue = runner.snapshot()
    return JSONResponse({
        "default_day": manifest.get("default_day"),
        "days": sorted(manifest.get("days", {})),
        "validity": manifest.get("validity"),
        "job": job,
        "queue": queue,
    })


async def api_post_day(request):
    # Auth gate: this POST triggers host VirES fetch/export subprocesses. Require the shared
    # secret (X-Foundry-Token / Bearer, constant-time) + a per-IP rate limit; fails closed.
    if not check_token(request):
        return JSONResponse(
            {"error": "auth required: send X-Foundry-Token"}, status_code=401)
    client = request.client.host if request.client else "?"
    if not _limiter.allow(client):
        return JSONResponse({"error": "rate limit exceeded"}, status_code=429)
    date = request.path_params["date"]
    try:
        parsed = dt.date.fromisoformat(date)
    except ValueError:
        return JSONResponse({"error": "invalid date"}, status_code=400)
    date = parsed.isoformat()

    validity = read_validity()
    if validity:
        start = validity["start"][:10]
        end = validity["end"][:10]
        if not (start <= date <= end):
            return JSONResponse(
                {"error": f"outside model validity {start}..{end}"},
                status_code=400)

    if date in read_manifest().get("days", {}):
        return JSONResponse({"status": "cached"})
    status = runner.submit(date)
    return JSONResponse({"status": status}, status_code=202)


app = Starlette(
    routes=[
        Route("/api/features", api_features),
        Route("/api/days", api_days),
        Route("/api/days/{date}", api_post_day, methods=["POST"]),
        # tiles + manifest.json — may live outside the checkout (GEOMAG_MODEL_EXPLORER_DATA)
        Mount("/data", TileFiles(directory=WEB_DATA, check_dir=False)),
        Mount("/", StaticFiles(directory=WEB, html=True)),
    ],
    # level 6: measured +47% event-loop throughput over the level-9 default
    # for +0.04% bytes; precompressed tiles bypass this middleware entirely
    # (it skips responses that already carry Content-Encoding).
    middleware=[Middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)],
)
