from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import api.main
import pytest
from api.routers import farm_operations_ledger as router
from core.farm_costing import ActualCostLine, SeasonBudgetLine


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [False, True])
async def test_unpriced_work_does_not_create_budget_variance(monkeypatch, unknown):
    conn = AsyncMock()
    missing = (
        [{"stage": "planting", "category": "water", "unpriced_operations": 2}] if unknown else []
    )
    conn.fetch.return_value = missing

    @asynccontextmanager
    async def connection(user):
        yield conn

    budget = [
        SeasonBudgetLine(c, "s1", c, stage="planting", planned_cost=100) for c in ("seed", "water")
    ]
    actual = [ActualCostLine("op1", "s1", "seed", stage="planting", actual_cost=160)]
    monkeypatch.setattr(api.main, "_DB_POOL", object())
    monkeypatch.setattr(router, "_enabled", lambda: True)
    monkeypatch.setattr(router, "tenant_connection", connection)
    monkeypatch.setattr(
        router.ledger_core, "fetch_budget_and_actual", AsyncMock(return_value=(budget, actual))
    )
    response = await router.get_budget_variance(
        "s1", currency="USD", user=SimpleNamespace(tenant_id="t1")
    )
    assert response["unpriced_operations"] == (2 if unknown else 0)
    assert response["incomplete_categories"] == missing
    assert response["cost_coverage"] == ("partial" if unknown else "recorded_operations")
    assert {v["category"] for v in response["variance"]} == (
        {"seed"} if unknown else {"seed", "water"}
    )
    assert [r["code"] for r in response["recommendations"]] == ["cost_variance_planting_seed"]
    sql, *parameters = conn.fetch.await_args.args
    assert parameters == ["t1", "s1", "USD"]
    assert router.ledger_core.ACTUAL_OPERATION_SQL in sql


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


@pytest.mark.asyncio
async def test_mixed_currency_erp_projection_is_refused_not_summed(monkeypatch):
    from fastapi import HTTPException

    @asynccontextmanager
    async def connection(user):
        yield AsyncMock()

    actual = [
        ActualCostLine("op1", "s1", "water", actual_cost=10, currency="USD"),
        ActualCostLine("op2", "s1", "water", actual_cost=5000, currency="YER"),
    ]
    monkeypatch.setattr(api.main, "_DB_POOL", object())
    monkeypatch.setattr(router, "_enabled", lambda: True)
    monkeypatch.setattr(router, "tenant_connection", connection)
    monkeypatch.setattr(
        router.ledger_core, "fetch_budget_and_actual", AsyncMock(return_value=([], actual))
    )
    with pytest.raises(HTTPException) as err:
        await router.get_erp_projection("s1", user=SimpleNamespace(tenant_id="t1"))
    assert err.value.status_code == 409
