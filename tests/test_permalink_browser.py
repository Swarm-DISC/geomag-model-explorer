"""Permalink feature (PLAN v2.1) against a sandboxed server (:8232) with the
flag on: a hash restores state + camera before the UI builds, interactions
write the hash back, garbage degrades to defaults, and flag-off (:8233, same
data) is byte-for-byte v1 behavior."""
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
PORT_ON = 8232
PORT_OFF = 8233
SEED_DAY = "2020-01-01"
TIMEOUT_MS = 120_000

DEMO_HASH = f"#day={SEED_DAY}&t=06:00&f=core&c=N&s=cmb&cam=0.000,0.000,2.500"


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
    """One seeded data sandbox; two servers over it: flag on / flag off."""
    tmp = tmp_path_factory.mktemp("permalink")
    env = dict(os.environ, GEOMAG_MODEL_EXPLORER_DATA=str(tmp))
    (tmp / "data").mkdir()
    (tmp / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    (tmp / "features_on.json").write_text('{"permalink": true}')
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


def test_hash_restores_state_and_camera(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SEED_DAY
    assert state["pos"] == 24            # 06:00 = epoch 24 of the day timeline
    assert state["component"] == "N"
    assert state["shell"] == "cmb"
    # exact for the v1 fields; later manifests may add more (all off here)
    assert state["enabled"] == {"core": True, "crust": False,
                                "iono": False, "magneto": False,
                                **{f: False for f in state["enabled"]
                                   if f not in ("core", "crust",
                                                "iono", "magneto")}}
    # the UI was built from the restored state, not the defaults
    assert page.is_checked("#toggle-core")
    assert not page.is_checked("#toggle-crust")
    assert page.is_checked("#comp-N")
    assert page.text_content("#time-label") == "06:00"
    assert page.text_content("#shell-label").startswith("CMB")
    cam = page.evaluate("() => window.geomagModelExplorer.globe.camera.position.toArray()")
    assert cam == pytest.approx([0.0, 0.0, 2.5], abs=1e-6)
    assert page.evaluate("() => window.geomagModelExplorer.features") == \
        {"permalink": True}


def test_interaction_updates_hash(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/", timeout=TIMEOUT_MS)
    _wait_ready(page)
    # the booted default state gets written to the hash (debounced):
    # all four fields on since v2.12, sun/relief/frame absent (= defaults)
    page.wait_for_function(
        "() => location.hash.includes('f=core,crust,iono,magneto')",
        timeout=TIMEOUT_MS)
    hash_ = page.evaluate("() => location.hash")
    assert f"day={SEED_DAY}" in hash_
    assert "sun=" not in hash_ and "r=" not in hash_ and "frame=" not in hash_
    page.uncheck("#toggle-iono")
    page.check("#comp-F")
    page.wait_for_function(
        "() => location.hash.includes('f=core,crust,magneto') && "
        "location.hash.includes('c=F')", timeout=TIMEOUT_MS)


def test_vmax_lock_roundtrip(servers, watched_page):
    """A locked colorbar range restores from the hash, stays in the
    write-back while locked, and leaves the hash once unlocked."""
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/" + DEMO_HASH + "&vmax=12345", timeout=TIMEOUT_MS)
    _wait_ready(page)
    assert page.evaluate("() => window.geomagModelExplorer.state.vmaxLock") == 12345
    assert page.get_attribute("#colorbar-lock", "aria-pressed") == "true"
    # the restored lock drives the colorbar labels (3 significant digits)
    assert page.text_content("#colorbar-max") == "+12,300 nT"
    page.wait_for_function(
        "() => location.hash.includes('vmax=12345.0')", timeout=TIMEOUT_MS)
    page.click("#colorbar-lock")
    assert page.evaluate("() => window.geomagModelExplorer.state.vmaxLock") is None
    page.wait_for_function(
        "() => !location.hash.includes('vmax')", timeout=TIMEOUT_MS)


def test_garbage_hash_degrades_to_defaults(servers, watched_page):
    on, _off = servers
    page, _errors = watched_page
    page.goto(on + "/#day=banana&t=99:99&f=bogus&c=X&s=nope&cam=a,b"
              "&vmax=banana&zz=1",
              timeout=TIMEOUT_MS)
    _wait_ready(page)
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["day"] == SEED_DAY          # manifest default
    assert state["pos"] == 32                # boot default (08:00 UT, v2.12)
    assert state["component"] == "Up"
    assert state["shell"] == "h500"
    assert state["enabled"]["crust"] is True
    assert state["vmaxLock"] is None
    assert page.get_attribute("#colorbar-lock", "aria-pressed") == "false"


def test_flag_off_is_v1_behavior(servers, watched_page):
    _on, off = servers
    page, _errors = watched_page
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(off + "/" + DEMO_HASH, timeout=TIMEOUT_MS)
    _wait_ready(page)
    # hash ignored, module never fetched, hash never written back
    state = page.evaluate("() => window.geomagModelExplorer.state")
    assert state["component"] == "Up" and state["shell"] == "h500"
    assert page.evaluate("() => window.geomagModelExplorer.features") == {}
    assert not [u for u in requests if "features/permalink" in u]
    page.uncheck("#toggle-iono")             # on by default since v2.12
    page.wait_for_timeout(800)               # > debounce, were it running
    assert page.evaluate("() => location.hash") == DEMO_HASH
