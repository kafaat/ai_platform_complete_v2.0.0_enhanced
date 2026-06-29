import importlib.util
from pathlib import Path


def _load_api():
    path = Path(__file__).resolve().parents[1] / "api" / "gis_phase8_global_scale.py"
    spec = importlib.util.spec_from_file_location("gis_phase8_global_scale", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_phase8_api_contracts_are_importable_and_deterministic():
    api = _load_api()
    topo = api.create_global_topology(
        {
            "home_region": "me-south-1",
            "satellite_regions": ["eu-west-1"],
            "tenants": 250,
            "fields": 100000,
        }
    )
    assert topo["traffic"]["routing"] == "geo_latency_with_tenant_residency_guard"

    matrix = api.create_load_matrix(
        {"fields": 100000, "target_tiles_per_day": 10000000, "concurrent_users": 1000}
    )
    results = {
        s["name"]: {"p95_ms": 250, "error_rate_pct": 0.1, "cache_hit_ratio": 0.9}
        for s in matrix["scenarios"]
    }
    assert api.assess_load_results({"matrix": matrix, "results": results})["passed"] is True

    dr = api.create_disaster_recovery_plan({"tier": "mission_critical", "regions": ["a", "b"]})
    assert dr["rpo_minutes"] <= 5

    eb = api.assess_error_budget(
        {"slo_pct": 99.9, "window_minutes": 60, "observed_errors": 10, "total_requests": 100000}
    )
    assert eb["status"] in {"healthy", "watch"}

    cost = api.create_cost_guardrails(
        {"monthly_budget_usd": 10000, "tiles_per_day": 1000000, "storage_tb": 2, "gpu_hours": 20}
    )
    assert cost["status"] == "ok"

    gate = api.assess_global_release_gate(
        {
            "multi_region_ready": True,
            "rpo_minutes": 5,
            "rto_minutes": 15,
            "load_passed": True,
            "error_budget_status": "healthy",
            "cost_status": "ok",
            "security_signoff": True,
        }
    )
    assert gate["ready"] is True
