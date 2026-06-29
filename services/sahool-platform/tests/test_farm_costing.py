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
    normalize_budget_line,
    project_to_erp_lines,
)


def test_budget_line_derives_cost_from_quantity_and_unit_cost():
    line = normalize_budget_line(
        SeasonBudgetLine("b1", "wheat-2026", "seed", planned_quantity=180, planned_unit_cost=2)
    )
    assert line.planned_cost == 360


def test_variance_engine_detects_over_budget_by_stage_and_category():
    variances = compute_variances(
        [SeasonBudgetLine("b1", "wheat-2026", "water", stage="flowering", planned_cost=1000)],
        [ActualCostLine("op1", "wheat-2026", "water", stage="flowering", actual_cost=1300)],
    )
    assert len(variances) == 1
    assert variances[0].variance_amount == 300
    assert round(variances[0].variance_percent or 0, 1) == 30.0
    assert variances[0].severity == "critical"


def test_indirect_cost_allocation_per_hectare():
    allocated = allocate_indirect_costs(
        [IndirectCostPool("p1", "administration", 300, AllocationMethod.PER_HECTARE)],
        [ProductionUnitBasis("field-a", area_ha=10), ProductionUnitBasis("field-b", area_ha=20)],
    )
    assert allocated["field-a"]["administration"] == 100
    assert allocated["field-b"]["administration"] == 200


def test_profitability_and_erp_projection_are_summaries_not_double_entry():
    actual = [
        ActualCostLine("op1", "wheat-2026", "seed", actual_cost=500),
        ActualCostLine("op2", "wheat-2026", "water", actual_cost=300),
    ]
    profit = compute_profitability(
        "wheat-2026", revenue=1500, cost_lines=actual, yield_quantity=10, unit="ton"
    )
    assert profit.total_cost == 800
    assert profit.gross_margin == 700
    assert profit.cost_per_unit == 80
    erp = project_to_erp_lines(actual, cost_center="Farm Aljawf", project="wheat-2026")
    assert {x.category: x.amount for x in erp} == {"seed": 500, "water": 300}
    assert "financial projection" in erp[0].memo


def test_cost_recommendations_are_explainable_and_human_reviewed():
    variances = compute_variances(
        [SeasonBudgetLine("b1", "wheat-2026", "fertilizer", stage="vegetative", planned_cost=100)],
        [ActualCostLine("op1", "wheat-2026", "fertilizer", stage="vegetative", actual_cost=140)],
    )
    recs = generate_cost_recommendations(variances)
    assert recs
    assert recs[0].provenance["prediction"] is False
    assert recs[0].provenance["requires_human_review"] is True
