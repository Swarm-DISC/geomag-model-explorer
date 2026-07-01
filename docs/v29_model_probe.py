"""Phase v2.9 prerequisite probe (PLAN §3): exact VirES model names,
validities, composed-MMA evaluability, and empirical SV magnitudes.

    uv run --extra fetch python docs/v29_model_probe.py

Writes docs/v29_model_probe.json; the human-readable conclusions are
copied into PLAN.md's v2.9 entry (the FAMILIES table is built from that
record, never from guesses). One-off — not part of the pipeline.
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

# Candidate served-model names to confirm (IDEAS §9.2 says probe, don't assume).
CANDIDATES = [
    "IGRF",
    "CHAOS-Core", "CHAOS-Static",
    "CHAOS-MMA-Primary", "CHAOS-MMA-Secondary",
    "LCS-1", "MF7",
]

# 5-degree probe grids: 73x37 surface+CMB = 5402 points per eval.
PROBE_NLON, PROBE_NLAT = 73, 37
CMB_M = 3_480_000.0
SV_WHEN = dt.datetime(2018, 6, 1, 12)     # well inside every validity
SV_HALF = dt.timedelta(days=182.625)


def model_catalog(req) -> dict:
    names = req.available_models(details=False)
    return {
        "n_available": len(names),
        "candidates_present": {c: c in names for c in CANDIDATES},
        "wdmam_like": [n for n in names if "wdmam" in n.lower()],
        "chaos_like": [n for n in names if "chaos" in n.lower()],
        "igrf_like": [n for n in names if "igrf" in n.lower()],
        "crust_like": [n for n in names
                       if any(k in n.lower() for k in ("lcs", "mf7", "mli"))],
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


def probe_field(model: str, shells: dict[str, float]) -> "fetch.FieldSpec":
    return replace(fetch.FIELDS["core"], model=model,
                   nlon=PROBE_NLON, nlat=PROBE_NLAT, shells=shells)


def composed_mma_eval() -> dict:
    """Confirm a summed two-model expression evaluates (the CHAOS magneto
    layer needs Primary + Secondary in one spec)."""
    spec = probe_field(
        "Magnetosphere = 'CHAOS-MMA-Primary' + 'CHAOS-MMA-Secondary'",
        {"surface": fetch.R_SURFACE_M})
    try:
        b = fetch.eval_stacked(spec, SV_WHEN)
        mag = np.linalg.norm(b[0], axis=-1)
        return {"ok": True, "surface_abs_nT": _stats(mag)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _stats(mag: np.ndarray) -> dict:
    return {"max": float(mag.max()),
            "p99": float(np.percentile(mag, 99)),
            "median": float(np.median(mag))}


def sv_magnitudes(model: str) -> dict:
    """|Bdot| from the centered difference at SV_WHEN, surface + CMB."""
    spec = probe_field(model, {"cmb": CMB_M, "surface": fetch.R_SURFACE_M})
    try:
        b0 = fetch.eval_stacked(spec, SV_WHEN - SV_HALF)
        b1 = fetch.eval_stacked(spec, SV_WHEN + SV_HALF)
        span_yr = 2 * SV_HALF / dt.timedelta(days=365.25)
        bdot = (b1 - b0) / span_yr
        out = {}
        for i, slug in enumerate(spec.shells):
            mag = np.linalg.norm(bdot[i], axis=-1)
            comp_max = np.abs(bdot[i]).max(axis=(0, 1))
            out[slug] = {**_stats(mag),
                         "component_max": [float(v) for v in comp_max]}
        return {"ok": True, "when": SV_WHEN.isoformat(),
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
    print(json.dumps(report["catalog"], indent=2))

    present = [c for c, ok in
               report["catalog"]["candidates_present"].items() if ok]
    print("== validities ==")
    report["models"] = validities(req, present)
    for name, rec in report["models"].items():
        print(f"  {name}: {rec.get('validity', rec)}")

    print("== composed CHAOS-MMA eval ==")
    report["composed_mma"] = composed_mma_eval()
    print(json.dumps(report["composed_mma"], indent=2))

    print("== SV magnitudes ==")
    report["sv"] = {
        "MCO_SHA_2C": sv_magnitudes("Core = 'MCO_SHA_2C'"),
        "CHAOS-Core": sv_magnitudes("Core = 'CHAOS-Core'"),
    }
    print(json.dumps(report["sv"], indent=2))

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
