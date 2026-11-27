"""Farm ledger seasons, one-currency reports and the governance farm context (live PG).

W1-14 (business-1, business-2):
- a budget, an operation or a revenue sent with an agronomic season (``seasons``, the table
  farmers write) is accepted; before, the tenant check read only ``farm_season_projects`` (no
  writer) and the v100-v102 foreign keys refused the row. v281 keeps the integrity check in the
  database as a trigger over the same union the simple farm book uses;
- amounts in two currencies are never summed under one label: variance, profitability and the
  summary answer 409 unless ``?currency=`` names one, and the budget read gives one total per
  currency.

W1-12 (x-3, airuntime-3): ``build_governance_farm_context`` reads the tenant's recorded costs,
revenue, water and field facts with provenance, and the pesticide gate receives them.

The router and the builder run against the real schema through a pool that runs as a
NOBYPASSRLS role, so tenant isolation applies exactly as in production.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("LEDGER_SEASON_CURRENCY_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")
_require("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
TABLES = (
    "seasons",
    "fields",
    "farm_season_budget_lines",
    "farm_operation_ledger",
    "farm_revenue_records",
    "farm_water_records",
    "water_ledger",
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
        if (
            await conn.fetchval(
                "SELECT 1 FROM pg_proc WHERE proname = 'farm_ledger_assert_season_ref'"
            )
            is None
        ):
            return "schema not migrated (v281 farm_ledger_assert_season_ref missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"LEDGER_SEASON_CURRENCY_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import farm_operations_ledger

    return main, farm_operations_ledger


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{uuid.uuid4().hex[:8]}", tenant_id=tenant, role=UserRole.OWNER, name_ar="مالك"
    )


class Live:
    """Setup connection + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        tag = uuid.uuid4().hex[:10]
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        self.field_id = f"gov-field-{tag}"
        self.other_field = f"gov-ofield-{tag}"
        self.season_id = f"gov-season-{tag}"  # a `seasons` row, not a season project
        self.other_season = f"gov-oseason-{tag}"  # another tenant's `seasons` row
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"gov_rls_{uuid.uuid4().hex[:10]}"
            await self.owner.execute(
                f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
                f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
            )
        role = self.role

        async def setup(conn):
            if role:
                await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3, setup=setup)
        today = date.today()
        for field, tenant, season in (
            (self.field_id, self.tenant, self.season_id),
            (self.other_field, self.other_tenant, self.other_season),
        ):
            await self.as_tenant(
                tenant,
                "INSERT INTO fields (field_id, name, tenant_id, area_ha, water_source)"
                " VALUES ($1, $1, $2::uuid, 2.5, 'well')",
                field,
                tenant,
            )
            await self.as_tenant(
                tenant,
                "INSERT INTO seasons (season_id, tenant_id, field_id, sowing_date, status)"
                " VALUES ($1, $2::uuid, $3, $4, 'active')",
                season,
                tenant,
                field,
                today - timedelta(days=30),
            )
        return self

    async def as_tenant(self, tenant, sql, *args):
        """Run one statement under the tenant's GUC (the role may be NOBYPASSRLS)."""
        async with self.owner.transaction():
            await self.owner.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            if sql.lstrip().upper().startswith("SELECT"):
                return await self.owner.fetchval(sql, *args)
            return await self.owner.execute(sql, *args)

    async def operation(self, cost, currency="USD", *, tenant=None, season=None, days_ago=1):
        op_id = f"op-{uuid.uuid4().hex[:12]}"
        await self.as_tenant(
            tenant or self.tenant,
            """INSERT INTO farm_operation_ledger
                   (operation_id, tenant_id, season_id, field_id, operation_type, operation_date,
                    status, cost_amount, cost_category, currency)
               VALUES ($1, $2::uuid, $3, $4, 'irrigation', $5, 'completed', $6, 'water', $7)""",
            op_id,
            tenant or self.tenant,
            season or self.season_id,
            self.field_id if (tenant or self.tenant) == self.tenant else self.other_field,
            date.today() - timedelta(days=days_ago),
            cost,
            currency,
        )
        return op_id

    async def revenue(self, amount, currency="USD", *, tenant=None, season=None):
        await self.as_tenant(
            tenant or self.tenant,
            """INSERT INTO farm_revenue_records
                   (revenue_id, tenant_id, season_id, revenue_date, amount, currency)
               VALUES ($1, $2::uuid, $3, $4, $5, $6)""",
            f"rev-{uuid.uuid4().hex[:12]}",
            tenant or self.tenant,
            season or self.season_id,
            date.today() - timedelta(days=2),
            amount,
            currency,
        )

    async def budget(self, planned_cost, currency="USD"):
        await self.as_tenant(
            self.tenant,
            """INSERT INTO farm_season_budget_lines
                   (budget_line_id, tenant_id, season_id, category, planned_cost, currency)
               VALUES ($1, $2::uuid, $3, 'water', $4, $5)""",
            f"b-{uuid.uuid4().hex[:12]}",
            self.tenant,
            self.season_id,
            planned_cost,
            currency,
        )

    async def __aexit__(self, *exc):
        o = self.owner
        tenants = [self.tenant, self.other_tenant]
        try:
            for table in (
                "water_ledger",
                "farm_water_records",
                "farm_revenue_records",
                "farm_season_budget_lines",
                "farm_operation_ledger",
                "seasons",
                "fields",
            ):
                for tenant in tenants:  # restricted role: each tenant's rows under its own GUC
                    async with o.transaction():
                        await o.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
                        await o.execute(f"DELETE FROM {table} WHERE tenant_id = $1::uuid", tenant)
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()


def _run(monkeypatch, case):
    main, router = _platform()
    monkeypatch.setenv("FEATURE_FARM_OPERATIONS_LEDGER", "true")

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, router)

    asyncio.run(body())


# ── W1-14: a `seasons` id is a ledger season ─────────────────────────────────────────────


def test_budget_post_with_a_seasons_table_id_is_created(monkeypatch):
    async def case(live, router):
        route = next(r for r in router.router.routes if r.path == "/api/v1/farm-ledger/budgets")
        assert route.status_code == 201, "the budget POST answers 201 Created"
        req = router.BudgetLinesIn(
            lines=[router.BudgetLineIn(season_id=live.season_id, category="seed", planned_cost=90)]
        )
        out = await router.upsert_season_budget_lines(req, user=_user(live.tenant))
        assert [s["planned_cost"] for s in out["saved"]] == [90], (
            f"a budget line on a seasons-table season must be saved, got {out}"
        )
        stored = await live.as_tenant(
            live.tenant,
            "SELECT count(*) FROM farm_season_budget_lines WHERE season_id = $1",
            live.season_id,
        )
        assert stored == 1, "the budget line is persisted against the seasons-table id"

    _run(monkeypatch, case)


def test_budget_post_with_an_unknown_or_foreign_season_is_404_not_503(monkeypatch):
    from fastapi import HTTPException

    async def case(live, router):
        for season in (f"missing-{uuid.uuid4().hex[:6]}", live.other_season):
            req = router.BudgetLinesIn(
                lines=[router.BudgetLineIn(season_id=season, category="seed", planned_cost=1)]
            )
            with pytest.raises(HTTPException) as caught:
                await router.upsert_season_budget_lines(req, user=_user(live.tenant))
            assert caught.value.status_code == 404, (
                f"season {season!r} is not this tenant's: 404, not a database outage (503); "
                f"got {caught.value.status_code} {caught.value.detail}"
            )

    _run(monkeypatch, case)


def test_operation_and_revenue_routes_accept_a_seasons_table_id(monkeypatch):
    async def case(live, router):
        user = _user(live.tenant)
        await router.create_revenue_record(
            router.RevenueRecordIn(
                season_id=live.season_id, revenue_date=date.today(), amount=10, currency="USD"
            ),
            user=user,
        )
        stored = await live.as_tenant(
            live.tenant,
            "SELECT count(*) FROM farm_revenue_records WHERE season_id = $1",
            live.season_id,
        )
        assert stored == 1, "a revenue record on a seasons-table season is persisted"

    _run(monkeypatch, case)


def test_the_database_refuses_an_unknown_or_foreign_season(monkeypatch):
    async def case(live, router):
        await live.operation(5)  # own `seasons` row: accepted by the v281 trigger
        for season in (f"missing-{uuid.uuid4().hex[:6]}", live.other_season):
            with pytest.raises(asyncpg.ForeignKeyViolationError) as caught:
                await live.operation(5, season=season)
            assert "season_not_found_for_tenant" in str(caught.value), (
                f"the trigger names the refusal for {season!r}: {caught.value}"
            )
        async with live.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", live.tenant)
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    """INSERT INTO farm_season_budget_lines
                           (budget_line_id, tenant_id, season_id, category, planned_cost)
                       VALUES ($1, $2::uuid, $3, 'x', 1)""",
                    f"b-{uuid.uuid4().hex[:8]}",
                    live.tenant,
                    live.other_season,
                )

    _run(monkeypatch, case)


# ── W1-14: one report, one currency ──────────────────────────────────────────────────────


def test_mixed_currency_variance_and_profitability_are_409_unless_one_is_named(monkeypatch):
    from fastapi import HTTPException

    async def case(live, router):
        user = _user(live.tenant)
        await live.budget(100, "USD")
        await live.operation(40, "USD")
        await live.operation(9000, "YER")
        await live.revenue(500, "USD")
        await live.revenue(70000, "YER")
        for call in (
            lambda: router.get_budget_variance(live.season_id, user=user),
            lambda: router.get_season_profitability(live.season_id, user=user),
        ):
            with pytest.raises(HTTPException) as caught:
                await call()
            assert caught.value.status_code == 409, "two currencies are never summed"
            assert caught.value.detail["currencies"] == ["USD", "YER"], (
                f"the 409 names the currencies found: {caught.value.detail}"
            )
        out = await router.get_season_profitability(live.season_id, currency="usd", user=user)
        profit = out["profitability"]
        assert (profit["currency"], profit["revenue"], profit["total_cost"]) == (
            "USD",
            500,
            40,
        ), f"a named currency reports only its own amounts: {profit}"
        variance = await router.get_budget_variance(live.season_id, currency="YER", user=user)
        assert [v["actual_cost"] for v in variance["variance"]] == [9000], (
            f"the YER variance holds only YER actuals: {variance['variance']}"
        )

    _run(monkeypatch, case)


def test_single_currency_season_reports_in_that_currency_not_a_default_yer(monkeypatch):
    async def case(live, router):
        await live.operation(40, "USD")
        await live.revenue(500, "USD")
        out = await router.get_season_profitability(live.season_id, user=_user(live.tenant))
        assert out["profitability"]["currency"] == "USD", (
            f"a USD-only season is labelled USD, not the YER default: {out['profitability']}"
        )

    _run(monkeypatch, case)


def test_budget_read_gives_one_block_per_currency(monkeypatch):
    async def case(live, router):
        await live.budget(100, "USD")
        await live.budget(30000, "YER")
        out = await router.get_season_budget(live.season_id, user=_user(live.tenant))
        assert out["totals_by_currency"] == {"USD": 100, "YER": 30000}, (
            f"one total per currency: {out}"
        )
        assert out["total_planned_cost"] is None and out["currency"] is None, (
            "no single total across two currencies"
        )

    _run(monkeypatch, case)


def test_mixed_currency_summary_is_409(monkeypatch):
    from fastapi import HTTPException

    async def case(live, router):
        user = _user(live.tenant)
        await live.operation(40, "USD")
        await live.operation(9000, "YER")
        with pytest.raises(HTTPException) as caught:
            await router.farm_ledger_summary(
                date_from=None, date_to=None, season_id=live.season_id, user=user
            )
        assert caught.value.status_code == 409, "the summary never sums two currencies"
        out = await router.farm_ledger_summary(
            date_from=None, date_to=None, season_id=live.season_id, currency="USD", user=user
        )
        assert (out["summary"]["currency"], out["summary"]["total_cost"]) == ("USD", 40), (
            f"named currency summary: {out['summary']}"
        )

    _run(monkeypatch, case)


async def _unpriced_operation(live, category="water"):
    """A completed operation with no cost and the column default currency (YER)."""
    await live.as_tenant(
        live.tenant,
        """INSERT INTO farm_operation_ledger
               (operation_id, tenant_id, season_id, field_id, operation_type, operation_date,
                status, cost_category)
           VALUES ($1, $2::uuid, $3, $4, 'irrigation', $5, 'completed', $6)""",
        f"op-{uuid.uuid4().hex[:12]}",
        live.tenant,
        live.season_id,
        live.field_id,
        date.today() - timedelta(days=1),
        category,
    )


def test_unpriced_work_counts_in_the_report_of_the_currency_it_is_recorded_in(monkeypatch):
    """Unpriced work affects completeness only in its own currency's report.

    tests_v9/test_farm_ledger_cost_coverage_live_pg.py holds the other half (an unpriced
    operation in another currency leaves this currency's category priced). Here: the USD
    report keeps unpriced USD work incomplete, and lists unpriced work recorded in YER (the
    column default when a writer omits the currency) beside it instead of hiding it.
    """

    async def case(live, router):
        user = _user(live.tenant)
        await live.budget(100, "USD")
        await live.operation(40, "USD")
        await live.operation(None, "USD")  # unpriced USD work: the USD water line is incomplete
        await _unpriced_operation(live, "seed")  # unpriced, column default currency (YER)
        for currency in (None, "USD"):
            out = await router.get_budget_variance(live.season_id, currency=currency, user=user)
            assert out["currency"] == "USD", f"the priced amounts are USD: {out}"
            assert out["cost_coverage"] == "partial" and out["unpriced_operations"] == 1, (
                f"only the USD-recorded unpriced operation counts in the USD report: {out}"
            )
            assert out["variance"] == [], (
                f"no -60% underspend is reported for a category with unpriced USD work: {out}"
            )
            assert out["unpriced_in_other_currencies"] == [
                {"currency": "YER", "category": "seed", "unpriced_operations": 1}
            ], f"unpriced work recorded in YER is listed beside the USD report: {out}"
        yer = await router.get_budget_variance(live.season_id, currency="YER", user=user)
        assert yer["incomplete_categories"] == [
            {"stage": "whole_season", "category": "seed", "unpriced_operations": 1}
        ], f"the YER report is where the YER-recorded unpriced work belongs: {yer}"
        assert yer["unpriced_in_other_currencies"] == [
            {"currency": "USD", "category": "water", "unpriced_operations": 1}
        ], f"and the YER report lists the USD one beside it: {yer}"

    _run(monkeypatch, case)


def test_economic_state_is_one_currency_or_409(monkeypatch):
    """Review finding: business-2 on the route the season profitability card reads."""
    from fastapi import HTTPException

    async def case(live, router):
        user = _user(live.tenant)
        await live.operation(40, "USD")
        await live.operation(9000, "YER")
        await live.revenue(500, "USD")
        with pytest.raises(HTTPException) as caught:
            await router.get_economic_state(live.season_id, user=user)
        assert caught.value.status_code == 409, "economic state never sums two currencies"
        assert caught.value.detail["currencies"] == ["USD", "YER"], caught.value.detail
        out = await router.get_economic_state(live.season_id, currency="usd", user=user)
        state = out["economic_state"]
        assert out["currency"] == "USD", f"the named currency labels the state: {out}"
        assert state["total_cost"] == 40, f"USD costs only: {state}"
        assert state["revenue"] == 500, f"USD revenue only: {state}"
        assert state["gross_margin"] == 460, f"no made-up loss: {state}"
        assert state["profitability_status"] == "profitable", f"no made-up loss: {state}"

    _run(monkeypatch, case)


def test_economic_state_drops_variance_lines_with_unpriced_work(monkeypatch):
    async def case(live, router):
        await live.budget(100, "USD")
        await live.operation(40, "USD")
        await live.operation(None, "USD")  # unpriced USD work
        await _unpriced_operation(live, "seed")  # unpriced, recorded in the default YER
        out = await router.get_economic_state(live.season_id, user=_user(live.tenant))
        assert out["currency"] == "USD", out
        assert out["cost_coverage"] == "partial", f"unpriced work is reported: {out}"
        assert out["unpriced_operations"] == 1, f"only USD-recorded unpriced work counts: {out}"
        assert out["unpriced_in_other_currencies"] == [
            {"currency": "YER", "category": "seed", "unpriced_operations": 1}
        ], f"YER-recorded unpriced work is listed, not counted: {out}"
        assert out["economic_state"]["budget_variance_status"] != "critical", (
            f"a missing cost is not a critical underspend: {out['economic_state']}"
        )

    _run(monkeypatch, case)


def test_named_currency_summary_still_counts_every_operation(monkeypatch):
    async def case(live, router):
        user = _user(live.tenant)
        await live.operation(40, "USD")
        await live.operation(9000, "YER")
        out = await router.farm_ledger_summary(
            date_from=None, date_to=None, season_id=live.season_id, currency="USD", user=user
        )
        assert out["summary"]["operation_count"] == 2, (
            f"the currency filters money, not the operations counted: {out['summary']}"
        )
        assert out["summary"]["cost_breakdown"] == {"water": 40}, out["summary"]

    _run(monkeypatch, case)


def test_a_bypassing_role_with_another_tenants_context_is_still_season_checked(monkeypatch):
    """Review finding: RLS WITH CHECK does not run for a role that bypasses it."""

    async def case(live, router):
        admin = await asyncpg.connect(os.getenv("TEST_DATABASE_ADMIN_URL") or DSN)
        try:
            if not await admin.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            ):
                if _CERTIFICATION_REQUIRED:
                    raise AssertionError("certifying run needs a role that bypasses RLS")
                pytest.skip("declared skip (not a pass): no role that bypasses RLS")
            insert = """INSERT INTO farm_operation_ledger
                   (operation_id, tenant_id, season_id, field_id, operation_type, operation_date,
                    status)
               VALUES ($1, $2::uuid, $3, $4, 'irrigation', CURRENT_DATE, 'completed')"""
            async with admin.transaction():
                await admin.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", live.tenant
                )
                with pytest.raises(asyncpg.ForeignKeyViolationError) as caught:
                    await admin.execute(
                        insert,
                        f"op-{uuid.uuid4().hex[:8]}",
                        live.other_tenant,
                        live.season_id,  # tenant A's season on a tenant B row
                        live.other_field,
                    )
                assert "season_not_found_for_tenant" in str(caught.value), caught.value
            async with admin.transaction():
                await admin.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", live.tenant
                )
                await admin.execute(
                    insert,
                    f"op-{uuid.uuid4().hex[:8]}",
                    live.other_tenant,
                    live.other_season,
                    live.other_field,
                )
                ctx = await admin.fetchval("SELECT current_setting('app.current_tenant', true)")
                assert ctx == live.tenant, "the trigger restores the caller's tenant context"
        finally:
            await admin.close()

    _run(monkeypatch, case)


def test_legacy_tenant_guc_writes_are_season_checked_like_current_tenant(monkeypatch):
    """Review finding: RLS reads sahool_effective_tenant_id() (app.current_tenant, else the
    legacy app.tenant_id); the trigger must read the same context.

    A NOBYPASSRLS writer with only app.tenant_id set to tenant A, writing a row for tenant B,
    is refused by the WITH CHECK policy (42501) whether or not B has that season: the trigger
    does not answer first with 23503 and so does not reveal B's season ids. An own-tenant
    write under app.tenant_id is checked as usual.
    """

    async def case(live, router):
        insert = """INSERT INTO farm_operation_ledger
               (operation_id, tenant_id, season_id, field_id, operation_type, operation_date,
                status)
           VALUES ($1, $2::uuid, $3, $4, 'irrigation', CURRENT_DATE, 'completed')"""
        async with live.pool.acquire() as conn:
            assert not await conn.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            ), "the pool runs as a NOBYPASSRLS role"
            for season in (f"missing-{uuid.uuid4().hex[:6]}", live.other_season):
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", live.tenant)
                    with pytest.raises(asyncpg.InsufficientPrivilegeError) as caught:
                        await conn.execute(
                            insert,
                            f"op-{uuid.uuid4().hex[:8]}",
                            live.other_tenant,
                            season,
                            live.other_field,
                        )
                    assert "row-level security" in str(caught.value), (
                        f"another tenant's row is refused by RLS, not by a season lookup "
                        f"({season!r}): {caught.value}"
                    )
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", live.tenant)
                with pytest.raises(asyncpg.ForeignKeyViolationError) as caught:
                    await conn.execute(
                        insert,
                        f"op-{uuid.uuid4().hex[:8]}",
                        live.tenant,
                        live.other_season,  # tenant B's season on an own-tenant row
                        live.field_id,
                    )
                assert "season_not_found_for_tenant" in str(caught.value), caught.value
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", live.tenant)
                await conn.execute(
                    insert, f"op-{uuid.uuid4().hex[:8]}", live.tenant, live.season_id, live.field_id
                )
                ctx = await conn.fetchval("SELECT current_setting('app.current_tenant', true)")
                assert not ctx, f"the trigger leaves app.current_tenant as it found it: {ctx!r}"

    _run(monkeypatch, case)


# ── W1-12: the governance farm context ───────────────────────────────────────────────────


async def _context(live, **kw):
    from api.main import tenant_connection
    from core.farm_operations_ledger import build_governance_farm_context

    async with tenant_connection(_user(live.tenant)) as conn:
        return await build_governance_farm_context(conn, live.tenant, **kw)


def test_recorded_costs_revenue_and_water_reach_the_farm_context_with_their_source(monkeypatch):
    async def case(live, router):
        op = await live.operation(120.5, "USD", days_ago=3)
        await live.operation(79.5, "USD", days_ago=200, season=live.season_id)
        await live.revenue(1000, "USD")
        # another tenant's amounts never enter this tenant's figures
        await live.operation(99999, "USD", tenant=live.other_tenant, season=live.other_season)
        await live.revenue(99999, "USD", tenant=live.other_tenant, season=live.other_season)
        d1, d2 = date.today() - timedelta(days=3), date.today() - timedelta(days=4)
        await live.as_tenant(
            live.tenant,
            """INSERT INTO farm_water_records
                   (tenant_id, operation_id, record_date, field_id, water_volume_m3)
               VALUES ($1::uuid, $2, $3, $4, 250)""",
            live.tenant,
            op,
            d1,
            live.field_id,
        )
        for day, mm in ((d1, 99.0), (d2, 4.0)):  # d1 is metered: its ledger depth is not added
            await live.as_tenant(
                live.tenant,
                """INSERT INTO water_ledger (tenant_id, field_id, ledger_date, irrigation_mm)
                   VALUES ($1::uuid, $2, $3, $4)""",
                live.tenant,
                live.field_id,
                day,
                mm,
            )

        farm = await _context(live, field_id=live.field_id, season_id=live.season_id)

        assert farm["annual_costs_usd"] == 200.0, f"trailing-year USD costs: {farm}"
        assert farm["annual_revenue_usd"] == 1000.0, f"trailing-year USD revenue: {farm}"
        assert farm["season_costs_usd"] == 200.0 and farm["season_revenue_usd"] == 1000.0, (
            f"season economics from the ledger: {farm}"
        )
        assert (farm["field_area_ha"], farm["water_source"]) == (2.5, "groundwater"), (
            f"area and water source from fields: {farm}"
        )
        # 250 m3 metered + 4 mm x 10 x 2.5 ha = 350 m3 over 2.5 ha
        assert farm["season_water_used_m3_ha"] == 140.0, f"season water: {farm['season_water']}"
        prov = farm["provenance"]
        assert prov["annual_costs_usd"]["source"] == "farm_operation_ledger", prov
        assert prov["annual_revenue_usd"]["source"] == "farm_revenue_records", prov
        assert prov["season_costs_usd"]["season_source"] == "seasons", prov
        assert prov["field_area_ha"] == {
            "source": "fields",
            "field_id": live.field_id,
            "column": "area_ha",
        }, prov
        assert "water_ledger" in prov["season_water_used_m3_ha"]["source"], prov
        assert farm["unavailable"]["cash_reserve_usd"] == "no_server_source", (
            "no server source for cash reserve: absent, never invented"
        )
        assert "cash_reserve_usd" not in farm, "an unsourced fact is absent, not zero"

    _run(monkeypatch, case)


def test_non_usd_or_unpriced_amounts_are_not_converted_or_completed(monkeypatch):
    async def case(live, router):
        await live.operation(9000, "YER")
        await live.operation(None, "USD")  # completed, unpriced
        await live.revenue(70000, "YER")
        farm = await _context(live, field_id=live.field_id, season_id=live.season_id)
        for key in ("annual_costs_usd", "annual_revenue_usd", "season_costs_usd"):
            assert key not in farm, f"{key} must not be invented from YER or unpriced work"
        assert farm["unavailable"]["annual_revenue_usd"] == "currency_not_usd:YER", farm
        assert farm["unavailable"]["annual_costs_usd"] == "unpriced_operations:1", farm
        assert farm["season_economics"]["costs_by_currency"] == {"YER": 9000}, farm
        assert "season_water_used_m3_ha" not in farm, "no water records is not zero water"

    _run(monkeypatch, case)


def test_the_pesticide_gate_receives_the_recorded_economics(monkeypatch):
    """End to end through the W0-01 gate: only the unsourced cash reserve is still missing."""
    from api.main import tenant_connection
    from core.farm_operations_ledger import threadsafe_farm_context_fn
    from core.pest_escalation_flow import EVIDENCE_UNAVAILABLE, evaluate_pesticide_guardrails

    ctx = {
        "field_id": None,
        "season_id": None,
        "chemical": "Spinosad",  # server-side flow data in production; set here for the test
        "dosage_kg_ha": 0.1,
        "cost_usd": 40.0,
        "projected_revenue_increase_usd": 300.0,
    }

    async def case(live, router):
        await live.operation(200, "USD")
        await live.revenue(1000, "USD")
        user = _user(live.tenant)
        sink: dict = {}
        fn = threadsafe_farm_context_fn(
            asyncio.get_running_loop(),
            lambda: tenant_connection(user),
            live.tenant,
            live.season_id,
            sink=sink,
        )
        call = {**ctx, "field_id": live.field_id, "season_id": live.season_id}
        verdict = await asyncio.to_thread(
            evaluate_pesticide_guardrails,
            call,
            tenant_id=live.tenant,
            user_id="7",
            farm_context_fn=fn,
        )
        assert verdict["status"] == EVIDENCE_UNAVAILABLE, verdict
        assert verdict["missing_fields"] == ["farm_context.cash_reserve_usd"], (
            f"revenue and costs now come from the ledger: {verdict['missing_fields']}"
        )
        assert sink["farm_context"]["annual_revenue_usd"] == 1000.0, sink
        # negative control: without the builder the economics are missing too
        bare = await asyncio.to_thread(
            evaluate_pesticide_guardrails, call, tenant_id=live.tenant, user_id="7"
        )
        assert "farm_context.annual_revenue_usd" in bare["missing_fields"], bare

    _run(monkeypatch, case)


def test_pest_escalation_execute_step_carries_the_server_farm_context(monkeypatch):
    """The router wires the builder into the W0-01 gate; the workflow state shows what it read."""
    monkeypatch.delenv("DATABASE_URL", raising=False)  # in-memory workflow store
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")

    async def case(live, router):
        from api.api_models import PestEscalationRequest
        from api.routers import pest_escalation

        await live.operation(200, "USD")
        await live.revenue(1000, "USD")
        req = PestEscalationRequest(
            workflow_id=f"wf-{uuid.uuid4().hex[:10]}",
            field_id=live.field_id,
            season_id=live.season_id,
            pest_type="locust",
            severity=0.9,
            approval_status="approved",
        )
        out = await pest_escalation.pest_escalation_run(req, user=_user(live.tenant))
        execute = out["step_results"]["execute"]
        # HTTP contract: Workflow can complete even though guardrails block
        # the physical action. Never infer a spray from workflow status.
        assert out["execution"]["status"] == "not_executed", out
        assert out["execution"]["executed"] is False, out
        assert out["execution"]["reason"] == "guardrails", out
        assert execute["executed"] is False and execute["blocked_by"] == "guardrails", (
            f"no chemical/dose on the server yet: execution stays blocked: {execute}"
        )
        farm = execute["guardrails"].get("farm_context") or {}
        assert farm.get("annual_revenue_usd") == 1000.0, (
            f"the gate read the tenant's recorded revenue: {execute['guardrails']}"
        )
        assert farm["provenance"]["annual_costs_usd"]["source"] == "farm_operation_ledger", farm
        assert farm["field_area_ha"] == 2.5, farm

    _run(monkeypatch, case)


_V281_TABLES = (
    "farm_operation_ledger",
    "farm_season_budget_lines",
    "farm_revenue_records",
    "farm_indirect_cost_pools",
    "farm_ledger_inventory_projections",
    "farm_ledger_erp_projection_outbox",
    "farm_ledger_economic_snapshots",
)


async def _season_fk_state(admin) -> dict[str, bool]:
    rows = await admin.fetch(
        "SELECT c.conrelid::regclass::text AS tbl, c.convalidated FROM pg_constraint c"
        " WHERE c.conname = c.conrelid::regclass::text || '_season_id_fkey'"
        " AND c.conrelid::regclass::text = ANY($1::text[])",
        list(_V281_TABLES),
    )
    return {r["tbl"]: r["convalidated"] for r in rows}


def test_v281_rollback_reports_each_tables_season_orphans_and_refuses_an_rls_migrator():
    """Lab receipt on 0f746db and on #1503: v281's down restores the seven season keys NOT VALID
    (no migration runs VALIDATE CONSTRAINT: operator step, docs/runbooks/
    validate_not_valid_constraints.md). It must tell the operator, per table, how many rows would
    make VALIDATE fail, and a count FORCE RLS could hide must not be reported: a migrator subject
    to RLS is refused. v281 is re-applied after."""
    down = (ROOT / "migrations" / "v281_farm_ledger_season_reference.down.sql").read_text(
        encoding="utf-8"
    )
    up = (ROOT / "migrations" / "v281_farm_ledger_season_reference.sql").read_text(encoding="utf-8")

    assert "SET LOCAL row_security = off;" in down, (
        "the down must count orphans with row security off, or FORCE RLS hides them from the count"
    )

    async def strays(admin, present) -> dict[str, int]:
        out = {}
        for t in sorted(present):
            out[t] = await admin.fetchval(
                f"SELECT count(*) FROM {t} x WHERE x.season_id IS NOT NULL AND NOT EXISTS"
                " (SELECT 1 FROM farm_season_projects p WHERE p.season_id = x.season_id)"
            )
        return out

    async def body():
        admin = await asyncpg.connect(os.getenv("TEST_DATABASE_ADMIN_URL") or DSN)
        orphan_id = f"op-v281-{uuid.uuid4().hex[:8]}"
        superuser = False
        try:
            superuser = bool(
                await admin.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            )
            if not superuser:
                if _CERTIFICATION_REQUIRED:
                    raise AssertionError("certifying run needs a superuser to replay v281's down")
                pytest.skip("declared skip (not a pass): replaying a migration needs a superuser")
            present = {
                t
                for t in _V281_TABLES
                if await admin.fetchval("SELECT to_regclass($1)", f"public.{t}") is not None
            }
            # A migrator subject to RLS would count 0 orphans on these FORCE-RLS tables and mark a
            # key valid over hidden rows (lab receipt and review of #1503): it must be refused.
            runtime = await admin.fetchval(
                "SELECT rolname FROM pg_roles WHERE NOT rolsuper AND NOT rolbypassrls"
                " AND rolname = 'sahool_app_test'"
            )
            if runtime:
                await admin.execute("SET ROLE sahool_app_test")
                try:
                    with pytest.raises(asyncpg.exceptions.RaiseError, match="v281 rollback: role"):
                        await admin.execute(down)
                finally:
                    if admin.is_in_transaction():
                        await admin.execute("ROLLBACK")
                    await admin.execute("RESET ROLE")
                assert await _season_fk_state(admin) == {}, "a refused down must change nothing"
            elif _CERTIFICATION_REQUIRED:
                raise AssertionError("certifying run needs the restricted role sahool_app_test")

            notices: list[str] = []
            admin.add_log_listener(lambda _c, msg: notices.append(msg.message))

            def reported() -> dict[str, int]:
                out = {}
                for m in notices:
                    hit = re.match(r"v281 rollback: (\w+) restored \w+ NOT VALID; (\d+) row", m)
                    if hit:
                        out[hit.group(1)] = int(hit.group(2))
                return out

            before = await strays(admin, present)
            await admin.execute(down)
            clean = await _season_fk_state(admin)
            assert set(clean) == present, f"down restored keys on {sorted(clean)}, not {present}"
            assert not any(clean.values()), f"no migration may validate the keys: {clean}"
            assert reported() == before, f"per-table orphan report {reported()} != {before}"
            await admin.execute(up)
            assert await _season_fk_state(admin) == {}, "v281 re-applied must drop the keys"

            async with admin.transaction():
                await admin.execute("SET LOCAL session_replication_role = replica")
                await admin.execute(
                    "INSERT INTO farm_operation_ledger (operation_id, tenant_id, season_id,"
                    " operation_type, operation_date, status)"
                    " VALUES ($1, $2::uuid, $3, 'irrigation', CURRENT_DATE, 'completed')",
                    orphan_id,
                    str(uuid.uuid4()),
                    f"season-only-{uuid.uuid4().hex[:8]}",
                )
            notices.clear()
            await admin.execute(down)
            expected = {**before, "farm_operation_ledger": before["farm_operation_ledger"] + 1}
            assert reported() == expected, (
                f"the orphan must be counted on its own table only: {reported()} != {expected}"
            )
        finally:
            if admin.is_in_transaction():
                await admin.execute("ROLLBACK")
            if superuser:
                async with admin.transaction():
                    await admin.execute("SET LOCAL session_replication_role = replica")
                    await admin.execute(
                        "DELETE FROM farm_operation_ledger WHERE operation_id = $1", orphan_id
                    )
                await admin.execute(up)
                assert await admin.fetchval(
                    "SELECT 1 FROM pg_proc WHERE proname = 'farm_ledger_assert_season_ref'"
                ), "v281 must be re-applied after the rollback test"
            await admin.close()

    asyncio.run(body())


@pytest.mark.parametrize("endpoint", ["revenues", "budgets"])
def test_finance_write_validates_amount_before_postgres(monkeypatch, endpoint):
    import json

    import httpx
    from fastapi import FastAPI

    async def case(live, router):
        main, _ = _platform()
        app = FastAPI()
        app.include_router(router.router)
        app.dependency_overrides[main.get_current_user] = lambda: _user(live.tenant)
        if endpoint == "revenues":
            quantity, price, amount = "quantity", "unit_price", "amount"
            table = "farm_revenue_records"
            base = {"season_id": live.season_id, "revenue_date": date.today().isoformat()}
        else:
            quantity, price, amount = "planned_quantity", "planned_unit_cost", "planned_cost"
            table = "farm_season_budget_lines"
            base = {"season_id": live.season_id, "category": "seed"}

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

            async def post(values):
                row = {**base, **values}
                payload = {"lines": [row]} if endpoint == "budgets" else row
                return await client.post(
                    "/api/v1/farm-ledger/" + endpoint,
                    content=json.dumps(payload),
                    headers={"content-type": "application/json"},
                )

            for invalid in (
                {quantity: 1e308, price: 10},
                {amount: "Infinity"},
                {price: float("nan")},
                {quantity: {"unexpected": float("inf")}},
            ):
                response = await post(invalid)
                persisted = await live.as_tenant(
                    live.tenant,
                    f"SELECT {amount}::text FROM {table} WHERE season_id = $1",
                    live.season_id,
                )
                assert (response.status_code, persisted) == (422, None)
                assert response.json()["detail"]

            for values, expected in (
                ({quantity: "2.5", price: "4", amount: 0}, 10.0),
                ({quantity: 1e308, price: 10, amount: 7}, 7.0),
                ({price: 5}, 0.0),
            ):
                response = await post(values)
                assert response.status_code == 201, response.text
                result = response.json()
                total = result[amount] if endpoint == "revenues" else result["saved"][0][amount]
                assert total == expected
                assert (
                    await live.as_tenant(
                        live.tenant,
                        f"SELECT count(*) FROM {table} WHERE season_id = $1 AND {amount} = $2",
                        live.season_id,
                        expected,
                    )
                    == 1
                )

    _run(monkeypatch, case)
