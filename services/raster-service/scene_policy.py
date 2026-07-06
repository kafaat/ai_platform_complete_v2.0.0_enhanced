"""Scene ranking and historical backfill selection policies for raster-service.

This module is intentionally framework-free so routers/workers can reuse the same
agronomic scene selection rules without importing the large FastAPI application
module. ``main.py`` re-exports the public helpers for backwards compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _to_mapping(scene: dict | Any) -> dict:
    if isinstance(scene, dict):
        return dict(scene)
    if hasattr(scene, "model_dump"):
        return dict(scene.model_dump())
    if hasattr(scene, "dict"):
        return dict(scene.dict())
    return dict(getattr(scene, "__dict__", {}) or {})


def scene_datetime(scene: dict | Any) -> datetime | None:
    val = getattr(scene, "datetime", None) if not isinstance(scene, dict) else scene.get("datetime")
    if not val:
        props = (
            getattr(scene, "properties", None)
            if not isinstance(scene, dict)
            else scene.get("properties")
        )
        props = props or {}
        val = props.get("datetime") or props.get("acquisition_datetime")
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).astimezone(UTC)
    except Exception:  # noqa: BLE001
        return None


def scene_to_dict(scene: dict | Any) -> dict:
    return _to_mapping(scene)


# Agronomic pull policy for core satellite timeline imagery. The values are intentionally
# conservative enough for Yemen/arid operations: do not reject every partially cloudy
# Sentinel-2 scene, but never put scenes with less than 50% clear coverage into the
# default NDVI timeline. >=70% clear is treated as high quality in UI/API metadata.
CORE_TIMELINE_INDICES: set[str] = {"truecolor", "ndvi", "ndre", "ndmi", "msavi", "ndwi", "ndsi"}
NDVI_PULL_MIN_CLEAR_PCT = 50.0
NDVI_PULL_MAX_CLOUD_PCT = 100.0 - NDVI_PULL_MIN_CLEAR_PCT
NDVI_HIGH_QUALITY_CLEAR_PCT = 70.0
NDVI_PULL_MIN_SPACING_DAYS = 3.0
NDVI_PULL_TARGET_SPACING_DAYS = 5.0


def scene_cloud_pct(scene: dict | Any) -> float | None:
    d = scene_to_dict(scene)
    props = d.get("properties") or {}
    value = d.get("aoi_cloud_pct")
    if value is None:
        value = d.get("cloud_cover_pct", props.get("eo:cloud_cover", props.get("cloud_cover")))
    try:
        return max(0.0, min(100.0, float(value))) if value is not None else None
    except Exception:  # noqa: BLE001
        return None


def scene_clear_pct(scene: dict | Any) -> float | None:
    cloud = scene_cloud_pct(scene)
    return (100.0 - cloud) if cloud is not None else None


def scene_quality_label(scene: dict | Any) -> str:
    clear = scene_clear_pct(scene)
    if clear is None:
        return "unknown"
    if clear >= NDVI_HIGH_QUALITY_CLEAR_PCT:
        return "high"
    if clear >= NDVI_PULL_MIN_CLEAR_PCT:
        return "medium"
    return "cloudy"


def scene_day_key(scene: dict | Any) -> str | None:
    dt = scene_datetime(scene)
    return dt.date().isoformat() if dt else None


def scene_quality_score(
    scene: dict | Any,
    *,
    now: datetime | None = None,
    max_cloud_pct: float = 40.0,
    prefer_recent_days: int = 45,
) -> dict:
    """Rank satellite scenes using production-safe, explainable weights."""
    d = scene_to_dict(scene)
    props = d.get("properties") or {}
    cloud = d.get("aoi_cloud_pct")
    cloud_source = "aoi_cloud_pct"
    if cloud is None:
        cloud = d.get("cloud_cover_pct", props.get("eo:cloud_cover", props.get("cloud_cover")))
        cloud_source = "scene_cloud_pct"
    try:
        cloud = float(cloud) if cloud is not None else 100.0
    except Exception:
        cloud = 100.0
    cloud = max(0.0, min(100.0, cloud))
    cloud_score = max(0.0, 1.0 - (cloud / max(float(max_cloud_pct), 1.0)))

    now = now or datetime.now(UTC)
    dt = scene_datetime(scene)
    if dt:
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        recency_score = max(0.0, 1.0 - age_days / max(float(prefer_recent_days), 1.0))
    else:
        age_days = None
        recency_score = 0.25

    coverage = d.get("coverage_pct", props.get("sahool:coverage_pct", 100.0))
    try:
        coverage_score = max(0.0, min(1.0, float(coverage) / 100.0))
    except Exception:
        coverage_score = 0.75

    provider_quality = d.get("provider_quality", props.get("sahool:quality", None))
    try:
        provider_quality = (
            max(0.0, min(1.0, float(provider_quality))) if provider_quality is not None else 0.75
        )
    except Exception:
        provider_quality = 0.75

    view_angle = d.get("view_angle", props.get("view:off_nadir", 0.0))
    try:
        angle_penalty = min(0.15, max(0.0, float(view_angle)) / 400.0)
    except Exception:
        angle_penalty = 0.0

    score = (
        (0.50 * cloud_score)
        + (0.20 * recency_score)
        + (0.20 * coverage_score)
        + (0.10 * provider_quality)
        - angle_penalty
    )
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 4),
        "cloud_pct": round(cloud, 3),
        "cloud_source": cloud_source,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "coverage_score": round(coverage_score, 4),
        "recency_score": round(recency_score, 4),
        "provider_quality": round(provider_quality, 4),
        "view_angle_penalty": round(angle_penalty, 4),
    }


def rank_scenes(
    scenes: list[dict | Any],
    *,
    max_cloud_pct: float = 40.0,
    prefer_recent_days: int = 45,
) -> list[dict]:
    ranked = []
    for scene in scenes:
        d = scene_to_dict(scene)
        q = scene_quality_score(
            scene, max_cloud_pct=max_cloud_pct, prefer_recent_days=prefer_recent_days
        )
        d["sahool_quality"] = q
        d["quality_score"] = q["score"]
        ranked.append(d)
    return sorted(
        ranked, key=lambda it: (-float(it.get("quality_score", 0)), it.get("datetime") or "")
    )


def select_backfill_scenes_by_policy(
    scenes: list[dict | Any],
    *,
    indices: list[str] | None = None,
    max_cloud_pct: float = NDVI_PULL_MAX_CLOUD_PCT,
    limit: int = 8,
    min_spacing_days: float = NDVI_PULL_MIN_SPACING_DAYS,
) -> list[dict]:
    """Select provider scenes for historical backfill using the NDVI timeline policy."""
    requested = {str(i).lower() for i in (indices or [])}
    core_requested = bool(requested & CORE_TIMELINE_INDICES) or not requested
    effective_max_cloud = NDVI_PULL_MAX_CLOUD_PCT if core_requested else float(max_cloud_pct)
    effective_max_cloud = (
        min(float(max_cloud_pct), effective_max_cloud)
        if max_cloud_pct is not None
        else effective_max_cloud
    )
    ranked = rank_scenes(scenes, max_cloud_pct=effective_max_cloud)

    eligible: list[dict] = []
    for item in ranked:
        cloud = scene_cloud_pct(item)
        if cloud is not None and cloud > effective_max_cloud:
            continue
        clear = scene_clear_pct(item)
        item["clear_pct"] = round(clear, 3) if clear is not None else None
        item["quality_label"] = scene_quality_label(item)
        eligible.append(item)

    selected: list[dict] = []
    selected_dt: list[datetime] = []
    for item in eligible:
        dt = scene_datetime(item)
        if dt and any(
            abs((dt - prev).total_seconds()) < min_spacing_days * 86400 for prev in selected_dt
        ):
            continue
        selected.append(item)
        if dt:
            selected_dt.append(dt)
        if len(selected) >= max(1, int(limit)):
            break

    if len(selected) < max(1, int(limit)):
        seen_days = {scene_day_key(s) for s in selected}
        for item in eligible:
            day = scene_day_key(item)
            if day in seen_days:
                continue
            selected.append(item)
            seen_days.add(day)
            if len(selected) >= max(1, int(limit)):
                break

    return sorted(selected, key=lambda it: scene_datetime(it) or datetime.min.replace(tzinfo=UTC))
