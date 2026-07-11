"""Canonical live-ingestion contract for Crop Intelligence stress events.

This adapter accepts only already-derived stress products.  It does not infer
severity from raw weather, raster values, or booleans.  Missing or malformed
signals are rejected so persistence never manufactures agronomic evidence.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from api.crop_stress_store import append_stress_event

_ALLOWED_PRODUCT_SCHEMAS = {
    "canonical_stress_product.v1",
    "weather_stress_product.v1",
    "water_stress_product.v1",
    "vegetation_stress_product.v1",
}
_ALLOWED_TYPES = {"water", "heat", "cold", "nutrient", "disease"}


def _finite_severity(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        return None
    return value


def normalize_stress_product(product: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a canonical upstream stress product into durable events.

    Required product fields: schema, source_service, product_id,
    product_version, observed_at, and stress_signals[].  Each signal must carry
    an explicit type and numeric severity in [0,1].
    """
    schema = str(product.get("schema") or "")
    if schema not in _ALLOWED_PRODUCT_SCHEMAS:
        raise ValueError("unsupported stress product schema")
    source_service = str(product.get("source_service") or "").strip()
    product_id = str(product.get("product_id") or "").strip()
    product_version = str(product.get("product_version") or "").strip()
    observed_at = product.get("observed_at")
    if not source_service or not product_id or not product_version or not observed_at:
        raise ValueError("stress product provenance is incomplete")

    signals = product.get("stress_signals")
    if not isinstance(signals, list) or not signals:
        raise ValueError("stress_signals must be a non-empty list")

    normalized: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        if not isinstance(signal, dict):
            raise ValueError(f"stress signal {index} must be an object")
        kind = str(signal.get("type") or "").lower()
        severity = _finite_severity(signal.get("severity"))
        if kind not in _ALLOWED_TYPES or severity is None:
            raise ValueError(f"stress signal {index} is invalid")
        evidence_id = signal.get("evidence_id") or f"{source_service}:{product_id}:{index}"
        normalized.append(
            {
                "type": kind,
                "severity": severity,
                "observed_at": signal.get("observed_at") or observed_at,
                "evidence_id": str(evidence_id),
                "source_service": source_service,
                "source_product_id": product_id,
                "source_version": product_version,
                "payload": {
                    "product_schema": schema,
                    "quality_status": product.get("quality_status"),
                    "signal": signal,
                    "product_provenance": product.get("provenance") or {},
                },
            }
        )
    return normalized


async def ingest_stress_product(
    conn: Any,
    *,
    tenant_id: UUID,
    field_id: str,
    season_id: str,
    product: dict[str, Any],
) -> dict[str, Any]:
    """Persist all explicit stress signals from one canonical product."""
    events = normalize_stress_product(product)
    persisted = 0
    deduplicated = 0
    keys: list[str] = []
    for event in events:
        result = await append_stress_event(
            conn,
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            event=event,
        )
        persisted += int(result["persisted"])
        deduplicated += int(result["deduplicated"])
        keys.append(result["dedup_key"])
    return {
        "status": "ingested",
        "accepted_signals": len(events),
        "persisted": persisted,
        "deduplicated": deduplicated,
        "dedup_keys": keys,
        "source_service": product["source_service"],
        "source_product_id": product["product_id"],
    }
