"""A field-geometry save is atomic with its history row — proven on a migrated PostgreSQL.

Three handlers change ``fields.geometry`` and then append a ``field_geometry_history`` row on
the same ``tenant_connection`` transaction: create, ``PATCH /api/v1/fields/{id}`` and
``POST /api/v1/fields/{id}/geometry/revert/{revision}``. The append used to sit in a bare
``try/except Exception: return None`` ("best effort") with no savepoint. When the INSERT
failed, PostgreSQL aborted the whole transaction; the swallowed error left every later
statement failing (the raster intent and the domain event swallow theirs too), and the final
COMMIT on an aborted transaction rolls back without raising. The handler then answered
success with the new geometry while nothing was stored.

These cases drive the real handlers under a NOBYPASSRLS role and make PostgreSQL itself refuse
the history INSERT, two ways: the INSERT privilege is revoked from the role, or a RESTRICTIVE
row-level-security policy scoped to that role rejects every new row. Both raise SQLSTATE 42501
(insufficient_privilege) and cannot be told apart by the driver; either one is a server-side
fault for a request whose tenant comes from the caller's own token, so the answer is 503.

Runs in the Integration job (``TEST_DATABASE_URL``, migrated by the manifest). Without a
reachable database the module is skipped, and the skip says so.
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


def _square(lon0: float, lat0: float, side: float = 0.01) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon0, lat0],
                [lon0 + side, lat0],
                [lon0 + side, lat0 + side],
                [lon0, lat0 + side],
                [lon0, lat0],
            ]
        ],
    }


# Two non-overlapping ~1.1 km squares near Sana'a.
ORIGINAL = _square(44.300, 15.450)
MOVED = _square(44.302, 15.452)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.field_geometry_history')") is None:
            return "schema not migrated (field_geometry_history missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import fields

    return main, fields


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{tenant[:8]}", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير"
    )


class Live:
    """Owner connection for setup/measurement + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        self.tenant_a = str(uuid.uuid4())
        self.tenant_b = str(uuid.uuid4())
        self.field_id = f"ga-{uuid.uuid4().hex[:12]}"
        self.role = f"ga_rls_{uuid.uuid4().hex[:10]}"

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        await self.owner.execute(
            f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
        )
        role = self.role

        async def setup(conn):
            await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3, setup=setup)
        await self.owner.execute(
            "INSERT INTO fields (field_id, name, tenant_id, geometry) "
            "VALUES ($1, $2, $3::uuid, $4::jsonb)",
            self.field_id,
            "حقل اختبار ذرّيّة الحدود",
            self.tenant_a,
            json.dumps(ORIGINAL),
        )
        return self

    async def refuse_history_insert(self, how: str = "privilege"):
        if how == "privilege":
            await self.owner.execute(f'REVOKE INSERT ON field_geometry_history FROM "{self.role}"')
        else:  # row-level security, scoped to this throwaway role only
            await self.owner.execute(
                f'CREATE POLICY "{self.role}_deny" ON field_geometry_history '
                f'AS RESTRICTIVE FOR INSERT TO "{self.role}" WITH CHECK (false)'
            )

    async def field_state(self) -> tuple[dict, int]:
        row = await self.owner.fetchrow(
            "SELECT geometry, geometry_version FROM fields WHERE field_id = $1", self.field_id
        )
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        return geometry, int(row["geometry_version"])

    async def history(self) -> list[dict]:
        rows = await self.owner.fetch(
            "SELECT revision, geometry FROM field_geometry_history "
            "WHERE field_id = $1 ORDER BY revision",
            self.field_id,
        )
        out = []
        for r in rows:
            g = r["geometry"]
            out.append(
                {"revision": r["revision"], "geometry": json.loads(g) if isinstance(g, str) else g}
            )
        return out

    async def __aexit__(self, *exc):
        try:
            # field_geometry_history is append-only (v139); the owner session lifts the trigger
            # for its own cleanup only.
            await self.owner.execute("SET session_replication_role = replica")
            await self.owner.execute(
                "DELETE FROM field_geometry_history WHERE field_id = $1", self.field_id
            )
            await self.owner.execute("SET session_replication_role = origin")
            await self.owner.execute("DELETE FROM fields WHERE field_id = $1", self.field_id)
        finally:
            await self.pool.close()
            await self.owner.execute(
                f'DROP POLICY IF EXISTS "{self.role}_deny" ON field_geometry_history'
            )
            await self.owner.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await self.owner.close()


def _run(coro_fn):
    async def body():
        async with Live() as live:
            await coro_fn(live)

    asyncio.run(body())


def _patch(fields, live, user, geometry: dict):
    from api.field_models import FieldUpdateRequest
    from fastapi import BackgroundTasks

    return fields.update_field(
        live.field_id,
        FieldUpdateRequest(geometry=geometry),
        BackgroundTasks(),
        user=user,
        idem=None,
    )


def _ring(geometry: dict) -> list:
    return geometry["coordinates"][0]


# ── geometry save is atomic with its history row ──────────────────────────────


def test_a_geometry_patch_stores_the_boundary_bumps_the_version_and_appends_history(monkeypatch):
    main, fields = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await _patch(fields, live, _user(live.tenant_a), MOVED)
        geometry, version = await live.field_state()
        history = await live.history()
        assert _ring(geometry) == _ring(MOVED)
        assert version == 2
        assert history and _ring(history[-1]["geometry"]) == _ring(MOVED)

    _run(case)


@pytest.mark.parametrize("how", ["privilege", "row_level_security"])
def test_a_refused_history_insert_fails_the_patch_instead_of_dropping_it(monkeypatch, how):
    from fastapi import HTTPException

    main, fields = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.refuse_history_insert(how)
        status = None
        answered = None
        try:
            answered = await _patch(fields, live, _user(live.tenant_a), MOVED)
        except HTTPException as exc:
            status = exc.status_code
        geometry, version = await live.field_state()
        stored = _ring(geometry) == _ring(MOVED)
        # A success answer must mean the boundary is stored; the pre-fix handler answered the
        # new boundary while the aborted transaction had rolled it back.
        assert answered is None, (
            f"answered success (boundary stored in DB: {stored}, version {version})"
        )
        assert status is not None and status >= 500
        # Nothing half-applied: the boundary, its version and its history move together.
        assert not stored and version == 1
        assert await live.history() == []

    _run(case)


def test_a_refused_history_insert_fails_the_revert_instead_of_dropping_it(monkeypatch):
    from fastapi import HTTPException

    main, fields = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        user = _user(live.tenant_a)
        await _patch(fields, live, user, MOVED)
        await _patch(fields, live, user, ORIGINAL)
        first = (await live.history())[0]["revision"]
        before_geometry, before_version = await live.field_state()
        await live.refuse_history_insert()
        with pytest.raises(HTTPException) as caught:
            from fastapi import BackgroundTasks

            await fields.revert_field_geometry(live.field_id, first, BackgroundTasks(), user=user)
        geometry, version = await live.field_state()
        assert caught.value.status_code >= 500
        assert _ring(geometry) == _ring(before_geometry) and version == before_version

    _run(case)
