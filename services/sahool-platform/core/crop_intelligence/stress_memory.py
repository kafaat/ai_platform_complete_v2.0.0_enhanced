from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

_SCHEMA = "crop_stress_memory.v2"
_PRODUCT_VERSION = "crop-stress-memory/2.0.0"
_ALLOWED_TYPES = {"water", "heat", "cold", "nutrient", "disease"}


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _finite_unit_interval(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return value


def build_stress_memory(
    observations: list[dict[str, Any]] | None,
    *,
    as_of: datetime | str | None = None,
    half_life_days: float = 7.0,
    max_age_days: float = 45.0,
    source_ids: list[str] | None = None,
    prior_snapshot: dict[str, Any] | None = None,
    decay: float | None = None,
) -> dict[str, Any]:
    """Build a persistence-ready, time-aware crop stress-memory product.

    Each observation must contain ``type``, ``severity`` in [0, 1], and
    ``observed_at``. The reducer never invents timestamps or severities.
    ``prior_snapshot`` is accepted only as lineage metadata; raw observations
    remain the source of truth to prevent compounding rounded aggregates.
    """
    now = _parse_time(as_of) if as_of is not None else datetime.now(UTC)
    if now is None:
        raise ValueError("as_of must be an ISO-8601 datetime")
    if not math.isfinite(float(half_life_days)) or half_life_days <= 0:
        raise ValueError("half_life_days must be finite and > 0")
    if not math.isfinite(float(max_age_days)) or max_age_days <= 0:
        raise ValueError("max_age_days must be finite and > 0")

    lineage_ids = list(source_ids or [])
    if prior_snapshot:
        lineage_ids.extend(prior_snapshot.get("evidence_ids") or [])

    if not observations:
        return {
            "schema": _SCHEMA,
            "product_version": _PRODUCT_VERSION,
            "status": "unavailable",
            "as_of": now.isoformat().replace("+00:00", "Z"),
            "overall_burden": None,
            "by_type": {},
            "recovery_state": "unknown",
            "observation_count": 0,
            "rejected_count": 0,
            "stale_count": 0,
            "latest_observed_at": None,
            "evidence_ids": list(dict.fromkeys(lineage_ids)),
            "limitations": ["stress_history_missing"],
            "persistence": {"snapshot_safe": True, "raw_history_required_for_recompute": True},
        }

    has_any_timestamp = any(item.get("observed_at") is not None for item in observations)
    has_all_timestamps = all(item.get("observed_at") is not None for item in observations)
    legacy_ordered = not has_any_timestamp
    if has_any_timestamp and not has_all_timestamps:
        return {
            "schema": _SCHEMA,
            "product_version": _PRODUCT_VERSION,
            "status": "invalid",
            "as_of": now.isoformat().replace("+00:00", "Z"),
            "overall_burden": None,
            "by_type": {},
            "recovery_state": "unknown",
            "observation_count": 0,
            "rejected_count": len(observations),
            "stale_count": 0,
            "latest_observed_at": None,
            "evidence_ids": list(dict.fromkeys(lineage_ids)),
            "limitations": ["mixed_timestamped_and_legacy_stress_history"],
            "persistence": {"snapshot_safe": True, "raw_history_required_for_recompute": True},
        }

    parsed: list[tuple[str, float, datetime | None, str | None]] = []
    rejected = 0
    stale = 0
    for item in observations:
        kind = str(item.get("type") or "").lower()
        severity = _finite_unit_interval(item.get("severity"))
        observed_at = None if legacy_ordered else _parse_time(item.get("observed_at"))
        if kind not in _ALLOWED_TYPES or severity is None:
            rejected += 1
            continue
        if not legacy_ordered:
            if observed_at is None or observed_at > now:
                rejected += 1
                continue
            age_days = (now - observed_at).total_seconds() / 86400.0
            if age_days > max_age_days:
                stale += 1
                continue
        evidence_id = item.get("evidence_id") if isinstance(item.get("evidence_id"), str) else None
        parsed.append((kind, severity, observed_at, evidence_id))

    if not parsed:
        limitations = ["no_valid_stress_observations"]
        if stale:
            limitations.append("all_stress_observations_stale")
        if rejected:
            limitations.append("invalid_stress_observations_rejected")
        return {
            "schema": _SCHEMA,
            "product_version": _PRODUCT_VERSION,
            "status": "invalid" if rejected else "unavailable",
            "as_of": now.isoformat().replace("+00:00", "Z"),
            "overall_burden": None,
            "by_type": {},
            "recovery_state": "unknown",
            "observation_count": 0,
            "rejected_count": rejected,
            "stale_count": stale,
            "latest_observed_at": None,
            "evidence_ids": list(dict.fromkeys(lineage_ids)),
            "limitations": limitations,
            "persistence": {"snapshot_safe": True, "raw_history_required_for_recompute": True},
        }

    if not legacy_ordered:
        parsed.sort(key=lambda row: row[2] or now)
    weighted: dict[str, float] = {}
    weights: dict[str, float] = {}
    total_weighted = 0.0
    total_weight = 0.0
    legacy_decay = 0.85 if decay is None else min(1.0, max(0.0, float(decay)))
    for index, (kind, severity, observed_at, evidence_id) in enumerate(parsed):
        if legacy_ordered:
            age = len(parsed) - 1 - index
            weight = legacy_decay**age
        else:
            assert observed_at is not None
            age_days = (now - observed_at).total_seconds() / 86400.0
            weight = 0.5 ** (age_days / half_life_days)
        weighted[kind] = weighted.get(kind, 0.0) + severity * weight
        weights[kind] = weights.get(kind, 0.0) + weight
        total_weighted += severity * weight
        total_weight += weight
        if evidence_id:
            lineage_ids.append(evidence_id)

    by_type = {key: round(weighted[key] / weights[key], 4) for key in sorted(weighted)}
    burden = total_weighted / total_weight if total_weight else 0.0
    latest_severity = parsed[-1][1]
    latest_at = parsed[-1][2]
    latest_age_days = (now - latest_at).total_seconds() / 86400.0 if latest_at else 0.0

    if burden >= 0.6 and latest_severity < burden * 0.7:
        recovery = "recovering"
    elif burden >= 0.6:
        recovery = "persistent_stress"
    elif burden >= 0.25:
        recovery = "residual_stress"
    else:
        recovery = "low_burden"

    limitations: list[str] = []
    if legacy_ordered:
        limitations.append("legacy_ordered_history_without_timestamps")
    if rejected:
        limitations.append("invalid_stress_observations_rejected")
    if stale:
        limitations.append("stale_stress_observations_excluded")
    material_limitations = [
        x for x in limitations if x != "legacy_ordered_history_without_timestamps"
    ]
    status = "degraded" if material_limitations or latest_age_days > half_life_days else "available"
    if latest_age_days > half_life_days:
        limitations.append("latest_stress_observation_aging")

    return {
        "schema": _SCHEMA,
        "product_version": _PRODUCT_VERSION,
        "status": status,
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "overall_burden": round(burden, 4),
        "by_type": by_type,
        "recovery_state": recovery,
        "observation_count": len(parsed),
        "rejected_count": rejected,
        "stale_count": stale,
        "latest_observed_at": latest_at.isoformat().replace("+00:00", "Z") if latest_at else None,
        "latest_age_days": round(latest_age_days, 4),
        "half_life_days": float(half_life_days),
        "legacy_decay": legacy_decay if legacy_ordered else None,
        "max_age_days": float(max_age_days),
        "evidence_ids": list(dict.fromkeys(lineage_ids)),
        "limitations": limitations,
        "persistence": {
            "snapshot_safe": True,
            "raw_history_required_for_recompute": True,
            "snapshot_key": "field_id+season_id+as_of",
        },
    }
