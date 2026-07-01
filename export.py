"""Offline export: data/raw/*.npz -> web/data tiles + manifest.json (+ textures).

Reads only local files (RULES §3). Tile format (PLAN §2 refinement):

    web/data/<field>/<shell>/<day>/t<NN>.i16      day = YYYY-MM-DD | "static"
    web/data/<field>/<shell>/<series-id>/t<NNN>.i16   (series, IDEAS §9.1)
    int16 LE, C row-major, [nlat][nlon][3], components N,E,C (nT)
    i = round(clip(B / qrange, -1, 1) * 32767); no header, dims in manifest.json

A day or series is cached iff listed in web/data/manifest.json — the manifest
is written last via tmp + os.replace, making it the atomic-publish mechanism.

    uv run python export.py --static             # crust tiles
    uv run python export.py --day 2020-01-01     # one day's tiles
    uv run python export.py --series <id>        # one curated series' tiles
    uv run python export.py --assets             # nio LUT + coastlines.png
                                                 # (needs `uv sync --extra assets`;
                                                 #  geojson via `fetch.py --assets`)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

from fetch import (COASTLINE_RAW, DATA_ROOT, FIELDS, ROOT, SERIES,
                   VALIDITY_PATH, FieldSpec, day_fields, raw_npz_path,
                   series_field, series_npz_path)

WEB_DATA = DATA_ROOT / "web" / "data"   # follows GEOMAG_MODEL_EXPLORER_DATA (PLAN §5)
MANIFEST_JSON = WEB_DATA / "manifest.json"
TEXTURES = ROOT / "web" / "textures"
DEFAULT_DAY = "2020-01-01"


def quantize(arr: np.ndarray, qrange: float) -> np.ndarray:
    """Float nT -> int16 with symmetric range. Clips out-of-range loudly."""
    over = float(np.abs(arr).max(initial=0.0))
    if over > qrange:
        print(f"WARNING: clipping values to ±{qrange} nT "
              f"(max |B| = {over:.1f} nT)", file=sys.stderr)
    scaled = np.clip(arr / qrange, -1.0, 1.0) * 32767.0
    return np.round(scaled).astype("<i2")


def tile_path(field: str, shell: str, day: str, step: int) -> Path:
    return WEB_DATA / field / shell / day / f"t{step:02d}.i16"


def series_tile_path(field: str, shell: str, series_id: str, step: int) -> Path:
    """Series ids share the day path slot (slugs are never date-shaped)."""
    return WEB_DATA / field / shell / series_id / f"t{step:03d}.i16"


def expected_tiles(field: FieldSpec, day: str):
    for shell in field.shells:
        for step in range(field.n_steps):
            yield tile_path(field.name, shell, day, step)


def _export_snapshot(field: FieldSpec, npz_file: Path, tile_for) -> dict:
    """One npz (all shells of one field at one epoch) -> tiles, paths from
    tile_for(shell). Returns per-shell {"min", "max", "p99"} in nT; p99 of
    |components| is the display auto-range (it reproduces the prior-art
    display defaults at the surface and stays usable at the CMB, where the
    raw max saturates 37x)."""
    stats = {}
    with np.load(npz_file) as npz:
        for shell in field.shells:
            b = npz[f"B_{shell}"]               # [nlat, nlon, 3]
            assert b.shape == (field.nlat, field.nlon, 3), \
                f"{npz_file}: B_{shell} has shape {b.shape}"
            stats[shell] = {"min": float(b.min()), "max": float(b.max()),
                            "p99": float(np.percentile(np.abs(b), 99))}
            out = tile_for(shell)
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".i16.tmp")
            tmp.write_bytes(quantize(b, field.qrange).tobytes())
            tmp.replace(out)
    return stats


def _merge_stats(acc: dict, new: dict) -> dict:
    """Per-shell merge across timesteps (p99 = max of per-step p99s)."""
    for shell, s in new.items():
        if shell not in acc:
            acc[shell] = dict(s)
        else:
            acc[shell]["min"] = min(acc[shell]["min"], s["min"])
            acc[shell]["max"] = max(acc[shell]["max"], s["max"])
            acc[shell]["p99"] = max(acc[shell]["p99"], s["p99"])
    return acc


def _require_raw(field: FieldSpec, day: str) -> None:
    missing = [p for step in range(field.n_steps)
               if not (p := raw_npz_path(day, field.name, step)).exists()]
    if missing:
        raise SystemExit(f"export: raw data incomplete for {day}/{field.name}: "
                         f"missing {missing[0]} (+{len(missing) - 1} more)")


def export_static() -> None:
    field = FIELDS["crust"]
    _require_raw(field, "static")
    stats = _export_snapshot(field, raw_npz_path("static", field.name, 0),
                             lambda shell: tile_path(field.name, shell,
                                                     "static", 0))
    print(f"export: static/crust tiles done ({_fmt_stats(stats)})")
    write_manifest(static_stats={"crust": stats})


def _fmt_stats(stats: dict) -> str:
    lo = min(s["min"] for s in stats.values())
    hi = max(s["max"] for s in stats.values())
    return f"range {lo:.1f}..{hi:.1f} nT"


def export_day(day: str) -> None:
    dt.date.fromisoformat(day)  # validate
    fields = day_fields()       # never core-sv: derived SV is series-only
    for field in fields:
        _require_raw(field, day)  # all-or-nothing: never publish partial days
    stats: dict[str, dict] = {}
    for field in fields:
        acc: dict = {}
        for step in range(field.n_steps):
            _merge_stats(acc, _export_snapshot(
                field, raw_npz_path(day, field.name, step),
                lambda shell, s=step: tile_path(field.name, shell, day, s)))
        stats[field.name] = acc
        print(f"export: {day}/{field.name} {field.n_steps} step(s) "
              f"({_fmt_stats(acc)})")
    write_manifest(day_record=(day, stats))


def export_series(series_id: str) -> None:
    """All of one curated series' tiles + its manifest record. All-or-nothing
    like export_day: raw must be complete before any tile is written."""
    series = SERIES[series_id]
    epochs = series.epochs()
    sfields = {name: series_field(series, name) for name in series.fields}
    # single_step fields tile once (t000), everything else once per epoch
    steps_for = {name: [s for s, _ in series.field_steps(name, epochs)]
                 for name in series.fields}
    for name in sfields:
        missing = [p for step in steps_for[name]
                   if not (p := series_npz_path(series_id, name, step)).exists()]
        if missing:
            raise SystemExit(
                f"export: raw data incomplete for series {series_id}/{name}: "
                f"missing {missing[0]} (+{len(missing) - 1} more)")
    stats: dict[str, dict] = {}
    for name, field in sfields.items():
        acc: dict = {}
        for step in steps_for[name]:
            _merge_stats(acc, _export_snapshot(
                field, series_npz_path(series_id, name, step),
                lambda shell, s=step: series_tile_path(name, shell,
                                                       series_id, s)))
        stats[name] = acc
        print(f"export: series {series_id}/{name} "
              f"{len(steps_for[name])} epoch(s) ({_fmt_stats(acc)})")
    record = {
        "kind": series.kind,
        "label": series.label,
        "family": series.family,
        "fields": list(series.fields),
        "single_step": list(series.single_step),
        # the storage range each field's tiles were quantized with — may
        # override the field default (CHAOS-Core at the CMB needs ~3x)
        "qrange_nT": {name: f.qrange for name, f in sfields.items()},
        "epochs": [e.isoformat() for e in epochs],
        "fixed_time": series.fixed_time.strftime("%H:%M"),
        "shells": {name: list(f.shells) for name, f in sfields.items()},
        "stats": stats,
        "exported_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
    }
    write_manifest(series_record=(series_id, record))


def _day_complete(day: str) -> bool:
    # day_fields(), not all non-static FIELDS: requiring core-sv tiles here
    # would silently unpublish every cached day (write_manifest prunes).
    return all(p.exists()
               for f in day_fields()
               for p in expected_tiles(f, day))


def _static_complete() -> bool:
    return all(p.exists() for p in expected_tiles(FIELDS["crust"], "static"))


def _series_complete(series_id: str, rec: dict) -> bool:
    """Checked against the record itself (not the SERIES catalog), so series
    removed from the catalog later still publish as long as their tiles last.
    single_step fields (v2.9) carry one tile; records predating the key
    default to per-epoch tiles."""
    single = set(rec.get("single_step", []))
    return all(
        series_tile_path(name, shell, series_id, step).exists()
        for name in rec["fields"]
        for shell in rec["shells"][name]
        for step in range(1 if name in single else len(rec["epochs"])))


def write_manifest(day_record: tuple[str, dict] | None = None,
                   static_stats: dict | None = None,
                   series_record: tuple[str, dict] | None = None) -> None:
    """Read-modify-write web/data/manifest.json, atomically. Only complete
    tile sets are (or stay) listed."""
    existing: dict = {}
    if MANIFEST_JSON.exists():
        existing = json.loads(MANIFEST_JSON.read_text())

    validity = existing.get("validity")
    if VALIDITY_PATH.exists():
        v = json.loads(VALIDITY_PATH.read_text())
        validity = {"start": v["start"], "end": v["end"]}

    fields = {}
    for f in FIELDS.values():
        # qrange_nT/vmax_nT key names are kept even for non-nT fields
        # (renaming would break additivity) — "units" is the truth (v2.9)
        rec = {"grid": [f.nlon, f.nlat], "qrange_nT": f.qrange,
               "vmax_nT": f.vmax, "cadence": f.cadence,
               "n_steps": f.n_steps, "shells": dict(f.shells),
               "units": f.units}
        if f.cadence == "static":
            prior = existing.get("fields", {}).get(f.name, {})
            stats = (static_stats or {}).get(f.name, prior.get("stats"))
            if stats:
                rec["stats"] = stats
        fields[f.name] = rec

    days = dict(existing.get("days", {}))
    if day_record:
        day, stats = day_record
        days[day] = {"exported_at":
                     dt.datetime.now(tz=dt.timezone.utc).isoformat(),
                     "stats": stats}
    days = {d: rec for d, rec in days.items() if _day_complete(d)}

    series = dict(existing.get("series", {}))
    if series_record:
        sid, rec = series_record
        series[sid] = rec
    series = {sid: rec for sid, rec in series.items()
              if _series_complete(sid, rec)}

    manifest = {
        # v2: optional "series" map (IDEAS §9.1) — additive only; a frontend
        # that ignores it sees exactly the v1 schema.
        # v3 (v2.9): per-field "units", per-series "family"/"single_step",
        # and the series-only core-sv field record — all additive again.
        "version": 3,
        "default_day": DEFAULT_DAY,
        "validity": validity,
        "fields": fields,
        "static_done": _static_complete(),
        "days": days,
        "series": series,
    }
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=1) + "\n")
    tmp.replace(MANIFEST_JSON)
    print(f"export: manifest.json updated "
          f"({len(days)} day(s), {len(series)} series, "
          f"static_done={manifest['static_done']})")


# --- dev-time textures (committed to web/textures/) ---

def gen_assets() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from chaosmagpy.plot_utils import nio_colormap

    TEXTURES.mkdir(parents=True, exist_ok=True)

    lut = nio_colormap()(np.linspace(0.0, 1.0, 256))[None, :, :]  # (1, 256, 4)
    plt.imsave(TEXTURES / "colormap_nio.png", lut)
    print(f"assets: {TEXTURES / 'colormap_nio.png'} (256x1 nio LUT)")

    if not COASTLINE_RAW.exists():
        raise SystemExit(f"assets: {COASTLINE_RAW} missing — run "
                         "`uv run --extra fetch python fetch.py --assets` first")
    geo = json.loads(COASTLINE_RAW.read_text())
    fig = plt.figure(figsize=(20.48, 10.24), dpi=100)   # 2048x1024 px
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.axis("off")
    for feature in geo["features"]:
        geom = feature["geometry"]
        parts = ([geom["coordinates"]] if geom["type"] == "LineString"
                 else geom["coordinates"])
        for line in parts:
            xy = np.asarray(line)
            ax.plot(xy[:, 0], xy[:, 1], color="white", linewidth=1.5)
    fig.savefig(TEXTURES / "coastlines.png", transparent=True, dpi=100)
    plt.close(fig)
    print(f"assets: {TEXTURES / 'coastlines.png'} (2048x1024 equirect)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--day", metavar="YYYY-MM-DD")
    parser.add_argument("--series", metavar="ID", choices=sorted(SERIES))
    parser.add_argument("--assets", action="store_true")
    args = parser.parse_args()
    if not (args.static or args.day or args.series or args.assets):
        parser.error("nothing to do: pass --static, --day, --series or --assets")
    if args.assets:
        gen_assets()
    if args.static:
        export_static()
    if args.day:
        export_day(args.day)
    if args.series:
        export_series(args.series)


if __name__ == "__main__":
    main()
