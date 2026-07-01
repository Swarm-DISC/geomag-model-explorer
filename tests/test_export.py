"""Export pipeline tests — quantization round-trip, tile sizes, manifest
atomic-publish semantics. No network; synthetic npz data."""
import json
import shutil

import numpy as np
import pytest

import export
import fetch
from export import quantize


def test_quantize_round_trip():
    rng = np.random.default_rng(42)
    for qrange in (1500.0, 65000.0, 200.0):
        arr = rng.uniform(-qrange, qrange, size=(181, 361, 3))
        q = quantize(arr, qrange)
        assert q.dtype == np.dtype("<i2")
        back = q.astype(np.float64) / 32767.0 * qrange
        max_err = np.abs(back - arr).max()
        assert max_err <= qrange / 32767.0, (qrange, max_err)


def test_quantize_clips_with_warning(capsys):
    arr = np.array([2.0 * 1500.0, -2.0 * 1500.0, 0.0])
    q = quantize(arr, 1500.0)
    assert q.tolist() == [32767, -32767, 0]
    assert "WARNING: clipping" in capsys.readouterr().err


def test_tile_byte_sizes():
    for f in fetch.FIELDS.values():
        n_bytes = f.nlat * f.nlon * 3 * 2
        expected = {("core", 392046), ("crust", 392046),
                    ("iono", 98826), ("magneto", 98826),
                    ("core-sv", 392046)}
        assert (f.name, n_bytes) in expected


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect fetch/export trees into a tmp dir."""
    raw = tmp_path / "raw"
    web_data = tmp_path / "web_data"
    monkeypatch.setattr(fetch, "RAW", raw)
    monkeypatch.setattr(export, "WEB_DATA", web_data)
    monkeypatch.setattr(export, "MANIFEST_JSON", web_data / "manifest.json")
    monkeypatch.setattr(fetch, "VALIDITY_PATH", tmp_path / "validity.json")
    monkeypatch.setattr(export, "VALIDITY_PATH", tmp_path / "validity.json")
    yield tmp_path
    # pytest keeps tmp dirs for the whole session; a v2.7-ladder synthetic
    # day is hundreds of MB and /tmp is a small tmpfs — clean eagerly
    shutil.rmtree(raw, ignore_errors=True)
    shutil.rmtree(web_data, ignore_errors=True)


def synth_arrays(f, rng) -> dict:
    """One snapshot's npz payload — float32, the dtype never matters to
    export and float64 would double the tmpfs footprint."""
    arrays = {"lons": np.linspace(-180, 180, f.nlon),
              "lats": np.linspace(-90, 90, f.nlat)}
    for slug in f.shells:
        arrays[f"B_{slug}"] = rng.uniform(
            -f.vmax, f.vmax, size=(f.nlat, f.nlon, 3)).astype(np.float32)
    return arrays


def synth_day(day: str, rng):
    """Write a complete synthetic raw day (+ static crust). day_fields()
    like the real fetch — core-sv raw never appears under a day."""
    for f in (*fetch.day_fields(), fetch.FIELDS["crust"]):
        d = "static" if f.cadence == "static" else day
        for step in range(f.n_steps):
            path = fetch.raw_npz_path(d, f.name, step)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as fh:
                np.savez(fh, **synth_arrays(f, rng))


def test_export_day_end_to_end(sandbox):
    rng = np.random.default_rng(7)
    day = "2021-03-17"
    synth_day(day, rng)
    export.export_static()
    export.export_day(day)

    manifest = json.loads(export.MANIFEST_JSON.read_text())
    assert manifest["static_done"] is True
    assert day in manifest["days"]
    stats = manifest["days"][day]["stats"]
    assert set(stats) == {"core", "iono", "magneto"}
    for fname, per_shell in stats.items():
        assert set(per_shell) == set(fetch.FIELDS[fname].shells)
        for s in per_shell.values():
            assert s["min"] <= 0 <= s["max"]
            assert 0 < s["p99"] <= max(abs(s["min"]), abs(s["max"]))
    assert set(manifest["fields"]["crust"]["stats"]) == \
        set(fetch.FIELDS["crust"].shells)

    # a day carries day_fields() + static crust — core-sv is series-only
    for f in (*fetch.day_fields(), fetch.FIELDS["crust"]):
        d = "static" if f.cadence == "static" else day
        for shell in f.shells:
            for step in range(f.n_steps):
                tile = export.tile_path(f.name, shell, d, step)
                assert tile.exists()
                assert tile.stat().st_size == f.nlat * f.nlon * 3 * 2
    assert not (export.WEB_DATA / "core-sv").exists()


def test_incomplete_day_never_published(sandbox):
    rng = np.random.default_rng(8)
    day = "2021-03-18"
    synth_day(day, rng)
    # Remove one raw snapshot -> export_day must refuse before writing tiles.
    fetch.raw_npz_path(day, "iono", 42).unlink()
    with pytest.raises(SystemExit, match="incomplete"):
        export.export_day(day)
    assert not export.MANIFEST_JSON.exists()


def test_manifest_drops_days_with_missing_tiles(sandbox):
    rng = np.random.default_rng(9)
    day = "2021-03-19"
    synth_day(day, rng)
    export.export_day(day)
    assert day in json.loads(export.MANIFEST_JSON.read_text())["days"]
    # Damage the published tile set, rewrite the manifest: day must drop out.
    export.tile_path("magneto", "h1500", day, 50).unlink()
    export.write_manifest()
    assert day not in json.loads(export.MANIFEST_JSON.read_text())["days"]


def synth_series(series_id: str, rng):
    """Write a complete synthetic raw series (single-step fields once)."""
    s = fetch.SERIES[series_id]
    epochs = s.epochs()
    for name in s.fields:
        f = fetch.series_field(s, name)
        for step, _when in s.field_steps(name, epochs):
            path = fetch.series_npz_path(series_id, name, step)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as fh:
                np.savez(fh, **synth_arrays(f, rng))


def test_export_series_end_to_end(sandbox):
    rng = np.random.default_rng(11)
    sid = "mio-seasonal-2020"
    synth_series(sid, rng)
    export.export_series(sid)

    manifest = json.loads(export.MANIFEST_JSON.read_text())
    assert manifest["version"] == 3
    rec = manifest["series"][sid]
    assert rec["kind"] == "annual"
    assert rec["family"] == "ci"
    assert rec["single_step"] == []
    assert rec["fields"] == ["iono"]
    assert len(rec["epochs"]) == 53
    assert rec["epochs"][0] == "2020-01-01T12:00:00"
    assert rec["fixed_time"] == "12:00"
    assert rec["shells"]["iono"] == list(fetch.LADDER)  # full v2.7 ladder
    for st in rec["stats"]["iono"].values():
        assert st["min"] <= 0 <= st["max"]
        assert st["p99"] > 0

    tile = export.series_tile_path("iono", "surface", sid, 52)
    assert tile.name == "t052.i16"
    assert tile.exists()
    assert tile.stat().st_size == 91 * 181 * 3 * 2


def test_export_series_incomplete_refuses(sandbox):
    rng = np.random.default_rng(12)
    sid = "mio-seasonal-2020"
    synth_series(sid, rng)
    fetch.series_npz_path(sid, "iono", 20).unlink()
    with pytest.raises(SystemExit, match="incomplete"):
        export.export_series(sid)
    assert not export.MANIFEST_JSON.exists()


def test_manifest_drops_series_with_missing_tiles(sandbox):
    rng = np.random.default_rng(13)
    sid = "mio-seasonal-2020"
    synth_series(sid, rng)
    export.export_series(sid)
    assert sid in json.loads(export.MANIFEST_JSON.read_text())["series"]
    export.series_tile_path("iono", "h800", sid, 30).unlink()
    export.write_manifest()
    assert sid not in json.loads(export.MANIFEST_JSON.read_text())["series"]


def test_series_survive_day_exports(sandbox):
    """Day exports read-modify-write the manifest: series entries persist."""
    rng = np.random.default_rng(14)
    sid = "mio-seasonal-2020"
    synth_series(sid, rng)
    export.export_series(sid)
    day = "2021-03-20"
    synth_day(day, rng)
    export.export_static()
    export.export_day(day)
    manifest = json.loads(export.MANIFEST_JSON.read_text())
    assert sid in manifest["series"]
    assert day in manifest["days"]


def test_manifest_validity_passthrough(sandbox):
    export.VALIDITY_PATH.write_text(json.dumps(
        {"start": "2013-11-25T03:00:00Z", "end": "2023-11-30T21:00:00Z"}))
    export.write_manifest()
    manifest = json.loads(export.MANIFEST_JSON.read_text())
    assert manifest["validity"]["start"].startswith("2013-11-25")


# --- v2.9: units key, family + single-step series ---

def test_field_records_carry_units(sandbox):
    export.write_manifest()
    fields = json.loads(export.MANIFEST_JSON.read_text())["fields"]
    assert fields["core-sv"]["units"] == "nT/yr"
    assert all(fields[n]["units"] == "nT"
               for n in ("core", "crust", "iono", "magneto"))
    # key names keep _nT even for nT/yr values — "units" is the truth
    assert fields["core-sv"]["qrange_nT"] == 100_000.0


def test_export_single_step_series_end_to_end(sandbox):
    rng = np.random.default_rng(13)
    sid = "daily-2020-01-01@chaos"
    synth_series(sid, rng)
    export.export_series(sid)
    rec = json.loads(export.MANIFEST_JSON.read_text())["series"][sid]
    assert rec["kind"] == "diurnal"
    assert rec["family"] == "chaos"
    assert rec["single_step"] == ["core", "crust"]
    # tiles carry the series' storage range, not the field default
    assert rec["qrange_nT"]["core"] == 10_000_000.0
    assert rec["qrange_nT"]["magneto"] == fetch.FIELDS["magneto"].qrange
    assert len(rec["epochs"]) == 97
    assert rec["epochs"][0] == "2020-01-01T00:00:00"
    assert rec["epochs"][-1] == "2020-01-02T00:00:00"
    # single-step fields tile once; stepped fields once per epoch
    assert export.series_tile_path("core", "surface", sid, 0).exists()
    assert not export.series_tile_path("core", "surface", sid, 1).exists()
    assert export.series_tile_path("magneto", "surface", sid, 96).exists()
    for name in rec["fields"]:
        assert set(rec["stats"][name]) == set(rec["shells"][name])
    # completeness honors single_step: losing the one core tile unpublishes
    export.series_tile_path("core", "h1500", sid, 0).unlink()
    export.write_manifest()
    assert sid not in json.loads(export.MANIFEST_JSON.read_text())["series"]
