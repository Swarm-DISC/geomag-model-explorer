"""End-to-end day-pick UX against a sandboxed server (:8213) whose fetch
subprocess is the synthetic stub: picking an uncached day shows the progress
chip, the job completes, and the new day renders — all without VirES."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PORT = 8213
SEED_DAY = "2020-01-01"
PICK_DAY = "2021-03-17"
TIMEOUT_MS = 120_000


def _wait_port(port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"server on :{port} never came up")


@pytest.fixture(scope="module")
def stub_server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("daypick")
    env = dict(os.environ,
               GEOMAG_MODEL_EXPLORER_DATA=str(tmp),
               GEOMAG_MODEL_EXPLORER_FETCH_CMD=f"{sys.executable} tests/stub_fetch.py",
               GEOMAG_MODEL_EXPLORER_EXPORT_CMD=f"{sys.executable} export.py")
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    # seed: synthetic static crust + one full day, exported for real
    for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY],
                 ["export.py", "--static"],
                 ["export.py", "--day", SEED_DAY]):
        subprocess.run([sys.executable, *args], cwd=REPO, env=env, check=True,
                       capture_output=True)
    # the seed day's raw npz is dead weight on the small tmpfs (the day
    # fetched on demand during the test writes its own raw fresh)
    shutil.rmtree(tmp / "data" / "raw", ignore_errors=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "serve:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_port(PORT)
        yield f"http://127.0.0.1:{PORT}"
    finally:
        server.terminate()
        server.wait(timeout=10)
        # ~600 MB of synthetic data on a small tmpfs — clean eagerly
        shutil.rmtree(tmp, ignore_errors=True)


def test_pick_uncached_day_shows_progress_then_renders(stub_server, page):
    page.set_viewport_size({"width": 800, "height": 600})
    errors = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}")
            if m.type == "error" else None)
    page.goto(stub_server + "/", timeout=TIMEOUT_MS)
    page.wait_for_function(
        "() => window.geomagModelExplorer && window.geomagModelExplorer.cacheSize() > 0",
        timeout=TIMEOUT_MS)
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_DAY

    # The stub job can finish faster than Playwright polls, so record chip
    # appearances with a MutationObserver instead of racing to observe one.
    page.evaluate("""() => {
      window.__chipShows = 0;
      const chip = document.getElementById('fetch-chip');
      new MutationObserver(() => { if (!chip.hidden) window.__chipShows++; })
        .observe(chip, {attributes: true, attributeFilter: ['hidden']});
    }""")
    page.fill("#date-picker", PICK_DAY)   # fill fires input + change

    # async UX: the current day stays selected while the job runs
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_DAY

    # job completes -> picked day becomes current, chip was shown then hidden
    page.wait_for_function(
        f"() => window.geomagModelExplorer.state.day === '{PICK_DAY}'",
        timeout=TIMEOUT_MS)
    assert page.evaluate("() => window.__chipShows") >= 1, \
        "progress chip never appeared"
    page.wait_for_selector("#fetch-chip[hidden]", state="attached",
                           timeout=TIMEOUT_MS)
    page.wait_for_timeout(500)
    page.evaluate("window.geomagModelExplorer.renderOnce()")
    assert page.evaluate(
        f"() => '{PICK_DAY}' in window.geomagModelExplorer.manifest.days")
    assert errors == [], f"browser errors: {errors}"
