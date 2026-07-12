"""Generated vegetation interpretation registry with stable compatibility API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PATH = Path(__file__).with_name("indicator_capabilities.generated.json")
_PAYLOAD = json.loads(_PATH.read_text(encoding="utf-8"))
REGISTRY_VERSION = str(_PAYLOAD.get("schema_version") or "indicator-registry.v1")
INDICATORS = {
    e["id"]: {k: v for k, v in e.items() if k != "id"} for e in _PAYLOAD.get("capabilities", [])
}


def definition(name: str) -> dict[str, Any]:
    key = name.strip().lower()
    if key not in INDICATORS:
        raise KeyError(key)
    return {"name": key, "registry_version": REGISTRY_VERSION, **INDICATORS[key]}


def validate_observation(name: str, observation: dict[str, Any]) -> list[str]:
    key = name.strip().lower()
    d = INDICATORS.get(key)
    errors = []
    if d is None:
        return [f"{key}_unregistered"]
    if d.get("kind") != "observed":
        return errors
    if observation.get("source") != "raster-service":
        errors.append(f"{key}_source_not_raster")
    if observation.get("estimated") is not False:
        errors.append(f"{key}_estimated_not_authoritative")
    prov = observation.get("provenance") or {}
    for field in ("scene_id", "acquisition_datetime", "algorithm_version", "qa_mask_version"):
        if not prov.get(field):
            errors.append(f"{key}_provenance_{field}_missing")
    if not (observation.get("data_available_at") or prov.get("data_available_at")):
        errors.append(f"{key}_data_available_at_missing")
    valid = observation.get("valid_pixel_pct")
    if valid is None:
        ratio = observation.get("valid_pixel_ratio")
        if ratio is not None:
            try:
                valid = float(ratio) * 100 if float(ratio) <= 1 else float(ratio)
            except (TypeError, ValueError):
                valid = None
    if valid is None:
        errors.append(f"{key}_valid_pixel_pct_missing")
    else:
        try:
            if float(valid) < float(d.get("min_valid_pixel_pct", 60)):
                errors.append(f"{key}_valid_pixel_pct_below_threshold")
        except (TypeError, ValueError):
            errors.append(f"{key}_valid_pixel_pct_invalid")
    return errors


def build_feature_manifest(
    indices: dict[str, dict[str, Any]] | list[str] | tuple[str, ...],
) -> dict[str, Any]:
    names = indices.keys() if isinstance(indices, dict) else indices
    features = []
    for name in sorted({str(n).lower() for n in names}):
        d = INDICATORS.get(name) or {
            "kind": "unregistered",
            "decision_eligible": False,
            "owner": None,
        }
        features.append(
            {
                "id": name,
                "kind": d.get("kind"),
                "owner": d.get("owner"),
                "decision_eligible": bool(d.get("decision_eligible")),
            }
        )
    return {"id": "vegetation-core", "version": REGISTRY_VERSION, "features": features}
