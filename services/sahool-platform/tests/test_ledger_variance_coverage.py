"""Pure ledger-variance coverage rules.

The routes (unpriced work under ``whole_season``, the currency scope, the mixed-currency ERP
refusal) are proven against the migrated ledger in
tests_v9/test_farm_ledger_cost_coverage_live_pg.py.
"""

from unittest.mock import AsyncMock

import pytest
from core.farm_costing import ActualCostLine, SeasonBudgetLine


def test_unpriced_category_is_dropped_across_budget_stages():
    """Ledger actuals carry no budget stage (``whole_season``); an unpriced operation in a
    category makes the planned stage line and the actual line of that category incomplete."""
    from core import farm_operations_ledger as ledger_core

    budget = [
        SeasonBudgetLine(c, "s1", c, stage="planting", planned_cost=100) for c in ("seed", "water")
    ]
    actual = [
        ActualCostLine("op1", "s1", "seed", stage="whole_season", actual_cost=160),
        ActualCostLine("op2", "s1", "water", stage="whole_season", actual_cost=10),
    ]
    missing = [{"stage": "whole_season", "category": "water", "unpriced_operations": 3}]
    variance, coverage = ledger_core.priced_variance(budget, actual, missing)
    assert {line.category for line in variance} == {"seed"}
    assert coverage == {
        "cost_coverage": "partial",
        "unpriced_operations": 3,
        "incomplete_categories": missing,
    }


@pytest.mark.asyncio
async def test_currency_scope_is_bound_as_a_parameter_and_optional():
    from core import farm_operations_ledger as ledger_core

    conn = AsyncMock()
    conn.fetch.return_value = []
    await ledger_core.fetch_budget_and_actual(conn, "t1", "s1")
    assert all(call.args[1:] == ("t1", "s1") for call in conn.fetch.await_args_list)
    assert all("currency) = $3" not in call.args[0] for call in conn.fetch.await_args_list)
    conn.fetch.reset_mock()
    await ledger_core.fetch_budget_and_actual(
        conn, "t1", "s1", ledger_core.normalize_currency(" usd ")
    )
    assert all(call.args[1:] == ("t1", "s1", "USD") for call in conn.fetch.await_args_list)
    assert all("upper(trim(currency)) = $3" in call.args[0] for call in conn.fetch.await_args_list)
    assert ledger_core.normalize_currency("  ") is None
