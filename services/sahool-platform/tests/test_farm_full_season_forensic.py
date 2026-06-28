from datetime import date

from core.farm_closed_loop import (
    OperationEvent,
    ResourceUse,
    build_economic_state,
    build_inventory_projection,
    operation_event_to_ledger_payload,
)
from core.farm_costing import (
    ActualCostLine,
    AllocationMethod,
    IndirectCostPool,
    ProductionUnitBasis,
    SeasonBudgetLine,
    allocate_indirect_costs,
    compute_profitability,
    compute_variances,
    generate_cost_recommendations,
    project_to_erp_lines,
)
from core.farm_operations_ledger import (
    EnergyRecord,
    EnergySource,
    EquipmentRecord,
    ExecutionMode,
    InputRecord,
    InputType,
    LaborRecord,
    LedgerCostLine,
    OperationLedgerRecord,
    OperationType,
    SyncStatus,
    WaterRecord,
    ai_feature_row,
    summarize_operational_records,
)


def test_full_wheat_season_forensic_trace_budget_actual_variance_profitability_ai_and_projection():
    """تتبع جنائي لموسم كامل: خطة → تنفيذ → سجلات → انحرافات → ربحية → توصيات → إسقاط ERP.

    الاختبار لا يتصل بقاعدة بيانات ولا ERP ولا مخزون. الهدف إثبات أن نواة الموسم كاملة
    ومغلقة الحلقة، وأن كل التوصيات/الإسقاطات معلنة المصدر ولا تكتب خارج SAHOOL.
    """
    tenant = "tenant-aljawf"
    season = "wheat-2026"
    field = "field-pivot-01"
    area_ha = 50.0

    budget = [
        SeasonBudgetLine(
            "b-prep", season, "land_preparation", stage="preparation", planned_cost=1200
        ),
        SeasonBudgetLine(
            "b-seed",
            season,
            "seed",
            stage="planting",
            planned_quantity=9000,
            unit="kg",
            planned_unit_cost=0.9,
        ),
        SeasonBudgetLine(
            "b-fert",
            season,
            "fertilizer",
            stage="vegetative",
            planned_quantity=12000,
            unit="kg",
            planned_unit_cost=0.65,
        ),
        SeasonBudgetLine(
            "b-water",
            season,
            "water",
            stage="flowering",
            planned_quantity=280000,
            unit="m3",
            planned_unit_cost=0.012,
        ),
        SeasonBudgetLine(
            "b-energy",
            season,
            "energy",
            stage="flowering",
            planned_quantity=18000,
            unit="kWh",
            planned_unit_cost=0.08,
        ),
        SeasonBudgetLine("b-pest", season, "pesticide", stage="flowering", planned_cost=1800),
        SeasonBudgetLine("b-harvest", season, "harvest", stage="harvest", planned_cost=5200),
        SeasonBudgetLine("b-transport", season, "transport", stage="transport", planned_cost=2400),
        SeasonBudgetLine("b-pack", season, "packaging", stage="packaging", planned_cost=900),
        SeasonBudgetLine("b-storage", season, "storage", stage="storage", planned_cost=600),
        SeasonBudgetLine(
            "b-admin", season, "administration", stage="whole_season", planned_cost=1800
        ),
    ]

    operations = [
        OperationLedgerRecord(
            "op-prep",
            tenant,
            date(2026, 10, 5),
            OperationType.LAND_PREPARATION,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.RENTED_EQUIPMENT,
            cost_lines=(LedgerCostLine("land_preparation", 1300),),
        ),
        OperationLedgerRecord(
            "op-plant",
            tenant,
            date(2026, 10, 20),
            OperationType.PLANTING,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("seed", 8200), LedgerCostLine("labor", 500)),
        ),
        OperationLedgerRecord(
            "op-fert",
            tenant,
            date(2026, 11, 30),
            OperationType.FERTILIZATION,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("fertilizer", 9100),),
        ),
        OperationLedgerRecord(
            "op-irrig",
            tenant,
            date(2027, 1, 15),
            OperationType.IRRIGATION,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("water", 4300), LedgerCostLine("energy", 2300)),
        ),
        OperationLedgerRecord(
            "op-pest",
            tenant,
            date(2027, 1, 25),
            OperationType.PEST_CONTROL,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.CONTRACTOR,
            cost_lines=(LedgerCostLine("pesticide", 2600),),
        ),
        OperationLedgerRecord(
            "op-harvest",
            tenant,
            date(2027, 4, 5),
            OperationType.HARVEST,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.CONTRACTOR,
            sync_status=SyncStatus.READY_FOR_SYNC,
            cost_lines=(LedgerCostLine("harvest", 5800),),
        ),
        OperationLedgerRecord(
            "op-post",
            tenant,
            date(2027, 4, 8),
            OperationType.TRANSPORT,
            season_id=season,
            field_id=field,
            execution_mode=ExecutionMode.MIXED,
            sync_status=SyncStatus.READY_FOR_SYNC,
            cost_lines=(
                LedgerCostLine("transport", 2600),
                LedgerCostLine("packaging", 1000),
                LedgerCostLine("storage", 700),
            ),
        ),
        OperationLedgerRecord(
            "op-admin",
            tenant,
            date(2027, 4, 15),
            OperationType.OTHER,
            season_id=season,
            farm_id="farm-aljawf",
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("administration", 2100),),
        ),
    ]

    water = [
        WaterRecord(
            "op-irrig",
            field,
            "well-03",
            "pivot-01",
            hours_operated=310,
            water_volume_m3=325000,
            measurement_method="meter",
        )
    ]
    energy = [
        EnergyRecord(
            "op-irrig",
            EnergySource.SOLAR,
            kwh=21500,
            hours_operated=310,
            well_id="well-03",
            pivot_id="pivot-01",
        )
    ]
    equipment = [
        EquipmentRecord("op-prep", "tractor-rented", hours_worked=42, fuel_liters=0),
        EquipmentRecord("op-irrig", "pivot-01", hours_worked=310),
        EquipmentRecord("op-harvest", "harvester-contractor", hours_worked=36),
    ]
    labor = [
        LaborRecord("op-plant", "crew-planting", workers_count=8, hours=64, wage_amount=500),
        LaborRecord("op-post", "crew-packaging", workers_count=6, hours=48, wage_amount=420),
    ]
    inputs = [
        InputRecord(
            "op-plant", InputType.SEED, "seed-wheat-certified", 9000, "kg", estimated_cost=8200
        ),
        InputRecord("op-fert", InputType.FERTILIZER, "urea", 14000, "kg", estimated_cost=9100),
        InputRecord(
            "op-pest", InputType.PESTICIDE, "fungicide-preventive", 85, "liter", estimated_cost=2600
        ),
        InputRecord("op-post", InputType.PACKAGING, "bags-50kg", 9000, "unit", estimated_cost=1000),
    ]

    summary = summarize_operational_records(
        operations, water=water, energy=energy, equipment=equipment, labor=labor, inputs=inputs
    )
    assert summary.record_count == 8
    assert summary.total_cost == 40500
    assert summary.direct_cost == 38400
    assert summary.indirect_cost == 2100
    assert summary.water_volume_m3 == 325000
    assert summary.energy_kwh == 21500
    assert summary.equipment_hours == 388
    assert summary.labor_hours == 112
    assert summary.input_quantities == {
        "seed:kg": 9000,
        "fertilizer:kg": 14000,
        "pesticide:liter": 85,
        "packaging:unit": 9000,
    }
    assert summary.syncable_cost == 10100

    actuals = [
        ActualCostLine(
            "op-prep", season, "land_preparation", stage="preparation", actual_cost=1300
        ),
        ActualCostLine("op-plant-seed", season, "seed", stage="planting", actual_cost=8200),
        ActualCostLine("op-plant-labor", season, "labor", stage="planting", actual_cost=500),
        ActualCostLine("op-fert", season, "fertilizer", stage="vegetative", actual_cost=9100),
        ActualCostLine("op-irrig-water", season, "water", stage="flowering", actual_cost=4300),
        ActualCostLine("op-irrig-energy", season, "energy", stage="flowering", actual_cost=2300),
        ActualCostLine("op-pest", season, "pesticide", stage="flowering", actual_cost=2600),
        ActualCostLine("op-harvest", season, "harvest", stage="harvest", actual_cost=5800),
        ActualCostLine("op-transport", season, "transport", stage="transport", actual_cost=2600),
        ActualCostLine("op-pack", season, "packaging", stage="packaging", actual_cost=1000),
        ActualCostLine("op-storage", season, "storage", stage="storage", actual_cost=700),
        ActualCostLine(
            "op-admin", season, "administration", stage="whole_season", actual_cost=2100
        ),
    ]
    variances = compute_variances(budget, actuals)
    by_key = {(v.stage, v.category): v for v in variances}
    assert by_key[("flowering", "water")].severity == "critical"
    assert round(by_key[("flowering", "water")].variance_percent or 0, 1) == 28.0
    assert by_key[("vegetative", "fertilizer")].severity == "watch"
    assert by_key[("flowering", "pesticide")].severity == "critical"
    assert by_key[("planting", "labor")].planned_cost == 0
    assert by_key[("planting", "labor")].explanation.startswith("تكلفة فعلية بدون بند موازنة")

    recommendations = generate_cost_recommendations(variances)
    assert {r.code for r in recommendations} >= {
        "cost_variance_flowering_water",
        "cost_variance_flowering_pesticide",
    }
    assert all(r.provenance["requires_human_review"] is True for r in recommendations)
    assert all(r.provenance["prediction"] is False for r in recommendations)

    profit = compute_profitability(
        season, revenue=72000, cost_lines=actuals, yield_quantity=210, unit="ton"
    )
    assert profit.total_cost == 40500
    assert profit.gross_margin == 31500
    assert profit.cost_per_unit == 192.85714285714286
    assert profit.revenue_per_unit == 342.85714285714283

    state = build_economic_state(
        season, summary, area_ha=area_ha, profitability=profit, variances=variances
    )
    assert state.cost_per_ha == 810
    assert state.water_m3_per_ha == 6500
    assert round(state.energy_kwh_per_m3, 4) == 0.0662
    assert state.budget_variance_status == "critical"
    assert state.profitability_status == "profitable"
    assert state.provenance == {
        "source": "farm_operations_ledger",
        "prediction": False,
        "canonical_state_write": False,
    }

    ai_row = ai_feature_row(summary, area_ha=area_ha)
    assert ai_row["cost_per_ha"] == 810
    assert ai_row["water_m3_per_ha"] == 6500
    assert ai_row["kwh_per_m3"] == summary.energy_kwh / summary.water_volume_m3
    assert ai_row["provenance"]["prediction"] is False

    inv_projection = build_inventory_projection(
        [
            ResourceUse("seed", 9000, "kg", 8200, "seed-wheat-certified"),
            ResourceUse("fertilizer", 14000, "kg", 9100, "urea"),
        ],
        sync_enabled=False,
    )
    assert all(x.posting_mode == "projection_only" for x in inv_projection)
    assert all(x.disabled_reason == "feature_flag_off" for x in inv_projection)

    erp_lines = project_to_erp_lines(actuals, cost_center="Farm Aljawf", project=season)
    assert sum(x.amount for x in erp_lines) == 40500
    assert all("financial projection" in x.memo for x in erp_lines)

    allocated = allocate_indirect_costs(
        [IndirectCostPool("admin", "administration", 2100, AllocationMethod.PER_HECTARE)],
        [
            ProductionUnitBasis("pivot-01", area_ha=50),
            ProductionUnitBasis("orchard-01", area_ha=20),
        ],
    )
    assert allocated["pivot-01"]["administration"] == 1500
    assert allocated["orchard-01"]["administration"] == 600

    event_payload = operation_event_to_ledger_payload(
        OperationEvent(
            "evt-irrigation-finish",
            tenant,
            date(2027, 1, 15),
            "irrigation",
            season_id=season,
            field_id=field,
            cost_category="water",
            cost_amount=4300,
            water_m3=325000,
            energy_kwh=21500,
            inputs=(ResourceUse("fertilizer", 14000, "kg", 9100, "urea"),),
            source="forensic_season_test",
        )
    )
    assert event_payload["autowrite_eligible"] is True
    assert event_payload["provenance"]["persisted"] is False
    assert event_payload["water"]["water_volume_m3"] == 325000
    assert event_payload["inputs"][0]["inventory_item_id"] == "urea"
