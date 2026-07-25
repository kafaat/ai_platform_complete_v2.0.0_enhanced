"""Phase 7 enterprise GIS runtime contracts.

Dependency-light production contracts for the seventh SAHOOL GIS phase:
real-time collaborative GIS, OGC conformance manifests, distributed raster job
planning, richer digital-twin scenario simulation, autonomous recommendations,
and planet-scale validation gates.  The functions are deterministic fallbacks so
CI can validate behavior without WebSocket brokers, Dask/Ray clusters, TEAM
Engine, or live tile CDNs.  Runtime services can replace the adapters behind the
same request/response shapes.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


@dataclass(frozen=True)
class CollaborationEvent:
    event_id: str
    session_id: str
    field_id: str
    user_id: str
    event_type: str
    revision: int
    payload: dict[str, Any]
    conflict_policy: str


@dataclass(frozen=True)
class ConflictResolution:
    accepted: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    merged_revision: int
    strategy: str
    warnings: list[str]


@dataclass(frozen=True)
class DistributedRasterTask:
    task_id: str
    field_id: str
    scene_id: str
    operation: str
    priority: int
    estimated_tiles: int
    worker_pool: str


@dataclass(frozen=True)
class AutonomousRecommendation:
    recommendation_id: str
    domain: str
    action: str
    priority: str
    confidence: float
    rationale: list[str]
    requires_human_approval: bool
    evidence: dict[str, Any]


def build_collaboration_event(
    *,
    session_id: str,
    field_id: str,
    user_id: str,
    event_type: str,
    payload: dict[str, Any],
    current_revision: int,
    conflict_policy: str = "revision_guard_then_merge",
) -> dict[str, Any]:
    if event_type not in {
        "presence",
        "cursor",
        "geometry_patch",
        "annotation",
        "commit",
        "rollback",
    }:
        raise ValueError("unsupported collaboration event_type")
    event = CollaborationEvent(
        event_id=_stable_id(
            {
                "session_id": session_id,
                "field_id": field_id,
                "user_id": user_id,
                "event_type": event_type,
                "payload": payload,
                "rev": current_revision,
            },
            "cge",
        ),
        session_id=session_id,
        field_id=field_id,
        user_id=user_id,
        event_type=event_type,
        revision=current_revision,
        payload=payload,
        conflict_policy=conflict_policy,
    )
    return asdict(event)


def resolve_geometry_conflicts(
    events: list[dict[str, Any]], *, base_revision: int, strategy: str = "latest_safe_patch_wins"
) -> dict[str, Any]:
    """Resolve concurrent GIS edits using revision guards.

    Geometry commits below the base revision are rejected; same-or-newer commits
    are accepted in revision order. Cursor/presence events remain ephemeral and
    are ignored by the commit merger.
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[str] = []
    for event in sorted(
        events, key=lambda e: (_num(e.get("revision")), str(e.get("event_id", "")))
    ):
        etype = event.get("event_type")
        rev = int(_num(event.get("revision"), 0))
        if etype in {"presence", "cursor"}:
            continue
        if rev < base_revision:
            rejected.append({**event, "reason": "stale_revision"})
            warnings.append("stale_revision_rejected")
        elif etype in {"geometry_patch", "commit", "rollback", "annotation"}:
            accepted.append(event)
    merged_revision = base_revision + len(
        [e for e in accepted if e.get("event_type") in {"geometry_patch", "commit", "rollback"}]
    )
    return asdict(
        ConflictResolution(
            accepted=accepted,
            rejected=rejected,
            merged_revision=merged_revision,
            strategy=strategy,
            warnings=sorted(set(warnings)),
        )
    )


def ogc_conformance_manifest(
    *, service_url: str, enabled: list[str] | None = None
) -> dict[str, Any]:
    enabled = enabled or ["features", "tiles", "coverages", "processes"]
    classes = {
        "features": "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
        "tiles": "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core",
        "coverages": "http://www.opengis.net/spec/ogcapi-coverages-1/1.0/conf/core",
        "processes": "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core",
    }
    endpoints = {
        "landingPage": service_url.rstrip("/") + "/ogc",
        "conformance": service_url.rstrip("/") + "/ogc/conformance",
        "collections": service_url.rstrip("/") + "/ogc/collections",
        "tiles": service_url.rstrip("/") + "/ogc/tiles",
        "processes": service_url.rstrip("/") + "/ogc/processes",
    }
    return {
        "conformsTo": [classes[k] for k in enabled if k in classes],
        "endpoints": endpoints,
        "test_engine": "TEAM Engine compatible manifest",
        "status": "ready_for_external_conformance_tests",
    }


def plan_distributed_raster_processing(
    scenes: list[dict[str, Any]],
    *,
    operations: list[str] | None = None,
    max_tiles_per_worker: int = 450,
    preferred_runtime: str = "dask",
) -> dict[str, Any]:
    operations = operations or ["cloud_mask", "cog", "overviews", "statistics", "tile_warm"]
    tasks: list[DistributedRasterTask] = []
    for scene in scenes:
        area_ha = max(1.0, _num(scene.get("area_ha"), 1.0))
        tile_estimate = max(1, int(math.ceil(area_ha / 20.0)))
        cloud = _num(scene.get("cloud_cover"), 0)
        priority = 10 if cloud < 15 else 6 if cloud < 40 else 3
        pool = (
            "gpu" if "cloud_mask" in operations and preferred_runtime in {"ray", "dask"} else "cpu"
        )
        for op in operations:
            tasks.append(
                DistributedRasterTask(
                    task_id=_stable_id({"scene": scene.get("scene_id"), "op": op}, "rtask"),
                    field_id=str(scene.get("field_id", "unknown")),
                    scene_id=str(scene.get("scene_id", "unknown")),
                    operation=op,
                    priority=priority,
                    estimated_tiles=tile_estimate,
                    worker_pool=pool if op in {"cloud_mask", "statistics"} else "cpu",
                )
            )
    total_tiles = sum(t.estimated_tiles for t in tasks if t.operation == "tile_warm")
    recommended_workers = max(1, math.ceil(total_tiles / max(1, max_tiles_per_worker)))
    return {
        "runtime": preferred_runtime,
        "tasks": [asdict(t) for t in tasks],
        "task_count": len(tasks),
        "total_tile_warm_estimate": total_tiles,
        "recommended_workers": recommended_workers,
        "queues": sorted(set(t.worker_pool for t in tasks)),
    }


def simulate_digital_twin_scenario(
    baseline: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Run a deterministic farm digital-twin what-if simulation."""
    baseline_yield = _num(baseline.get("yield_t_ha"), 4.0)
    baseline_water = _num(baseline.get("water_mm"), 450.0)
    baseline_cost = _num(baseline.get("cost_per_ha"), 900.0)
    price = _num(baseline.get("market_price_per_t"), 250.0)

    irrigation_change = _num(scenario.get("irrigation_change_pct"), 0.0) / 100.0
    nitrogen_change = _num(scenario.get("nitrogen_change_pct"), 0.0) / 100.0
    stress_reduction = _num(scenario.get("stress_reduction_pct"), 0.0) / 100.0

    yield_factor = 1.0 + min(
        0.18,
        max(-0.12, irrigation_change * 0.18 + nitrogen_change * 0.10 + stress_reduction * 0.22),
    )
    water_factor = 1.0 + irrigation_change
    cost_factor = 1.0 + max(0.0, nitrogen_change * 0.08) + max(0.0, irrigation_change * 0.04)

    projected_yield = round(baseline_yield * yield_factor, 3)
    projected_water = round(baseline_water * water_factor, 2)
    projected_cost = round(baseline_cost * cost_factor, 2)
    baseline_profit = baseline_yield * price - baseline_cost
    projected_profit = projected_yield * price - projected_cost
    return {
        "scenario_id": _stable_id({"baseline": baseline, "scenario": scenario}, "scenario"),
        "baseline": {
            "yield_t_ha": baseline_yield,
            "water_mm": baseline_water,
            "profit_per_ha": round(baseline_profit, 2),
        },
        "projection": {
            "yield_t_ha": projected_yield,
            "water_mm": projected_water,
            "profit_per_ha": round(projected_profit, 2),
        },
        "delta": {
            "yield_t_ha": round(projected_yield - baseline_yield, 3),
            "water_mm": round(projected_water - baseline_water, 2),
            "profit_per_ha": round(projected_profit - baseline_profit, 2),
        },
        "assumptions": scenario,
    }


def generate_autonomous_recommendations(
    twin_snapshot: dict[str, Any], *, approval_threshold: float = 0.82
) -> dict[str, Any]:
    state = twin_snapshot.get("state", {})
    fields = state.get("fields", []) or []
    irrigation = state.get("irrigation", {}) or {}
    weather = state.get("weather", {}) or {}
    equipment = state.get("equipment", []) or []
    recs: list[AutonomousRecommendation] = []

    stress_count = sum(
        1 for f in fields if str(f.get("status", "")).lower() in {"stress", "critical", "warning"}
    )
    if stress_count:
        conf = min(0.94, 0.68 + stress_count * 0.06)
        recs.append(
            AutonomousRecommendation(
                recommendation_id=_stable_id(
                    {"domain": "crop", "stress": stress_count, "farm": twin_snapshot.get("farm")},
                    "arec",
                ),
                domain="crop_health",
                action="inspect_stress_zones_and_generate_irrigation_or_nutrition_task",
                priority="high" if stress_count >= 2 else "medium",
                confidence=round(conf, 2),
                rationale=["field_stress_detected", f"affected_fields={stress_count}"],
                requires_human_approval=conf < approval_threshold,
                evidence={"stress_field_count": stress_count},
            )
        )
    if str(irrigation.get("status", "")).lower() == "deficit":
        conf = 0.86
        recs.append(
            AutonomousRecommendation(
                recommendation_id=_stable_id({"domain": "water", "irrigation": irrigation}, "arec"),
                domain="irrigation",
                action="increase_next_irrigation_window_or_prioritize_deficit_zones",
                priority="high",
                confidence=conf,
                rationale=["irrigation_deficit", "soil_water_balance_below_target"],
                requires_human_approval=conf < approval_threshold,
                evidence=irrigation,
            )
        )
    if str(weather.get("risk", "")).lower() in {"high", "critical"}:
        recs.append(
            AutonomousRecommendation(
                recommendation_id=_stable_id({"domain": "weather", "weather": weather}, "arec"),
                domain="weather_operations",
                action="block_spraying_and_reschedule_sensitive_operations",
                priority="critical" if str(weather.get("risk")).lower() == "critical" else "high",
                confidence=0.9,
                rationale=["weather_risk_high", "operation_window_unsafe"],
                requires_human_approval=False,
                evidence=weather,
            )
        )
    offline = [
        e
        for e in equipment
        if str(e.get("status", "")).lower() in {"offline", "fault", "maintenance"}
    ]
    if offline:
        recs.append(
            AutonomousRecommendation(
                recommendation_id=_stable_id({"domain": "equipment", "offline": offline}, "arec"),
                domain="equipment",
                action="create_maintenance_ticket_for_blocking_equipment",
                priority="medium",
                confidence=0.84,
                rationale=["equipment_unavailable", f"count={len(offline)}"],
                requires_human_approval=False,
                evidence={"equipment": offline},
            )
        )
    return {
        "recommendations": [asdict(r) for r in recs],
        "count": len(recs),
        "policy": {"approval_threshold": approval_threshold},
    }


def validate_planet_scale_readiness(metrics: dict[str, Any]) -> dict[str, Any]:
    thresholds = {
        "fields": 100_000,
        "tiles_per_day": 10_000_000,
        "concurrent_users": 1_000,
        "p95_tile_ms": 350,
        "p95_stac_ms": 500,
        "error_rate_pct": 1.0,
    }
    checks = {
        "field_scale": _num(metrics.get("fields")) >= thresholds["fields"],
        "tile_volume": _num(metrics.get("tiles_per_day")) >= thresholds["tiles_per_day"],
        "concurrency": _num(metrics.get("concurrent_users")) >= thresholds["concurrent_users"],
        "tile_latency": _num(metrics.get("p95_tile_ms"), 9999) <= thresholds["p95_tile_ms"],
        "stac_latency": _num(metrics.get("p95_stac_ms"), 9999) <= thresholds["p95_stac_ms"],
        "error_budget": _num(metrics.get("error_rate_pct"), 100) <= thresholds["error_rate_pct"],
    }
    passed = all(checks.values())
    blockers = [k for k, ok in checks.items() if not ok]
    return {"ready": passed, "checks": checks, "blockers": blockers, "thresholds": thresholds}


def build_tile_cdn_policy(
    *, layer_id: str, update_frequency: str, sensitivity: str = "tenant_private"
) -> dict[str, Any]:
    ttl_by_frequency = {"hourly": 900, "daily": 86400, "weekly": 604800, "static": 2592000}
    ttl = ttl_by_frequency.get(update_frequency, 3600)
    return {
        "layer_id": layer_id,
        "cache_key": f"tenant:field:layer:{layer_id}:zxy:etag",
        "ttl_seconds": ttl,
        "headers": {
            "Cache-Control": f"private, max-age={ttl}"
            if sensitivity == "tenant_private"
            else f"public, max-age={ttl}, stale-while-revalidate=3600"
        },
        "invalidation_events": [
            "raster_registry.updated",
            "geometry_revision.committed",
            "scene_processing.completed",
        ],
        "warm_strategy": "priority_tiles_first_then_background_pyramid",
    }
