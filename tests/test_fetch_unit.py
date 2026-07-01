"""Unit tests for fetch.py helpers — no network, no viresclient import
(fetch.py imports viresclient lazily inside the functions that need it)."""
import datetime as dt
import re

import numpy as np
import pytest

import fetch
from fetch import (FAMILIES, FIELDS, LADDER, N_STEPS, R_SURFACE_M, SERIES,
                   STEP_MINUTES, SeriesSpec, chunk_slices, day_fields,
                   day_times, make_grid, model_name, series_field,
                   series_npz_path, sv_window)


def test_make_grid_shape_and_endpoints():
    lons, lats, LON, LAT = make_grid(361, 181)
    assert lons.shape == (361,) and lats.shape == (181,)
    assert LON.shape == LAT.shape == (181, 361)
    assert lons[0] == -180.0 and lons[-1] == 180.0    # duplicated seam column
    assert lats[0] == -90.0 and lats[-1] == 90.0      # row 0 = lat -90
    assert LAT[0, 0] == -90.0 and LAT[-1, 0] == 90.0
    assert np.allclose(np.diff(lons), 1.0)


def test_make_grid_2deg():
    lons, lats, *_ = make_grid(181, 91)
    assert np.allclose(np.diff(lons), 2.0)
    assert np.allclose(np.diff(lats), 2.0)


def test_chunk_slices_partition():
    n, size = 392_046, 200_000
    slices = list(chunk_slices(n, size))
    assert slices[0] == slice(0, 200_000)
    assert slices[-1].stop == n
    covered = sum(s.stop - s.start for s in slices)
    assert covered == n
    assert all(s.stop - s.start <= size for s in slices)


def test_chunk_slices_exact_fit():
    assert list(chunk_slices(10, 5)) == [slice(0, 5), slice(5, 10)]


def test_day_times_span():
    times = day_times(dt.date(2020, 1, 1))
    assert len(times) == N_STEPS == 97
    assert times[0] == dt.datetime(2020, 1, 1, 0, 0)
    assert times[1] - times[0] == dt.timedelta(minutes=STEP_MINUTES)
    assert times[-1] == dt.datetime(2020, 1, 2, 0, 0)   # next-day 00:00


def test_field_specs_consistent():
    for f in FIELDS.values():
        assert f.qrange >= f.vmax, f.name      # storage range covers display
        assert f.alias in f.model
        assert f.n_steps in (1, N_STEPS)
        radii = list(f.shells.values())
        assert radii == sorted(radii), f"{f.name}: shells not ascending"


def test_unified_shell_ladder():
    # PLAN v2.7: every model shares the 0..1500 km / 100 km ladder; core
    # alone extends below the surface (CMB + 500 km mantle steps).
    assert list(LADDER) == \
        ["surface"] + [f"h{a}" for a in range(100, 1501, 100)]
    assert LADDER["surface"] == R_SURFACE_M
    for a in range(100, 1501, 100):
        assert LADDER[f"h{a}"] == R_SURFACE_M + a * 1000.0
    for name in ("crust", "iono", "magneto"):
        assert FIELDS[name].shells == LADDER
    assert list(FIELDS["core"].shells) == \
        ["cmb", "d2500", "d2000", "d1500", "d1000", "d500", *LADDER]
    assert {s: r for s, r in FIELDS["core"].shells.items()
            if s in LADDER} == LADDER


def test_iono_never_at_sheet_current():
    # MIO is singular at the ~110 km sheet — must never be evaluated there
    # (the v2.7 ladder's 100 km steps dodge it by construction).
    assert "h110" not in FIELDS["iono"].shells


def test_series_ids_are_path_safe():
    # ids share the tile path slot with days: slug-shaped, never a date,
    # never "static" (IDEAS §9.1).
    for sid, s in SERIES.items():
        assert s.id == sid
        assert re.fullmatch(r"[a-z0-9@-]+", sid), sid
        assert not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sid), sid
        assert sid != "static"
        assert s.fields and all(name in FIELDS for name in s.fields)
        for name, subset in (s.shells or {}).items():
            assert set(subset) <= set(FIELDS[name].shells), (sid, name)


def test_mio_seasonal_2020_epochs():
    s = SERIES["mio-seasonal-2020"]
    epochs = s.epochs()
    assert len(epochs) == 53                       # weekly through a leap year
    assert epochs[0] == dt.datetime(2020, 1, 1, 12)
    assert epochs[-1] == dt.datetime(2020, 12, 30, 12)
    assert all(e.hour == 12 and e.minute == 0 for e in epochs)
    assert {b - a for a, b in zip(epochs, epochs[1:])} == \
        {dt.timedelta(days=7)}


def test_series_field_shell_subset():
    s = SeriesSpec(id="sv-test@igrf", kind="secular", label="test",
                   fields=("core",),
                   start=dt.date(2000, 1, 1), end=dt.date(2001, 1, 1),
                   step_days=366, fixed_time=dt.time(0),
                   shells={"core": ("cmb", "surface")})
    f = series_field(s, "core")
    assert list(f.shells) == ["cmb", "surface"]
    assert f.shells["cmb"] == FIELDS["core"].shells["cmb"]
    # without a subset the catalog field itself is used
    assert series_field(SERIES["mio-seasonal-2020"], "iono") is FIELDS["iono"]


def test_series_npz_path_is_three_digit():
    p = series_npz_path("mio-seasonal-2020", "iono", 7)
    assert p.name == "t007.npz"
    assert p.parts[-4:-2] == ("series", "mio-seasonal-2020")


# --- v2.9: model families + derived core SV ---

def test_day_fields_excludes_static_and_sv():
    names = [f.name for f in day_fields()]
    assert names == ["core", "iono", "magneto"]   # never crust, never core-sv


def test_families_shape():
    assert set(FAMILIES) == {"ci", "chaos"}
    # ci is derived from FIELDS — no drift possible, but pin the contract
    assert FAMILIES["ci"] == {name: f.model for name, f in FIELDS.items()}
    for family, layers in FAMILIES.items():
        assert set(layers) <= set(FIELDS), family
        for name, spec in layers.items():
            # alias stability: eval_stacked keys results by B_NEC_<alias>
            assert spec.split("=")[0].strip() == FIELDS[name].alias, \
                (family, name)
    # human decision 2026-06-12: CHAOS ships without an ionospheric layer
    assert "iono" not in FAMILIES["chaos"]
    assert "'CHAOS-Core'" in FAMILIES["chaos"]["core"]
    assert "'CHAOS-MMA'" in FAMILIES["chaos"]["magneto"]


def test_core_sv_spec():
    f = FIELDS["core-sv"]
    assert f.sv and f.units == "nT/yr"
    assert f.shells == FIELDS["core"].shells      # same 22-shell ladder
    assert (f.nlon, f.nlat) == (FIELDS["core"].nlon, FIELDS["core"].nlat)
    # probe record (PLAN v2.9): CMB |Bdot| max ~71.5k, surface p99 ~196
    assert f.qrange == 100_000.0 and f.vmax == 200.0
    # nT fields carry the default unit and are never derived
    for name in ("core", "crust", "iono", "magneto"):
        assert FIELDS[name].units == "nT" and not FIELDS[name].sv


def test_model_name():
    assert model_name("Core = 'MCO_SHA_2C'") == "MCO_SHA_2C"
    assert model_name("Magnetosphere = 'CHAOS-MMA'") == "CHAOS-MMA"
    assert model_name("Core = IGRF") == "IGRF"    # served unquoted


def test_sv_window_interior_and_clamped():
    vstart = dt.datetime(2013, 11, 25)
    vend = dt.datetime(2023, 11, 30)
    # interior: symmetric ±182.625 d, span exactly one Julian year
    t0, t1, span = sv_window(dt.datetime(2018, 6, 1, 12), vstart, vend)
    assert span == pytest.approx(1.0)
    assert t1 - t0 == dt.timedelta(days=2 * 182.625)
    assert (dt.datetime(2018, 6, 1, 12) - t0) == (t1 - dt.datetime(2018, 6, 1, 12))
    # upper edge: clamps to vend, one-sided remainder, still ~a year
    t0, t1, span = sv_window(dt.datetime(2023, 6, 1, 12), vstart, vend)
    assert t1 == vend
    assert 0.9 < span < 1.0
    # window collapsing below half a year refuses loudly
    with pytest.raises(SystemExit):
        sv_window(dt.datetime(2023, 11, 29), dt.datetime(2023, 9, 1), vend)


def test_sv_snapshot_is_exact_slope(tmp_path, monkeypatch):
    """_save_snapshot for an sv field stores the centered-difference slope:
    with a synthetic field linear in time it is exact regardless of clamping."""
    f = FIELDS["core-sv"]
    epoch = dt.datetime(2018, 1, 1)
    slope = np.zeros((len(f.shells), f.nlat, f.nlon, 3))
    slope += np.array([10.0, -20.0, 40.0])        # nT/yr per NEC component

    def fake_eval(field, when):
        yrs = (when - epoch) / dt.timedelta(days=365.25)
        return slope * yrs
    monkeypatch.setattr(fetch, "eval_stacked", fake_eval)
    monkeypatch.setattr(fetch, "model_validity",
                        lambda spec: (dt.datetime(2013, 11, 25),
                                      dt.datetime(2023, 11, 30)))
    out = tmp_path / "t000.npz"
    fetch._save_snapshot(f, out, dt.datetime(2018, 6, 1, 12), force=False)
    with np.load(out) as npz:
        for slug in f.shells:
            assert np.allclose(npz[f"B_{slug}"],
                               np.array([10.0, -20.0, 40.0])), slug


def test_core_secular_epochs_no_leap_drift():
    for sid in ("core-secular", "core-secular@chaos"):
        epochs = SERIES[sid].epochs()
        assert len(epochs) == 10
        assert epochs == [dt.datetime(y, 6, 1, 12) for y in range(2014, 2024)]


def test_chaos_daily_epochs_match_day_times():
    s = SERIES["daily-2020-01-01@chaos"]
    assert s.epochs() == day_times(dt.date(2020, 1, 1))


def test_field_steps_single_step():
    s = SERIES["daily-2020-01-01@chaos"]
    epochs = s.epochs()
    # single-step fields: one job at the middle epoch (12:00, like the CI
    # day cache's noon core snapshot)
    assert s.field_steps("core", epochs) == \
        [(0, dt.datetime(2020, 1, 1, 12))]
    assert s.field_steps("crust", epochs) == \
        [(0, dt.datetime(2020, 1, 1, 12))]
    assert s.field_steps("magneto", epochs) == list(enumerate(epochs))


def test_series_field_family_resolution():
    f = series_field(SERIES["core-secular@chaos"], "core")
    assert f.model == "Core = 'CHAOS-Core'"
    assert f.alias == "Core"                       # B_NEC key unchanged
    assert f.shells == FIELDS["core"].shells
    # CHAOS-Core reaches degree 20: CMB |B| peaks ~8.4M nT, so the chaos
    # series store core at a wider range than the CI-sized field default
    assert f.qrange == 10_000_000.0
    assert series_field(SERIES["daily-2020-01-01@chaos"], "core").qrange \
        == 10_000_000.0
    assert series_field(SERIES["core-secular@chaos"], "core-sv").qrange \
        == FIELDS["core-sv"].qrange                # SV fits the default
    sv = series_field(SERIES["core-secular@chaos"], "core-sv")
    assert sv.model == "Core = 'CHAOS-Core'" and sv.sv
    # ci series still pass the catalog field through untouched
    assert series_field(SERIES["core-secular"], "core") is FIELDS["core"]
    # a layer missing from the family is a catalog bug, surfaced loudly
    bogus = SeriesSpec(id="x@chaos", kind="annual", label="x",
                       fields=("iono",), family="chaos",
                       start=dt.date(2020, 1, 1), end=dt.date(2020, 1, 2),
                       step_days=1, fixed_time=dt.time(12))
    with pytest.raises(KeyError):
        series_field(bogus, "iono")


def test_series_catalog_families_consistent():
    for sid, s in SERIES.items():
        assert s.family in FAMILIES, sid
        for name in s.fields:
            assert name in FAMILIES[s.family], (sid, name)
        assert set(s.single_step) <= set(s.fields), sid
        # family-by-id convention: non-ci series carry "@<family>"
        if s.family != "ci":
            assert sid.endswith(f"@{s.family}"), sid
