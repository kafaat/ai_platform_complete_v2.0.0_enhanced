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


def test_erp_currency_is_inherited_and_mixed_lines_cannot_be_summed():
    import pytest

    usd = ActualCostLine("op", "s", "water", actual_cost=10, currency="usd")
    yer = ActualCostLine("op2", "s", "water", actual_cost=5000, currency="YER")
    assert project_to_erp_lines([usd])[0].currency == "USD"
    with pytest.raises(ValueError, match="erp_projection_currency_mismatch"):
        project_to_erp_lines([usd, yer])
    with pytest.raises(ValueError, match="erp_projection_currency_mismatch"):
        project_to_erp_lines([usd], currency="YER")


def test_variance_rejects_mixed_currencies():
    import pytest

    with pytest.raises(ValueError, match="cost_scope_currency_mismatch"):
        compute_variances(
            [SeasonBudgetLine("b", "s", "water", planned_cost=5000, currency="YER")],
            [ActualCostLine("a", "s", "water", actual_cost=10, currency="USD")],
        )


def test_variance_rejects_mixed_seasons_even_with_same_currency():
    import pytest

    with pytest.raises(ValueError, match="cost_scope_season_mismatch"):
        compute_variances(
            [SeasonBudgetLine("b", "s1", "water", planned_cost=5000)],
            [ActualCostLine("a", "s2", "water", actual_cost=1000)],
        )


def test_profitability_rejects_cost_currency_different_from_revenue():
    import pytest

    with pytest.raises(ValueError, match="cost_scope_currency_mismatch"):
        compute_profitability(
            "s",
            revenue=5000,
            currency="YER",
            cost_lines=[ActualCostLine("a", "s", "water", actual_cost=10, currency="USD")],
        )


def test_profitability_rejects_cost_from_another_season():
    import pytest

    with pytest.raises(ValueError, match="cost_scope_season_mismatch"):
        compute_profitability(
            "s1",
            revenue=5000,
            cost_lines=[ActualCostLine("a", "s2", "water", actual_cost=1000)],
        )


def test_scope_accepts_normalized_currency_and_single_pass_iterators():
    budget = SeasonBudgetLine("b", "s", "water", planned_cost=5000, currency=" yer ")
    actual = ActualCostLine("a", "s", "water", actual_cost=6000, currency="YER")
    variances = compute_variances(iter([budget]), iter([actual]))
    assert variances[0].variance_amount == 1000
    profit = compute_profitability("s", revenue=8000, cost_lines=iter([actual]), currency="yer")
    assert profit.gross_margin == 2000
    assert profit.currency == "YER"


def test_profitability_without_a_named_currency_keeps_blank_currency_costs():
    # Devin on #1611: the ledger stores a blank currency as given, and the report resolves no
    # currency from blanks, so the route names none. Refusing those costs against a default
    # YER turned the profitability and economic-state reports into HTTP 500.
    blank = ActualCostLine("a", "s", "water", actual_cost=100, currency="")
    profit = compute_profitability("s", revenue=500, cost_lines=[blank])
    assert (profit.total_cost, profit.gross_margin, profit.currency) == (100, 400, "")
    assert compute_profitability("s", revenue=500, cost_lines=[]).currency == "YER"


def test_profitability_without_a_named_currency_still_refuses_a_mix():
    import pytest

    blank = ActualCostLine("a", "s", "water", actual_cost=100, currency="")
    yer = ActualCostLine("b", "s", "water", actual_cost=100, currency="YER")
    for lines in ([blank, yer], [yer, blank]):
        with pytest.raises(ValueError, match="cost_scope_currency_mismatch"):
            compute_profitability("s", revenue=500, cost_lines=lines)
    with pytest.raises(ValueError, match="cost_scope_currency_mismatch"):
        compute_profitability("s", revenue=500, cost_lines=[blank], currency="YER")
