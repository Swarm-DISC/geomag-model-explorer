"""Phase v2.11 prerequisite probe (PLAN §3, IDEAS §9.2): confirm the
single-field model names, validities, and empirical amplitudes for the
all-VirES-models lineup before anything reaches FAMILIES/SERIES.

    uv run --extra fetch python docs/v211_model_probe.py

Writes docs/v211_model_probe.json; the human-readable conclusions are
copied into PLAN.md's v2.11 entry (the FAMILIES/SERIES additions are
built from that record, never from guesses). One-off — not part of the
pipeline.

Deliberately unevaluated (presence recorded, no eval): CHAOS-MIO (the
2026-06-12 no-CHAOS-ionosphere decision stands), AMPS (polar current
climatology, not a global field model), MLI_SHA_2E (human decision,
this phase). All three stay in the UI as greyed-out entries.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fetch  # noqa: E402  (eval_stacked, FIELDS, R_SURFACE_M)

OUT = Path(__file__).with_suffix(".json")

# Candidates for evaluation this phase (single-field families), plus the
# already-covered baselines for amplitude comparison.
CANDIDATES = [
    "IGRF", "MCO_SHA_2D",                     # core
    "LCS-1", "MF7", "MLI_SHA_2D",             # crust
    "MIO_SHA_2D",                             # ionosphere
    "MMA_SHA_2F",                             # magnetosphere
]
UNEVALUATED = ["CHAOS-MIO", "AMPS", "MLI_SHA_2E"]   # presence only

CMB_M = 3_480_000.0
DAY_NOON = dt.datetime(2020, 1, 1, 12)    # the curated day's core snapshot
SV_WHEN = dt.datetime(2018, 6, 1, 12)     # well inside every Swarm validity
MCO2D_WHEN = dt.datetime(2016, 1, 1, 12)  # MCO_SHA_2D validity ends 2018-01-01
SV_HALF = dt.timedelta(days=182.625)


def model_catalog(req) -> dict:
    names = req.available_models(details=False)
    return {
        "n_available": len(names),
        "names": sorted(names),               # the full list, this time
        "candidates_present": {c: c in names for c in CANDIDATES},
        "unevaluated_present": {c: c in names for c in UNEVALUATED},
    }


def validities(req, names: list[str]) -> dict:
    out = {}
    for name in names:
        try:
            info = req.get_model_info(models=[f"'{name}'"])
            (alias, rec), = info.items()
            out[name] = {"alias": alias, "expression": rec.get("expression"),
                         "validity": rec["validity"]}
        except Exception as exc:  # record, don't die: absence is a result
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def _stats(mag: np.ndarray) -> dict:
    return {"max": float(mag.max()),
            "p99": float(np.percentile(mag, 99)),
            "median": float(np.median(mag))}


def amplitudes(field_key: str, model: str, shells: dict[str, float],
               when: dt.datetime) -> dict:
    """|B| stats on the field's REAL export grid (a coarse probe grid would
    undersample degree-185 crust anomalies and lowball the qrange)."""
    spec = replace(fetch.FIELDS[field_key], model=model, shells=shells)
    try:
        b = fetch.eval_stacked(spec, when)
        out = {}
        for i, slug in enumerate(spec.shells):
            mag = np.linalg.norm(b[i], axis=-1)
            comp_max = np.abs(b[i]).max(axis=(0, 1))
            out[slug] = {**_stats(mag),
                         "component_max": [float(v) for v in comp_max]}
        return {"ok": True, "when": when.isoformat(),
                "grid": [spec.nlon, spec.nlat], "shells": out}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def sv_magnitudes(model: str, when: dt.datetime) -> dict:
    """|Bdot| from the centered difference at `when`, surface + CMB."""
    spec = replace(fetch.FIELDS["core"], model=model,
                   shells={"cmb": CMB_M, "surface": fetch.R_SURFACE_M})
    try:
        b0 = fetch.eval_stacked(spec, when - SV_HALF)
        b1 = fetch.eval_stacked(spec, when + SV_HALF)
        span_yr = 2 * SV_HALF / dt.timedelta(days=365.25)
        bdot = (b1 - b0) / span_yr
        out = {}
        for i, slug in enumerate(spec.shells):
            mag = np.linalg.norm(bdot[i], axis=-1)
            comp_max = np.abs(bdot[i]).max(axis=(0, 1))
            out[slug] = {**_stats(mag),
                         "component_max": [float(v) for v in comp_max]}
        return {"ok": True, "when": when.isoformat(),
                "span_years": float(span_yr), "shells": out}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    from viresclient import SwarmRequest

    req = SwarmRequest()
    report: dict = {"probed_at":
                    dt.datetime.now(tz=dt.timezone.utc).isoformat()}

    print("== available_models ==")
    report["catalog"] = model_catalog(req)
    print(json.dumps({k: v for k, v in report["catalog"].items()
                      if k != "names"}, indent=2))

    print("== validities ==")
    report["models"] = validities(req, CANDIDATES + UNEVALUATED)
    for name, rec in report["models"].items():
        print(f"  {name}: {rec.get('validity', rec)}")

    surface = {"surface": fetch.R_SURFACE_M}
    core_shells = {"cmb": CMB_M, "surface": fetch.R_SURFACE_M}

    print("== amplitudes (export grids) ==")
    report["amplitudes"] = {
        # crust at 1 deg, surface — qrange candidates vs the MLI 2C baseline
        "MLI_SHA_2C": amplitudes("crust", "Crust = 'MLI_SHA_2C'",
                                 surface, DAY_NOON),
        "MLI_SHA_2D": amplitudes("crust", "Crust = 'MLI_SHA_2D'",
                                 surface, DAY_NOON),
        "LCS-1": amplitudes("crust", "Crust = 'LCS-1'", surface, DAY_NOON),
        "MF7": amplitudes("crust", "Crust = 'MF7'", surface, DAY_NOON),
        # core at 1 deg, CMB + surface — does the family need a qrange
        # override like CHAOS-Core (10M) or fit the CI default (3M)?
        "MCO_SHA_2D": amplitudes("core", "Core = 'MCO_SHA_2D'",
                                 core_shells, MCO2D_WHEN),
        "IGRF": amplitudes("core", "Core = IGRF", core_shells, DAY_NOON),
        "IGRF@1950": amplitudes("core", "Core = IGRF", core_shells,
                                dt.datetime(1950, 6, 1, 12)),
        # iono/magneto at 2 deg, surface — field-default qrange fit check
        "MIO_SHA_2D": amplitudes("iono", "Ionosphere = 'MIO_SHA_2D'",
                                 surface, DAY_NOON),
        "MMA_SHA_2F": amplitudes("magneto", "Magnetosphere = 'MMA_SHA_2F'",
                                 surface, DAY_NOON),
    }
    for name, rec in report["amplitudes"].items():
        line = (rec["shells"] if rec.get("ok") else rec)
        print(f"  {name}: {json.dumps(line)[:200]}")

    print("== SV magnitudes (new core families) ==")
    report["sv"] = {
        "MCO_SHA_2D": sv_magnitudes("Core = 'MCO_SHA_2D'", MCO2D_WHEN),
        "IGRF": sv_magnitudes("Core = IGRF", SV_WHEN),
        "IGRF@1950": sv_magnitudes("Core = IGRF", dt.datetime(1950, 6, 1, 12)),
    }
    print(json.dumps(report["sv"], indent=2))

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
