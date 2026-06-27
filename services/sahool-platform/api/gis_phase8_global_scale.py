"""Phase 8 Global Scale API contracts."""

from __future__ import annotations

from typing import Any

from shared.enterprise_gis.phase8_global_scale import (
    build_disaster_recovery_plan,
    build_global_deployment_topology,
    compute_error_budget,
    evaluate_load_results,
    generate_load_test_matrix,
    plan_cost_guardrails,
    validate_global_release_gate,
)


def create_global_topology(request: dict[str, Any]) -> dict[str, Any]:
    return build_global_deployment_topology(
        home_region=str(request["home_region"]),
        satellite_regions=list(request.get("satellite_regions") or []),
        tenants=int(request.get("tenants", 1)),
        fields=int(request.get("fields", 1)),
        data_residency=str(request.get("data_residency", "tenant_region")),
    )


def create_load_matrix(request: dict[str, Any]) -> dict[str, Any]:
    return generate_load_test_matrix(
        fields=int(request.get("fields", 1)),
        target_tiles_per_day=int(request.get("target_tiles_per_day", 1)),
        concurrent_users=int(request.get("concurrent_users", 1)),
    )


def assess_load_results(request: dict[str, Any]) -> dict[str, Any]:
    return evaluate_load_results(
        dict(request.get("matrix") or {}), dict(request.get("results") or {})
    )


def create_disaster_recovery_plan(request: dict[str, Any]) -> dict[str, Any]:
    return build_disaster_recovery_plan(
        tier=str(request.get("tier", "enterprise")), regions=list(request.get("regions") or [])
    )


def assess_error_budget(request: dict[str, Any]) -> dict[str, Any]:
    return compute_error_budget(
        slo_pct=float(request.get("slo_pct", 99.9)),
        window_minutes=int(request.get("window_minutes", 60)),
        observed_errors=int(request.get("observed_errors", 0)),
        total_requests=int(request.get("total_requests", 1)),
    )


def create_cost_guardrails(request: dict[str, Any]) -> dict[str, Any]:
    return plan_cost_guardrails(
        monthly_budget_usd=float(request.get("monthly_budget_usd", 1)),
        tiles_per_day=int(request.get("tiles_per_day", 1)),
        storage_tb=float(request.get("storage_tb", 0)),
        gpu_hours=float(request.get("gpu_hours", 0)),
    )


def assess_global_release_gate(request: dict[str, Any]) -> dict[str, Any]:
    return validate_global_release_gate(dict(request))
