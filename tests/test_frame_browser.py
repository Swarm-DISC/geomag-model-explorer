"""Reference-frame feature (PLAN v2.12; IDEAS 1.4 ECEF/ECI subset) against a
sandboxed server (:8224) with the flag on: the ECEF|ECI radios appear, ECI
poses the earth group by the mean-solar hour angle from the displayed UT
(+Y polar axis), the hover readout stays geographic under the rotation, and
frame=eci round-trips through the permalink (garbage ignored). Flag-off
(:8225, same data) shows no control and an identity pose — exactly v1."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ARTIFACTS = Path(__file__).parent / "artifacts"
PORT_ON = 8224
PORT_OFF = 8225
SEED_DAY = "2020-01-01"
TIMEOUT_MS = 120_000

# 06:00 UT -> ECI hour angle 90° about +Y.
DEMO_HASH = "#f=crust&c=Up&s=surface&t=06:00"

QUAT_JS = "() => window.geomagModelExplorer.globe.earth.quaternion.toArray()"

# Force a render and hash the full canvas (preserveDrawingBuffer is on).
CANVAS_JS = """
() => { window.geomagModelExplorer.renderOnce();
        return window.geomagModelExplorer.renderer.domElement.toDataURL(); }
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
def servers(tmp_path_factory):
    """One seeded sandbox (static + day); flag on / flag off."""
    tmp = tmp_path_factory.mktemp("frame")
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    (tmp / "features_on.json").write_text(
        '{"permalink": true, "frame": true}')
    for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY],
                 ["export.py", "--static"],
                 ["export.py", "--day", SEED_DAY]):
        subprocess.run([sys.executable, *args], cwd=REPO, env=env, check=True,
                       capture_output=True)
    # servers read only tiles; raw npz would double the sandbox on a small
    # tmpfs (host quirk — clean heavy test sandboxes eagerly)
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


def _hover_lon(page):
    """Signed longitude the readout reports at the canvas center."""
    box = page.locator("#globe canvas").bounding_box()
    # park off the globe first so the center hover is a fresh pointermove
    # (and the readout content is never stale)
    page.mouse.move(box["x"] + 5, box["y"] + 5)
    page.wait_for_selector("#readout[hidden]", state="attached",
                           timeout=TIMEOUT_MS)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_selector("#readout:not([hidden])", timeout=TIMEOUT_MS)
    text = page.eval_on_selector("#readout", "el => el.textContent")
    m = re.search(r"([\d.]+)°([EW])", text)
    assert m, f"no longitude in readout: {text!r}"
    lon = float(m.group(1))
    return lon if m.group(2) == "E" else -lon


def test_frame_toggle_rotates_globe(servers, watched_page):
    """ECI at 06:00 UT is a 90° eastward pose about +Y; ECEF is identity."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.is_checked("#frame-ecef")
    assert page.evaluate(QUAT_JS) == [0, 0, 0, 1]
    before = page.evaluate(CANVAS_JS)

    page.check("#frame-eci")
    assert page.evaluate("() => window.geomagModelExplorer.state.frame") == "eci"
    q = page.evaluate(QUAT_JS)
    s = math.sin(math.pi / 4)
    for got, want in zip(q, [0, s, 0, s]):
        assert abs(got - want) < 1e-3, f"quaternion {q}"
    assert page.evaluate(CANVAS_JS) != before
    page.screenshot(path=str(ARTIFACTS / "frame_eci.png"))

    page.check("#frame-ecef")
    assert page.evaluate(QUAT_JS) == [0, 0, 0, 1]
    assert page.evaluate(CANVAS_JS) == before


def test_eci_tracks_time_slider(servers, watched_page):
    """The pose follows the displayed UT via the post-render notification."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH + "&frame=eci", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.locator("#time-slider").fill("720")         # 06:00 -> 12:00 UT
    # 180° about +Y: q = [0, 1, 0, 0]
    page.wait_for_function(
        """() => {
          const q = window.geomagModelExplorer.globe.earth.quaternion;
          return Math.abs(q.y - 1) < 1e-3 && Math.abs(q.w) < 1e-3;
        }""",
        timeout=TIMEOUT_MS)


def test_hover_stays_geographic(servers, watched_page):
    """The readout reports Earth-fixed coordinates: rotating the globe 90°
    eastward under a fixed camera shifts the longitude at the canvas center
    by −90°."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    lon_ecef = _hover_lon(page)
    page.check("#frame-eci")
    page.evaluate(CANVAS_JS)       # render once: matrixWorld picks up the pose
    lon_eci = _hover_lon(page)
    delta = (lon_ecef - lon_eci + 180) % 360 - 180
    assert abs(delta - 90) < 2, f"ECEF {lon_ecef}° vs ECI {lon_eci}°"


def test_frame_permalink_roundtrip(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH + "&frame=eci", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.frame") == "eci"
    assert page.is_checked("#frame-eci")
    # the write-back keeps frame=eci ...
    page.wait_for_function(
        "() => location.hash.includes('frame=eci')", timeout=TIMEOUT_MS)
    # ... and drops the key back in ECEF
    page.check("#frame-ecef")
    page.wait_for_function(
        "() => !location.hash.includes('frame=')", timeout=TIMEOUT_MS)


def test_garbage_frame_hash_degrades(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#frame=banana", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.frame") == "ecef"
    assert page.is_checked("#frame-ecef")
    assert page.evaluate(QUAT_JS) == [0, 0, 0, 1]


def test_flag_off_has_no_frame(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + "/#frame=eci", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => document.getElementById('frame-toggle')") is None
    assert page.evaluate("() => window.geomagModelExplorer.state.frame") == "ecef"
    assert page.evaluate(QUAT_JS) == [0, 0, 0, 1]
