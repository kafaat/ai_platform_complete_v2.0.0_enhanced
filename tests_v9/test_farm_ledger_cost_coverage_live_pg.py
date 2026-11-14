"""Season budget variance and the ERP projection read the migrated farm ledger (live PG).

The variance must not count unpriced completed work as a saving: a completed operation with
no recorded cost makes its whole category incomplete. Ledger operations carry no budget
stage (``farm_operation_ledger`` has no ``stage`` column; actuals are keyed
``whole_season``), so the incomplete category is reported under ``whole_season``. The ERP
projection is in one currency, bound to the envelope and its digest, and a mixed-currency
season is refused rather than summed.

These were asserted against a patched ``tenant_connection`` yielding a mock, which proves
nothing about the SQL: the currency scope, the ``completed``/date filter, the tenant and
season binding. Here the router runs against the real schema through a pool that runs as a
NOBYPASSRLS role, so tenant isolation applies exactly as in production.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
TABLES = ("farm_season_projects", "farm_season_budget_lines", "farm_operation_ledger")


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
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
    """Owner connection for setup + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        tag = uuid.uuid4().hex[:10]
        self.season_id = f"cost-season-{tag}"
        self.other_season = f"cost-other-{tag}"
        self.other_tenant_season = f"cost-foreign-{tag}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"cost_rls_{uuid.uuid4().hex[:10]}"
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

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, setup=setup)
        for season, tenant in (
            (self.season_id, self.tenant),
            (self.other_season, self.tenant),
            (self.other_tenant_season, self.other_tenant),
        ):
            await self.owner.execute(
                "INSERT INTO farm_season_projects (season_id, tenant_id, name, status)"
                " VALUES ($1, $2::uuid, 'Cost coverage season', 'active')",
                season,
                tenant,
            )
        return self

    async def budget(self, category: str, planned_cost: float, currency: str = "USD"):
        await self.owner.execute(
            """INSERT INTO farm_season_budget_lines
                   (budget_line_id, tenant_id, season_id, category, planned_cost, currency)
               VALUES ($1, $2::uuid, $3, $4, $5, $6)""",
            f"b-{uuid.uuid4().hex[:12]}",
            self.tenant,
            self.season_id,
            category,
            planned_cost,
            currency,
        )

    async def operation(
        self,
        category: str,
        cost: float | None,
        currency: str = "USD",
        *,
        status: str = "completed",
        days_ahead: int = 0,
        tenant: str | None = None,
        season_id: str | None = None,
    ):
        await self.owner.execute(
            """INSERT INTO farm_operation_ledger
                   (operation_id, tenant_id, season_id, operation_type, operation_date, status,
                    cost_amount, cost_category, currency)
               VALUES ($1, $2::uuid, $3, 'generic', $4, $5, $6, $7, $8)""",
            f"op-{uuid.uuid4().hex[:12]}",
            tenant or self.tenant,
            season_id or self.season_id,
            date.today() + timedelta(days=days_ahead),
            status,
            cost,
            category,
            currency,
        )

    async def __aexit__(self, *exc):
        o = self.owner
        seasons = [self.season_id, self.other_season, self.other_tenant_season]
        try:
            await o.execute(
                "DELETE FROM farm_operation_ledger WHERE season_id = ANY($1::text[])", seasons
            )
            await o.execute(
                "DELETE FROM farm_season_projects WHERE season_id = ANY($1::text[])", seasons
            )
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


def test_unpriced_completed_work_marks_its_category_incomplete_not_saved(monkeypatch):
    async def case(live, router):
        await live.budget("seed", 100)
        await live.budget("water", 100)
        await live.operation("seed", 140)
        await live.operation("water", None)  # completed, unpriced: counts
        await live.operation("seed", None, status="planned")  # not actual work
        await live.operation("seed", None, "YER")  # other currency
        await live.operation("seed", None, days_ahead=1)  # dated after today
        await live.operation(
            "seed", None, tenant=live.other_tenant, season_id=live.other_tenant_season
        )
        await live.operation("seed", None, season_id=live.other_season)

        out = await router.get_budget_variance(
            live.season_id, currency=" usd ", user=_user(live.tenant)
        )
        assert out["currency"] == "USD"
        assert out["cost_coverage"] == "partial"
        assert out["unpriced_operations"] == 1
        assert out["incomplete_categories"] == [
            {"stage": "whole_season", "category": "water", "unpriced_operations": 1}
        ]
        assert [(v["stage"], v["category"]) for v in out["variance"]] == [("whole_season", "seed")]
        seed = out["variance"][0]
        assert (seed["planned_cost"], seed["actual_cost"]) == (100, 140)
        assert seed["variance_percent"] == pytest.approx(40.0)
        assert [r["code"] for r in out["recommendations"]] == ["cost_variance_whole_season_seed"]

    _run(monkeypatch, case)


def test_fully_priced_season_reports_recorded_operations(monkeypatch):
    async def case(live, router):
        await live.budget("seed", 100)
        await live.operation("seed", 90)
        out = await router.get_budget_variance(
            live.season_id, currency="USD", user=_user(live.tenant)
        )
        assert (out["cost_coverage"], out["unpriced_operations"]) == ("recorded_operations", 0)
        assert out["incomplete_categories"] == []
        assert [v["actual_cost"] for v in out["variance"]] == [90]

    _run(monkeypatch, case)


def test_erp_projection_binds_its_currency_lines_and_digest(monkeypatch):
    async def case(live, router):
        from core.erp_projection_contract import canonical_digest

        await live.operation("water", 42)
        await live.operation("water", 5000, "YER")
        out = await router.get_erp_projection(
            live.season_id, currency=" usd ", user=_user(live.tenant)
        )
        assert out["currency"] == "USD"
        assert [(line["category"], line["amount"], line["currency"]) for line in out["lines"]] == [
            ("water", 42, "USD")
        ]
        payload = {
            k: out[k] for k in ("schema_version", "season_id", "currency", "provider", "lines")
        }
        assert out["projection_digest"] == canonical_digest(payload)

    _run(monkeypatch, case)


def test_mixed_currency_erp_projection_is_refused_not_summed(monkeypatch):
    from fastapi import HTTPException

    async def case(live, router):
        await live.operation("water", 10, "USD")
        await live.operation("water", 5000, "YER")
        with pytest.raises(HTTPException) as caught:
            await router.get_erp_projection(live.season_id, user=_user(live.tenant))
        assert caught.value.status_code == 409

    _run(monkeypatch, case)


def test_another_tenants_ledger_is_invisible(monkeypatch):
    async def case(live, router):
        await live.operation(
            "water", None, tenant=live.other_tenant, season_id=live.other_tenant_season
        )
        out = await router.get_budget_variance(
            live.other_tenant_season, currency="USD", user=_user(live.tenant)
        )
        assert (out["cost_coverage"], out["incomplete_categories"]) == ("recorded_operations", [])

    _run(monkeypatch, case)
