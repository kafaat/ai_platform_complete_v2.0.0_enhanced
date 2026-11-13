"""The Field and Water twins read the active season from a migrated Postgres (live PG).

Both endpoints must interpret a field through its *active season* (``seasons`` with
``status='active'``), not the legacy ``fields.crop``; the Field Twin must also judge NDVI
freshness by NDVI's own observation time, so a newer EVI cannot make an old NDVI look
fresh. #1402 tests the season adapters as pure functions and ran the routers' SQL on
PostgreSQL 16 as a superuser, so tenant isolation (RLS) was not exercised. Here the routers
run against the real schema through a pool that runs as a NOBYPASSRLS role, so row-level
security applies exactly as in production.

Both views are read models: the assertions also pin ``decision_authority == "none"`` and
the water twin's ``preview_only``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
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


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("seasons", "field_indicators", "water_ledger", "dispatch_decisions"):
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
    from api.routers import field_twin, water_twin

    return main, field_twin, water_twin


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
        self.field_id = f"dt-field-{uuid.uuid4().hex[:10]}"
        self.season_id = f"dt-season-{uuid.uuid4().hex[:10]}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"dt_rls_{uuid.uuid4().hex[:10]}"
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
        o = self.owner
        # The legacy field metadata says peanut; the active season says wheat.
        await o.execute(
            "INSERT INTO fields (field_id, name, tenant_id, crop, planting_date)"
            " VALUES ($1, 'Twin field', $2::uuid, 'peanut', $3)",
            self.field_id,
            self.tenant,
            date(2026, 1, 1),
        )
        await o.execute(
            """INSERT INTO seasons (season_id, tenant_id, field_id, crops, status, cultivar,
                                    sowing_date)
               VALUES ($1, $2::uuid, $3, $4::jsonb, 'active', 'habib', $5)""",
            self.season_id,
            self.tenant,
            self.field_id,
            json.dumps(["wheat"]),
            date(2026, 10, 20),
        )
        return self

    async def indicator(self, indicator_id: str, value: float, recorded_at: datetime):
        await self.owner.execute(
            """INSERT INTO field_indicators (field_id, tenant_id, indicator_id, category, value,
                                             recorded_at)
               VALUES ($1, $2::uuid, $3, 'vegetation', $4, $5)""",
            self.field_id,
            self.tenant,
            indicator_id,
            value,
            recorded_at,
        )

    async def __aexit__(self, *exc):
        o = self.owner
        try:
            await o.execute("DELETE FROM field_indicators WHERE field_id = $1", self.field_id)
            await o.execute("DELETE FROM seasons WHERE field_id = $1", self.field_id)
            await o.execute("DELETE FROM fields WHERE field_id = $1", self.field_id)
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()


def _run(monkeypatch, case):
    main, field_twin, water_twin = _platform()

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, field_twin, water_twin)

    asyncio.run(body())


def test_field_twin_reads_the_active_season_and_judges_ndvi_by_its_own_time(monkeypatch):
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")

    async def case(live, field_twin, _water_twin):
        now = datetime.now(UTC)
        await live.indicator("ndvi", 0.75, now - timedelta(days=40))
        await live.indicator("evi", 0.60, now - timedelta(hours=1))
        out = await field_twin.get_field_twin(live.field_id, user=_user(live.tenant))
        assert out["state"] == "stale", "a fresh EVI must not make a 40-day-old NDVI fresh"
        assert out["observed_at"] == (now - timedelta(days=40)).date().isoformat()
        assert out["season_context"]["season_id"] == live.season_id
        assert out["season_context"]["crops"] == ["wheat"]
        assert out["season_context"]["cultivar"] == "habib"
        assert out["legacy_field_crop"] == "peanut"
        assert out["decision_authority"] == "none"
        assert out["view_role"] == "derived_read_model_only"

    _run(monkeypatch, case)


def test_field_twin_of_another_tenants_field_is_404(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")

    async def case(live, field_twin, _water_twin):
        with pytest.raises(HTTPException) as caught:
            await field_twin.get_field_twin(live.field_id, user=_user(live.other_tenant))
        assert caught.value.status_code == 404

    _run(monkeypatch, case)


def test_water_twin_active_season_wins_over_the_legacy_field_crop(monkeypatch):
    async def case(live, _field_twin, water_twin):
        req = water_twin.FieldWaterTwinRequest(
            taw_mm=100, raw_mm=50, initial_depletion_mm=30, daily_etc_mm=4, horizon_days=2
        )
        out = await water_twin.field_water_twin(
            req=req, field_id=live.field_id, user=_user(live.tenant)
        )
        assert out["season_context"]["season_id"] == live.season_id
        assert out["season_context"]["crop"] == "wheat"
        assert out["season_context"]["source"] == "seasons.active"
        assert out["season_context"]["decision_authority"] == "none"
        assert out["preview_only"] is True

    _run(monkeypatch, case)
