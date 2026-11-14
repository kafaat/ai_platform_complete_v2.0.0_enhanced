"""The unified-timeline facade answers a foreign field with 404 — proven on a migrated PostgreSQL.

``GET /api/v1/fields/{field_id}/unified-timeline`` checks the field against the caller's tenant
(``_assert_field_in_tenant``, a 404) inside a broad ``try``. The ``except Exception`` caught that
HTTPException too and answered ``200 degraded`` with the exception text, so another tenant's
field id looked like a temporarily unreadable timeline. These cases drive the real handler under
a NOBYPASSRLS role: a foreign field is a 404, and the caller's own field reads the real
``events`` table (``degraded: false``).

Runs in the shared Integration step (``TEST_DATABASE_URL``, migrated by the manifest; the
superuser there creates the throwaway restricted role). That step sets
``FIELD_TIMELINE_CERTIFICATION_REQUIRED=1``, so an unreachable or unmigrated database fails the
module instead of turning it into a green skip. Without the switch every case is skipped, and the
skip says why.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[44.40, 15.55], [44.41, 15.55], [44.41, 15.56], [44.40, 15.56], [44.40, 15.55]]
    ],
}


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.events')") is None:
            return "schema not migrated (events missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
_REQUIRED = os.getenv("FIELD_TIMELINE_CERTIFICATION_REQUIRED") == "1"


@pytest.fixture(autouse=True)
def _database_or_declared_skip():
    if _WHY:
        message = f"field-timeline live certification has no database: {_WHY}"
        if _REQUIRED:
            pytest.fail(message, pytrace=False)
        pytest.skip(f"declared skip (not a pass): {message}")


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import field_workspace_timeline

    return main, field_workspace_timeline


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{tenant[:8]}", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير"
    )


async def _with_field(body):
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    field_id = f"tl-{uuid.uuid4().hex[:12]}"
    role = f"tl_rls_{uuid.uuid4().hex[:10]}"
    owner = await asyncpg.connect(DSN)
    await owner.execute(
        f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
        f'GRANT USAGE ON SCHEMA public TO "{role}";'
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
    )

    async def setup(conn):
        await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, setup=setup)
    try:
        await owner.execute(
            "INSERT INTO fields (field_id, name, tenant_id, geometry) "
            "VALUES ($1, $2, $3::uuid, $4::jsonb)",
            field_id,
            "حقل اختبار الخطّ الزمنيّ",
            tenant_a,
            json.dumps(GEOMETRY),
        )
        await body(pool, field_id, tenant_a, tenant_b)
    finally:
        await owner.execute("DELETE FROM fields WHERE field_id = $1", field_id)
        await pool.close()
        await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
        await owner.close()


def _call(timeline, field_id: str, tenant: str):
    return timeline.field_unified_timeline_facade(
        field_id, limit=50, newest_first=True, category=None, season_id=None, user=_user(tenant)
    )


def test_the_timeline_of_another_tenants_field_is_404(monkeypatch):
    from fastapi import HTTPException

    main, timeline = _platform()

    async def body(pool, field_id, tenant_a, tenant_b):
        monkeypatch.setattr(main, "_DB_POOL", pool)
        with pytest.raises(HTTPException) as caught:
            await _call(timeline, field_id, tenant_b)
        assert caught.value.status_code == 404

    asyncio.run(_with_field(body))


def test_the_timeline_of_the_callers_field_reads_the_events_table(monkeypatch):
    main, timeline = _platform()

    async def body(pool, field_id, tenant_a, tenant_b):
        monkeypatch.setattr(main, "_DB_POOL", pool)
        out = await _call(timeline, field_id, tenant_a)
        assert out["degraded"] is False, out
        assert out["field_id"] == field_id

    asyncio.run(_with_field(body))
