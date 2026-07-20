"""Loading-states contract around applyTextures (PLAN: loading-states):
stale tiles dim (uStale) while a new shell/day/mode target is in flight, the
globe overlay appears after a grace delay and hides on the atomic commit,
the colorbar relabel is deferred to that commit, tile failures surface as a
retryable error overlay, and an idle prefetch warms the ±2 neighbor shells.

Sandboxed server on :8239 (8213-8223 are squatted by unrelated fleet
services). Tile latency/failure is injected by a page-side fetch shim —
`window.__tileDelayMs` / `window.__tileFail` — so no server delay knob and
no blocking Playwright route handlers are needed.
"""
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
PORT = 8239
SEED_DAY = "2020-01-01"
SERIES_ID = "mio-seasonal-2020"
TIMEOUT_MS = 120_000

# Installed before any page script: tiles (and only tiles — the .i16 marker
# never appears in manifest/texture/feature URLs) gain a switchable delay or
# hard failure. Reject with a TypeError, exactly what a dead network yields.
FETCH_SHIM = """
  const origFetch = window.fetch.bind(window);
  window.__tileDelayMs = 0;
  window.__tileFail = false;
  window.fetch = (input, init) => {
    const url = typeof input === 'string' ? input : input.url;
    if (url.includes('.i16')) {
      if (window.__tileFail) {
        return Promise.reject(new TypeError('simulated tile network failure'));
      }
      if (window.__tileDelayMs > 0) {
        return new Promise((resolve, reject) =>
          setTimeout(() => origFetch(input, init).then(resolve, reject),
                     window.__tileDelayMs));
      }
    }
    return origFetch(input, init);
  };
"""


def _wait_port(port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"server on :{port} never came up")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Seeded sandbox (static + day + series, for the mode-switch test)."""
    tmp = tmp_path_factory.mktemp("loading")
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    features = tmp / "features.json"
    features.write_text('{"studies": true}')
    for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY,
                  "--series", SERIES_ID],
                 ["export.py", "--static"],
                 ["export.py", "--day", SEED_DAY],
                 ["export.py", "--series", SERIES_ID]):
        subprocess.run([sys.executable, *args], cwd=REPO, env=env, check=True,
                       capture_output=True)
    shutil.rmtree(tmp / "data" / "raw", ignore_errors=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "serve:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=REPO, env=dict(env, GEOMAG_MODEL_EXPLORER_FEATURES=str(features)),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_port(PORT)
        yield f"http://127.0.0.1:{PORT}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)   # synthetic data on tmpfs


@pytest.fixture()
def app_page(server, page):
    page.set_viewport_size({"width": 800, "height": 600})
    errors = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}")
            if m.type == "error" else None)
    page.add_init_script(FETCH_SHIM)
    yield page, errors
    assert errors == [], f"browser errors: {errors}"


def _wait_settled(page):
    page.wait_for_function(
        "() => window.geomagModelExplorer"
        " && window.geomagModelExplorer.cacheSize() > 0"
        " && !window.geomagModelExplorer.pending()",
        timeout=TIMEOUT_MS)


def _pending(page):
    return page.evaluate("() => window.geomagModelExplorer.pending()")


def _stale(page):
    return page.evaluate(
        "() => window.geomagModelExplorer.globe"
        ".fieldMaterial.uniforms.uStale.value")


def _slider(page):
    i = int(page.eval_on_selector("#shell-slider", "el => Number(el.value)"))
    n = int(page.eval_on_selector("#shell-slider", "el => Number(el.max)")) + 1
    return i, n


def _set_slider(page, idx):
    page.eval_on_selector(
        "#shell-slider",
        f"el => {{ el.value = '{idx}';"
        " el.dispatchEvent(new Event('input', {bubbles: true})); }")


def _far_index(i, n):
    """A rung outside the ±2 neighbor-prefetch radius of i."""
    return 0 if i >= 3 else n - 1


def _after_raf(page):
    """scheduleScrubApply defers applyTextures to the next animation frame —
    wait one out so a following settle-wait cannot pass before the apply has
    even started (two back-to-back scrubs would otherwise coalesce)."""
    page.evaluate("() => new Promise(requestAnimationFrame)")


def test_boot_overlay_shows_then_hides(app_page, server):
    page, _errors = app_page
    page.add_init_script("window.__tileDelayMs = 1000;")
    page.goto(server + "/", timeout=TIMEOUT_MS)
    # markup ships the overlay visible: it covers the delayed boot fetch
    assert page.is_visible("#load-overlay"), "boot overlay not visible"
    _wait_settled(page)
    assert page.is_hidden("#load-overlay"), "overlay still up after commit"
    assert _stale(page) == 0


def test_scrub_dims_and_defers_colorbar(app_page, server):
    page, _errors = app_page
    page.goto(server + "/", timeout=TIMEOUT_MS)
    _wait_settled(page)
    old_label = page.text_content("#colorbar-max")
    page.evaluate("window.__tileDelayMs = 1500")
    i, n = _slider(page)
    _set_slider(page, _far_index(i, n))    # beyond any prefetch warmth
    page.wait_for_function(
        "() => window.geomagModelExplorer.pending()", timeout=5_000)
    # in flight: display marked stale, colorbar still describes what is shown
    assert _stale(page) == 1
    assert page.text_content("#colorbar-max") == old_label, \
        "colorbar relabeled before the new shell's tiles arrived"
    page.wait_for_timeout(400)             # grace delay (200 ms) elapsed
    assert page.is_visible("#load-overlay"), "overlay missing mid-fetch"
    _wait_settled(page)
    assert page.is_hidden("#load-overlay")
    assert _stale(page) == 0
    assert page.text_content("#colorbar-max") != old_label, \
        "colorbar never relabeled for the new shell (CMB core range)"


def test_warm_scrub_never_flashes_overlay(app_page, server):
    page, _errors = app_page
    page.goto(server + "/", timeout=TIMEOUT_MS)
    _wait_settled(page)
    i, n = _slider(page)
    far = _far_index(i, n)
    _set_slider(page, far)                 # populate the far shell's tiles
    _after_raf(page)
    _wait_settled(page)
    _set_slider(page, i)                   # and the original's again
    _after_raf(page)
    _wait_settled(page)
    page.evaluate("window.__tileDelayMs = 1500")   # a fetch would be slow —
    _set_slider(page, far)                 # but everything is cached
    page.wait_for_timeout(400)
    assert page.is_hidden("#load-overlay"), \
        "overlay flashed on a fully-cached scrub"
    assert not _pending(page)
    assert _stale(page) == 0


def test_mode_switch_pends_then_commits(app_page, server):
    page, _errors = app_page
    page.goto(server + "/", timeout=TIMEOUT_MS)
    _wait_settled(page)
    page.evaluate("window.__tileDelayMs = 1500")
    page.check("#field-seasons")           # Ionosphere study (series data)
    # controls swap immediately; the globe holds dimmed old tiles meanwhile
    assert page.is_visible("#series-select")
    page.wait_for_function(
        "() => window.geomagModelExplorer.pending()", timeout=5_000)
    assert _stale(page) == 1
    page.wait_for_timeout(400)
    assert page.is_visible("#load-overlay"), "overlay missing on mode switch"
    _wait_settled(page)
    assert page.is_hidden("#load-overlay")
    assert _stale(page) == 0


def test_playback_never_pends(app_page, server):
    page, _errors = app_page
    page.goto(server + "/", timeout=TIMEOUT_MS)
    _wait_settled(page)
    page.click("#play-btn")
    for _ in range(7):                     # ~3.5 s of playback
        page.wait_for_timeout(500)
        assert page.is_hidden("#load-overlay"), "overlay during playback"
        assert not _pending(page), "playback entered the pending state"
    assert page.evaluate("() => window.geomagModelExplorer.state.pos") > 0
    page.click("#play-btn")                # pause


def test_tile_failure_offers_retry(app_page, server):
    page, _errors = app_page
    page.goto(server + "/", timeout=TIMEOUT_MS)
    _wait_settled(page)
    page.evaluate("window.__tileFail = true")
    i, n = _slider(page)
    _set_slider(page, _far_index(i, n))
    page.wait_for_selector("#load-overlay.error", timeout=10_000)
    assert _pending(page)
    assert _stale(page) == 1               # the shown tiles really are stale
    page.evaluate("window.__tileFail = false")
    page.click("#load-overlay")            # the error overlay is the retry
    _wait_settled(page)
    assert page.is_hidden("#load-overlay")
    assert _stale(page) == 0


def test_idle_prefetch_warms_neighbor_shells(app_page, server):
    page, _errors = app_page
    page.goto(server + "/", timeout=TIMEOUT_MS)
    # read the settled cache population atomically with the settle predicate —
    # a separate evaluate could race the 1 s idle-prefetch timer
    settled = page.wait_for_function(
        "() => window.geomagModelExplorer"
        " && !window.geomagModelExplorer.pending()"
        " && window.geomagModelExplorer.cacheSize()",
        timeout=TIMEOUT_MS).json_value()
    page.wait_for_function(                # idle timer (1 s) + fetches
        f"() => window.geomagModelExplorer.cacheSize() > {settled}",
        timeout=15_000)
    i, n = _slider(page)
    page.evaluate("window.__tileDelayMs = 1500")
    _set_slider(page, i + 1 if i + 1 < n else i - 1)   # inside ±2 radius
    page.wait_for_timeout(400)
    assert page.is_hidden("#load-overlay"), \
        "neighbor scrub was not served from the prefetched cache"
    assert not _pending(page)
