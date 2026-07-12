"""Agronomic context contract, freshness, and point-in-time integrity for AgriAI."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import agronomic_adapters as adapters

CONTRACT_VERSION = "agronomic-context.v2"
REQUIRED_CONTEXT = (
    "field_id",
    "season_id",
    "crop_id",
    "cultivar_id",
    "growth_stage",
    "soil_profile",
    "irrigation_profile",
    "weather_snapshot",
    "climate_profile",
    "water_quality_snapshot",
    "vegetation_snapshot",
    "history_snapshot",
    "feature_manifest",
)


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _snapshot_time(snapshot: dict[str, Any]) -> datetime | None:
    return _parse_time(
        snapshot.get("data_available_at")
        or snapshot.get("created_at")
        or snapshot.get("observed_at")
    )


def _max_age_hours(name: str) -> float | None:
    defaults = {
        "weather_snapshot": 12.0,
        "vegetation_snapshot": 24.0 * 14,
        "history_snapshot": 24.0,
    }
    env = os.getenv(f"AGRIAI_{name.upper()}_MAX_AGE_HOURS")
    if env:
        try:
            return float(env)
        except ValueError:
            return defaults.get(name)
    return defaults.get(name)


def _temporal_integrity(context: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    decision_at = _parse_time(context.get("decision_at")) or datetime.now(UTC)
    for key in (
        "weather_snapshot",
        "vegetation_snapshot",
        "history_snapshot",
        "soil_profile",
        "water_quality_snapshot",
    ):
        snap = context.get(key) or {}
        available_at = _snapshot_time(snap)
        if available_at is None:
            issues.append(f"{key}.data_available_at_missing_or_invalid")
            continue
        if available_at > decision_at:
            issues.append(f"{key}.future_data")
        max_age = _max_age_hours(key)
        if max_age is not None and decision_at - available_at > timedelta(hours=max_age):
            issues.append(f"{key}.stale")
    return not issues, issues


def _lineage_integrity(context: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    veg = context.get("vegetation_snapshot") or {}
    if not veg.get("snapshot_hash"):
        issues.append("vegetation_snapshot.snapshot_hash_missing")
    manifest = context.get("feature_manifest") or {}
    if (
        not (manifest.get("manifest_id") or manifest.get("id"))
        or not manifest.get("version")
        or not manifest.get("features")
    ):
        issues.append("feature_manifest_incomplete")
    history = context.get("history_snapshot") or {}
    if not history.get("snapshot_hash"):
        issues.append("history_snapshot.snapshot_hash_missing")
    for key in (
        "soil_profile",
        "irrigation_profile",
        "weather_snapshot",
        "climate_profile",
        "water_quality_snapshot",
    ):
        item = context.get(key) or {}
        if not (item.get("snapshot_id") or item.get("profile_id") or item.get("source_id")):
            issues.append(f"{key}.identity_missing")
    return not issues, issues


def validate_context(context: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    missing = [k for k in REQUIRED_CONTEXT if not context.get(k)]
    veg = context.get("vegetation_snapshot") or {}
    gate = veg.get("quality_gate") or {}
    vegetation_executable = bool(gate.get("executable"))
    temporal_ok, temporal_issues = _temporal_integrity(context)
    lineage_ok, lineage_issues = _lineage_integrity(context)
    complete = not missing and vegetation_executable and temporal_ok and lineage_ok
    return {
        "contract_version": CONTRACT_VERSION,
        "complete": complete,
        "missing": missing,
        "vegetation_executable": vegetation_executable,
        "temporal_integrity": temporal_ok,
        "temporal_issues": temporal_issues,
        "lineage_integrity": lineage_ok,
        "lineage_issues": lineage_issues,
        "strict": strict,
        "context_hash": canonical_hash(context),
        "reason": None if complete else "agronomic_context_incomplete",
    }


def normalized_engine_inputs(context: dict[str, Any]) -> tuple[dict, dict, dict, dict]:
    """Translate governed domain snapshots into model inputs.

    Where a snapshot carries scientific parameters, the strict adapters
    validate them and fail closed on missing/invalid values (crop card,
    soil hydraulics, daily weather series, irrigation efficiency). Sparse
    contexts without those parameters keep the legacy pass-through shape.
    """
    crop_card = dict(context.get("crop_card") or context.get("crop_parameters") or {})
    if crop_card.get("version") is not None:
        crop_card.setdefault("crop_id", context.get("crop_id"))
        crop_card.setdefault("cultivar_id", context.get("cultivar_id"))
        crop = adapters.crop_card_to_model(crop_card)
        crop.setdefault("growth_stage", context.get("growth_stage"))
    else:
        crop = crop_card
        crop.setdefault("crop_id", context.get("crop_id"))
        crop.setdefault("cultivar_id", context.get("cultivar_id"))
        crop.setdefault("growth_stage", context.get("growth_stage"))

    weather_raw = dict(context.get("weather_snapshot") or {})
    weather = (
        adapters.weather_series_to_model(weather_raw) if weather_raw.get("daily") else weather_raw
    )
    weather.setdefault("climate_profile", context.get("climate_profile") or {})

    soil_raw = dict(context.get("soil_profile") or {})
    soil = (
        adapters.soil_profile_to_model(soil_raw)
        if soil_raw.get("field_capacity") is not None
        else soil_raw
    )
    soil.setdefault("water_quality", context.get("water_quality_snapshot") or {})

    irrigation = dict(context.get("irrigation_profile") or {})
    history = dict(context.get("history_snapshot") or {})
    management = dict(context.get("agromanagement") or {})
    if irrigation.get("application_efficiency") is not None:
        management.update(adapters.irrigation_to_model(irrigation, history))
    elif irrigation.get("season_applied_mm") is not None:
        management.setdefault("irrigation_mm", irrigation["season_applied_mm"])
    management.setdefault("irrigation_profile", irrigation)
    management.setdefault("history_snapshot", history)
    management.setdefault("feature_manifest", context.get("feature_manifest") or {})
    return crop, weather, soil, management
