"""W1-14 / W1-12 pure rules: one report currency, the season union, the governance context.

The SQL paths run against a live database in
``tests_v9/test_ledger_season_currency_governance_live_pg.py``; this file pins the pure rules
those paths rely on, with no database.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from core import farm_operations_ledger as ledger
from core import governance_farm_context as gov
from core.pest_escalation_flow import ERROR, evaluate_pesticide_guardrails

pytestmark = pytest.mark.unit


def test_season_scope_accepts_seasons_and_season_projects():
    sql, detail = ledger._TENANT_SCOPE_SQL["season"]
    assert "FROM seasons" in sql, "an agronomic season (seasons) is a ledger season (business-1)"
    assert "FROM farm_season_projects" in sql, "a ledger season project stays accepted"
    assert detail == "season_not_found_for_tenant", "the refusal code is unchanged"


def test_report_currency_is_the_requested_or_the_only_recorded_one():
    assert ledger.resolve_report_currency(["USD", "YER"], " usd ") == "USD", (
        "a requested currency wins and is normalised"
    )
    assert ledger.resolve_report_currency(["usd ", "USD"], None) == "USD", (
        "one recorded currency is the report currency"
    )
    assert ledger.resolve_report_currency([], None) is None, "nothing recorded: no currency"


def test_two_recorded_currencies_without_a_request_are_refused():
    with pytest.raises(ledger.MixedCurrencyError) as caught:
        ledger.resolve_report_currency(["YER", "USD", "yer"], None)
    assert caught.value.currencies == ["USD", "YER"], "the error names each currency once"
    assert caught.value.detail()["code"] == "mixed_currency", "a stable 409 code"


@pytest.mark.parametrize(
    ("amounts", "rows", "unpriced", "expected"),
    [
        ({"USD": 12.345}, 2, 0, (12.35, "ok")),
        ({}, 0, 0, (None, "no_recorded_rows")),
        ({"USD": 10.0}, 3, 1, (None, "unpriced_operations:1")),
        ({"YER": 9000.0}, 1, 0, (None, "currency_not_usd:YER")),
        ({"USD": 1.0, "YER": 2.0}, 2, 0, (None, "currency_not_usd:USD,YER")),
    ],
)
def test_usd_total_only_for_complete_usd_scopes(amounts, rows, unpriced, expected):
    assert gov.usd_total(amounts, rows=rows, unpriced=unpriced) == expected, (
        "a USD figure exists only for recorded, fully priced, USD-only amounts"
    )


def test_metered_volume_wins_over_the_ledger_depth_of_the_same_day():
    d1, d2 = date(2026, 6, 1), date(2026, 6, 2)
    water = gov.merge_season_water([(d1, 250.0)], [(d1, 99.0), (d2, 4.0)], 2.5)
    # 250 m3 metered on d1 + 4 mm x 10 x 2.5 ha on d2 = 350 m3 over 2.5 ha
    assert (water["total_m3"], water["m3_ha"]) == (350.0, 140.0), f"no double count: {water}"
    assert (water["metered_days"], water["ledger_days"]) == (1, 1), water


def test_an_unmeasured_day_makes_season_water_incomplete():
    d1, d2 = date(2026, 6, 1), date(2026, 6, 2)
    water = gov.merge_season_water([(d1, 100.0), (d2, None)], [], 2.0)
    assert water["m3_ha"] is None, "a day without a measured volume is not zero water"
    assert water["reason"] == "unmeasured_days:1", water


def test_no_water_records_is_not_zero_water():
    water = gov.merge_season_water([], [], 2.0)
    assert (water["m3_ha"], water["reason"]) == (None, "no_water_records"), water


def test_ledger_depth_needs_the_field_area():
    water = gov.merge_season_water([], [(date(2026, 6, 1), 5.0)], None)
    assert (water["m3_ha"], water["reason"]) == (None, "field_area_unavailable"), water


def test_water_source_vocabulary_maps_only_known_sources():
    assert gov.WATER_SOURCE_CLASS["well"] == "groundwater", "a well is groundwater"
    assert gov.WATER_SOURCE_CLASS["canal"] == "surface", "a canal is surface water"
    assert "rainfed" not in gov.WATER_SOURCE_CLASS, "rainfed is not a guardrails water source"


def test_farm_context_fn_refuses_another_tenant_and_the_gate_blocks():
    loop = asyncio.new_event_loop()
    try:
        fn = gov.threadsafe_farm_context_fn(loop, lambda: None, "tenant-a", None)
        with pytest.raises(PermissionError):
            fn("tenant-b", "f-1")
        verdict = evaluate_pesticide_guardrails(
            {"field_id": "f-1"}, tenant_id="tenant-b", user_id="7", farm_context_fn=fn
        )
    finally:
        loop.close()
    assert verdict["allowed"] is False and verdict["status"] == ERROR, (
        f"a farm context error is a block (fail closed): {verdict}"
    )


def test_unpriced_work_is_scoped_to_its_recorded_currency_and_the_rest_listed():
    """Unpriced work counts only in its own currency's report; other currencies are listed."""
    from unittest.mock import AsyncMock

    conn = AsyncMock()
    conn.fetch.return_value = []
    incomplete, other = asyncio.run(ledger.fetch_unpriced_work(conn, "t1", "s1", "USD"))
    assert (incomplete, other) == ([], []), "no rows, nothing incomplete or listed"
    own, others = (call.args for call in conn.fetch.await_args_list)
    assert own[1:] == ("t1", "s1", "USD") and "upper(trim(currency)) = $3" in own[0], (
        f"the report's unpriced work is filtered by its currency: {own}"
    )
    assert others[1:] == ("t1", "s1", "USD") and "IS DISTINCT FROM $3::text" in others[0], (
        f"unpriced work in other currencies is read apart: {others}"
    )
    _, coverage = ledger.priced_variance(
        [], [], [], [{"currency": "YER", "category": "seed", "unpriced_operations": 1}]
    )
    assert coverage["cost_coverage"] == "recorded_operations", (
        f"another currency's unpriced work does not change this report's coverage: {coverage}"
    )
    assert coverage["unpriced_in_other_currencies"][0]["currency"] == "YER", coverage


def test_money_filter_matches_one_currency_and_nothing_when_none():
    sql = ledger.money_filter_sql(3)
    assert sql == "upper(trim(currency)) IS NOT DISTINCT FROM $3::text", (
        f"money sums are filtered by one normalised currency parameter: {sql}"
    )
