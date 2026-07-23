"""Phase 8 global-scale GIS runtime contracts.

This module turns Phase 7 readiness concepts into deterministic, testable
contracts for planet-scale operations: multi-region deployment, data placement,
load validation, SLO/error-budget governance, disaster recovery, cost controls,
and final release gates.  The code intentionally avoids cloud SDK dependencies
so CI can validate the behavior in any environment while runtime adapters can
bind these contracts to Kubernetes, Terraform, Cloudflare, MinIO/S3, Dask/Ray,
Prometheus, and the live SAHOOL services.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


@dataclass(frozen=True)
class RegionPlan:
    region: str
    role: str
    min_replicas: int
    tile_cache_tier: str
    object_store_mode: str
    data_residency: str


@dataclass(frozen=True)
class LoadScenario:
    name: str
    virtual_users: int
    duration_minutes: int
    target_rps: int
    p95_budget_ms: int
    error_budget_pct: float
    endpoints: list[str]


@dataclass(frozen=True)
class ReleaseGateResult:
    gate: str
    passed: bool
    reason: str
    evidence: dict[str, Any]


def build_global_deployment_topology(
    *,
    home_region: str,
    satellite_regions: list[str],
    tenants: int,
    fields: int,
    data_residency: str = "tenant_region",
) -> dict[str, Any]:
    """Build a multi-region deployment topology for global GIS runtime."""
    if not home_region:
        raise ValueError("home_region is required")
    unique_satellites = [r for r in dict.fromkeys(satellite_regions) if r != home_region]
    field_scale = max(1, int(_num(fields, 1)))
    tenant_scale = max(1, int(_num(tenants, 1)))
    base_replicas = max(3, min(24, math.ceil(field_scale / 25000)))
    regions = [
        RegionPlan(
            home_region, "primary-control-plane", base_replicas, "hot", "read_write", data_residency
        )
    ]
    for _idx, region in enumerate(unique_satellites):
        role = "active-edge" if field_scale >= 50000 else "warm-standby"
        regions.append(
            RegionPlan(
                region, role, max(2, base_replicas // 2), "warm", "replicated_read", data_residency
            )
        )
    shard_count = max(4, min(256, math.ceil(field_scale / 5000), math.ceil(tenant_scale / 100)))
    return {
        "topology_id": _stable_id(
            {
                "home": home_region,
                "regions": unique_satellites,
                "tenants": tenants,
                "fields": fields,
            },
            "topo",
        ),
        "regions": [asdict(r) for r in regions],
        "sharding": {
            "strategy": "tenant_hash_then_spatial_partition",
            "tenant_shards": shard_count,
            "spatial_partitions": ["country", "governorate", "district", "year"],
            "hot_field_threshold": 100000,
        },
        "traffic": {
            "routing": "geo_latency_with_tenant_residency_guard",
            "failover": "primary_to_nearest_active_edge",
            "write_policy": "single_writer_per_tenant_region",
        },
    }


def generate_load_test_matrix(
    *, fields: int, target_tiles_per_day: int, concurrent_users: int
) -> dict[str, Any]:
    """Create staged load tests with explicit budgets."""
    tiles_day = max(1, int(_num(target_tiles_per_day, 1)))
    users = max(1, int(_num(concurrent_users, 1)))
    target_rps = max(10, math.ceil(tiles_day / 86400))
    smoke = LoadScenario(
        "smoke", min(50, users), 5, min(50, target_rps), 500, 1.0, ["/healthz", "/readyz", "/stac"]
    )
    ramp = LoadScenario(
        "ramp",
        max(100, users // 4),
        20,
        max(50, target_rps // 4),
        450,
        0.75,
        ["/tiles/{z}/{x}/{y}", "/stac/search", "/ogc/collections"],
    )
    peak = LoadScenario(
        "peak",
        users,
        45,
        target_rps,
        350,
        0.5,
        ["/tiles/{z}/{x}/{y}", "/tilejson", "/statistics", "/stac/search"],
    )
    soak = LoadScenario(
        "soak",
        max(100, users // 2),
        240,
        max(20, target_rps // 2),
        400,
        0.5,
        ["/tiles/{z}/{x}/{y}", "/mosaicjson", "/stac/search"],
    )
    return {
        "matrix_id": _stable_id(
            {"fields": fields, "tiles": target_tiles_per_day, "users": users}, "load"
        ),
        "scenarios": [asdict(s) for s in [smoke, ramp, peak, soak]],
        "required_metrics": [
            "p50_ms",
            "p95_ms",
            "p99_ms",
            "error_rate_pct",
            "cache_hit_ratio",
            "cpu_pct",
            "memory_pct",
        ],
        "pass_rule": "all scenarios p95<=budget and error_rate<=budget with cache_hit_ratio>=0.80 after warmup",
    }


def evaluate_load_results(
    matrix: dict[str, Any], results: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Evaluate load results against the generated matrix."""
    gates: list[ReleaseGateResult] = []
    for scenario in matrix.get("scenarios", []):
        name = scenario["name"]
        r = results.get(name, {})
        p95 = _num(r.get("p95_ms"), 999999)
        err = _num(r.get("error_rate_pct"), 100)
        hit = _num(r.get("cache_hit_ratio"), 0)
        passed = (
            p95 <= _num(scenario.get("p95_budget_ms"))
            and err <= _num(scenario.get("error_budget_pct"))
            and (hit >= 0.80 or name == "smoke")
        )
        reason = "passed" if passed else f"p95={p95}, error={err}, cache_hit={hit}"
        gates.append(
            ReleaseGateResult(f"load:{name}", passed, reason, {"budget": scenario, "result": r})
        )
    return {"passed": all(g.passed for g in gates), "gates": [asdict(g) for g in gates]}


def build_disaster_recovery_plan(
    *, tier: str = "enterprise", regions: list[str] | None = None
) -> dict[str, Any]:
    regions = regions or ["primary", "secondary"]
    budgets = {
        "standard": {"rpo_minutes": 60, "rto_minutes": 240},
        "enterprise": {"rpo_minutes": 15, "rto_minutes": 60},
        "mission_critical": {"rpo_minutes": 5, "rto_minutes": 15},
    }
    budget = budgets.get(tier, budgets["enterprise"])
    return {
        "dr_plan_id": _stable_id({"tier": tier, "regions": regions}, "dr"),
        "tier": tier,
        "regions": regions,
        **budget,
        "replication": {
            "postgres": "logical_replication_with_point_in_time_recovery",
            "object_storage": "versioned_cross_region_replication",
            "redis": "rebuildable_cache_no_source_of_truth",
            "nats": "jetstream_mirror_for_critical_subjects",
        },
        "runbook_steps": [
            "freeze writes for affected tenant region when possible",
            "promote standby database",
            "switch object-store endpoint alias",
            "invalidate tile CDN origin mapping",
            "replay critical GIS and recommendation events",
            "run synthetic STAC/tile/field smoke tests",
        ],
    }


def compute_error_budget(
    *, slo_pct: float, window_minutes: int, observed_errors: int, total_requests: int
) -> dict[str, Any]:
    slo = max(0.0, min(99.999, _num(slo_pct, 99.9)))
    allowed_error_fraction = max(0.0, 1.0 - slo / 100.0)
    total = max(1, int(_num(total_requests, 1)))
    allowed_errors = math.floor(total * allowed_error_fraction)
    burn = (
        _num(observed_errors, 0) / max(1, allowed_errors)
        if allowed_errors
        else (999.0 if observed_errors else 0.0)
    )
    return {
        "slo_pct": slo,
        "window_minutes": int(_num(window_minutes, 0)),
        "allowed_errors": allowed_errors,
        "observed_errors": int(_num(observed_errors, 0)),
        "burn_rate": round(burn, 3),
        "status": "healthy" if burn <= 0.5 else "watch" if burn <= 1.0 else "freeze_releases",
    }


def plan_cost_guardrails(
    *, monthly_budget_usd: float, tiles_per_day: int, storage_tb: float, gpu_hours: float
) -> dict[str, Any]:
    budget = max(1.0, _num(monthly_budget_usd, 1.0))
    # Conservative planning units, not vendor quotes.
    estimated = (
        (_num(tiles_per_day) / 1_000_000) * 18.0 * 30
        + _num(storage_tb) * 24.0
        + _num(gpu_hours) * 1.8
    )
    risk = estimated / budget
    actions = []
    if risk > 0.85:
        actions.extend(
            [
                "increase_tile_cache_ttl",
                "defer_noncritical_backfills",
                "use_spot_gpu_for_batch_segmentation",
            ]
        )
    if _num(storage_tb) > 20:
        actions.append("compact_geoparquet_and_archive_cold_cogs")
    if _num(tiles_per_day) > 10_000_000:
        actions.append("enable_edge_cache_warming_only_for_priority_fields")
    return {
        "budget_usd": round(budget, 2),
        "estimated_usd": round(estimated, 2),
        "risk_ratio": round(risk, 3),
        "status": "ok" if risk <= 0.75 else "watch" if risk <= 1.0 else "over_budget",
        "actions": actions,
    }


def validate_global_release_gate(inputs: dict[str, Any]) -> dict[str, Any]:
    """Final Phase 8 release gate for global runtime."""
    gates = [
        ReleaseGateResult(
            "multi_region",
            bool(inputs.get("multi_region_ready")),
            "multi-region topology deployed",
            {"value": inputs.get("multi_region_ready")},
        ),
        ReleaseGateResult(
            "dr",
            _num(inputs.get("rpo_minutes"), 999) <= 15
            and _num(inputs.get("rto_minutes"), 999) <= 60,
            "DR meets enterprise budget",
            {"rpo": inputs.get("rpo_minutes"), "rto": inputs.get("rto_minutes")},
        ),
        ReleaseGateResult(
            "load",
            bool(inputs.get("load_passed")),
            "load matrix passed",
            {"value": inputs.get("load_passed")},
        ),
        ReleaseGateResult(
            "error_budget",
            str(inputs.get("error_budget_status")) in {"healthy", "watch"},
            "error budget not exhausted",
            {"status": inputs.get("error_budget_status")},
        ),
        ReleaseGateResult(
            "cost",
            str(inputs.get("cost_status")) in {"ok", "watch"},
            "cost guardrails acceptable",
            {"status": inputs.get("cost_status")},
        ),
        ReleaseGateResult(
            "security",
            bool(inputs.get("security_signoff")),
            "security sign-off complete",
            {"value": inputs.get("security_signoff")},
        ),
    ]
    blockers = [g.gate for g in gates if not g.passed]
    return {"ready": not blockers, "blockers": blockers, "gates": [asdict(g) for g in gates]}
