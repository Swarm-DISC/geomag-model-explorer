"""Relief feature (PLAN v2.6 step B; on by default since v2.12) against a
sandboxed server (:8220) with the flag on: the Relief checkbox displaces the
surface (canvas changes, the silhouette gains/loses pixels) and untoggling
restores the exact previous pixels (uRelief == 0 is bit-identical); the off
state round-trips as r=0 (absent = on; the pre-v2.12 r=1 still parses;
garbage ignored); playback runs with relief on; and with the sun flag also
on, enabling Sunlight re-lights the relief (the uLightDir handoff).
Flag-off (:8221, same data) shows no checkbox and never displaces."""
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
ARTIFACTS = Path(__file__).parent / "artifacts"
PORT_ON = 8220
PORT_OFF = 8221
SEED_DAY = "2020-01-01"
TIMEOUT_MS = 120_000

DEMO_HASH = "#f=crust&c=Up&s=surface&r=1"

# Force a render and hash the full canvas (preserveDrawingBuffer is on).
CANVAS_JS = """
() => { window.geomagModelExplorer.renderOnce();
        return window.geomagModelExplorer.renderer.domElement.toDataURL(); }
"""

# Pixels brighter than the 0x06080f background = globe silhouette area.
SILHOUETTE_JS = """
() => {
  window.geomagModelExplorer.renderOnce();
  const el = window.geomagModelExplorer.renderer.domElement;
  const c = document.createElement('canvas');
  c.width = el.width; c.height = el.height;
  const ctx = c.getContext('2d');
  ctx.drawImage(el, 0, 0);
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i] > 20 || d[i + 1] > 20 || d[i + 2] > 28) n++;
  }
  return n;
}
"""

LIGHT_EXPR = ("window.geomagModelExplorer.globe.fieldMaterial"
              ".uniforms.uLightDir.value.toArray()")
LIGHT_JS = f"() => {LIGHT_EXPR}"


def _wait_port(port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"server on :{port} never came up")


@pytest.fixture(scope="module")
def servers(tmp_path_factory):
    """One seeded sandbox (static + day); flags on / flags off."""
    tmp = tmp_path_factory.mktemp("relief")
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    (tmp / "features_on.json").write_text(
        '{"permalink": true, "sun": true, "relief": true}')
    for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY],
                 ["export.py", "--static"],
                 ["export.py", "--day", SEED_DAY]):
        subprocess.run([sys.executable, *args], cwd=REPO, env=env, check=True,
                       capture_output=True)
    # servers read only tiles; raw npz would crowd the small tmpfs
    shutil.rmtree(tmp / "data" / "raw", ignore_errors=True)
    procs = []
    try:
        for port, features in ((PORT_ON, str(tmp / "features_on.json")),
                               (PORT_OFF, str(tmp / "features_off_missing"))):
            procs.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "serve:app",
                 "--host", "127.0.0.1", "--port", str(port)],
                cwd=REPO, env=dict(env, GEOMAG_MODEL_EXPLORER_FEATURES=features),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            _wait_port(port)
        yield f"http://127.0.0.1:{PORT_ON}", f"http://127.0.0.1:{PORT_OFF}"
    finally:
        for p in procs:
            p.terminate()
            p.wait(timeout=10)
        # synthetic data on a small tmpfs — clean eagerly
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def watched_page(page):
    page.set_viewport_size({"width": 800, "height": 600})
    errors = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}")
            if m.type == "error" else None)
    yield page, errors
    assert errors == [], f"browser errors: {errors}"


def _wait_ready(page):
    page.wait_for_function(
        "() => window.geomagModelExplorer && window.geomagModelExplorer.cacheSize() > 0",
        timeout=TIMEOUT_MS)


def test_relief_toggle_and_exact_restore(servers, watched_page):
    # r=0&sun=0 is the v1 look (the v2.6 bit-identity reference) now that
    # both default on
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#f=crust&c=Up&s=surface&r=0&sun=0", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert not page.is_checked("#relief-toggle")
    flat = page.evaluate(CANVAS_JS)
    flat_silhouette = page.evaluate(SILHOUETTE_JS)
    page.screenshot(path=str(ARTIFACTS / "relief_off.png"))

    page.check("#relief-toggle")
    assert page.evaluate("() => window.geomagModelExplorer.state.relief") is True
    assert page.evaluate(
        "() => window.geomagModelExplorer.globe.fieldMaterial"
        ".uniforms.uRelief.value") == pytest.approx(0.15)
    raised = page.evaluate(CANVAS_JS)
    assert raised != flat                       # displacement is visible
    # signed displacement moves the silhouette itself, not just shading
    assert abs(page.evaluate(SILHOUETTE_JS) - flat_silhouette) > 50
    page.screenshot(path=str(ARTIFACTS / "relief_on.png"))

    page.uncheck("#relief-toggle")
    assert page.evaluate("() => window.geomagModelExplorer.state.relief") is False
    assert page.evaluate(CANVAS_JS) == flat     # uRelief == 0: bit-identical


def test_relief_permalink_roundtrip(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.relief") is True
    assert page.is_checked("#relief-toggle")
    # the write-back normalizes the pre-v2.12 r=1 away (on = the default) ...
    page.wait_for_function(
        "() => !location.hash.includes('r=')", timeout=TIMEOUT_MS)
    # ... and writes the off form once relief is switched off
    page.uncheck("#relief-toggle")
    page.wait_for_function(
        "() => location.hash.includes('r=0')", timeout=TIMEOUT_MS)


def test_garbage_relief_hash_degrades(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#r=banana", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # garbage degrades to the default — on, since v2.12
    assert page.evaluate("() => window.geomagModelExplorer.state.relief") is True
    assert page.is_checked("#relief-toggle")


def test_playback_with_relief_on(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#f=iono&c=Up&s=surface&r=1", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.click("#play-btn")
    page.wait_for_function(
        "() => window.geomagModelExplorer.timePos() > 0.5", timeout=TIMEOUT_MS)
    page.click("#play-btn")                     # pause; watched_page asserts
                                                # the run produced no errors


def test_sun_lights_the_relief(servers, watched_page):
    """The v2.6 integration surface (v2.12: overlay retired, same handoff):
    with relief on, enabling Sunlight swings uLightDir from the headlight to
    the view-space sun, and the canvas re-shades."""
    on, _off = servers
    page, _errors = watched_page
    # sun=0 boots on the headlight so the handoff is observable
    page.goto(on + "/" + DEMO_HASH + "&t=12:00&sun=0", timeout=TIMEOUT_MS)
    _wait_ready(page)
    headlight = page.evaluate(LIGHT_JS)
    before = page.evaluate(CANVAS_JS)

    page.check("#sun-toggle")
    page.wait_for_function(
        f"""() => {{
          const h = {json.dumps(headlight)};
          const v = {LIGHT_EXPR};
          return Math.hypot(v[0] - h[0], v[1] - h[1], v[2] - h[2]) > 0.05;
        }}""", timeout=TIMEOUT_MS)
    assert page.evaluate(CANVAS_JS) != before
    page.screenshot(path=str(ARTIFACTS / "relief_sunlit.png"))

    page.uncheck("#sun-toggle")                 # handoff back to the headlight
    page.wait_for_function(
        f"""() => {{
          const h = {json.dumps(headlight)};
          const v = {LIGHT_EXPR};
          return Math.hypot(v[0] - h[0], v[1] - h[1], v[2] - h[2]) < 1e-6;
        }}""", timeout=TIMEOUT_MS)


def test_flag_off_has_no_relief(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + "/#r=1", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # state.relief defaults on but is inert without the module: no displacement
    assert page.evaluate(
        "() => document.getElementById('relief-toggle')") is None
    assert page.evaluate(
        "() => window.geomagModelExplorer.globe.fieldMaterial"
        ".uniforms.uRelief.value") == 0
