"""Upstream data fetch for geomag-model-explorer — the ONLY module that talks to the network.

All field values come from VirES (viresclient, `uv sync --extra fetch`) using the
Swarm Level-2 Comprehensive Inversion (CI) chain. The one non-VirES download is
the Natural Earth coastline GeoJSON (`--assets`), kept here so export.py and the
web app read only local files (RULES §3).

    uv run --extra fetch python fetch.py --static            # crust (once)
    uv run --extra fetch python fetch.py --day 2020-01-01    # core + iono + magneto
    uv run --extra fetch python fetch.py --series <id>       # curated series (§9.1)
    uv run --extra fetch python fetch.py --validity          # model validity ranges
    uv run --extra fetch python fetch.py --assets            # coastline geojson

Outputs land under data/raw/<day|static>/<field>/tNN.npz (series under
data/raw/series/<id>/<field>/tNNN.npz); every fetched snapshot set is recorded
in data/MANIFEST.toml (committed). Fetches are resumable: existing npz files
are skipped unless --force.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import tomllib
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
# Scaling-ladder rung 2 (PLAN §5): GEOMAG_MODEL_EXPLORER_DATA relocates the whole cache
# tree (data/raw + web/data) off the checkout; default stays in-checkout.
DATA_ROOT = Path(os.environ.get("GEOMAG_MODEL_EXPLORER_DATA", str(ROOT)))
DATA = DATA_ROOT / "data"
RAW = DATA / "raw"
MANIFEST_PATH = DATA / "MANIFEST.toml"
VALIDITY_PATH = DATA / "validity.json"

# --- shared constants (export.py imports these; keep them dependency-free) ---

R_SURFACE_M = 6_371_000.0
N_STEPS = 97          # t00..t96; t96 = next-day 00:00 so 23:45-24:00 interpolates
STEP_MINUTES = 15
CHUNK_MAX = 200_000   # max points per eval_model call; larger sets are split

COASTLINE_NAME = "ne_110m_coastline.geojson"
COASTLINE_URL = ("https://raw.githubusercontent.com/nvkelso/"
                 "natural-earth-vector/master/geojson/ne_110m_coastline.geojson")
COASTLINE_RAW = RAW / "assets" / COASTLINE_NAME


@dataclass(frozen=True)
class FieldSpec:
    name: str
    model: str                 # VirES model spec; alias left of '=' keys the result
                               # (the CI default — FAMILIES overrides per family)
    nlon: int                  # lon -180..+180 inclusive (duplicated seam column)
    nlat: int                  # lat -90..+90 inclusive; row 0 = lat -90
    shells: dict[str, float]   # slug -> radius_m (insertion order = display order)
    cadence: str               # "static" | "day" | "15min"
    qrange: float              # symmetric int16 storage range, nT — sized for the
                               # strongest shell (CMB for core, anomalies for crust)
    vmax: float                # default display colormap range, nT (prior art)
    units: str = "nT"          # physical units; "nT/yr" for derived SV (v2.9) —
                               # non-nT fields never sum with nT ones (IDEAS §9.6)
    sv: bool = False           # derived secular variation: evaluate the model at
                               # t ± 6 months and store the centered difference

    @property
    def alias(self) -> str:
        return self.model.split("=")[0].strip()

    @property
    def n_steps(self) -> int:
        return {"static": 1, "day": 1, "15min": N_STEPS}[self.cadence]


# Unified shell ladder (PLAN v2.7): every model shares 0..1500 km altitude at
# 100 km steps, so any field combination is summable on any shell and the
# slider is identical across fields and tabs. The 0 km slug stays "surface"
# (permalink stability).
LADDER: dict[str, float] = {
    "surface": R_SURFACE_M,
    **{f"h{a}": R_SURFACE_M + a * 1000.0 for a in range(100, 1501, 100)},
}

FIELDS: dict[str, FieldSpec] = {
    "core": FieldSpec(
        name="core", model="Core = 'MCO_SHA_2C'", nlon=361, nlat=181,
        shells={"cmb": 3_480_000.0,
                # dNNN = depth in km: mantle steps so the shell slider
                # transitions smoothly from the CMB to the surface
                "d2500": 3_871_000.0, "d2000": 4_371_000.0,
                "d1500": 4_871_000.0, "d1000": 5_371_000.0,
                "d500": 5_871_000.0,
                **LADDER},
        cadence="day", qrange=3_000_000.0, vmax=65_000.0),  # CMB |B| hits 2.5e6
    "crust": FieldSpec(
        name="crust", model="Crust = 'MLI_SHA_2C'", nlon=361, nlat=181,
        shells=dict(LADDER),
        cadence="static", qrange=1_500.0, vmax=100.0),
    "iono": FieldSpec(
        name="iono", model="Ionosphere = 'MIO_SHA_2C'", nlon=181, nlat=91,
        shells=dict(LADDER),
        cadence="15min", qrange=200.0, vmax=25.0),
    "magneto": FieldSpec(
        name="magneto", model="Magnetosphere = 'MMA_SHA_2C'", nlon=181, nlat=91,
        shells=dict(LADDER),
        cadence="15min", qrange=500.0, vmax=25.0),
    # Derived core secular variation (PLAN v2.9, IDEAS §9.6): same expansion
    # evaluated as a centered finite difference at t ± 6 months, in nT/yr.
    # Series-only — day_fields() excludes it, so cached days are untouched.
    # qrange/vmax from the 2026-06-12 probe (PLAN v2.9 probe record):
    # |Bdot| max ~71.5k nT/yr at the CMB (CHAOS-Core), surface p99 ~196.
    "core-sv": FieldSpec(
        name="core-sv", model="Core = 'MCO_SHA_2C'", nlon=361, nlat=181,
        shells={"cmb": 3_480_000.0,
                "d2500": 3_871_000.0, "d2000": 4_371_000.0,
                "d1500": 4_871_000.0, "d1000": 5_371_000.0,
                "d500": 5_871_000.0,
                **LADDER},
        cadence="day", qrange=100_000.0, vmax=200.0,
        units="nT/yr", sv=True),
}


def day_fields() -> list[FieldSpec]:
    """The fields a cached *day* carries: non-static and not derived. The
    completeness checks in export.py prune any day missing a field's tiles,
    so listing core-sv here would silently unpublish every cached day."""
    return [f for f in FIELDS.values() if f.cadence != "static" and not f.sv]


# Model families (PLAN v2.9, IDEAS §9.2): (family, field) -> VirES model
# spec. Names and validities are probe-confirmed (docs/v29_model_probe.json;
# PLAN v2.9 probe record) — never guessed. Aliases left of '=' are identical
# across families so eval_stacked's B_NEC_<alias> key never changes. The day
# pipeline never consults FAMILIES: family is a property of curated series
# ("...@chaos" by id convention), not of the day cache.
FAMILIES: dict[str, dict[str, str]] = {
    "ci": {name: f.model for name, f in FIELDS.items()},
    "chaos": {
        "core": "Core = 'CHAOS-Core'",
        "core-sv": "Core = 'CHAOS-Core'",
        "crust": "Crust = 'CHAOS-Static'",
        "magneto": "Magnetosphere = 'CHAOS-MMA'",  # served Primary+Secondary
        # no "iono": the CHAOS family ships without an ionospheric layer
        # (human decision 2026-06-12 — CHAOS-MIO exists but is skipped).
    },
}


@dataclass(frozen=True)
class SeriesSpec:
    """A materialized series (IDEAS §9.1): an ordered epoch list at a fixed
    time of day, evaluated for a fixed field set. The id doubles as the tile
    path key (filesystem-safe slug, never date-shaped, never 'static'); a
    model family other than CI belongs in the id by convention (…@igrf)."""
    id: str
    kind: str                  # "annual" | "secular" | "diurnal"
    label: str                 # one line for the UI's series picker
    fields: tuple[str, ...]    # FIELDS keys evaluated at every epoch
    start: dt.date
    end: dt.date               # inclusive bound for epoch generation
    step_days: int
    fixed_time: dt.time        # the same time of day at every epoch
    shells: dict[str, tuple[str, ...]] | None = None   # per-field subset;
                               # None/absent field = all of the field's shells
    family: str = "ci"         # FAMILIES key; resolves each field's model
    step_minutes: int = 0      # >0: sub-daily epochs (diurnal kind);
                               # overrides step_days
    step_years: int = 0        # >0: calendar-year steps (no leap drift);
                               # overrides step_days
    single_step: tuple[str, ...] = ()  # fields evaluated once, at the middle
                               # epoch, instead of at every epoch (a diurnal
                               # series would otherwise tile core x97 and
                               # static crust x97 — ~1.4 GB of duplicates)
    qrange: dict[str, float] | None = None  # per-field storage-range
                               # override for this series' tiles (CHAOS-Core
                               # reaches degree 20: its CMB |B| peaks ~8.4M
                               # nT, 2.8x the CI-sized field default)

    def epochs(self) -> list[dt.datetime]:
        out = []
        cur = dt.datetime.combine(self.start, self.fixed_time)
        last = dt.datetime.combine(self.end, self.fixed_time)
        while cur <= last:
            out.append(cur)
            if self.step_years:
                cur = cur.replace(year=cur.year + self.step_years)
            elif self.step_minutes:
                cur += dt.timedelta(minutes=self.step_minutes)
            else:
                cur += dt.timedelta(days=self.step_days)
        return out

    def field_steps(self, field_name: str, epochs: list[dt.datetime]) \
            -> list[tuple[int, dt.datetime]]:
        """(step, when) jobs for one field: every epoch, or — for single_step
        fields — one job at the middle epoch (12:00 for a 00:00-anchored
        diurnal day, matching the CI day cache's noon core snapshot)."""
        if field_name in self.single_step:
            return [(0, epochs[len(epochs) // 2])]
        return list(enumerate(epochs))


# Curated, code-reviewed catalog — series are defined here, not user-generated,
# so the on-demand write surface stays the day-fetch queue alone (IDEAS §9.1).
SERIES: dict[str, SeriesSpec] = {
    "mio-seasonal-2020": SeriesSpec(
        id="mio-seasonal-2020", kind="annual",
        label="Ionosphere through 2020 — weekly, 12:00 UT",
        fields=("iono",),
        start=dt.date(2020, 1, 1), end=dt.date(2020, 12, 31),
        step_days=7, fixed_time=dt.time(12)),
    # v2.9 Core tab: B and dB/dt on the same yearly timeline. June 1 keeps
    # every t ± 6 mo SV window inside CI validity except 2023's upper edge,
    # which sv_window clamps by about a day (span ~0.997 yr).
    "core-secular": SeriesSpec(
        id="core-secular", kind="secular",
        label="Core field & secular variation — yearly, 2014–2023 (Swarm CI)",
        fields=("core", "core-sv"),
        start=dt.date(2014, 6, 1), end=dt.date(2023, 6, 1),
        step_days=0, step_years=1, fixed_time=dt.time(12)),
    "core-secular@chaos": SeriesSpec(
        id="core-secular@chaos", kind="secular",
        label="Core field & secular variation — yearly, 2014–2023 (CHAOS)",
        fields=("core", "core-sv"), family="chaos",
        start=dt.date(2014, 6, 1), end=dt.date(2023, 6, 1),
        step_days=0, step_years=1, fixed_time=dt.time(12),
        qrange={"core": 10_000_000.0}),   # CMB |B| max 8.41M (export check)
    # v2.9 Combined-models tab under the CHAOS lens: one curated day at the
    # day cache's own cadence (97 x 15 min; t96 = next-day 00:00, mirroring
    # day_times). Core and crust are single-step like the CI day cache.
    "daily-2020-01-01@chaos": SeriesSpec(
        id="daily-2020-01-01@chaos", kind="diurnal",
        label="CHAOS on 2020-01-01 — 15-min steps",
        fields=("core", "crust", "magneto"), family="chaos",
        single_step=("core", "crust"),
        start=dt.date(2020, 1, 1), end=dt.date(2020, 1, 2),
        step_days=0, step_minutes=STEP_MINUTES, fixed_time=dt.time(0),
        qrange={"core": 10_000_000.0}),
}


def series_field(series: SeriesSpec, field_name: str) -> FieldSpec:
    """The FieldSpec a series evaluates: the catalog field with its model
    resolved through the series' family, optionally restricted to the
    series' shell subset (insertion order preserved)."""
    field = FIELDS[field_name]
    model = FAMILIES[series.family][field_name]   # KeyError = layer not in
    if model != field.model:                      # this family (e.g. chaos
        field = replace(field, model=model)       # iono) — catalog bug
    qrange = (series.qrange or {}).get(field_name)
    if qrange:
        field = replace(field, qrange=qrange)
    subset = (series.shells or {}).get(field_name)
    if not subset:
        return field
    return replace(field, shells={s: field.shells[s] for s in field.shells
                                  if s in subset})


# --- pure helpers (unit-tested without viresclient) ---

def make_grid(nlon: int, nlat: int):
    """Equirect grid: lons -180..180 (seam duplicated), lats -90..90 ascending."""
    lons = np.linspace(-180.0, 180.0, nlon)
    lats = np.linspace(-90.0, 90.0, nlat)
    LON, LAT = np.meshgrid(lons, lats)   # shape [nlat, nlon], row 0 = lat -90
    return lons, lats, LON, LAT


def chunk_slices(n: int, size: int):
    """Yield slices partitioning range(n) into chunks of at most `size`."""
    for start in range(0, n, size):
        yield slice(start, min(start + size, n))


def day_times(date: dt.date) -> list[dt.datetime]:
    """The N_STEPS snapshot times for a picked day (last = next-day 00:00)."""
    start = dt.datetime(date.year, date.month, date.day)
    return [start + dt.timedelta(minutes=STEP_MINUTES * i) for i in range(N_STEPS)]


SV_HALF_DAYS = 182.625      # half a Julian year: the ±6-month SV stencil


def sv_window(when: dt.datetime, vstart: dt.datetime, vend: dt.datetime) \
        -> tuple[dt.datetime, dt.datetime, float]:
    """The centered-difference window for Bdot(when), clamped to model
    validity (one-sided near the edges). Returns (t0, t1, span_years);
    refuses windows under half a year — the estimate stops being SV."""
    t0 = max(when - dt.timedelta(days=SV_HALF_DAYS), vstart)
    t1 = min(when + dt.timedelta(days=SV_HALF_DAYS), vend)
    span = (t1 - t0) / dt.timedelta(days=365.25)
    if span < 0.5:
        raise SystemExit(
            f"sv: window for {when.isoformat()} collapses to {span:.2f} yr "
            f"inside validity {vstart.isoformat()}..{vend.isoformat()}")
    return t0, t1, span


def model_name(model_spec: str) -> str:
    """Served model name from a spec: the quoted token, or the bare name
    right of '=' (IGRF is served unquoted)."""
    if "'" in model_spec:
        return model_spec.split("'")[1]
    return model_spec.split("=")[-1].strip()


def model_validity(model_spec: str) -> tuple[dt.datetime, dt.datetime]:
    """Validity range for one model from data/validity.json (naive UTC).
    Offline and deterministic — run `fetch.py --validity` to refresh."""
    if not VALIDITY_PATH.exists():
        raise SystemExit("sv: data/validity.json missing — run "
                         "`fetch.py --validity` first")
    per_model = json.loads(VALIDITY_PATH.read_text()).get("per_model", {})
    name = model_name(model_spec)
    if name not in per_model:
        raise SystemExit(f"sv: no validity for {name} in {VALIDITY_PATH} — "
                         "re-run `fetch.py --validity`")
    rec = per_model[name]
    return tuple(dt.datetime.fromisoformat(rec[k]).replace(tzinfo=None)
                 for k in ("start", "end"))


def raw_npz_path(day: str, field: str, step: int) -> Path:
    """day is 'YYYY-MM-DD' or 'static'."""
    return RAW / day / field / f"t{step:02d}.npz"


def series_npz_path(series_id: str, field: str, step: int) -> Path:
    """Series epochs are 3-digit (up to 1000 epochs vs a day's 97 steps)."""
    return RAW / "series" / series_id / field / f"t{step:03d}.npz"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def aggregate_sha256(paths: list[Path]) -> str:
    """sha256 over the sorted per-file digests — pins a multi-file snapshot."""
    digests = sorted(_sha256_file(p) for p in paths)
    return _sha256_bytes("\n".join(digests).encode())


# --- VirES evaluation (lazy viresclient imports) ---

def eval_stacked(field: FieldSpec, when: dt.datetime) -> np.ndarray:
    """Evaluate one field at one instant on all its shells, stacked into a
    single point set (radius is per-point), chunked. Returns
    [nshell, nlat, nlon, 3] B_NEC in nT."""
    from viresclient import SwarmRequest

    _, _, LON, LAT = make_grid(field.nlon, field.nlat)
    npts = LAT.size
    radii = np.asarray(list(field.shells.values()), dtype=np.float64)
    lat_all = np.tile(LAT.ravel(), len(radii))
    lon_all = np.tile(LON.ravel(), len(radii))
    rad_all = np.repeat(radii, npts)
    naive = when.replace(tzinfo=None) if when.tzinfo else when
    when64 = np.datetime64(naive, "ns")

    out = np.empty((len(rad_all), 3), dtype=np.float64)
    req = SwarmRequest()
    key = f"B_NEC_{field.alias}"
    for sl in chunk_slices(len(rad_all), CHUNK_MAX):
        result, _meta = req.eval_model(
            models=[field.model],
            time=np.full(sl.stop - sl.start, when64, dtype="datetime64[ns]"),
            latitude=lat_all[sl],
            longitude=lon_all[sl],
            radius=rad_all[sl],
            show_progress=False,
        )
        out[sl] = result[key]
    return out.reshape(len(radii), field.nlat, field.nlon, 3)


def snapshot_complete(path: Path, field: FieldSpec) -> bool:
    """True iff the npz exists and has every shell of the *current* spec —
    a bare existence check would leave cached days without shells added
    later (re-fetching a day self-heals: only incomplete snapshots re-run)."""
    if not path.exists():
        return False
    with np.load(path) as npz:
        return all(f"B_{slug}" in npz for slug in field.shells)


def _save_snapshot(field: FieldSpec, path: Path, when: dt.datetime,
                   force: bool) -> Path:
    """Fetch + save one field·timestep npz (all shells); skip if complete."""
    if snapshot_complete(path, field) and not force:
        return path
    if field.sv:
        # Derived SV (IDEAS §9.6): centered finite difference of the same
        # model at t ± 6 months, in nT/yr. MCO_SHA_2C's core SV basis is
        # order-4 B-splines at 6-month knots (CIY4), so this is a smoothed,
        # honest O(Δ²) estimate; CHAOS-Core (order 6) likewise.
        t0, t1, span = sv_window(when, *model_validity(field.model))
        stacked = (eval_stacked(field, t1) - eval_stacked(field, t0)) / span
    else:
        stacked = eval_stacked(field, when)
    lons, lats, _, _ = make_grid(field.nlon, field.nlat)
    arrays = {"lons": lons, "lats": lats}
    for i, slug in enumerate(field.shells):
        arrays[f"B_{slug}"] = stacked[i]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".npz.tmp")
    with tmp.open("wb") as fh:        # file handle: np.savez must not append .npz
        np.savez(fh, **arrays)
    tmp.replace(path)
    return path


def _viresclient_version() -> str:
    from viresclient import __version__
    return __version__


def _manifest_entry(field: FieldSpec, day: str, when_desc: str,
                    paths: list[Path]) -> dict:
    return {
        "model": field.model,
        "grid": f"{field.nlon}x{field.nlat}",
        "shells": list(field.shells.keys()),
        "radii_m": list(field.shells.values()),
        "n_snapshots": len(paths),
        "time": when_desc,
        "viresclient": _viresclient_version(),
        "fetched_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "sha256": aggregate_sha256(paths),
    }


def fetch_static(force: bool = False) -> None:
    """Crust (MLI_SHA_2C) on all its shells — fetched once, epoch 2020-01-01."""
    field = FIELDS["crust"]
    when = dt.datetime(2020, 1, 1)
    print(f"fetch: static/{field.name} ({field.model}, "
          f"{len(field.shells)} shells stacked)")
    path = _save_snapshot(field, raw_npz_path("static", field.name, 0),
                          when, force)
    upsert_manifest({f"static/{field.name}":
                     _manifest_entry(field, "static", when.isoformat(), [path])})
    print("fetch: static done; MANIFEST.toml updated.")


def write_progress(progress_file: Path | None, day: str, done: int, total: int,
                   message: str) -> None:
    if progress_file is None:
        return
    payload = {"date": day, "done": done, "total": total, "message": message}
    tmp = progress_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(progress_file)


def fetch_day(date: dt.date, progress_file: Path | None = None,
              force: bool = False) -> None:
    """One picked day: core 1 eval (12:00 UT), iono + magneto N_STEPS evals."""
    day = date.isoformat()
    jobs: list[tuple[FieldSpec, int, dt.datetime]] = []
    noon = dt.datetime(date.year, date.month, date.day, 12)
    jobs.append((FIELDS["core"], 0, noon))
    for field_name in ("iono", "magneto"):
        field = FIELDS[field_name]
        for step, when in enumerate(day_times(date)):
            jobs.append((field, step, when))

    total = len(jobs)
    print(f"fetch: day {day} — {total} stacked evaluations")
    write_progress(progress_file, day, 0, total, "starting")
    done_paths: dict[str, list[Path]] = {}
    for i, (field, step, when) in enumerate(jobs):
        msg = f"{field.name} t{step:02d}/{field.n_steps - 1:02d}"
        path = raw_npz_path(day, field.name, step)
        if not (snapshot_complete(path, field) and not force):
            _save_snapshot(field, path, when, force)
            print(f"  [{i + 1}/{total}] {msg}")
        done_paths.setdefault(field.name, []).append(path)
        write_progress(progress_file, day, i + 1, total, msg)

    entries = {}
    for field_name, paths in done_paths.items():
        field = FIELDS[field_name]
        desc = (noon.isoformat() if field.cadence == "day"
                else f"{day}T00:00/{STEP_MINUTES}min/{N_STEPS}")
        entries[f"{day}/{field_name}"] = _manifest_entry(field, day, desc, paths)
    upsert_manifest(entries)
    write_progress(progress_file, day, total, total, "fetch complete")
    print(f"fetch: day {day} done; MANIFEST.toml updated.")


def fetch_series(series_id: str, progress_file: Path | None = None,
                 force: bool = False) -> None:
    """One curated series: every field at every epoch, fixed time of day.
    Resumable like fetch_day — complete snapshots are skipped."""
    series = SERIES[series_id]
    epochs = series.epochs()
    jobs: list[tuple[FieldSpec, int, dt.datetime]] = [
        (series_field(series, name), step, when)
        for name in series.fields
        for step, when in series.field_steps(name, epochs)]
    total = len(jobs)
    print(f"fetch: series {series_id} — {total} stacked evaluations "
          f"({len(epochs)} epochs x {len(series.fields)} field(s))")
    write_progress(progress_file, series_id, 0, total, "starting")
    done_paths: dict[str, list[Path]] = {}
    for i, (field, step, when) in enumerate(jobs):
        n_steps = len(series.field_steps(field.name, epochs))
        msg = f"{field.name} t{step:03d}/{n_steps - 1:03d}"
        path = series_npz_path(series_id, field.name, step)
        if not (snapshot_complete(path, field) and not force):
            _save_snapshot(field, path, when, force)
            print(f"  [{i + 1}/{total}] {msg}")
        done_paths.setdefault(field.name, []).append(path)
        write_progress(progress_file, series_id, i + 1, total, msg)

    step_desc = (f"{series.step_minutes}min" if series.step_minutes
                 else f"{series.step_years}y" if series.step_years
                 else f"{series.step_days}d")
    entries = {}
    for field_name, paths in done_paths.items():
        field = series_field(series, field_name)
        if field_name in series.single_step:
            desc = (f"{series.field_steps(field_name, epochs)[0][1].isoformat()}"
                    " (single step)")
        else:
            desc = f"{epochs[0].isoformat()}/{step_desc}/{len(epochs)}"
        if field.sv:
            desc += " (sv: centered ±6mo finite difference, nT/yr)"
        entries[f"series/{series_id}/{field_name}"] = {
            **_manifest_entry(field, series_id, desc, paths),
            "series_kind": series.kind,
            "series_family": series.family,
        }
    upsert_manifest(entries)
    write_progress(progress_file, series_id, total, total, "fetch complete")
    print(f"fetch: series {series_id} done; MANIFEST.toml updated.")


def query_validity() -> None:
    """Validity ranges for every FAMILIES model -> data/validity.json.
    The top-level start/end stay the **CI intersection**: they bound the
    date picker and the day-fetch endpoint, which are CI-only surfaces
    (other families ship as curated series with catalog-fixed epochs).
    Per-family models live under per_model (sv evaluation reads it too)."""
    from viresclient import SwarmRequest

    req = SwarmRequest()
    specs: dict[str, str] = {}
    for layers in FAMILIES.values():
        for spec in layers.values():
            specs.setdefault(model_name(spec), spec)
    per_model: dict[str, dict] = {}
    for name, spec in sorted(specs.items()):
        info = req.get_model_info(models=[spec])
        # info: {alias: {'expression': ..., 'validity': {'start': ..., 'end': ...}}}
        alias = spec.split("=")[0].strip()
        validity = info[alias]["validity"]
        per_model[name] = {"start": validity["start"], "end": validity["end"]}
    ci = {model_name(spec) for spec in FAMILIES["ci"].values()}
    out = {"start": max(per_model[n]["start"] for n in ci),
           "end": min(per_model[n]["end"] for n in ci),
           "per_model": per_model,
           "queried_at": dt.datetime.now(tz=dt.timezone.utc).isoformat()}
    VALIDITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    VALIDITY_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"validity: {out['start']} .. {out['end']} -> {VALIDITY_PATH}")


def fetch_assets(force: bool = False) -> None:
    """Natural Earth 110m coastline GeoJSON (public domain) for the basemap."""
    if COASTLINE_RAW.exists() and not force:
        print(f"skip: {COASTLINE_RAW} exists")
        return
    print(f"fetch: {COASTLINE_URL}")
    with urllib.request.urlopen(COASTLINE_URL, timeout=60) as resp:
        data = resp.read()
    COASTLINE_RAW.parent.mkdir(parents=True, exist_ok=True)
    COASTLINE_RAW.write_bytes(data)
    upsert_manifest({f"assets/{COASTLINE_NAME}": {
        "url": COASTLINE_URL,
        "license": "public domain (Natural Earth)",
        "fetched_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "sha256": _sha256_bytes(data),
    }})
    print("fetch: assets done; MANIFEST.toml updated.")


# --- MANIFEST.toml upsert (vizlab pattern, list-aware) ---

def _toml_value(v) -> str:
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"unsupported TOML value: {v!r}")


def upsert_manifest(entries: dict[str, dict]) -> None:
    """Merge entries (keyed '<day>/<field>') into data/MANIFEST.toml,
    preserving entries not being overwritten."""
    existing: dict = {}
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open("rb") as fh:
            existing = tomllib.load(fh)
    merged = dict(existing.get("files", {}))
    merged.update(entries)
    lines = ["# Auto-generated by fetch.py. One entry per fetched field-day",
             "# (model spec, grid, shells, time range, sha256 = aggregate of",
             "# the sorted per-snapshot digests).", ""]
    for key in sorted(merged):
        lines.append(f'[files."{key}"]')
        for k, v in merged[key].items():
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text("\n".join(lines).rstrip() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static", action="store_true", help="fetch crust (once)")
    parser.add_argument("--day", metavar="YYYY-MM-DD",
                        help="fetch one day (core + iono + magneto)")
    parser.add_argument("--series", metavar="ID", choices=sorted(SERIES),
                        help=f"fetch a curated series: {', '.join(sorted(SERIES))}")
    parser.add_argument("--validity", action="store_true",
                        help="query model validity ranges")
    parser.add_argument("--assets", action="store_true",
                        help="download coastline geojson")
    parser.add_argument("--progress-file", type=Path, default=None)
    parser.add_argument("--force", action="store_true",
                        help="re-fetch even if files exist")
    args = parser.parse_args()
    if not (args.static or args.day or args.series or args.validity
            or args.assets):
        parser.error("nothing to do: pass --static, --day, --series, "
                     "--validity or --assets")
    if args.assets:
        fetch_assets(force=args.force)
    if args.validity:
        query_validity()
    if args.static:
        fetch_static(force=args.force)
    if args.day:
        fetch_day(dt.date.fromisoformat(args.day),
                  progress_file=args.progress_file, force=args.force)
    if args.series:
        fetch_series(args.series, progress_file=args.progress_file,
                     force=args.force)


if __name__ == "__main__":
    main()
