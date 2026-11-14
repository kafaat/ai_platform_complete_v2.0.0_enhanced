"""Strict, side-effect-free feature admission for research/shadow evaluation.

Does not replace legacy feature-store APIs or authorize agronomic execution.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("ISO-8601 timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)


def strict_shadow_snapshot(
    records: list[dict[str, Any]],
    *,
    tenant_id: str,
    season_id: str,
    feature_set_id: str,
    as_of: str,
    max_age_hours: int = 8760,
) -> dict[str, Any]:
    """Select available features without mixing tenants, seasons or feature sets.

    This is a pure opt-in contract. No database, model registry or execution path
    is touched. Both publication and ingestion must precede the decision.
    """
    if not all((tenant_id, season_id, feature_set_id)) or max_age_hours < 0:
        raise ValueError("scope and nonnegative maximum age are required")
    cutoff = _timestamp(as_of)
    selected: dict[tuple[str, str], tuple[tuple[datetime, datetime, str], dict[str, Any]]]
    selected = {}
    excluded: dict[str, int] = {}

    def reject(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for record in records:
        if record.get("tenant_id") != tenant_id:
            reject("other_tenant")
            continue
        if record.get("season_id") != season_id:
            reject("other_season")
            continue
        if record.get("feature_set_id") != feature_set_id:
            reject("other_feature_set")
            continue
        if record.get("entity_type", "field") != "field":
            reject("wrong_entity_type")
            continue
        if not record.get("entity_id") or not record.get("source_version"):
            reject("missing_provenance")
            continue
        features = record.get("features")
        if not isinstance(features, dict) or not features:
            reject("invalid_features")
            continue
        invalid_feature = False
        for name, value in features.items():
            if not isinstance(name, str) or not name:
                invalid_feature = True
                break
            if isinstance(value, bool):
                invalid_feature = True
                break
            if not isinstance(value, (str, int, float)):
                invalid_feature = True
                break
            if isinstance(value, (int, float)) and not math.isfinite(value):
                invalid_feature = True
                break
        if invalid_feature:
            reject("invalid_features")
            continue
        try:
            event = _timestamp(record.get("event_time"))
            available = _timestamp(record.get("available_at"))
            ingested = _timestamp(record.get("ingested_at"))
        except (ValueError, TypeError):
            reject("invalid_time")
            continue
        if event > available:
            reject("event_after_publication")
            continue
        if max(event, available, ingested) > cutoff:
            reject("future_information")
            continue
        if (cutoff - event).total_seconds() > max_age_hours * 3600:
            reject("stale")
            continue
        key = ("field", str(record["entity_id"]))
        rank = (max(available, ingested), event, str(record["source_version"]))
        if key not in selected or rank > selected[key][0]:
            selected[key] = (rank, record)

    rows = [
        {
            "tenant_id": tenant_id,
            "season_id": season_id,
            "feature_set_id": feature_set_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_time": record["event_time"],
            "available_at": record["available_at"],
            "ingested_at": record["ingested_at"],
            "source_version": record["source_version"],
            "features": record["features"],
        }
        for (entity_type, entity_id), (_, record) in sorted(selected.items())
    ]
    payload = {
        "tenant_id": tenant_id,
        "season_id": season_id,
        "feature_set_id": feature_set_id,
        "as_of": cutoff.isoformat(),
        "max_age_hours": max_age_hours,
        "rows": rows,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    digest = sha256(encoded).hexdigest()
    return {
        "snapshot_id": f"pit_{digest[:20]}",
        "row_count": len(rows),
        "rows": rows,
        "excluded_by_reason": excluded,
        "mode": "shadow",
    }
