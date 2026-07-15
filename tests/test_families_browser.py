"""Model families + core SV UI (PLAN v2.9/v2.10/v2.11) against a sandboxed
server with the `families` flag on (:8222): the "Field to explore" dropdown
is primary and the "Model" dropdown lenses it, All×CHAOS swaps the date
picker for the curated diurnal series, layers a family lacks grey out with
family-aware tooltips, choosing a field a model can't serve greys that model
out and falls it back, the Core study's B ↔ dB/dt radio drives the core-sv
field with nT/yr units, and family permalinks round-trip. v2.11 adds the
Crust (timeless static series) and Magnetosphere (kind-less, day-cache +
diurnal reuse) studies, single-field families (LCS-1, MMA_SHA_2F seeded
here; the others are data-driven clones), permanently greyed unevaluated
entries (MLI_SHA_2E, AMPS), and the ⓘ model-info modal. The flag-off server
(:8223, same data, studies still on) shows no Model dropdown and degrades
secular/diurnal series links to v1 (F6).

The sandbox lives in /var/tmp (disk, not the host's 4.9G /tmp tmpfs): the
seeded tiles — a full day + five series — are ~920 MB."""
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
CRUST_CI_ID = "crust-static"
CRUST_LCS1_ID = "crust-static@lcs1"
MMA2F_DAY_ID = "daily-2020-01-01@mma2f"
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
        # per_model feeds the manifest's v4 "models" block (the ⓘ modal's
        # degree/validity rows) — a representative subset is enough
        (tmp / "data" / "validity.json").write_text(json.dumps(
            {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z",
             "per_model": {
                 "MCO_SHA_2C": {"start": "2013-11-25T03:00:00Z",
                                "end": "2023-11-30T21:00:00Z",
                                "expression":
                                    "MCO_SHA_2C(max_degree=18,min_degree=1)"},
                 "LCS-1": {"start": "0001-01-01T00:00:00Z",
                           "end": "4000-01-01T00:00:00Z",
                           "expression":
                               "'LCS-1'(max_degree=185,min_degree=1)"},
             }}))
        (tmp / "features_on.json").write_text(
            '{"permalink": true, "studies": true, "families": true,'
            ' "modelinfo": true}')
        (tmp / "features_off.json").write_text(
            '{"permalink": true, "studies": true}')
        for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY,
                      "--series", ANNUAL_ID],
                     ["tests/stub_fetch.py", "--series", SECULAR_ID],
                     ["tests/stub_fetch.py", "--series", CHAOS_DAY_ID],
                     ["tests/stub_fetch.py", "--series", CRUST_CI_ID],
                     ["tests/stub_fetch.py", "--series", CRUST_LCS1_ID],
                     ["tests/stub_fetch.py", "--series", MMA2F_DAY_ID],
                     ["export.py", "--static"],
                     ["export.py", "--day", SEED_DAY],
                     ["export.py", "--series", ANNUAL_ID],
                     ["export.py", "--series", SECULAR_ID],
                     ["export.py", "--series", CHAOS_DAY_ID],
                     ["export.py", "--series", CRUST_CI_ID],
                     ["export.py", "--series", CRUST_LCS1_ID],
                     ["export.py", "--series", MMA2F_DAY_ID]):
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
    # secondary "Model" selector: seeded families in curated FAMILY_ORDER,
    # then the permanently disabled unevaluated entries (v2.11)
    assert page.is_visible("#family-select")
    fams = page.eval_on_selector_all(
        "#family-select option", "os => os.map(o => o.value)")
    assert fams == ["ci", "chaos", "lcs1", "mma2f", "mli2e", "amps"]
    assert page.input_value("#family-select") == "ci"
    # primary "Field to explore" dropdown: stable ids, per-source labels,
    # default All ('daily' relabeled All in v2.10; Crust + Magnetosphere
    # added in v2.11)
    assert page.eval_on_selector_all(
        "#field-select option", "os => os.map(o => o.value)") \
        == ["daily", "core", "crust", "seasons", "magneto"]
    assert page.eval_on_selector_all(
        "#field-select option", "os => os.map(o => o.textContent)") \
        == ["All", "Core", "Crust", "Ionosphere", "Magnetosphere"]
    assert page.input_value("#field-select") == "daily"
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
    # the day picker locks to the curated diurnal series' date (56239c6
    # "lock the day selector"); the series <select> stays hidden on All
    assert page.is_visible("#date-picker")
    assert page.is_disabled("#date-picker")
    assert page.input_value("#date-picker") == SEED_DAY
    assert page.is_hidden("#series-select")
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == CHAOS_DAY_ID
    # the transport looks exactly like a real day
    assert page.get_attribute("#time-slider", "max") == "1440"
    assert page.text_content("#time-label") == "00:00"
    # CHAOS has no ionospheric layer: the iono toggle greys out, says why
    # (decision 2026-06-12). The field dropdown stays fully selectable — field
    # is primary; picking Ionosphere falls the model back (own test below).
    assert page.is_disabled("#toggle-iono")
    assert "not part of the CHAOS" in _title_of(page, "#toggle-iono")
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


def test_field_switch_falls_model_back(servers, watched_page):
    """Field is primary: choosing Ionosphere while the model is CHAOS (which
    has no ionospheric layer) greys CHAOS out and falls the model back to CI.
    Since the symmetric field grey-out (v2.11) a real user can't click a
    field the model lacks — select_option drives the option programmatically,
    exercising the fallback as the permalink/garbage safety net."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # Core has data in both models — switch to CHAOS there
    page.select_option("#field-select", "core")
    page.select_option("#family-select", "chaos")
    assert page.evaluate("() => window.geomagModelExplorer.state.family") == "chaos"
    # now pick Ionosphere: CHAOS can't serve it, so the model falls back to CI
    page.select_option("#field-select", "seasons")
    assert page.input_value("#field-select") == "seasons"
    assert page.input_value("#family-select") == "ci"
    assert page.evaluate("() => window.geomagModelExplorer.state.family") == "ci"
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == ANNUAL_ID
    # and CHAOS is greyed out in the Model dropdown while Ionosphere is
    # chosen — with the CHAOS-MIO footnote (v2.11: the one model skipped
    # inside an otherwise-covered family)
    assert page.eval_on_selector(
        "#family-select option[value=chaos]", "o => o.disabled") is True
    assert "CHAOS-MIO" in page.eval_on_selector(
        "#family-select option[value=chaos]", "o => o.title")
    assert page.eval_on_selector(
        "#family-select option[value=ci]", "o => o.disabled") is False


def test_core_tab_b_dbdt_toggle(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#field-select", "core")
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
    assert page.input_value("#field-select") == "core"
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
    assert page.input_value("#field-select") == "daily"


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


# --- v2.11: Crust + Magnetosphere studies, unevaluated entries, ⓘ modal ---

def test_unevaluated_models_stay_disabled(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    for fam, needle in (("mli2e", "degree"), ("amps", "polar")):
        sel = f"#family-select option[value={fam}]"
        assert page.eval_on_selector(sel, "o => o.disabled") is True
        assert needle in page.eval_on_selector(sel, "o => o.title")
    # they survive every refresh: switch fields and re-check
    page.select_option("#field-select", "crust")
    assert page.eval_on_selector(
        "#family-select option[value=amps]", "o => o.disabled") is True


def test_crust_study_is_timeless(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#field-select", "crust")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.day") == CRUST_CI_ID
    # single-epoch series: no time axis — the transport hides entirely
    assert page.is_hidden("#timebar")
    assert page.is_hidden("#date-picker")
    assert page.is_visible("#series-select")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.enabled.crust")
    # switch the lens to LCS-1: its own series, its own storage range
    page.select_option("#family-select", "lcs1")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.day") == CRUST_LCS1_ID
    assert page.evaluate(
        "() => window.geomagModelExplorer.manifest"
        f".series['{CRUST_LCS1_ID}'].qrange_nT.crust") == 2000.0
    assert page.is_hidden("#timebar")
    # leaving the crust study restores the transport
    page.select_option("#field-select", "daily")
    assert page.is_visible("#timebar")


def test_magneto_study_reuses_day_and_diurnals(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#field-select", "magneto")
    # CI rides the day cache, pinned like All — full 15-min transport
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.day") == SEED_DAY
    assert page.is_visible("#date-picker")
    assert page.is_disabled("#date-picker")
    assert page.get_attribute("#time-slider", "max") == "1440"
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.enabled.magneto")
    assert not page.evaluate(
        "() => window.geomagModelExplorer.state.enabled.core")
    # MMA_SHA_2F: its own diurnal series
    page.select_option("#family-select", "mma2f")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.day") == MMA2F_DAY_ID
    # CHAOS: no dedicated series — its day series carries the magneto layer
    page.select_option("#family-select", "chaos")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.day") == CHAOS_DAY_ID
    # LCS-1 has nothing with a magnetosphere layer: greyed out
    assert page.eval_on_selector(
        "#family-select option[value=lcs1]", "o => o.disabled") is True


def test_field_options_grey_per_model(servers, watched_page):
    """Symmetric grey-out (user report 2026-07-03): a field the chosen model
    cannot serve must not be selectable — it previously stayed live and
    picking it silently swapped the model back to one that had it (All ×
    MMA_SHA_2F offered Crust, which landed on Swarm CI)."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#family-select", "mma2f")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.family") == "mma2f"
    disabled = dict(page.eval_on_selector_all(
        "#field-select option", "os => os.map(o => [o.value, o.disabled])"))
    assert disabled == {"daily": False, "core": True, "crust": True,
                        "seasons": True, "magneto": False}
    assert "no Crust data in the MMA_SHA_2F model series" == \
        page.eval_on_selector("#field-select option[value=crust]",
                              "o => o.title")
    # back to Swarm CI: every study reopens
    page.select_option("#family-select", "ci")
    disabled = dict(page.eval_on_selector_all(
        "#field-select option", "os => os.map(o => [o.value, o.disabled])"))
    assert set(disabled.values()) == {False}
    # the CHAOS-MIO footnote rides the field-side tooltip too
    page.select_option("#family-select", "chaos")
    assert "CHAOS-MIO" in page.eval_on_selector(
        "#field-select option[value=seasons]", "o => o.title")


def test_magneto_tab_permalink_roundtrip(servers, watched_page):
    """The kind-less tabs are indistinguishable from the data alone — the
    functional tab= key (v2.11) is what brings Magnetosphere back."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#field-select", "magneto")
    page.wait_for_function(
        "() => location.hash.includes('tab=magneto')", timeout=TIMEOUT_MS)
    href = page.evaluate("() => location.href")
    page.goto("about:blank")
    page.goto(href, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.input_value("#field-select") == "magneto"
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.enabled.magneto")


def test_model_info_modal(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.locator("#model-info-btn").count() == 1
    page.click("#model-info-btn")
    assert page.eval_on_selector("#model-info", "d => d.open") is True
    text = page.text_content("#model-info")
    assert "Swarm CI" in text
    assert "MCO_SHA_2C" in text                    # day-cache core model
    assert "max_degree=18" in text                 # expression (manifest v4)
    assert "CHAOS-MIO" in text and "AMPS" in text  # unevaluated footer
    page.keyboard.press("Escape")                  # native <dialog> Esc
    assert page.eval_on_selector("#model-info", "d => d.open") is False
    # per-family content swap: the LCS-1 crust study
    page.select_option("#field-select", "crust")
    page.select_option("#family-select", "lcs1")
    page.click("#model-info-btn")
    text = page.text_content("#model-info")
    assert "LCS-1" in text and "max_degree=185" in text
    assert "single snapshot" in text
    # backdrop click closes (the dialog itself is the event target there)
    page.mouse.click(5, 5)
    assert page.eval_on_selector("#model-info", "d => d.open") is False


def test_flag_off_has_no_family_controls(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    page.goto(off + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.locator("#family-select").count() == 0
    assert page.locator("#sv-toggle").count() == 0
    assert page.locator("#model-info-btn").count() == 0  # modelinfo off too
    # no Core study and no per-source labels in the v1 lineup; the field
    # dropdown shows exactly the two v1 studies
    assert page.eval_on_selector_all(
        "#field-select option", "os => os.map(o => o.value)") \
        == ["daily", "seasons"]
    assert page.eval_on_selector_all(
        "#field-select option", "os => os.map(o => o.textContent)") \
        == ["Daily", "Ionosphere (Seasonal)"]


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
    assert page.input_value("#field-select") == "daily"
    assert page.get_attribute("#time-slider", "max") == "1440"
