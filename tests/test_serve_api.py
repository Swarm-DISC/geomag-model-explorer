"""Day-fetch API tests: starlette TestClient + stubbed fetch subprocess
(real export.py runs on the stub's synthetic npz). Hermetic via
GEOMAG_MODEL_EXPLORER_DATA -> tmp dir; serve/fetch/export read it at import time, so the
modules are (re)imported per sandbox."""
from __future__ import annotations

import importlib
import json
import shutil
import sys
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
STUB = f"{sys.executable} {REPO / 'tests' / 'stub_fetch.py'}"
EXPORT = f"{sys.executable} {REPO / 'export.py'}"


@pytest.fixture()
def served(tmp_path, monkeypatch):
    """Fresh serve module + client against an GEOMAG_MODEL_EXPLORER_DATA sandbox."""
    monkeypatch.setenv("GEOMAG_MODEL_EXPLORER_DATA", str(tmp_path))
    monkeypatch.setenv("GEOMAG_MODEL_EXPLORER_FETCH_CMD", STUB)
    monkeypatch.setenv("GEOMAG_MODEL_EXPLORER_EXPORT_CMD", EXPORT)
    monkeypatch.setenv("GEOMAG_MODEL_EXPLORER_FEATURES", str(tmp_path / "features.json"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "validity.json").write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    for mod in ("fetch", "export", "serve"):
        sys.modules.pop(mod, None)
    serve = importlib.import_module("serve")
    client = TestClient(serve.app)
    # The day-fetch POST is token-gated (REVIEW #6); carry the token by default so the
    # functional tests below exercise the post-auth behavior.
    import _auth
    secret = _auth.resolve_secret()
    if secret:
        client.headers["X-Foundry-Token"] = secret
    yield serve, client, tmp_path
    for mod in ("fetch", "export", "serve"):
        sys.modules.pop(mod, None)
    # synthetic days are ~300 MB and /tmp is a small tmpfs — clean eagerly
    # (pytest's keep-last-3 policy would fill the disk across runs)
    shutil.rmtree(tmp_path, ignore_errors=True)


def wait_for_day(client, day, timeout=120.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get("/api/days").json()
        # the day is published by the export subprocess's LAST act (the
        # atomic manifest write), so it can be listed a beat before the
        # runner clears the job record — wait until this day's job is gone,
        # not just until the day appears (a later queued day's job may
        # already be running by then)
        job = data["job"]
        if day in data["days"] and (job is None or job.get("date") != day):
            return data
        if job and job["state"] == "error":
            raise AssertionError(f"job failed: {job}")
        time.sleep(0.3)
    raise AssertionError(f"day {day} not published within {timeout}s")


def test_features_endpoint(served):
    _serve, client, tmp = served
    # no deploy config -> every feature off (v1 behavior)
    assert client.get("/api/features").json() == {}
    # flags are read per request: a config edit needs no restart
    (tmp / "features.json").write_text('{"permalink": true}')
    assert client.get("/api/features").json() == {"permalink": True}
    # a broken config degrades to all-off, never to a 500
    (tmp / "features.json").write_text("{nope")
    assert client.get("/api/features").json() == {}


def test_day_fetch_requires_token(served):
    """The day-fetch POST rejects a token-less request before any validity check (REVIEW #6)."""
    _serve, client, _tmp = served
    import _auth
    if not _auth.resolve_secret():
        pytest.skip("no foundry token configured in this environment")
    anon = TestClient(_serve.app)  # no X-Foundry-Token header
    assert anon.post("/api/days/2021-03-17").status_code == 401
    assert anon.post("/api/days/not-a-date").status_code == 401  # auth runs before date parsing
    # read-only routes stay open
    assert anon.get("/api/days").status_code == 200
    assert anon.get("/api/features").status_code == 200


def test_invalid_and_out_of_range_dates(served):
    _serve, client, _tmp = served
    assert client.post("/api/days/not-a-date").status_code == 400
    assert client.post("/api/days/2031-01-01").status_code == 400
    assert client.post("/api/days/2010-01-01").status_code == 400
    body = client.post("/api/days/2031-01-01").json()
    assert "validity" in body["error"]


def test_day_job_end_to_end(served):
    _serve, client, tmp = served
    day = "2021-03-17"
    resp = client.post(f"/api/days/{day}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"

    # dedup while queued/running
    resp2 = client.post(f"/api/days/{day}")
    assert resp2.status_code == 202
    assert resp2.json()["status"] in ("queued", "running")

    data = wait_for_day(client, day)
    assert data["job"] is None
    # published manifest lists the day with per-shell stats
    manifest = json.loads(
        (tmp / "web" / "data" / "manifest.json").read_text())
    assert day in manifest["days"]
    assert "p99" in manifest["days"][day]["stats"]["core"]["surface"]

    # now cached: POST returns 200 without re-queueing
    resp3 = client.post(f"/api/days/{day}")
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "cached"

    # tiles are served through the /data mount
    tile = client.get(f"/data/iono/surface/{day}/t00.i16")
    assert tile.status_code == 200


def test_queue_orders_and_reports(served):
    _serve, client, _tmp = served
    d1, d2 = "2021-05-01", "2021-05-02"
    client.post(f"/api/days/{d1}")
    resp = client.post(f"/api/days/{d2}")
    assert resp.status_code == 202
    data = client.get("/api/days").json()
    pending = set(data["queue"]) | (
        {data["job"]["date"]} if data["job"] else set())
    assert {d1, d2} <= pending
    wait_for_day(client, d2)
    assert d1 in client.get("/api/days").json()["days"]


def test_fetch_failure_reports_error(served, monkeypatch):
    _serve, client, tmp = served
    monkeypatch.setenv("GEOMAG_MODEL_EXPLORER_STUB_FAIL", "1")
    day = "2021-07-07"
    client.post(f"/api/days/{day}")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        data = client.get("/api/days").json()
        if data["job"] and data["job"]["state"] == "error":
            assert data["job"]["date"] == day
            assert "exit 3" in data["job"]["error"]
            break
        time.sleep(0.2)
    else:
        raise AssertionError("error state never reported")
    # the failed day was never published
    assert day not in client.get("/api/days").json()["days"]
