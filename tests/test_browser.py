"""Browser tests against the LIVE service on :8212 (and the portal prefix).

Run after `systemctl --user restart geomag-model-explorer-web.service`:

    uv run pytest tests/test_browser.py

SwiftShader software GL: keep viewports small and timeouts generous.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BASE = "http://127.0.0.1:8212"
PORTAL = "http://127.0.0.1:8080/foundry/geomag-model-explorer"
ARTIFACTS = Path(__file__).parent / "artifacts"
VIEWPORT = {"width": 800, "height": 600}
TIMEOUT_MS = 60_000


def _collect_errors(page):
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda msg: errors.append(f"console.error: {msg.text}")
            if msg.type == "error" else None)
    return errors


def _wait_ready(page):
    page.wait_for_function(
        "() => window.geomagModelExplorer && window.geomagModelExplorer.cacheSize() > 0",
        timeout=TIMEOUT_MS)
    page.evaluate("window.geomagModelExplorer.renderOnce()")


def _center_pixel(page):
    return page.evaluate(
        "() => window.geomagModelExplorer.readPixel("
        "Math.floor(window.geomagModelExplorer.renderer.domElement.width / 2),"
        "Math.floor(window.geomagModelExplorer.renderer.domElement.height / 2))")


@pytest.fixture()
def app_page(page):
    page.set_viewport_size(VIEWPORT)
    errors = _collect_errors(page)
    page.goto(BASE + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    yield page, errors
    assert errors == [], f"browser errors: {errors}"


def test_globe_renders(app_page):
    page, _errors = app_page
    bg = page.evaluate("() => window.geomagModelExplorer.readPixel(2, 2)")
    center = _center_pixel(page)
    assert center[:3] != bg[:3], (
        f"canvas center {center} equals background {bg} — globe not rendered?")
    ARTIFACTS.mkdir(exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "phase1_globe.png"))


def test_drag_rotates(app_page):
    page, _errors = app_page
    before = _center_pixel(page)
    box = page.locator("#globe canvas").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 150, cy + 60, steps=8)
    page.mouse.up()
    page.evaluate("window.geomagModelExplorer.renderOnce()")
    after = _center_pixel(page)
    assert before != after, "drag-rotate did not change the rendered view"


def _hash_canvas(page):
    """Cheap whole-canvas fingerprint via a 64×64 downscale."""
    return page.evaluate("""() => {
      const src = window.geomagModelExplorer.renderer.domElement;
      const c = document.createElement('canvas');
      c.width = 64; c.height = 64;
      const ctx = c.getContext('2d');
      ctx.drawImage(src, 0, 0, 64, 64);
      return c.toDataURL();
    }""")


def _apply(page, js):
    page.evaluate(f"async () => {{ {js} }}")
    page.wait_for_function(
        "() => window.geomagModelExplorer.cacheSize() > 0", timeout=TIMEOUT_MS)
    page.wait_for_timeout(300)   # let pending texture loads land
    page.evaluate("window.geomagModelExplorer.renderOnce()")


def test_field_toggles_change_pixels(app_page):
    """Phase 3: each field with data at the surface alters the rendering."""
    page, _errors = app_page
    days = page.evaluate("() => Object.keys(window.geomagModelExplorer.manifest.days)")
    if not days:
        pytest.skip("no full day cached yet (Phase 2 pending)")
    # all four fields are on by default since v2.12: drop each in turn
    baseline = _hash_canvas(page)
    for field in ("core", "iono", "magneto"):
        page.uncheck(f"#toggle-{field}")
        page.wait_for_timeout(500)
        page.evaluate("window.geomagModelExplorer.renderOnce()")
        h = _hash_canvas(page)
        assert h != baseline, f"disabling {field} did not change the canvas"
        page.check(f"#toggle-{field}")
        page.wait_for_timeout(300)


def test_component_radios_change_pixels(app_page):
    page, _errors = app_page
    page.evaluate("window.geomagModelExplorer.renderOnce()")
    seen = {}
    for comp in ("Up", "N", "E", "F"):
        page.check(f"#comp-{comp}")
        page.evaluate("window.geomagModelExplorer.renderOnce()")
        seen[comp] = _hash_canvas(page)
    assert len(set(seen.values())) == 4, (
        "component radios did not produce 4 distinct renderings")
    page.check("#comp-Up")


def test_shell_slider_sweep(app_page):
    """Phase 4: every shell renders distinctly; availability greying tracks."""
    page, _errors = app_page
    days = page.evaluate("() => Object.keys(window.geomagModelExplorer.manifest.days)")
    if not days:
        pytest.skip("no full day cached yet")
    for field in ("core", "iono", "magneto"):
        page.check(f"#toggle-{field}")
    page.wait_for_timeout(800)
    n = int(page.eval_on_selector("#shell-slider", "el => Number(el.max)")) + 1
    assert n >= 7, f"expected >=7 shells in the union, got {n}"
    hashes = []
    for i in range(n):
        page.eval_on_selector(
            "#shell-slider",
            f"el => {{ el.value = '{i}';"
            " el.dispatchEvent(new Event('input', {bubbles: true})); }")
        page.wait_for_timeout(600)
        page.evaluate("window.geomagModelExplorer.renderOnce()")
        hashes.append(_hash_canvas(page))
    assert len(set(hashes)) == n, "some shells rendered identically"
    # at the CMB (slider position 0) only core has data
    page.eval_on_selector(
        "#shell-slider",
        "el => { el.value = '0';"
        " el.dispatchEvent(new Event('input', {bubbles: true})); }")
    page.wait_for_timeout(400)
    assert page.eval_on_selector("#shell-label", "el => el.textContent") \
        .startswith("CMB")
    for field in ("crust", "iono", "magneto"):
        assert page.is_disabled(f"#toggle-{field}"), \
            f"{field} should be greyed at the CMB"
    assert not page.is_disabled("#toggle-core")
    page.evaluate("window.geomagModelExplorer.renderOnce()")
    ARTIFACTS.mkdir(exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "phase4_cmb.png"))


def test_colorbar_lock(app_page):
    """Locked scale survives a shell change; unlock resumes auto-range."""
    page, _errors = app_page
    days = page.evaluate("() => Object.keys(window.geomagModelExplorer.manifest.days)")
    if not days:
        pytest.skip("no full day cached yet")
    page.check("#toggle-core")
    for field in ("crust", "iono", "magneto"):   # core-only scale (all four
        page.uncheck(f"#toggle-{field}")         # default on since v2.12)
    page.wait_for_timeout(500)
    surface_label = page.text_content("#colorbar-max")
    page.click("#colorbar-lock")
    assert page.get_attribute("#colorbar-lock", "aria-pressed") == "true"
    lock = page.evaluate("() => window.geomagModelExplorer.state.vmaxLock")
    assert isinstance(lock, (int, float)) and lock > 0
    page.eval_on_selector(
        "#shell-slider",
        "el => { el.value = '0';"
        " el.dispatchEvent(new Event('input', {bubbles: true})); }")
    page.wait_for_timeout(600)
    page.evaluate("window.geomagModelExplorer.renderOnce()")
    assert page.text_content("#shell-label").startswith("CMB")
    assert page.text_content("#colorbar-max") == surface_label, \
        "locked colorbar range changed across a shell change"
    locked_render = _hash_canvas(page)
    # unlock at the CMB: auto-range (core CMB p99 ≈ 1.45e6 nT) takes over
    page.click("#colorbar-lock")
    assert page.evaluate("() => window.geomagModelExplorer.state.vmaxLock") is None
    assert page.get_attribute("#colorbar-lock", "aria-pressed") == "false"
    page.wait_for_timeout(400)
    page.evaluate("window.geomagModelExplorer.renderOnce()")
    assert page.text_content("#colorbar-max") != surface_label, \
        "unlocking did not recompute the colorbar range"
    assert _hash_canvas(page) != locked_render, \
        "unlocking did not change the rendered colour mapping"


def test_playback_advances_frames(app_page):
    """Phase 5: playback yields distinct frames; texture cache stays bounded."""
    page, _errors = app_page
    days = page.evaluate("() => Object.keys(window.geomagModelExplorer.manifest.days)")
    if not days:
        pytest.skip("no full day cached yet")
    page.check("#toggle-iono")
    page.check("#toggle-magneto")
    page.uncheck("#toggle-crust")
    page.wait_for_timeout(800)
    page.select_option("#speed-select", "4")
    page.click("#play-btn")
    hashes = set()
    for _ in range(6):
        page.wait_for_timeout(1000)
        hashes.add(_hash_canvas(page))
    page.click("#play-btn")   # pause
    assert len(hashes) >= 4, f"only {len(hashes)} distinct frames in playback"
    assert page.evaluate("() => window.geomagModelExplorer.state.pos") > 0
    # bounded by the 128 MB byte budget (dataset.js), not an entry count:
    # ~245 core-grid tiles is the worst legal population; playback plus the
    # idle neighbor-shell prefetch must stay inside it
    assert page.evaluate("() => window.geomagModelExplorer.cacheSize()") <= 245


def test_playback_is_smooth(app_page):
    """Regression: the displayed time never steps backwards at a 15-min
    boundary (textures must swap in the same frame uMix resets)."""
    page, _errors = app_page
    days = page.evaluate("() => Object.keys(window.geomagModelExplorer.manifest.days)")
    if not days:
        pytest.skip("no full day cached yet")
    page.check("#toggle-iono")
    page.check("#toggle-magneto")
    page.wait_for_timeout(800)
    page.select_option("#speed-select", "4")
    page.click("#play-btn")
    page.wait_for_timeout(500)        # let prefetch warm up
    trace = page.evaluate("""async () => {
      const a = window.geomagModelExplorer;
      const out = [];
      await new Promise((resolve) => {
        function tick() {
          out.push(a.timePos());
          if (out.length >= 120) return resolve();
          requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
      return out;
    }""")
    page.click("#play-btn")   # pause
    # the trace must actually cross 15-min boundaries to test anything
    assert max(trace) - min(trace) > 1, f"trace too short: {trace[:5]}..."
    for prev, cur in zip(trace, trace[1:]):
        if cur - prev < -90:          # day wrap 96 -> 0 is fine
            continue
        assert cur - prev >= -1e-6, \
            f"displayed time stepped backwards: {prev} -> {cur}"


def test_hover_readout(app_page):
    """Phase 6: hovering the globe shows lat/lon and a plausible nT value."""
    page, _errors = app_page
    box = page.locator("#globe canvas").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_selector("#readout:not([hidden])", timeout=TIMEOUT_MS)
    text = page.eval_on_selector("#readout", "el => el.textContent")
    assert "nT" in text and "Upward" in text
    assert "°" in text
    # hovering off the globe hides it
    page.mouse.move(box["x"] + 5, box["y"] + 5)
    page.wait_for_selector("#readout[hidden]", state="attached",
                           timeout=TIMEOUT_MS)


def test_api_days(page):
    resp = page.request.get(BASE + "/api/days")
    assert resp.ok
    data = resp.json()
    assert data["default_day"] == "2020-01-01"
    assert isinstance(data["days"], list)


@pytest.mark.skip(reason="the /foundry/geomag-model-explorer portal route was removed; a "
                         "restored route would also need Playwright http_credentials for "
                         "the vanaheim basic auth")
def test_portal_prefix(page):
    page.set_viewport_size(VIEWPORT)
    errors = _collect_errors(page)
    page.goto(PORTAL + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.cacheSize()") > 0
    assert errors == [], f"browser errors via portal: {errors}"
