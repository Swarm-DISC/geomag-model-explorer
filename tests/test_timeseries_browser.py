"""Timeline viewer (PLAN v2.13) against a sandboxed server with the
`timeseries` flag on (:8224): the Globe | Time series | Combined toggle, pin
by click (drags must not pin) and by coordinate entry (geodetic input snaps
to the shell ladder), three uPlot panels whose values equal the summed
lookup() readout, the N/E/Up | R/θ/φ | NEC re-signing, texture-LRU
neutrality + stale-assembly cancellation, permalink round-trip (view/pt/ptc)
and the secular-series timeline (37 quarterly 2° epochs, nT/yr units). The
flag-off server (:8225, same data) has no toggle/panel and silently ignores
v2.13 permalink keys (stability contract).

The sandbox lives in /var/tmp (disk, not the host's tmpfs): the seeded
tiles — one day + static + the quarterly secular series — are a few
hundred MB."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PORT_ON = 8224
PORT_OFF = 8225
SEED_DAY = "2020-01-01"
SECULAR_ID = "core-secular"
TIMEOUT_MS = 120_000

SECULAR_LINK = (f"#tab=core&series={SECULAR_ID}&f=core-sv&c=Up&s=cmb"
                "&view=series&pt=52.00,12.00")


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
    """One seeded sandbox (day + static + secular series); timeseries flag
    on / off (permalink + studies + families on for both, so the secular
    permalink is honored either way)."""
    tmp = Path(tempfile.mkdtemp(prefix="geomag-model-explorer-timeseries-",
                                dir="/var/tmp"))
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    try:
        (tmp / "data").mkdir()
        (tmp / "data" / "validity.json").write_text(json.dumps(
            {"start": "2013-11-25T03:00:00Z",
             "end": "2023-11-30T21:00:00Z", "per_model": {}}))
        (tmp / "features_on.json").write_text(
            '{"permalink": true, "studies": true, "families": true,'
            ' "timeseries": true}')
        (tmp / "features_off.json").write_text(
            '{"permalink": true, "studies": true, "families": true}')
        for args in (["tests/stub_fetch.py", "--static", "--day", SEED_DAY],
                     ["tests/stub_fetch.py", "--series", SECULAR_ID],
                     ["export.py", "--static"],
                     ["export.py", "--day", SEED_DAY],
                     ["export.py", "--series", SECULAR_ID]):
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
                    env=dict(env,
                             GEOMAG_MODEL_EXPLORER_FEATURES=str(features)),
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
        "() => window.geomagModelExplorer"
        " && window.geomagModelExplorer.cacheSize() > 0",
        timeout=TIMEOUT_MS)


def _pin(page, lat="52.07", lon="12.68", rh="6871"):
    """Pin via typed geocentric coordinates; r=6871 km is the boot shell
    (h500), so pinning alone never moves the shell (LRU tests rely on it)."""
    page.fill("#ts-lat", lat)
    page.fill("#ts-lon", lon)
    page.fill("#ts-rh", rh)
    page.click("#ts-pin")


def _wait_charts(page):
    page.wait_for_function(
        "() => window.__timeseries && window.__timeseries.plots().length === 3"
        " && !!window.__timeseries.last()",
        timeout=TIMEOUT_MS)


def test_geodesy(servers, watched_page):
    """WGS84 anchors: 45°/h0 -> 44.8076°/6367.4895 km; round-trip < 1 mm."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    res = page.evaluate("""async () => {
      const g = await import('./geodesy.js');
      const gc = g.geodeticToGeocentric(45, 0);
      const back = g.geocentricToGeodetic(gc.latDeg, gc.radiusM);
      const eq = g.geodeticToGeocentric(0, 0);
      const pole = g.geodeticToGeocentric(90, 0);
      return { lat: gc.latDeg, rKm: gc.radiusM / 1000,
               dLat: Math.abs(back.latDeg - 45),
               dH: Math.abs(back.heightM),
               eq: [eq.latDeg, eq.radiusM],
               pole: [pole.latDeg, pole.radiusM] };
    }""")
    assert abs(res["lat"] - 44.8076) < 5e-4
    assert abs(res["rKm"] - 6367.4895) < 5e-3
    assert res["dLat"] < 1e-9 and res["dH"] < 1e-3
    assert res["eq"] == [0, 6378137]
    assert res["pole"][0] == 90 and abs(res["pole"][1] - 6356752.31) < 0.1


def test_view_toggle(servers, watched_page):
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    assert page.locator("#view-toggle").count() == 1
    assert page.locator("#series-panel[hidden]").count() == 1

    page.check("#view-series")
    assert page.evaluate(
        "getComputedStyle(document.getElementById('globe')).display") == "none"
    assert page.locator("#series-panel:not([hidden])").count() == 1
    assert "pin a location" in page.locator("#ts-hint").text_content()

    page.check("#view-globe")
    assert page.locator("#series-panel[hidden]").count() == 1
    assert page.evaluate(
        "window.geomagModelExplorer.renderer.domElement.clientHeight") > 100


def test_click_pins_not_drag(servers, watched_page):
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-combined")
    box = page.evaluate("""() => {
      const r = window.geomagModelExplorer.renderer.domElement
                  .getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }""")

    # a 60 px drag is an orbit, not a pin
    page.mouse.move(box["x"], box["y"])
    page.mouse.down()
    page.mouse.move(box["x"] + 60, box["y"] + 20, steps=5)
    page.mouse.up()
    assert page.evaluate("window.geomagModelExplorer.state.point") is None

    page.mouse.click(box["x"], box["y"])
    pt = page.evaluate("window.geomagModelExplorer.state.point")
    assert pt and abs(pt["lat"]) <= 90 and abs(pt["lon"]) <= 180
    assert page.evaluate(
        "!!window.geomagModelExplorer.globe.earth.getObjectByName('ts-marker')")
    assert page.locator("#ts-lat").input_value() != ""
    assert page.locator("#ts-snap").text_content().strip() != ""


def test_coord_entry_snaps(servers, watched_page):
    """Geodetic 45°N / h 460 km sits between h400 and h500 rungs -> h500;
    the pinned latitude is the geocentric conversion (≈ 44.81°)."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    page.check("#ts-datum-geodetic")
    _pin(page, lat="45", lon="10", rh="460")
    st = page.evaluate("window.geomagModelExplorer.state")
    assert st["shell"] == "h500", st["shell"]
    assert abs(st["point"]["lat"] - 44.81) < 0.05
    assert abs(st["point"]["lon"] - 10) < 1e-9
    assert page.locator("#shell-label").text_content() == "+500 km"
    assert "h≈" in page.locator("#ts-snap").text_content()


def test_charts_render_and_match_readout(servers, watched_page):
    """The chart at epoch k equals the hover readout's sum of lookup() over
    the enabled-and-available fields — same tiles, same descale."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    _pin(page)
    _wait_charts(page)

    res = page.evaluate("window.__timeseries.last()")
    n = page.evaluate("window.geomagModelExplorer.timeline.nEpochs")
    assert len(res["xs"]) == n == 97
    assert res["gaps"] == 0
    assert all(v is not None for v in res["N"])
    assert max(res["N"]) - min(res["N"]) > 0   # iono/magneto vary intraday

    expected = page.evaluate("""async () => {
      const g = window.geomagModelExplorer;
      const ds = await import('./dataset.js');   // same module instance
      const pt = g.state.point;
      const sum = [0, 0, 0];
      for (const [field, on] of Object.entries(g.state.enabled)) {
        if (!on) continue;
        const src = ds.frameSource(g.state, field);
        if (!src || !src.shells.includes(g.state.shell)) continue;
        const s = src.stepped ? Math.min(10, src.n - 1) : 0;
        const nec = await ds.lookup(field, g.state.shell, g.state.day, s,
                                    pt.lat, pt.lon);
        for (let c = 0; c < 3; c++) sum[c] += nec[c];
      }
      return sum;
    }""")
    got = [res["N"][10], res["E"][10], res["C"][10]]
    for a, b in zip(expected, got):
        assert abs(a - b) < 1e-6, f"{expected} vs {got}"


def test_convention_flips(servers, watched_page):
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    _pin(page)
    _wait_charts(page)

    def chart(i):
        return page.evaluate(f"window.__timeseries.plots()[{i}].data[1]")

    neu3 = chart(2)                       # Upward = -C
    page.check("#ts-conv-nec")
    nec3 = chart(2)                       # C as stored
    assert all(abs(a + b) < 1e-9 for a, b in zip(neu3, nec3))
    page.check("#ts-conv-rtp")
    assert chart(0) == neu3               # B_r = -C = Upward
    label = page.evaluate("window.__timeseries.plots()[0].series[1].label")
    assert "B_r" in label and "nT" in label


def test_chart_chrome(servers, watched_page):
    """v2.13 addendum: no uPlot legends; the component name lives in a
    rotated y-axis label instead (canvas-drawn, so assert via the seam —
    parentheticals stripped to fit the 96px-min panels)."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    _pin(page)
    _wait_charts(page)
    assert page.locator(".u-legend").count() == 0
    labels = page.evaluate(
        "window.__timeseries.plots().map(u => u.axes[1].label)")
    assert labels == [f"{n} (nT)" for n in ("Northward", "Eastward", "Upward")]
    page.check("#ts-conv-rtp")
    labels = page.evaluate(
        "window.__timeseries.plots().map(u => u.axes[1].label)")
    assert labels == ["B_r (nT)", "B_θ (nT)", "B_φ (nT)"]


def test_lru_neutral_and_cancel(servers, watched_page):
    """Assembly leaves dataset's texture LRU untouched, and a rapid re-pin
    cancels the stale run — the shown key is the latest pin's."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    before = page.evaluate("window.geomagModelExplorer.cacheSize()")
    _pin(page)
    _wait_charts(page)
    assert page.evaluate("window.geomagModelExplorer.cacheSize()") == before

    _pin(page, lat="10")                  # immediately supersede
    _pin(page, lat="20")
    page.wait_for_function(
        "() => window.__timeseries.key()"
        " && window.__timeseries.key().includes('|20.000,')",
        timeout=TIMEOUT_MS)
    assert page.evaluate("window.geomagModelExplorer.cacheSize()") == before


def test_permalink_roundtrip(servers, watched_page):
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-combined")
    page.check("#ts-conv-rtp")
    _pin(page)
    _wait_charts(page)
    page.wait_for_function(
        "() => window.location.hash.includes('view=combined')"
        " && window.location.hash.includes('pt=52.07,12.68')"
        " && window.location.hash.includes('ptc=rtp')",
        timeout=TIMEOUT_MS)

    link = page.evaluate("window.location.href")
    page.goto("about:blank")
    page.goto(link)
    _wait_ready(page)
    st = page.evaluate("window.geomagModelExplorer.state")
    assert st["view"] == "combined"
    assert st["tsConvention"] == "rtp"
    assert abs(st["point"]["lat"] - 52.07) < 1e-9
    _wait_charts(page)                     # restored pin assembles by itself
    assert page.evaluate(
        "window.geomagModelExplorer.globe.earth.getObjectByName('ts-marker')"
        ".visible")


def test_secular_series_timeline(servers, watched_page):
    """A series timeline drives the charts: 37 quarterly epochs, nT/yr units."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on + "/" + SECULAR_LINK)
    _wait_ready(page)
    _wait_charts(page)
    res = page.evaluate("window.__timeseries.last()")
    assert len(res["xs"]) == 37
    assert res["units"] == "nT/yr"
    # quarterly spacing on the x axis (89–92 days)
    spans = [b - a for a, b in zip(res["xs"], res["xs"][1:])]
    assert all(89 * 86400 <= s <= 92 * 86400 for s in spans)
    label = page.evaluate("window.__timeseries.plots()[0].series[1].label")
    assert "nT/yr" in label
    # SV display: the y-axis label reads as a rate (v2.13 addendum)
    axis = page.evaluate("window.__timeseries.plots()[0].axes[1].label")
    assert "dB/dt" in axis and "nT/yr" in axis


def test_xaxis_adaptive_labels(servers, watched_page):
    """v2.13 addendum: the year is always on the axis — plain year labels
    on multi-year spans, month names carrying the year at January/first
    tick around a year, first-tick ISO date + HH:MM inside a day. Only the
    bottom panel renders labels, so assert plots()[2]._values."""
    on, _ = servers
    page, _errors = watched_page
    # multi-year secular series → pure year labels
    page.goto(on + "/" + SECULAR_LINK)
    _wait_ready(page)
    _wait_charts(page)
    vals = [v for v in page.evaluate(
        "window.__timeseries.plots()[2].axes[0]._values") if v]
    assert vals and all(re.fullmatch(r"\d{4}", v) for v in vals)
    # x-zoom to ~a year (4 quarterly epochs): month names + the year at
    # the first visible tick (propagates via syncXScale)
    page.evaluate("""() => {
      const u = window.__timeseries.plots()[2];
      const xs = window.__timeseries.last().xs;
      u.setScale('x', { min: xs[0], max: xs[4] });
    }""")
    vals = [v for v in page.evaluate(
        "window.__timeseries.plots()[2].axes[0]._values") if v]
    assert any(re.fullmatch(r"[A-Z][a-z]{2}", v) for v in vals)
    assert any(re.fullmatch(r"[A-Z][a-z]{2} \d{4}", v) for v in vals)
    # ~3-year zoom: quarter-spaced ticks (Sep Dec Mar Jun) never land on
    # January — the year must still be carried on every rollover
    page.evaluate("""() => {
      const u = window.__timeseries.plots()[2];
      const xs = window.__timeseries.last().xs;
      u.setScale('x', { min: xs[0], max: xs[12] });
    }""")
    vals = [v for v in page.evaluate(
        "window.__timeseries.plots()[2].axes[0]._values") if v]
    if all(re.fullmatch(r"\d{4}", v) for v in vals if v):
        pass   # wide enough that uPlot chose year increments — fine
    else:
        years = {m.group(1) for v in vals if v
                 for m in [re.search(r"(\d{4})$", v)] if m}
        assert len(years) >= 2, vals   # rollover years are marked
    # a plain day (97 × 15 min): first tick carries the ISO date, rest HH:MM
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    _pin(page)
    _wait_charts(page)
    vals = [v for v in page.evaluate(
        "window.__timeseries.plots()[2].axes[0]._values") if v]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", vals[0])
    assert all(re.fullmatch(r"\d{2}:\d{2}", v) for v in vals[1:])


def test_panel_alignment_shared_grid(servers, watched_page):
    """Post-addendum fix: all three panels share one plot box and one set
    of x splits. uPlot auto-pads only sides that carry an axis, so the
    lone labeled bottom panel used to sit ~25 px narrower — data and
    gridlines shifted against the panels above. The axis (with its
    vertical gridlines) now draws on every panel; labels bottom-only."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on + "/" + SECULAR_LINK)
    _wait_ready(page)
    _wait_charts(page)
    boxes = page.evaluate(
        "window.__timeseries.plots().map(u => [u.bbox.left, u.bbox.width])")
    assert boxes[0] == boxes[1] == boxes[2], boxes
    splits = page.evaluate(
        "window.__timeseries.plots().map(u => u.axes[0]._splits)")
    assert splits[0] and splits[0] == splits[1] == splits[2]
    labels = page.evaluate(
        "window.__timeseries.plots()"
        ".map(u => (u.axes[0]._values || []).filter(v => v).length)")
    assert labels[2] > 0 and labels[0] == labels[1] == 0, labels


def test_drag_zoom_disabled(servers, watched_page):
    """Post-addendum fix: drag-selecting a span must not zoom — the x
    range stays the full timeline. Programmatic setScale remains as the
    adaptive-label tests' span seam."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on + "/" + SECULAR_LINK)
    _wait_ready(page)
    _wait_charts(page)
    xs = page.evaluate("window.__timeseries.last().xs")
    box = page.evaluate("""() => {
      const r = window.__timeseries.plots()[2]
        .over.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    }""")
    page.mouse.move(box["x"] + box["w"] * 0.25, box["y"] + box["h"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["w"] * 0.75, box["y"] + box["h"] / 2,
                    steps=8)
    page.mouse.up()
    scale = page.evaluate(
        "[window.__timeseries.plots()[2].scales.x.min,"
        " window.__timeseries.plots()[2].scales.x.max]")
    assert scale == [xs[0], xs[-1]], scale


def test_readouts(servers, watched_page):
    """v2.13 addendum: one bottom-centre time readout — the crosshair
    instant while hovering (muted), the transport instant otherwise (gold)
    — plus a per-chart crosshair value corner (the legend's old job)."""
    on, _ = servers
    page, _errors = watched_page
    page.goto(on)
    _wait_ready(page)
    page.check("#view-series")
    _pin(page)
    _wait_charts(page)
    ro = page.locator("#ts-time-readout")
    assert ro.count() == 1
    t0 = ro.text_content()
    assert t0 == "2020-01-01 08:00 UT"     # boot pos 32 = 08:00 (v2.12 tune)
    # hover the middle of the top chart: the readout flips to the hovered
    # epoch and every panel's value corner fills in
    box = page.evaluate("""() => {
      const r = window.__timeseries.plots()[0].over.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }""")
    page.mouse.move(box["x"], box["y"])
    page.wait_for_function(
        "() => document.getElementById('ts-time-readout')"
        ".classList.contains('hover')", timeout=TIMEOUT_MS)
    hov = ro.text_content()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UT", hov)
    assert hov != t0                       # mid-day ≈ 12:00, not the boot pos
    vals = page.locator(".ts-value").all_text_contents()
    assert len(vals) == 3 and all(v.endswith(" nT") for v in vals)
    # leave the charts: fall back to the transport instant
    page.mouse.move(5, 5)
    page.wait_for_function(
        "() => !document.getElementById('ts-time-readout')"
        ".classList.contains('hover')", timeout=TIMEOUT_MS)
    assert ro.text_content() == t0
    # seek: the fallback tracks the transport (same throttle as the cursor)
    page.locator("#time-slider").fill("0")
    page.wait_for_function(
        "() => document.getElementById('ts-time-readout')"
        ".textContent === '2020-01-01 00:00 UT'", timeout=TIMEOUT_MS)


def test_flag_off(servers, watched_page):
    """No toggle, no panel, and v2.13 permalink keys degrade silently."""
    _, off = servers
    page, _errors = watched_page
    page.goto(off + "/#view=series&pt=52.07,12.68&ptc=rtp")
    _wait_ready(page)
    assert page.locator("#view-toggle").count() == 0
    assert page.locator("#series-panel").count() == 0
    assert page.evaluate("window.geomagModelExplorer.state.view") is None
    assert page.evaluate("window.geomagModelExplorer.state.point") is None
