"""Canonical registry for vegetation indicators.

Raster owns pixel computation. Vegetation owns interpretation, eligibility and
provenance validation. This module is intentionally pure and versioned:
``validate_observation`` is the single authority check used by the production
quality gate (vegetation_contracts.quality_gate), and ``build_feature_manifest``
derives the deterministic manifest embedded in every vegetation snapshot.
"""

from __future__ import annotations

from typing import Any

REGISTRY_VERSION = "indicator-registry.v1"

# fmt: off
INDICATORS: dict[str, dict[str, Any]] = {
    "ndvi":  {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B04"], "formula": "(B08-B04)/(B08+B04)", "decision_eligible": True,  "min_valid_pixel_pct": 60.0},
    "evi":   {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B04", "B02"], "decision_eligible": True,  "min_valid_pixel_pct": 60.0},
    "savi":  {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B04"], "decision_eligible": True,  "min_valid_pixel_pct": 60.0},
    "msavi": {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B04"], "decision_eligible": True,  "min_valid_pixel_pct": 60.0},
    "ndmi":  {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B11"], "decision_eligible": True,  "min_valid_pixel_pct": 60.0},
    "ndwi":  {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B03", "B08"], "decision_eligible": False, "min_valid_pixel_pct": 60.0},
    "gndvi": {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B03"], "decision_eligible": False, "min_valid_pixel_pct": 60.0},
    "ndre":  {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B8A", "B05"], "decision_eligible": True,  "min_valid_pixel_pct": 60.0},
    "reci":  {"kind": "observed", "range": [-1.0, 20.0], "unit": "index", "bands": ["B8A", "B05"], "decision_eligible": False, "min_valid_pixel_pct": 60.0},
    # "recl" is the runtime/legacy id for the red-edge chlorophyll index (kept as a
    # distinct entry in config/indicators_registry.json alongside "reci").
    "recl":  {"kind": "observed", "range": [-1.0, 20.0], "unit": "index", "bands": ["B8A", "B05"], "decision_eligible": False, "min_valid_pixel_pct": 60.0},
    "nbr":   {"kind": "observed", "range": [-1.0, 1.0], "unit": "index", "bands": ["B08", "B12"], "decision_eligible": False, "min_valid_pixel_pct": 60.0},
    "lai":   {"kind": "derived", "range": [0.0, 8.0], "unit": "m2/m2", "decision_eligible": False, "requires": ["ndvi"]},
    "fapar": {"kind": "derived", "range": [0.0, 1.0], "unit": "fraction", "decision_eligible": False, "requires": ["ndvi"]},
    "cwsi":  {"kind": "derived", "range": [0.0, 1.0], "unit": "index", "decision_eligible": False, "requires": ["lst", "air_temperature"]},
}
# fmt: on


def definition(name: str) -> dict[str, Any]:
    key = name.strip().lower()
    if key not in INDICATORS:
        raise KeyError(f"unknown_indicator:{key}")
    return {"name": key, "registry_version": REGISTRY_VERSION, **INDICATORS[key]}


def validate_observation(name: str, item: dict[str, Any]) -> list[str]:
    """Authority check for one indicator observation; returns typed error codes.

    Observed indicators must come from raster-service (estimated=False) with full
    provenance (scene, acquisition time, algorithm + QA-mask versions), a data
    availability timestamp, and a valid-pixel percentage above the registry
    threshold. Derived indicators only need a value inside the declared range.
    """
    d = definition(name)
    errors: list[str] = []
    value = item.get("value")
    if not isinstance(value, (int, float)):
        errors.append(f"{name}_value_missing")
    else:
        lo, hi = d["range"]
        if not lo <= float(value) <= hi:
            errors.append(f"{name}_value_out_of_range")
    if d["kind"] == "observed":
        if item.get("source") != "raster-service" or item.get("estimated") is not False:
            errors.append(f"{name}_not_authoritative")
        p = item.get("provenance") or {}
        for k in ("scene_id", "acquisition_datetime", "algorithm_version", "qa_mask_version"):
            if not p.get(k):
                errors.append(f"{name}_provenance_{k}_missing")
        if item.get("data_available_at") is None and p.get("data_available_at") is None:
            errors.append(f"{name}_data_available_at_missing")
        vp = item.get("valid_pixel_pct", p.get("valid_pixel_pct"))
        if not isinstance(vp, (int, float)) or float(vp) < float(d.get("min_valid_pixel_pct", 0)):
            errors.append(f"{name}_valid_pixel_pct_below_threshold")
    return errors


def build_feature_manifest(indices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Deterministic manifest for a snapshot's indices.

    Unregistered names are classified honestly as kind="unregistered" and never
    decision-eligible (fail-soft: an unknown key must not crash snapshot building).
    """
    features = []
    for name in sorted(indices):
        key = name.strip().lower()
        d = INDICATORS.get(key) or {"kind": "unregistered", "decision_eligible": False}
        item = indices[name]
        features.append(
            {
                "name": key,
                "kind": d["kind"],
                "algorithm_version": (item.get("provenance") or {}).get("algorithm_version")
                or item.get("algorithm_version"),
                "source": item.get("source"),
                "decision_eligible": bool(d["decision_eligible"]),
            }
        )
    return {"id": "vegetation-core", "version": REGISTRY_VERSION, "features": features}
