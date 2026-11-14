"""Strict, side-effect-free feature admission for research/shadow evaluation.

Does not replace legacy feature-store APIs or authorize agronomic execution.

This module adds *scope* admission only: one tenant, one season, one feature set,
field entities, and plain finite scalar feature values. Every point-in-time
decision (timezone-aware stamps, ``event_time <= available_at <= ingested_at <=
prediction_at``, nothing after ``as_of``, provenance, staleness, latest-wins
selection) is delegated to the feature store's single authority,
``shared.feature_store.runtime.build_point_in_time_snapshot``. Do not add cutoff
or availability checks here: a second point-in-time authority would drift from
the first.
"""

from __future__ import annotations

import json
import math
from hashlib import sha256
from typing import Any

from shared.feature_store.runtime import build_point_in_time_snapshot


def _scalar_features_valid(features: Any) -> bool:
    if not isinstance(features, dict) or not features:
        return False
    for name, value in features.items():
        if not isinstance(name, str) or not name:
            return False
        # bool is an int subclass; a flag is not a numeric feature value here.
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return False
        if isinstance(value, float) and not math.isfinite(value):
            return False
    return True


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
    is touched. Records outside the requested scope are excluded here; the rest
    are judged by ``build_point_in_time_snapshot`` and its exclusion reasons are
    reported alongside the scope reasons.
    """
    if not all(isinstance(v, str) and v for v in (tenant_id, season_id, feature_set_id)):
        raise ValueError("tenant_id, season_id and feature_set_id are required")
    excluded: dict[str, int] = {}
    in_scope: list[dict[str, Any]] = []

    def reject(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for record in records:
        if not isinstance(record, dict):
            reject("record_invalid")
        elif record.get("tenant_id") != tenant_id:
            reject("other_tenant")
        elif record.get("season_id") != season_id:
            reject("other_season")
        elif record.get("feature_set_id") != feature_set_id:
            reject("other_feature_set")
        elif record.get("entity_type", "field") != "field":
            reject("wrong_entity_type")
        elif not _scalar_features_valid(record.get("features")):
            reject("invalid_features")
        else:
            in_scope.append(record)

    # Raises ValueError for a naive or invalid as_of and a negative max_age_hours.
    snapshot = build_point_in_time_snapshot(in_scope, as_of=as_of, max_age_hours=max_age_hours)
    for reason, count in snapshot["exclusion_reasons"].items():
        excluded[reason] = excluded.get(reason, 0) + count

    rows = [
        {**row, "season_id": season_id, "feature_set_id": feature_set_id}
        for row in snapshot["rows"]
    ]
    payload = {
        "tenant_id": tenant_id,
        "season_id": season_id,
        "feature_set_id": feature_set_id,
        "as_of": snapshot["as_of"],
        "max_age_hours": max_age_hours,
        "rows": rows,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    digest = sha256(encoded).hexdigest()
    return {
        "snapshot_id": f"pit_{digest[:20]}",
        "authority_snapshot_id": snapshot["snapshot_id"],
        "as_of": snapshot["as_of"],
        "row_count": len(rows),
        "rows": rows,
        "excluded_by_reason": dict(sorted(excluded.items())),
        "mode": "shadow",
    }
