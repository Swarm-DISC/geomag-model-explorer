"""Sunlight feature (PLAN v2.12, superseding the v2.6 overlay) against a
sandboxed server (:8218) with the flag on: the Sunlight checkbox appears (on
by default), toggling shades the globe by day/night (uSunlight/uSunDir
uniforms — the retired terminator/glyph overlay must never exist), the sun
direction matches the analytic subsolar point and tracks the time slider,
and the off state round-trips as sun=0 (absent = on; the pre-v2.12 sun=1
still parses; garbage ignored). Flag-off (:8219, same data) shows no
checkbox and never shades."""
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
PORT_ON = 8218
PORT_OFF = 8219
SEED_DAY = "2020-01-01"
SEED_SERIES = "mio-seasonal-2020"
TIMEOUT_MS = 120_000

DEMO_HASH = "#f=iono&c=Up&s=surface&t=12:00&sun=1"
MIDNIGHT_HASH = "#f=iono&c=Up&s=surface&t=00:00"
SEASONS_HASH = (f"#tab=seasons&series={SEED_SERIES}"
                "&f=iono&c=Up&s=surface&sun=1")

# Distance between the field material's object-space uSunDir and the subsolar
# direction recomputed from the displayed UT in web/sun.js.
SUN_ERROR_JS = """
async () => {
  const { globe, state, manifest } = window.geomagModelExplorer;
  const u = globe.fieldMaterial.uniforms.uSunDir.value;
  const m = await import('./sun.js');
  const { lat, lon } = m.subsolarPoint(m.displayedUT(state, manifest));
  const D = Math.PI / 180;
  return Math.hypot(u.x - Math.cos(lat * D) * Math.sin(lon * D),
                    u.y - Math.sin(lat * D),
                    u.z - Math.cos(lat * D) * Math.cos(lon * D));
}
"""

# uSunlight on both materials (field shell + coastline reference sphere).
SUNLIGHT_JS = """
() => [window.geomagModelExplorer.globe.fieldMaterial,
       window.geomagModelExplorer.globe.coastMaterial]
        .map((m) => m.uniforms.uSunlight.value)
"""

# Force a render and hash the full canvas (preserveDrawingBuffer is on).
CANVAS_JS = """
() => { window.geomagModelExplorer.renderOnce();
        return window.geomagModelExplorer.renderer.domElement.toDataURL(); }
"""

# Mean brightness over the canvas — the night hemisphere facing the camera
# must pull this down when sunlight is on.
BRIGHTNESS_JS = """
() => {
  window.geomagModelExplorer.renderOnce();
  const el = window.geomagModelExplorer.renderer.domElement;
  const c = document.createElement('canvas');
  c.width = el.width; c.height = el.height;
  const ctx = c.getContext('2d');
  ctx.drawImage(el, 0, 0);
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += d[i] + d[i + 1] + d[i + 2];
  return sum / (d.length / 4);
}
"""

NO_OVERLAY_JS = ("() => !!window.geomagModelExplorer.globe.scene"
                 ".getObjectByName('sun-overlay')")


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
    tmp = tmp_path_factory.mktemp("sun")
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    (tmp / "features_on.json").write_text(
        '{"permalink": true, "sun": true, "studies": true}')
    for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY,
                  "--series", SEED_SERIES],
                 ["export.py", "--static"],
                 ["export.py", "--day", SEED_DAY],
                 ["export.py", "--series", SEED_SERIES]):
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


def test_subsolar_math(servers, watched_page):
    """The analytic ephemeris lands on the textbook values."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    pts = page.evaluate("""
      async () => {
        const m = await import('./sun.js');
        return {
          june: m.subsolarPoint(new Date('2020-06-20T21:43:00Z')),
          equinox: m.subsolarPoint(new Date('2020-03-20T03:50:00Z')),
          noon: m.subsolarPoint(new Date('2020-01-01T12:00:00Z')),
          daily: m.displayedUT({day: '2020-01-01', pos: 48}, {}).toISOString(),
          series: m.displayedUT({day: 's', pos: 0.5}, {series: {s: {epochs:
            ['2020-01-01T12:00:00', '2020-01-08T12:00:00']}}}).toISOString(),
        };
      }""")
    assert abs(pts["june"]["lat"] - 23.44) < 0.1     # solstice declination
    assert abs(pts["equinox"]["lat"]) < 0.1
    assert abs(pts["noon"]["lon"]) < 2               # |EoT| < 8 min in Jan
    assert pts["daily"] == "2020-01-01T12:00:00.000Z"
    # whole-day epoch spacing snaps the offset to whole days (PLAN v2.8):
    # the series' fixed 12:00 clock time holds at fractional positions
    assert pts["series"] == "2020-01-05T12:00:00.000Z"  # UT, not host-local


def test_sunlight_toggle_shades_globe(servers, watched_page):
    """At 00:00 UT the night hemisphere faces the default camera (lon 0):
    Sunlight is on by default and darkens the canvas; toggling off restores
    full brightness, and re-enabling reproduces the shaded canvas
    bit-identically (uSunlight == 0 leaves the color path untouched). The
    v2.6 overlay objects must never exist."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + MIDNIGHT_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.is_checked("#sun-toggle")
    assert page.evaluate(SUNLIGHT_JS) == [1, 1]
    assert page.evaluate(SUN_ERROR_JS) < 1e-3
    assert page.evaluate(NO_OVERLAY_JS) is False
    shaded = page.evaluate(CANVAS_JS)
    dark = page.evaluate(BRIGHTNESS_JS)
    page.screenshot(path=str(ARTIFACTS / "sun_shading.png"))

    page.uncheck("#sun-toggle")
    assert page.evaluate("() => window.geomagModelExplorer.state.sun") is False
    assert page.evaluate(SUNLIGHT_JS) == [0, 0]
    assert dark < page.evaluate(BRIGHTNESS_JS) * 0.8

    page.check("#sun-toggle")
    assert page.evaluate(SUNLIGHT_JS) == [1, 1]
    assert page.evaluate(CANVAS_JS) == shaded


def test_sun_off_form(servers, watched_page):
    """sun=0 (the v2.12 off form) restores an unlit boot."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + MIDNIGHT_HASH + "&sun=0", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.sun") is False
    assert not page.is_checked("#sun-toggle")
    assert page.evaluate(SUNLIGHT_JS) == [0, 0]


def test_sun_tracks_time_slider(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate(SUN_ERROR_JS) < 1e-3
    before = page.evaluate(
        "() => window.geomagModelExplorer.globe.fieldMaterial"
        ".uniforms.uSunDir.value.toArray()")
    page.locator("#time-slider").fill("0")           # 12:00 -> 00:00 UT
    # the uniform updates from the post-render change notification: it must
    # both move away from the noon direction and still match the analytic sun
    page.wait_for_function(
        f"""async () => {{
          const before = {json.dumps(before)};
          const err = await ({SUN_ERROR_JS})();
          const u = window.geomagModelExplorer.globe.fieldMaterial
            .uniforms.uSunDir.value.toArray();
          return err < 1e-3 &&
            u.some((v, i) => Math.abs(v - before[i]) > 0.1);
        }}""",
        timeout=TIMEOUT_MS)


def test_seasons_sun_holds_clock(servers, watched_page):
    """PLAN v2.8: scrubbing between the weekly epochs of a fixed-time-of-day
    series must not sweep the sun through the intermediate hours. The
    displayed UT holds the series' 12:00 clock (whole-day snap), so the
    subsolar longitude stays at the noon meridian (± equation of time),
    uSunDir tracks it, and the timeline label shows the same date."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + SEASONS_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_SERIES
    for tick in (73, 74, 76):          # slider ticks: pos = tick/7, fractional
        page.locator("#time-slider").fill(str(tick))
        page.wait_for_function(
            f"""async () => {{
              const {{ state, manifest }} = window.geomagModelExplorer;
              if (Math.abs(state.pos - {tick} / 7) > 1e-9) return false;
              const m = await import('./sun.js');
              const ut = m.displayedUT(state, manifest);
              const {{ lon }} = m.subsolarPoint(ut);
              const err = await ({SUN_ERROR_JS})();
              const label = document.getElementById('time-label').textContent;
              return ut.getUTCHours() === 12 && ut.getUTCMinutes() === 0 &&
                Math.abs(lon) < 5 &&
                err !== null && err < 1e-3 &&
                label === ut.toISOString().slice(0, 10);
            }}""",
            timeout=TIMEOUT_MS)


def test_sun_permalink_roundtrip(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.sun") is True
    assert page.is_checked("#sun-toggle")
    assert page.evaluate(SUNLIGHT_JS) == [1, 1]
    assert page.evaluate(SUN_ERROR_JS) < 1e-3
    # the write-back normalizes the pre-v2.12 sun=1 away (on = the default) ...
    page.wait_for_function(
        "() => !location.hash.includes('sun=')", timeout=TIMEOUT_MS)
    # ... and writes the off form when the shading is switched off
    page.uncheck("#sun-toggle")
    page.wait_for_function(
        "() => location.hash.includes('sun=0')", timeout=TIMEOUT_MS)


def test_garbage_sun_hash_degrades(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#sun=banana", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # garbage degrades to the default — on, since v2.12
    assert page.evaluate("() => window.geomagModelExplorer.state.sun") is True
    assert page.is_checked("#sun-toggle")


def test_flag_off_has_no_sun(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + "/#sun=1", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # state.sun defaults on but is inert without the module: nothing shades
    assert page.evaluate("() => document.getElementById('sun-toggle')") is None
    assert page.evaluate(SUNLIGHT_JS) == [0, 0]
