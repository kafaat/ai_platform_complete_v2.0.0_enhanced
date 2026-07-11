"""Production vegetation snapshot contracts and execution quality gates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

CONTRACT_VERSION = "vegetation-snapshot.v2"


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def derive_lai_from_ndvi(ndvi: float) -> dict[str, Any]:
    value = max(0.0, min(8.0, 0.57 * pow(2.718281828, 2.33 * float(ndvi))))
    return {
        "value": round(value, 3),
        "estimated": True,
        "source": "vegetation-model",
        "algorithm": "lai_ndvi_empirical_v1",
        "algorithm_version": "1.0.0",
        "uncertainty": 0.30,
    }


def quality_gate(
    indices: dict[str, dict[str, Any]], *, min_quality: float = 0.60
) -> dict[str, Any]:
    ndvi = indices.get("ndvi") or {}
    reasons: list[str] = []
    if ndvi.get("estimated") is not False or ndvi.get("source") != "raster-service":
        reasons.append("ndvi_not_authoritative")
    value = ndvi.get("value")
    if not isinstance(value, (int, float)) or not -1.0 <= float(value) <= 1.0:
        reasons.append("ndvi_value_invalid")
    quality = ndvi.get("quality_score")
    if not isinstance(quality, (int, float)) or float(quality) < min_quality:
        reasons.append("ndvi_quality_below_threshold")
    provenance = ndvi.get("provenance") or {}
    for key in ("scene_id", "acquisition_datetime", "algorithm_version"):
        if not provenance.get(key):
            reasons.append(f"ndvi_provenance_{key}_missing")
    if ndvi.get("data_available_at") is None and provenance.get("data_available_at") is None:
        reasons.append("ndvi_data_available_at_missing")
    return {
        "executable": not reasons,
        "reasons": reasons,
        "min_quality": min_quality,
        "authoritative_indices": sorted(
            k
            for k, v in indices.items()
            if v.get("source") == "raster-service" and v.get("estimated") is False
        ),
        "derived_indices": sorted(k for k, v in indices.items() if v.get("estimated") is True),
    }


def build_snapshot(
    *,
    field_id: str,
    tenant_id: str,
    season_id: str | None,
    acquisition_date: str | None,
    indices: dict[str, dict[str, Any]],
    source: str,
    quality: dict[str, Any],
    data_available_at: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    body = {
        "contract_version": CONTRACT_VERSION,
        "field_id": field_id,
        "tenant_id": tenant_id,
        "season_id": season_id,
        "acquisition_date": acquisition_date,
        "data_available_at": data_available_at or now,
        "source": source,
        "indices": indices,
        "quality_gate": quality,
    }
    return {**body, "snapshot_hash": canonical_hash(body), "created_at": now}
