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


def test_collaboration_events_reject_stale_revision_and_merge_safe_patches():
    fresh = build_collaboration_event(session_id="s1", field_id="f1", user_id="u1", event_type="geometry_patch", payload={"op": "move_vertex"}, current_revision=5)
    stale = build_collaboration_event(session_id="s1", field_id="f1", user_id="u2", event_type="geometry_patch", payload={"op": "delete_ring"}, current_revision=3)
    out = resolve_geometry_conflicts([stale, fresh], base_revision=4)
    assert len(out["accepted"]) == 1
    assert len(out["rejected"]) == 1
    assert out["merged_revision"] == 5


def test_ogc_manifest_exposes_expected_conformance_classes():
    manifest = ogc_conformance_manifest(service_url="https://api.sahool.local", enabled=["features", "tiles"])
    assert len(manifest["conformsTo"]) == 2
    assert manifest["endpoints"]["conformance"].endswith("/ogc/conformance")


def test_distributed_raster_plan_scales_workers_from_tile_volume():
    scenes = [{"scene_id": "s1", "field_id": "f1", "area_ha": 1000, "cloud_cover": 5}, {"scene_id": "s2", "field_id": "f2", "area_ha": 500, "cloud_cover": 45}]
    plan = plan_distributed_raster_processing(scenes, max_tiles_per_worker=40, preferred_runtime="dask")
    assert plan["task_count"] == 10
    assert plan["recommended_workers"] >= 2
    assert "gpu" in plan["queues"]


def test_digital_twin_scenario_returns_positive_delta_for_better_inputs():
    out = simulate_digital_twin_scenario(
        {"yield_t_ha": 4, "water_mm": 400, "cost_per_ha": 800, "market_price_per_t": 250},
        {"irrigation_change_pct": 10, "nitrogen_change_pct": 5, "stress_reduction_pct": 20},
    )
    assert out["delta"]["yield_t_ha"] > 0
    assert out["projection"]["profit_per_ha"] > out["baseline"]["profit_per_ha"]


def test_autonomous_recommendations_cover_stress_irrigation_weather_and_equipment():
    twin = {
        "farm": {"farm_id": "farm1"},
        "state": {
            "fields": [{"field_id": "f1", "status": "stress"}, {"field_id": "f2", "status": "critical"}],
            "irrigation": {"status": "deficit"},
            "weather": {"risk": "high"},
            "equipment": [{"equipment_id": "pump", "status": "offline"}],
        },
    }
    out = generate_autonomous_recommendations(twin)
    domains = {r["domain"] for r in out["recommendations"]}
    assert {"crop_health", "irrigation", "weather_operations", "equipment"}.issubset(domains)


def test_planet_scale_readiness_reports_blockers_until_thresholds_pass():
    fail = validate_planet_scale_readiness({"fields": 10, "tiles_per_day": 100, "concurrent_users": 20, "p95_tile_ms": 800, "p95_stac_ms": 900, "error_rate_pct": 3})
    assert fail["ready"] is False
    assert "field_scale" in fail["blockers"]
    ok = validate_planet_scale_readiness({"fields": 120000, "tiles_per_day": 12000000, "concurrent_users": 1500, "p95_tile_ms": 250, "p95_stac_ms": 300, "error_rate_pct": 0.2})
    assert ok["ready"] is True


def test_tile_cdn_policy_uses_private_cache_and_invalidation_events():
    policy = build_tile_cdn_policy(layer_id="ndvi", update_frequency="daily")
    assert policy["ttl_seconds"] == 86400
    assert "geometry_revision.committed" in policy["invalidation_events"]
