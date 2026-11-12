"""Writes that answered 200 while storing nothing — proven on a migrated PostgreSQL.

Each case drives the real platform code (handler or persistence function, real asyncpg pool or
connection, real schema from the manifest) under a NOBYPASSRLS role, because test doubles accept
any parameter type and any ON CONFLICT target:

* S-H2 — ``POST /api/v1/fields/{id}/pins`` passed the ISO ``created_at`` string to a timestamptz
  parameter; asyncpg rejects a ``str`` there at execute time, the best-effort ``except`` swallowed
  it, and every pin answered ``persisted: false``. The same class dropped every recommendation
  (``issued_at``) behind ``delivered: true``. Pins must also land on the caller's own field and
  inside its boundary (with a GPS tolerance).
* R-H6 — ``PUT /api/v1/notifications/preferences`` used ``ON CONFLICT (tenant_id, user_ref)``
  while the only unique index on those columns is partial; Postgres infers no arbiter and every
  call failed with 42P10 (503), so preferences were never saved.

Runs in the Integration job (``TEST_DATABASE_URL``, migrated by the manifest). Without a reachable
database the module is skipped, and the skip says so.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
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

# A ~1.1 km square near Sana'a: lon 44.200..44.210, lat 15.350..15.360.
FIELD_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[44.200, 15.350], [44.210, 15.350], [44.210, 15.360], [44.200, 15.360], [44.200, 15.350]]
    ],
}


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.scouting_pins')") is None:
            return "schema not migrated (scouting_pins missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import fields, notifications, recommendations

    return main, fields, notifications, recommendations


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{tenant[:8]}", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير"
    )


class Live:
    """Owner connection for setup/measurement + a pool that runs as a NOBYPASSRLS role.

    The CI database user is a superuser, which bypasses RLS even with FORCE; a pin on another
    tenant's field would then be "found". When the DSN user can bypass RLS, a throwaway
    NOLOGIN NOBYPASSRLS role is created and every pooled connection ``SET ROLE``s to it.
    """

    def __init__(self):
        self.tenant_a = str(uuid.uuid4())
        self.tenant_b = str(uuid.uuid4())
        self.field_id = f"hb-{uuid.uuid4().hex[:12]}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        bypass = await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        if bypass:
            self.role = f"hb_rls_{uuid.uuid4().hex[:10]}"
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
        await self.owner.execute(
            "INSERT INTO fields (field_id, name, tenant_id, geometry) VALUES ($1, $2, $3::uuid, $4::jsonb)",
            self.field_id,
            "حقل اختبار الإدامة",
            self.tenant_a,
            json.dumps(FIELD_GEOMETRY),
        )
        return self

    async def __aexit__(self, *exc):
        try:
            await self.owner.execute(
                "DELETE FROM scouting_pins WHERE tenant_id = ANY($1::uuid[])",
                [self.tenant_a, self.tenant_b],
            )
            await self.owner.execute(
                "DELETE FROM notification_preferences WHERE tenant_id = ANY($1::uuid[])",
                [self.tenant_a, self.tenant_b],
            )
            await self.owner.execute("DELETE FROM fields WHERE field_id = $1", self.field_id)
        finally:
            await self.pool.close()
            if self.role:
                await self.owner.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await self.owner.close()


def _run(coro_fn):
    async def body():
        async with Live() as live:
            await coro_fn(live)

    asyncio.run(body())


def _pin(field_id: str, lat: float, lng: float):
    from api.main import PinCreateRequest

    return PinCreateRequest(
        pin_id=f"pin-{uuid.uuid4().hex[:12]}",
        field_id=field_id,
        lat=lat,
        lng=lng,
        issue_category="pest",
        severity="high",
    )


# ── S-H2: scouting pins ────────────────────────────────────────────────────


def test_a_pin_inside_the_callers_field_is_stored_and_reported_persisted(monkeypatch):
    main, fields, _, _ = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        req = _pin(live.field_id, 15.355, 44.205)
        out = await fields.create_pin(live.field_id, req, user=_user(live.tenant_a))
        row = await live.owner.fetchrow(
            "SELECT field_id, created_at FROM scouting_pins WHERE pin_id = $1", req.pin_id
        )
        assert out["persisted"] is True, out
        assert row is not None and row["field_id"] == live.field_id
        assert isinstance(row["created_at"], datetime)

    _run(case)


def test_a_pin_on_another_tenants_field_is_404_and_writes_nothing(monkeypatch):
    from fastapi import HTTPException

    main, fields, _, _ = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        req = _pin(live.field_id, 15.355, 44.205)
        with pytest.raises(HTTPException) as caught:
            await fields.create_pin(live.field_id, req, user=_user(live.tenant_b))
        assert caught.value.status_code == 404
        assert not await live.owner.fetchval(
            "SELECT count(*) FROM scouting_pins WHERE pin_id = $1", req.pin_id
        )

    _run(case)


def test_a_pin_outside_the_field_boundary_is_422_and_writes_nothing(monkeypatch):
    from fastapi import HTTPException

    main, fields, _, _ = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        # 0.0005 deg west of the boundary at lat 15.355 is ~54 m: beyond the GPS tolerance.
        req = _pin(live.field_id, 15.355, 44.1995)
        with pytest.raises(HTTPException) as caught:
            await fields.create_pin(live.field_id, req, user=_user(live.tenant_a))
        assert caught.value.status_code == 422
        assert not await live.owner.fetchval(
            "SELECT count(*) FROM scouting_pins WHERE pin_id = $1", req.pin_id
        )

    _run(case)


def test_a_pin_a_few_metres_past_the_boundary_is_within_gps_tolerance(monkeypatch):
    main, fields, _, _ = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        # 0.0001 deg east of the boundary at lat 15.355 is ~11 m, under the 25 m tolerance.
        req = _pin(live.field_id, 15.355, 44.2101)
        out = await fields.create_pin(live.field_id, req, user=_user(live.tenant_a))
        assert out["persisted"] is True, out

    _run(case)


# ── S-H2: recommendations ──────────────────────────────────────────────────


def test_a_recommendation_with_the_engines_iso_timestamp_is_written(monkeypatch):
    """The engine stamps ``datetime.now().isoformat()``; that string must reach the row.

    Run on the caller-supplied connection inside a transaction that is rolled back, because
    governed recommendation rows are immutable (no DELETE) and must not outlive the test.
    """
    main, _, _, recommendations = _platform()

    async def case(live):
        user = _user(live.tenant_a)
        req = main.RecommendationRequest(
            tenant_id=live.tenant_a,
            farm_id="farm-hb",
            field_id=live.field_id,
            crop="tomato",
            validation={},
        )
        rec_id = f"rec-{uuid.uuid4().hex[:12]}"
        enriched = {
            "rec_id": rec_id,
            "delivered": True,
            "reason_ar": "اختبار",
            "base_recommendation": {"action": "irrigate"},
            "cross_reference": {"count": 0},
            "provenance": {"model_versions": {}},
            "timestamp": datetime.now().isoformat(),
        }
        async with live.pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true), "
                    "set_config('app.current_user_id', $2, true)",
                    live.tenant_a,
                    user.user_id,
                )
                persisted = await recommendations._persist_recommendation(
                    user, req, enriched, conn=conn
                )
                issued_at = await conn.fetchval(
                    "SELECT issued_at FROM recommendations WHERE rec_id = $1", rec_id
                )
            finally:
                await tx.rollback()
        assert persisted is True
        assert isinstance(issued_at, datetime)

    _run(case)


def test_the_recommendation_endpoint_reports_persisted_only_for_a_stored_row(monkeypatch):
    """The reviewer's symptom: ``delivered: true`` with an empty table. Now the body says.

    Governed recommendation rows reject DELETE by trigger, so the row this writes is removed
    afterwards with triggers suspended (``session_replication_role``, superuser only); under a
    non-superuser DSN it stays behind under its throwaway tenant.
    """
    main, _, _, recommendations = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        user = _user(live.tenant_a)
        req = main.RecommendationRequest(
            tenant_id=live.tenant_a,
            farm_id="farm-hb",
            field_id=live.field_id,
            crop="tomato",
            validation={},
        )
        try:
            resp = await recommendations.recommendations(req, user=user)
            body = json.loads(resp.body)
            stored = await live.owner.fetchval(
                "SELECT count(*) FROM recommendations WHERE rec_id = $1", body.get("rec_id")
            )
        finally:
            if await live.owner.fetchval(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            ):
                async with live.owner.transaction():
                    await live.owner.execute("SET LOCAL session_replication_role = replica")
                    await live.owner.execute(
                        "DELETE FROM event_outbox WHERE event_id IN "
                        "(SELECT event_id FROM events WHERE tenant_id::text = $1)",
                        live.tenant_a,
                    )
                    await live.owner.execute(
                        "DELETE FROM events WHERE tenant_id::text = $1", live.tenant_a
                    )
                    await live.owner.execute(
                        "DELETE FROM recommendations WHERE tenant_id = $1::uuid", live.tenant_a
                    )
        assert body["delivered"] is True, body
        assert body["persisted"] is True, body
        assert stored == 1

    _run(case)


# ── R-H6: notification preferences ─────────────────────────────────────────


def test_notification_preferences_are_saved_and_then_updated_in_place(monkeypatch):
    main, _, notifications, _ = _platform()

    async def case(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        user = _user(live.tenant_a)
        first = main.NotificationPreferences(email_enabled=True, email_address="a@example.org")
        second = main.NotificationPreferences(email_enabled=True, email_address="b@example.org")
        await notifications.update_notification_preferences(first, user=user)
        out = await notifications.update_notification_preferences(second, user=user)
        rows = await live.owner.fetch(
            "SELECT email_address FROM notification_preferences "
            "WHERE tenant_id = $1::uuid AND user_ref = $2",
            live.tenant_a,
            user.user_id,
        )
        assert out.email_address == "b@example.org"
        assert [r["email_address"] for r in rows] == ["b@example.org"]

    _run(case)
