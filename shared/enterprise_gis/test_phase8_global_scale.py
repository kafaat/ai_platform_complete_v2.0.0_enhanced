from shared.enterprise_gis.phase8_global_scale import (
    build_disaster_recovery_plan,
    build_global_deployment_topology,
    compute_error_budget,
    evaluate_load_results,
    generate_load_test_matrix,
    plan_cost_guardrails,
    validate_global_release_gate,
)


def test_global_topology_creates_primary_edges_and_shards():
    topo = build_global_deployment_topology(home_region="me-south-1", satellite_regions=["eu-west-1", "ap-south-1"], tenants=350, fields=125000)
    assert topo["regions"][0]["role"] == "primary-control-plane"
    assert len(topo["regions"]) == 3
    assert topo["sharding"]["tenant_shards"] >= 4


def test_load_matrix_and_results_gate_peak_cache_and_latency():
    matrix = generate_load_test_matrix(fields=120000, target_tiles_per_day=12000000, concurrent_users=1500)
    assert {s["name"] for s in matrix["scenarios"]} == {"smoke", "ramp", "peak", "soak"}
    results = {s["name"]: {"p95_ms": min(300, s["p95_budget_ms"]), "error_rate_pct": 0.1, "cache_hit_ratio": 0.9} for s in matrix["scenarios"]}
    assert evaluate_load_results(matrix, results)["passed"] is True
    results["peak"]["cache_hit_ratio"] = 0.4
    assert evaluate_load_results(matrix, results)["passed"] is False


def test_dr_plan_sets_enterprise_rpo_rto_and_runbook():
    plan = build_disaster_recovery_plan(tier="enterprise", regions=["a", "b"])
    assert plan["rpo_minutes"] == 15
    assert plan["rto_minutes"] == 60
    assert "object_storage" in plan["replication"]


def test_error_budget_status_freezes_when_burn_exceeds_budget():
    healthy = compute_error_budget(slo_pct=99.9, window_minutes=60, observed_errors=10, total_requests=100000)
    assert healthy["status"] in {"healthy", "watch"}
    burned = compute_error_budget(slo_pct=99.9, window_minutes=60, observed_errors=300, total_requests=100000)
    assert burned["status"] == "freeze_releases"


def test_cost_guardrails_recommend_actions_near_budget():
    out = plan_cost_guardrails(monthly_budget_usd=5000, tiles_per_day=12000000, storage_tb=25, gpu_hours=1000)
    assert out["status"] in {"watch", "over_budget"}
    assert "compact_geoparquet_and_archive_cold_cogs" in out["actions"]


def test_global_release_gate_blocks_until_all_enterprise_conditions_pass():
    fail = validate_global_release_gate({"multi_region_ready": True, "rpo_minutes": 60, "rto_minutes": 120, "load_passed": True, "error_budget_status": "healthy", "cost_status": "ok", "security_signoff": True})
    assert fail["ready"] is False
    assert "dr" in fail["blockers"]
    ok = validate_global_release_gate({"multi_region_ready": True, "rpo_minutes": 10, "rto_minutes": 30, "load_passed": True, "error_budget_status": "watch", "cost_status": "watch", "security_signoff": True})
    assert ok["ready"] is True
