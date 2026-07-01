"""Model families + core SV UI (PLAN v2.9) against a sandboxed server with
the `families` flag on (:8222): the Model-series selector lenses the page,
Combined×CHAOS swaps the date picker for the curated diurnal series, layers
a family lacks grey out with family-aware tooltips, the Core tab's B ↔ dB/dt
radio drives the core-sv field with nT/yr units, and family permalinks
round-trip. The flag-off server (:8223, same data, studies still on) shows
no new controls and degrades secular/diurnal series links to v1 (F6).

The sandbox lives in /var/tmp (disk, not the host's 4.9G /tmp tmpfs): the
seeded tiles — a full day + three series — are ~750 MB."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PORT_ON = 8222
PORT_OFF = 8223
SEED_DAY = "2020-01-01"
ANNUAL_ID = "mio-seasonal-2020"
SECULAR_ID = "core-secular"
CHAOS_DAY_ID = "daily-2020-01-01@chaos"
TIMEOUT_MS = 120_000

DEMO_CORE = f"#tab=core&series={SECULAR_ID}&f=core-sv&c=Up&s=cmb"
DEMO_CHAOS = (f"#family=chaos&tab=daily&series={CHAOS_DAY_ID}"
              "&e=2020-01-01T12:00&f=core,crust,magneto&c=Up&s=h300")


def _wait_port(port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"server on :{port} never came up")


@pytest.fixture(scope="module")
def servers():
    """One seeded sandbox (day + static + annual/secular/chaos-diurnal
    series); families on / families off (studies on for both)."""
    tmp = Path(tempfile.mkdtemp(prefix="geomag-model-explorer-families-",
                                dir="/var/tmp"))
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    try:
        (tmp / "data").mkdir()
        (tmp / "data" / "validity.json").write_text(json.dumps(
            {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
        (tmp / "features_on.json").write_text(
            '{"permalink": true, "studies": true, "families": true}')
        (tmp / "features_off.json").write_text(
            '{"permalink": true, "studies": true}')
        for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY,
                      "--series", ANNUAL_ID],
                     ["tests/stub_fetch.py", "--series", SECULAR_ID],
                     ["tests/stub_fetch.py", "--series", CHAOS_DAY_ID],
                     ["export.py", "--static"],
                     ["export.py", "--day", SEED_DAY],
                     ["export.py", "--series", ANNUAL_ID],
                     ["export.py", "--series", SECULAR_ID],
                     ["export.py", "--series", CHAOS_DAY_ID]):
            subprocess.run([sys.executable, *args], cwd=REPO, env=env,
                           check=True, capture_output=True)
        shutil.rmtree(tmp / "data" / "raw", ignore_errors=True)
        procs = []
        try:
            for port, features in ((PORT_ON, tmp / "features_on.json"),
                                   (PORT_OFF, tmp / "features_off.json")):
                procs.append(subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "serve:app",
                     "--host", "127.0.0.1", "--port", str(port)],
                    cwd=REPO,
                    env=dict(env, GEOMAG_MODEL_EXPLORER_FEATURES=str(features)),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                _wait_port(port)
            yield f"http://127.0.0.1:{PORT_ON}", f"http://127.0.0.1:{PORT_OFF}"
        finally:
            for p in procs:
                p.terminate()
                p.wait(timeout=10)
    finally:
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


def _title_of(page, selector):
    return page.evaluate(
        f"() => document.querySelector('{selector}').parentElement.title")


def test_families_lineup_and_daily_untouched(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # page-level Model-series selector with both probed families
    assert page.is_visible("#family-select")
    fams = page.eval_on_selector_all(
        "#family-select option", "os => os.map(o => o.value)")
    assert fams == ["ci", "chaos"]
    assert page.input_value("#family-select") == "ci"
    # per-source labels on stable tab ids (checkpoint outcome)
    assert page.text_content("#tab-daily") == "Combined models"
    assert page.text_content("#tab-core") == "Core"
    assert page.text_content("#tab-seasons") == "Ionosphere"
    assert page.get_attribute("#tab-daily", "aria-selected") == "true"
    # Daily ≡ v1: date picker, 1440 one-minute ticks, summing checkboxes
    assert page.is_visible("#date-picker")
    assert page.is_hidden("#series-select")
    assert page.get_attribute("#time-slider", "max") == "1440"
    assert page.is_hidden("#sv-toggle")
    # the units rule as code: no checkbox exists for the nT/yr field
    assert page.locator("#toggle-core-sv").count() == 0


def test_chaos_lens_on_combined(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#family-select", "chaos")
    # the date picker yields to the curated diurnal series
    assert page.is_hidden("#date-picker")
    assert page.is_visible("#series-select")
    assert page.input_value("#series-select") == CHAOS_DAY_ID
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == CHAOS_DAY_ID
    # the transport looks exactly like a real day
    assert page.get_attribute("#time-slider", "max") == "1440"
    assert page.text_content("#time-label") == "00:00"
    # CHAOS has no ionospheric layer: grey out, say why (decision 2026-06-12)
    assert page.is_disabled("#toggle-iono")
    assert "not part of the CHAOS" in _title_of(page, "#toggle-iono")
    assert page.is_disabled("#tab-seasons")
    # crust and magneto are CHAOS layers — still live
    assert not page.is_disabled("#toggle-crust")
    assert not page.is_disabled("#toggle-magneto")
    assert "CHAOS" in page.text_content("#model-attribution")
    # back to Swarm CI: snapshot restores the real day and the picker
    page.select_option("#family-select", "ci")
    assert page.is_visible("#date-picker")
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_DAY
    assert not page.is_disabled("#toggle-iono")
    assert "Comprehensive Inversion" in \
        page.text_content("#model-attribution")


def test_family_switch_leaves_dead_tab(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.click("#tab-seasons")
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == ANNUAL_ID
    # CHAOS has no annual series: the seasons tab dies, Combined catches us
    page.select_option("#family-select", "chaos")
    assert page.get_attribute("#tab-daily", "aria-selected") == "true"
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == CHAOS_DAY_ID


def test_core_tab_b_dbdt_toggle(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.click("#tab-core")
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SECULAR_ID
    # one displayed field at a time: radio replaces the summing checkboxes
    assert page.is_hidden("#field-toggles")
    assert page.is_visible("#sv-toggle")
    assert page.is_checked("#sv-b")
    assert page.evaluate("() => window.geomagModelExplorer.state.enabled.core")
    # yearly transport: 10 epochs × 10 ticks, dated label
    assert page.get_attribute("#time-slider", "max") == "90"
    assert page.text_content("#time-label") == "2014-06-01"
    assert "nT" in page.text_content("#colorbar-max")
    assert "nT/yr" not in page.text_content("#colorbar-max")
    # lock the scale in nT, then switch units: the lock must not survive
    page.click("#colorbar-lock")
    assert page.evaluate("() => window.geomagModelExplorer.state.vmaxLock") is not None
    page.click("#sv-dbdt")
    assert page.evaluate("() => window.geomagModelExplorer.state.vmaxLock") is None
    assert page.evaluate("() => window.geomagModelExplorer.state.enabled['core-sv']")
    assert not page.evaluate("() => window.geomagModelExplorer.state.enabled.core")
    assert "nT/yr" in page.text_content("#colorbar-max")
    page.click("#sv-b")
    assert "nT/yr" not in page.text_content("#colorbar-max")


def test_core_permalink_roundtrip(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_CORE, timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SECULAR_ID
    assert state["enabled"]["core-sv"] and not state["enabled"]["core"]
    assert state["shell"] == "cmb"
    assert page.get_attribute("#tab-core", "aria-selected") == "true"
    assert page.is_checked("#sv-dbdt")
    assert "nT/yr" in page.text_content("#colorbar-max")
    # write-back keeps the series keys; ci is encoded as *no* family key
    page.wait_for_function(
        f"() => location.hash.includes('series={SECULAR_ID}') && "
        "location.hash.includes('tab=core') && "
        "location.hash.includes('f=core-sv') && "
        "!location.hash.includes('family=')", timeout=TIMEOUT_MS)


def test_chaos_permalink_roundtrip(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_CHAOS, timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == CHAOS_DAY_ID
    assert state["family"] == "chaos"
    assert state["pos"] == 48                  # e=12:00 of the 15-min epochs
    assert state["shell"] == "h300"
    assert state["enabled"]["core"] and state["enabled"]["crust"] \
        and state["enabled"]["magneto"]
    assert page.input_value("#family-select") == "chaos"
    page.wait_for_function(
        f"() => location.hash.includes('series={CHAOS_DAY_ID}') && "
        "location.hash.includes('family=chaos') && "
        "location.hash.includes('tab=daily')", timeout=TIMEOUT_MS)


def test_lens_only_permalink_lands_on_family_default(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#family=chaos", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.family") == "chaos"
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == CHAOS_DAY_ID
    assert page.get_attribute("#tab-daily", "aria-selected") == "true"


def test_garbage_family_ignored(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + f"/#family=wdmam&day={SEED_DAY}&t=06:00&f=core&c=N&s=cmb",
              timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["family"] == "ci"
    assert state["day"] == SEED_DAY            # the v1 keys stay in charge
    assert state["pos"] == 24
    assert state["shell"] == "cmb"


def test_old_v1_link_unchanged(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + f"/#day={SEED_DAY}&t=06:00&f=core&c=N&s=cmb",
              timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SEED_DAY
    page.locator("#time-slider").fill("450")   # 07:30 — trigger a write-back
    page.wait_for_function(
        "() => location.hash.includes('t=07:30')", timeout=TIMEOUT_MS)
    assert "family=" not in page.evaluate("() => location.hash")


def test_flag_off_has_no_family_controls(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.locator("#family-select").count() == 0
    assert page.locator("#tab-core").count() == 0
    assert page.locator("#sv-toggle").count() == 0
    assert page.text_content("#tab-daily") == "Daily"
    assert page.text_content("#tab-seasons") == "Ionosphere (Seasonal)"


@pytest.mark.parametrize("sid", [SECULAR_ID, CHAOS_DAY_ID])
def test_flag_off_degrades_gated_series_links(servers, watched_page, sid):
    """F6: with studies on but families off, secular/diurnal series links
    must not land a foreign timeline on the Daily tab."""
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + f"/#tab=core&series={sid}&f=core-sv", timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SEED_DAY
    assert state["pos"] == 0
    assert page.get_attribute("#tab-daily", "aria-selected") == "true"
    assert page.get_attribute("#time-slider", "max") == "1440"
