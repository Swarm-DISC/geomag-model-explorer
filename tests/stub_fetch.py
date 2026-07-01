"""Test stand-in for `fetch.py --day D --progress-file P` — writes a tiny
synthetic raw day (real npz shapes, random data) fast, plus progress JSON.
GEOMAG_MODEL_EXPLORER_DATA must point at the sandbox. Set GEOMAG_MODEL_EXPLORER_STUB_FAIL=1 to
simulate a fetch failure."""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch  # noqa: E402


def synth_arrays(f, rng) -> dict:
    """Synthetic npz payload for one snapshot. float32: the v2.7 ladder makes
    a full synthetic day ~1.3 GB in float64 — too big for the host's tmpfs
    (export only quantizes to int16, so the dtype never matters)."""
    arrays = {"lons": np.linspace(-180, 180, f.nlon),
              "lats": np.linspace(-90, 90, f.nlat)}
    for slug in f.shells:
        arrays[f"B_{slug}"] = rng.uniform(
            -f.vmax, f.vmax, size=(f.nlat, f.nlon, 3)).astype(np.float32)
    return arrays


def write_static(rng) -> None:
    f = fetch.FIELDS["crust"]
    path = fetch.raw_npz_path("static", f.name, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        np.savez(fh, **synth_arrays(f, rng))


def write_series(series_id: str, rng) -> None:
    s = fetch.SERIES[series_id]
    epochs = s.epochs()
    for name in s.fields:
        f = fetch.series_field(s, name)
        for step, _when in s.field_steps(name, epochs):
            path = fetch.series_npz_path(series_id, name, step)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as fh:
                np.savez(fh, **synth_arrays(f, rng))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day")
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--series")
    parser.add_argument("--progress-file", type=Path, default=None)
    args = parser.parse_args()

    if os.environ.get("GEOMAG_MODEL_EXPLORER_STUB_FAIL"):
        print("stub: simulated VirES failure", file=sys.stderr)
        sys.exit(3)

    rng = np.random.default_rng(0)
    if args.static:
        write_static(rng)
    if args.series:
        write_series(args.series, rng)
    if not args.day:
        return
    fields = fetch.day_fields()   # mirrors fetch_day: never core-sv
    total = sum(f.n_steps for f in fields)
    done = 0
    for f in fields:
        for step in range(f.n_steps):
            path = fetch.raw_npz_path(args.day, f.name, step)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as fh:
                np.savez(fh, **synth_arrays(f, rng))
            done += 1
            fetch.write_progress(args.progress_file, args.day, done, total,
                                 f"{f.name} t{step:02d}")


if __name__ == "__main__":
    main()
