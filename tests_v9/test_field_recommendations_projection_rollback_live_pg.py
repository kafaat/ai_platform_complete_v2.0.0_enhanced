"""GET /api/v1/fields/{id}/recommendations leaves no field_state write behind a 503 (live PG).

The route recomputes the derived ``field_state`` projection (an UPSERT). It used to do that in
its first ``tenant_connection`` block, which commits on exit, and only later answer 503 when no
recommendation could be built (no crop, no season, no weather). The 503 then left a committed
projection row behind. The projection write now shares one transaction with the 503 decision, so
a 503 rolls it back, while a 200 still writes it (the control below: the fix must not stop the
route from writing on success).

Runs over HTTP into the real platform app, on a migrated Postgres, through the restricted
NOBYPASSRLS role of ``TEST_DATABASE_URL``; ``TEST_DATABASE_ADMIN_URL`` only seeds and inspects.
Both fields have no coordinates, so no weather call is made.
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

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_CERTIFICATION_REQUIRED = os.getenv("FIELD_STATE_ROLLBACK_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    import fastapi  # noqa: F401
    import httpx
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv("TEST_DATABASE_URL") or ""
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_TABLES = ("fields", "seasons", "field_state")


async def _probe() -> str:
    if not DSN or not ADMIN_DSN:
        return "TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL are both required"
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
# FIELD_STATE_ROLLBACK_CERTIFICATION_REQUIRED=1 (set by its own CI step and the lab runner)
# turns a missing database into a failure: the shared integration step gives only the superuser
# TEST_DATABASE_URL, so without this switch the test skipped green and guarded nothing (lab
# receipt for #1469).
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(f"FIELD_STATE_ROLLBACK_CERTIFICATION_REQUIRED=1 but: {_WHY}")
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    for p in (PLATFORM, ROOT):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import api.main as main

    return main


async def _scenario(monkeypatch) -> dict:
    main = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    bare = f"fsr-bare-{uuid.uuid4().hex[:8]}"  # no crop, no season, no coordinates ⇒ 503
    sown = f"fsr-sown-{uuid.uuid4().hex[:8]}"  # wheat sown 30 days ago ⇒ a yield rec ⇒ 200
    admin = await asyncpg.connect(ADMIN_DSN)
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    await admin.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $3::uuid),"
        " ($2, $2, $3::uuid)",
        bare,
        sown,
        tenant,
    )
    await admin.execute(
        "INSERT INTO seasons (season_id, tenant_id, field_id, crops, sowing_date, status)"
        " VALUES ($1, $2::uuid, $3, '[\"wheat\"]'::jsonb, $4, 'active')",
        f"fsr-season-{uuid.uuid4().hex[:8]}",
        tenant,
        sown,
        date.today() - timedelta(days=30),
    )
    main.app.dependency_overrides[main.get_current_user] = lambda: UserSchema(
        user_id="fsr-viewer", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مشاهد"
    )

    async def projection_rows(field_id: str) -> int:
        return await admin.fetchval("SELECT count(*) FROM field_state WHERE field_id=$1", field_id)

    out: dict = {}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:
            for name, field_id in (("bare", bare), ("sown", sown)):
                before = await projection_rows(field_id)
                resp = await client.get(f"/api/v1/fields/{field_id}/recommendations")
                out[name] = {
                    "status": resp.status_code,
                    "before": before,
                    "after": await projection_rows(field_id),
                    "body": resp.json() if resp.status_code == 200 else resp.text,
                }
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            async with admin.transaction():
                await admin.execute("SET LOCAL session_replication_role = replica")
                for table in ("field_state", "seasons", "fields"):
                    await admin.execute(f"DELETE FROM {table} WHERE tenant_id = $1::uuid", tenant)
        finally:
            await admin.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def test_a_503_without_recommendations_leaves_no_projection_write(scenario):
    bare = scenario["bare"]
    assert bare["status"] == 503, bare["body"]
    assert (bare["before"], bare["after"]) == (0, 0), "a 503 committed a field_state row"


def test_a_200_still_writes_the_projection(scenario):
    sown = scenario["sown"]
    assert sown["status"] == 200, sown["body"]
    assert sown["body"]["recommendations"], sown["body"]
    assert "field_state" in sown["body"]
    assert (sown["before"], sown["after"]) == (0, 1), "a 200 no longer writes field_state"
