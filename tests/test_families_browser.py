"""Model families + core SV UI (PLAN v2.9/v2.10/v2.11/v2.14) against a
sandboxed server with the `families` flag on (:8228): the "Explore category"
pills are primary and the "Model" dropdown lenses them, All×CHAOS swaps the
date picker for the curated diurnal series, layers a family lacks grey out
with family-aware tooltips, the pills never grey out — choosing a category
a model can't serve falls the model back and announces it (v2.14) — the
Core study's B ↔ dB/dt radio drives the core-sv field with nT/yr units, and
family permalinks round-trip. v2.11 adds the Crust (timeless static series)
and Magnetosphere (kind-less, day-cache + diurnal reuse) studies,
single-field families (LCS-1, MMA_SHA_2F seeded here; the others are
data-driven clones), permanently greyed unevaluated entries (MLI_SHA_2E,
AMPS), and the ⓘ model-info modal. The flag-off server (:8229, same data,
studies still on) shows no Model dropdown and degrades secular/diurnal
series links to v1 (F6).

The sandbox lives in /var/tmp (disk, not the host's 4.9G /tmp tmpfs): the
seeded tiles — a full day + five series — are ~920 MB (core-secular is
quarterly at 2° since the v2.13 addendum)."""
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
# 8213-8223 are occupied by unrelated fleet services on this host (v2.13
# finding) — the suite moved to the free range with v2.14
PORT_ON = 8228
PORT_OFF = 8229
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
    # primary "Explore category" pills: stable ids, per-source labels,
    # default All ('daily' relabeled All in v2.10; Crust + Magnetosphere
    # added in v2.11; pills since v2.14)
    assert page.eval_on_selector_all(
        "#field-pills input", "is => is.map(i => i.value)") \
        == ["daily", "core", "crust", "seasons", "magneto"]
    assert page.eval_on_selector_all(
        "#field-pills label", "ls => ls.map(l => l.textContent)") \
        == ["All", "Core", "Crust", "Ionosphere", "Magnetosphere"]
    assert page.is_checked("#field-daily")
    # Daily ≡ v1: date picker, 1440 one-minute ticks, summing checkboxes
    assert page.is_visible("#date-picker")
    assert page.is_hidden("#series-select")
    assert page.get_attribute("#time-slider", "max") == "1440"
    assert page.is_hidden("#sv-toggle")
    # the units rule as code: no checkbox exists for the nT/yr field
    assert page.locator("#toggle-core-sv").count() == 0
    # v2.14 layer labels: row 2 reads "Fields to include" on a summing tab,
    # and the series/date slot is headed "Visualisation mode"
    assert page.text_content("#fields-label") == "Fields to include"
    assert page.text_content("#date-control .ctl-label") == "Visualisation mode"


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
    # (decision 2026-06-12). The category pills stay fully clickable —
    # category is primary; picking Ionosphere falls the model back (own
    # test below).
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
    """Category is primary: choosing Ionosphere while the model is CHAOS
    (which has no ionospheric layer) falls the model back to CI and
    announces it (v2.14) — the pills never grey out, so this is a real
    click path, not just the permalink/garbage safety net."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # Core has data in both models — switch to CHAOS there
    page.check("#field-core")
    page.select_option("#family-select", "chaos")
    assert page.evaluate("() => window.geomagModelExplorer.state.family") == "chaos"
    # now pick Ionosphere: CHAOS can't serve it, so the model falls back to
    # CI — flagged by the transient status chip naming both families
    page.check("#field-seasons")
    assert page.is_checked("#field-seasons")
    assert page.input_value("#family-select") == "ci"
    assert page.evaluate("() => window.geomagModelExplorer.state.family") == "ci"
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == ANNUAL_ID
    note = page.text_content("#model-switch-note")
    assert "Swarm CI" in note and "CHAOS has no Ionosphere data" in note
    # the chip is transient — gone after ~4 s
    page.wait_for_selector("#model-switch-note", state="detached",
                           timeout=TIMEOUT_MS)
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
    page.check("#field-core")
    assert page.evaluate("() => window.geomagModelExplorer.state.day") == SECULAR_ID
    # one displayed field at a time: radio replaces the summing checkboxes,
    # and the row label follows the swap (v2.14)
    assert page.is_hidden("#field-toggles")
    assert page.is_visible("#sv-toggle")
    assert page.is_checked("#sv-b")
    assert page.text_content("#fields-label") == "Field to show"
    assert page.evaluate("() => window.geomagModelExplorer.state.enabled.core")
    # quarterly transport (v2.13 addendum): 37 epochs × 10 ticks, dated label
    assert page.get_attribute("#time-slider", "max") == "360"
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
    # the colorbar relabels on the texture commit, not on the click — until
    # the dB/dt tiles bind it still (correctly) describes the shown B field
    page.wait_for_function(
        "() => !window.geomagModelExplorer.pending()", timeout=TIMEOUT_MS)
    assert "nT/yr" in page.text_content("#colorbar-max")
    page.click("#sv-b")
    page.wait_for_function(
        "() => !window.geomagModelExplorer.pending()", timeout=TIMEOUT_MS)
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
    assert page.is_checked("#field-core")
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
    assert page.is_checked("#field-daily")


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
    # they survive every refresh: switch categories and re-check
    page.check("#field-crust")
    assert page.eval_on_selector(
        "#family-select option[value=amps]", "o => o.disabled") is True


def test_crust_study_is_timeless(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.check("#field-crust")
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
    page.check("#field-daily")
    assert page.is_visible("#timebar")


def test_magneto_study_reuses_day_and_diurnals(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.check("#field-magneto")
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


def test_category_pills_never_disabled(servers, watched_page):
    """v2.14 inverts the v2.11 symmetric grey-out (user decision
    2026-07-15): the category is the top-level choice and must always be
    actionable. A pill the chosen model can't serve stays clickable —
    clicking it falls the model back to the first family that serves it
    (Swarm CI serves everything and sorts first) and announces the switch;
    the Model select stays the honest, greyed side."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.select_option("#family-select", "mma2f")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.family") == "mma2f"
    # no pill is ever disabled, whatever the model
    assert page.eval_on_selector_all(
        "#field-pills input", "is => is.some(i => i.disabled)") is False
    # clicking Crust under MMA_SHA_2F auto-switches the model to Swarm CI
    page.check("#field-crust")
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.family") == "ci"
    assert page.input_value("#family-select") == "ci"
    assert page.evaluate(
        "() => window.geomagModelExplorer.state.day") == CRUST_CI_ID
    note = page.text_content("#model-switch-note")
    assert "Swarm CI" in note and "MMA_SHA_2F has no Crust data" in note
    # the Model select still greys honestly: MMA_SHA_2F has no crust series
    assert page.eval_on_selector(
        "#family-select option[value=mma2f]", "o => o.disabled") is True
    assert "no Crust data in the MMA_SHA_2F model series" == \
        page.eval_on_selector("#family-select option[value=mma2f]",
                              "o => o.title")
    # pills still all enabled after the refresh
    assert page.eval_on_selector_all(
        "#field-pills input", "is => is.some(i => i.disabled)") is False


def test_magneto_tab_permalink_roundtrip(servers, watched_page):
    """The kind-less tabs are indistinguishable from the data alone — the
    functional tab= key (v2.11) is what brings Magnetosphere back."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    page.check("#field-magneto")
    page.wait_for_function(
        "() => location.hash.includes('tab=magneto')", timeout=TIMEOUT_MS)
    href = page.evaluate("() => location.href")
    page.goto("about:blank")
    page.goto(href, timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.is_checked("#field-magneto")
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
    assert "CHAOS-MIO" in text and "AMPS" in text  # unevaluated footer
    # the exact VirES expression rides a dedicated code row (v2.14),
    # verbatim from manifest.models, with the docs link beneath
    exprs = page.eval_on_selector_all(
        "#model-info .mi-expr code", "cs => cs.map(c => c.textContent)")
    assert any("max_degree=18" in e for e in exprs)
    assert page.eval_on_selector("#model-info .mi-docs a", "a => a.href") \
        == ("https://viresclient.readthedocs.io/en/latest/"
            "available_parameters.html#models")
    # 127.0.0.1 is a secure context: the copy affordance is present
    assert page.locator("#model-info .mi-copy").count() > 0
    page.keyboard.press("Escape")                  # native <dialog> Esc
    assert page.eval_on_selector("#model-info", "d => d.open") is False
    # per-family content swap: the LCS-1 crust study
    page.check("#field-crust")
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
    # no Core study and no per-source labels in the v1 lineup; the category
    # pills show exactly the two v1 studies
    assert page.eval_on_selector_all(
        "#field-pills input", "is => is.map(i => i.value)") \
        == ["daily", "seasons"]
    assert page.eval_on_selector_all(
        "#field-pills label", "ls => ls.map(l => l.textContent)") \
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
    # the refused link leaves the boot default in charge — pos 32 (08:00 UT)
    # since the v2.12 landing-view tune (stale expectation, latent while the
    # old port made the suite unrunnable; same family as 95eda4c)
    assert state["pos"] == 32
    assert page.is_checked("#field-daily")
    assert page.get_attribute("#time-slider", "max") == "1440"
