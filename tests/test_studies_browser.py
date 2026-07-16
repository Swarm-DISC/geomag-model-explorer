"""Studies feature (PLAN v2.3/v2.10/v2.14) against a sandboxed server
(:8226) with the flag on: the "Explore category" pills appear, the
Ionosphere study plays the annual series (timeline swap, series picker,
iono defaults), permalinks round-trip via tab=/series=/e=, and garbage
degrades. Flag-off (:8227, same data) shows no category pills — exactly
v1."""
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
# 8213-8223 are occupied by unrelated fleet services on this host (v2.13
# finding) — the suite moved to the free range with v2.14
PORT_ON = 8226
PORT_OFF = 8227
SEED_DAY = "2020-01-01"
SERIES_ID = "mio-seasonal-2020"
TIMEOUT_MS = 120_000

# epoch 26 = 2020-01-01 + 26 weeks = 2020-07-01 (leap year)
DEMO_HASH = (f"#tab=seasons&series={SERIES_ID}&e=2020-07-01T12:00"
             "&f=iono&c=Up&s=surface")


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
    """One seeded sandbox (day + static + series); flag on / flag off."""
    tmp = tmp_path_factory.mktemp("studies")
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    (tmp / "features_on.json").write_text(
        '{"permalink": true, "studies": true}')
    for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY,
                  "--series", SERIES_ID],
                 ["export.py", "--static"],
                 ["export.py", "--day", SEED_DAY],
                 ["export.py", "--series", SERIES_ID]):
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


def test_tab_strip_defaults_to_daily(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # the category pills hold the v1 lineup and default to Daily
    assert page.eval_on_selector_all(
        "#field-pills input", "is => is.map(i => i.value)") \
        == ["daily", "seasons"]
    assert page.is_checked("#field-daily")
    assert page.is_visible("#date-picker")
    assert page.is_hidden("#series-select")
    # the Daily timeline is untouched: 1440 one-minute ticks
    assert page.get_attribute("#time-slider", "max") == "1440"


def test_seasons_tab_plays_the_series(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.check("#field-seasons")
    # study defaults: iono on, the series becomes the day, slider ticks in days
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SERIES_ID
    assert page.is_checked("#toggle-iono")
    assert not page.is_checked("#toggle-crust")
    # the tab's field gate: every other model is disabled, not just off
    for field in ("core", "crust", "magneto"):
        assert page.is_disabled(f"#toggle-{field}"), field
    assert not page.is_disabled("#toggle-iono")
    assert page.is_hidden("#date-picker")
    assert page.is_visible("#series-select")
    assert page.get_attribute("#time-slider", "max") == "364"  # 52 weeks
    assert page.text_content("#time-label") == "2020-01-01"
    # scrub to July 1st (tick 182 = epoch 26) and wait for the texture swap
    page.locator("#time-slider").fill("182")
    assert page.text_content("#time-label") == "2020-07-01"
    page.wait_for_function(
        "() => Math.abs(window.geomagModelExplorer.timePos() - 26) < 1e-6",
        timeout=TIMEOUT_MS)
    # back to Daily: the v1 transport returns and the gate lifts
    page.check("#field-daily")
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_DAY
    assert page.get_attribute("#time-slider", "max") == "1440"
    assert page.is_visible("#date-picker")
    assert not page.is_disabled("#toggle-crust")


def test_seasons_gate_overrides_permalink_fields(servers, watched_page):
    """A hash enabling out-of-study fields (f=crust,iono) on the seasonal
    tab gets them forced off — the gate, not the link, decides."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH.replace("f=iono", "f=crust,iono"),
              timeout=TIMEOUT_MS)
    _wait_ready(page)
    enabled = page.evaluate("() => window.geomagModelExplorer.state.enabled")
    assert enabled == {"core": False, "crust": False,
                       "iono": True, "magneto": False,
                       **{f: False for f in enabled
                          if f not in ("core", "crust", "iono", "magneto")}}
    assert page.is_disabled("#toggle-crust")
    assert not page.is_checked("#toggle-crust")


def test_seasons_permalink_roundtrip(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SERIES_ID
    assert state["pos"] == 26
    assert state["enabled"] == {"core": False, "crust": False,
                                "iono": True, "magneto": False,
                                **{f: False for f in state["enabled"]
                                   if f not in ("core", "crust",
                                                "iono", "magneto")}}
    assert page.is_checked("#field-seasons")
    assert page.text_content("#time-label") == "2020-07-01"
    # the write-back keeps the series keys (and drops day=/t=)
    page.wait_for_function(
        f"() => location.hash.includes('series={SERIES_ID}') && "
        "location.hash.includes('tab=seasons') && "
        "location.hash.includes('e=2020-07-01T12:00') && "
        "!location.hash.includes('day=')", timeout=TIMEOUT_MS)
    # switching to Daily swaps the hash back to v1 keys
    page.check("#field-daily")
    page.wait_for_function(
        f"() => location.hash.includes('day={SEED_DAY}') && "
        "!location.hash.includes('series=')", timeout=TIMEOUT_MS)


def test_garbage_series_hash_degrades(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#tab=seasons&series=bogus&e=zz", timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SEED_DAY
    # garbage lands on the boot default — pos 32 (08:00 UT) since the v2.12
    # landing-view tune (same stale expectation 95eda4c fixed in the
    # permalink suite; latent here while the old port made the suite unrunnable)
    assert state["pos"] == 32
    assert page.is_checked("#field-daily")


def test_flag_off_has_no_category_pills(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => document.getElementById('field-pills')") is None
    assert page.evaluate("() => document.getElementById('series-select')") \
        is None
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_DAY
    assert page.get_attribute("#time-slider", "max") == "1440"


def test_chrome_collapse_toggles(servers, watched_page):
    """v2.14: the header and the vis-options box fold away (mobile chrome;
    never in the permalink). Desktop sizes boot expanded."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert not page.eval_on_selector(
        "#controls", "e => e.classList.contains('collapsed')")
    page.click("#controls-toggle")
    assert page.is_hidden("#field-pills")
    assert page.is_visible("#title")
    page.click("#vis-options-toggle")
    assert page.is_hidden("#component-radios")
    page.click("#controls-toggle")
    assert page.is_visible("#field-pills")
    page.click("#vis-options-toggle")
    assert page.is_visible("#component-radios")


def test_chrome_boots_collapsed_on_phones(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    for box in ("#controls", "#vis-options"):
        assert page.eval_on_selector(
            box, "e => e.classList.contains('collapsed')"), box
    page.click("#controls-toggle")
    assert page.is_visible("#field-pills")


def test_view_reset_restores_defaults(servers, watched_page):
    """v2.14: the ⌂ chip resets EVERYTHING — it wipes the permalink hash and
    reloads, so every selection, overlay and the camera return to the boot
    defaults (the boot path is the definition of the default state)."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + f"/#tab=seasons&series={SERIES_ID}&e=2020-07-01T12:00"
              "&f=iono&c=N&s=surface&cam=1.500,1.500,1.500",
              timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.component") == "N"
    with page.expect_navigation():
        page.click("#view-reset")
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SEED_DAY          # the day cache, not the series
    assert state["pos"] == 32                # 08:00 UT boot (v2.12 tune)
    assert state["component"] == "Up"
    assert state["shell"] == "h500"
    assert state["enabled"]["core"] and state["enabled"]["iono"]
    assert page.is_checked("#field-daily")
    pos = page.evaluate(
        "() => window.geomagModelExplorer.globe.camera.position.toArray()")
    assert pos[0] == 0 and abs(pos[1] - 0.3) < 1e-9 \
        and abs(pos[2] - 3.3) < 1e-9, pos
    # NOT asserting an empty hash: the live write-back re-encodes the
    # (now-default) state into the hash within the debounce window
