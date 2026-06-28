"""Phase 7 Enterprise GIS API contracts.

These functions are intentionally framework-light so they can be imported by
FastAPI/DRF routers or tested directly.  They delegate to shared enterprise GIS
contracts added in Phase 7.
"""

from __future__ import annotations

from typing import Any

from shared.enterprise_gis.phase7_enterprise import (
    build_collaboration_event,
    build_tile_cdn_policy,
    generate_autonomous_recommendations,
    ogc_conformance_manifest,
    plan_distributed_raster_processing,
    resolve_geometry_conflicts,
    simulate_digital_twin_scenario,
    validate_planet_scale_readiness,
)


def create_collaboration_event(request: dict[str, Any]) -> dict[str, Any]:
    return build_collaboration_event(
        session_id=str(request["session_id"]),
        field_id=str(request["field_id"]),
        user_id=str(request["user_id"]),
        event_type=str(request["event_type"]),
        payload=dict(request.get("payload") or {}),
        current_revision=int(request.get("current_revision", request.get("revision", 0))),
        conflict_policy=str(request.get("conflict_policy", "revision_guard_then_merge")),
    )


def merge_collaboration_events(request: dict[str, Any]) -> dict[str, Any]:
    return resolve_geometry_conflicts(
        list(request.get("events") or []),
        base_revision=int(request.get("base_revision", 0)),
        strategy=str(request.get("strategy", "latest_safe_patch_wins")),
    )


def get_ogc_manifest(service_url: str, enabled: list[str] | None = None) -> dict[str, Any]:
    return ogc_conformance_manifest(service_url=service_url, enabled=enabled)


def create_distributed_raster_plan(request: dict[str, Any]) -> dict[str, Any]:
    return plan_distributed_raster_processing(
        list(request.get("scenes") or []),
        operations=request.get("operations"),
        max_tiles_per_worker=int(request.get("max_tiles_per_worker", 450)),
        preferred_runtime=str(request.get("preferred_runtime", "dask")),
    )


def run_digital_twin_scenario(request: dict[str, Any]) -> dict[str, Any]:
    return simulate_digital_twin_scenario(
        dict(request.get("baseline") or {}), dict(request.get("scenario") or {})
    )


def produce_autonomous_recommendations(request: dict[str, Any]) -> dict[str, Any]:
    return generate_autonomous_recommendations(
        dict(request.get("twin_snapshot") or {}),
        approval_threshold=float(request.get("approval_threshold", 0.82)),
    )


def assess_planet_scale_readiness(request: dict[str, Any]) -> dict[str, Any]:
    return validate_planet_scale_readiness(dict(request.get("metrics") or request))


def tile_cdn_policy(request: dict[str, Any]) -> dict[str, Any]:
    return build_tile_cdn_policy(
        layer_id=str(request["layer_id"]),
        update_frequency=str(request.get("update_frequency", "daily")),
        sensitivity=str(request.get("sensitivity", "tenant_private")),
    )
