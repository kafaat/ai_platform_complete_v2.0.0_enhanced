from shared.precision_agriculture.phase6_intelligence import (
    compose_digital_twin_snapshot,
    compute_profitability_map,
    compute_yield_stability,
    extract_boundary,
    generate_management_zones,
    generate_prescription_map,
)

POLY = {
    "type": "Polygon",
    "coordinates": [[[44.0, 16.0], [44.01, 16.0], [44.01, 16.01], [44.0, 16.01], [44.0, 16.0]]],
}


def test_boundary_extraction_returns_valid_topology_and_area():
    out = extract_boundary(field_id="f1", seed_geometry=POLY, imagery_id="s2-a")
    assert out["field_id"] == "f1"
    assert out["topology"]["valid"] is True
    assert out["area_ha"] > 0
    assert out["confidence"] >= 0.9


def test_management_zones_assigns_all_samples_and_summarizes():
    samples = [
        {"id": "p1", "ndvi": 0.25, "soil_ec": 3.0, "yield": 2.0},
        {"id": "p2", "ndvi": 0.45, "soil_ec": 2.1, "yield": 3.5},
        {"id": "p3", "ndvi": 0.65, "soil_ec": 1.5, "yield": 5.0},
        {"id": "p4", "ndvi": 0.75, "soil_ec": 1.2, "yield": 5.8},
        {"id": "p5", "ndvi": 0.35, "soil_ec": 2.7, "yield": 2.8},
        {"id": "p6", "ndvi": 0.58, "soil_ec": 1.8, "yield": 4.4},
    ]
    out = generate_management_zones(samples, n_zones=3)
    assert len(out["features"]) == len(samples)
    assert sum(z["sample_count"] for z in out["zones"]) == len(samples)
    assert {z["label"] for z in out["zones"]} == {"stress", "medium", "high_potential"}


def test_prescription_map_uses_zone_multipliers():
    zones = [
        {"id": "a", "zone": 1, "label": "stress", "rate_multiplier": 0.75},
        {"id": "b", "zone": 3, "label": "high_potential", "rate_multiplier": 1.25},
    ]
    rx = generate_prescription_map(
        zones, crop="wheat", prescription_type="nitrogen", target_yield_t_ha=5
    )
    rates = [f["properties"]["rate"] for f in rx["features"]]
    assert rx["unit"] == "kgN/ha"
    assert rates[1] > rates[0]
    assert "ISOXML" in rx["exports"]


def test_yield_stability_classifies_stable_and_unstable():
    out = compute_yield_stability({"A": [5.0, 5.1, 5.2, 5.1], "B": [2.0, 5.0, 1.5, 6.0]})
    by_zone = {c["zone"]: c for c in out["classes"]}
    assert by_zone["A"]["label"] == "stable_high"
    assert by_zone["B"]["label"] == "unstable"


def test_profitability_map_labels_loss_area():
    out = compute_profitability_map(
        [{"zone": 1, "expected_yield_t_ha": 1.0, "rate_multiplier": 1.0}],
        market_price_per_t=200,
        variable_costs_per_ha={"water": 100, "fertilizer": 250},
    )
    assert out["features"][0]["label"] == "loss_area"
    assert out["features"][0]["profit_per_ha"] < 0


def test_digital_twin_snapshot_rolls_up_health_and_alerts():
    twin = compose_digital_twin_snapshot(
        farm={"farm_id": "farm-1", "name": "Al Jawf pilot"},
        fields=[{"field_id": "f1", "status": "stress"}, {"field_id": "f2", "status": "ok"}],
        equipment=[{"equipment_id": "pump-1", "status": "offline"}],
        weather={"risk": "high"},
        irrigation={"status": "deficit"},
    )
    assert twin["health_score"] < 100
    assert len(twin["alerts"]) == 2
    assert twin["field_count"] == 2
