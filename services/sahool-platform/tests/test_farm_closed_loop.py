from datetime import date

from core.farm_closed_loop import (
    OperationEvent,
    ResourceUse,
    build_economic_state,
    build_inventory_projection,
    operation_event_to_ledger_payload,
)
from core.farm_costing import ProfitabilitySummary, VarianceLine
from core.farm_operations_ledger import LedgerSummary


def test_operation_event_to_ledger_payload_preserves_scope_and_resources():
    event = OperationEvent(
        event_id="evt1",
        tenant_id="tenant1",
        occurred_on=date(2026, 1, 1),
        operation_type="irrigation",
        season_id="wheat-2026",
        field_id="field1",
        cost_category="water",
        cost_amount=120,
        water_m3=900,
        energy_kwh=60,
        inputs=(ResourceUse("fertilizer", 20, "kg", 10, "urea"),),
    )
    payload = operation_event_to_ledger_payload(event)
    assert payload["autowrite_eligible"] is True
    assert payload["water"]["water_volume_m3"] == 900
    assert payload["energy"]["kwh"] == 60
    assert payload["inputs"][0]["inventory_item_id"] == "urea"
    assert payload["provenance"]["persisted"] is False


def test_operation_event_without_scope_is_not_autowrite_eligible():
    event = OperationEvent("evt2", "tenant1", date(2026, 1, 1), "other")
    payload = operation_event_to_ledger_payload(event)
    assert payload["autowrite_eligible"] is False
    assert payload["disabled_reason"] == "missing_field_or_production_unit_or_farm"


def test_inventory_projection_is_projection_only_and_flagged():
    lines = build_inventory_projection(
        [ResourceUse("seed", 100, "kg", 50, "seed-a")],
        sync_enabled=False,
    )
    assert lines[0].posting_mode == "projection_only"
    assert lines[0].direction == "outbound"
    assert lines[0].disabled_reason == "feature_flag_off"


def test_economic_state_derives_efficiency_without_prediction():
    summary = LedgerSummary(
        total_cost=1000,
        direct_cost=700,
        indirect_cost=300,
        currency="YER",
        cost_breakdown={"water": 200, "administration": 300},
        water_volume_m3=100,
        energy_kwh=100,
        diesel_liters=0,
        equipment_hours=0,
        labor_hours=0,
        input_quantities={},
        record_count=2,
        syncable_cost=0,
        control_only=True,
    )
    profit = ProfitabilitySummary("wheat-2026", 1500, 1000, 500, 33.3, 10, "ton", 100, 150)
    variances = [
        VarianceLine("wheat-2026", "water", "whole_season", 100, 130, 30, 30, "critical", "x")
    ]
    state = build_economic_state(
        "wheat-2026", summary, area_ha=2, profitability=profit, variances=variances
    )
    assert state.cost_per_ha == 500
    assert state.water_cost_per_m3 == 2
    assert state.energy_kwh_per_m3 == 1
    assert state.budget_variance_status == "critical"
    assert state.profitability_status == "profitable"
    assert state.provenance["prediction"] is False
    assert state.recommendations
