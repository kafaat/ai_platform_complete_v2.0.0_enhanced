"""D4/D5 على PostgreSQL حيّة: مسار ``POST /api/v1/irrigation/schedules`` الحقيقيّ.

ليس نسخةً من المنطق ولا اتّصالاً وهميّاً: الموجِّه الحقيقيّ عبر ASGI، و``tenant_connection``
و``CommandStore`` و``_idempotent`` الحقيقيّة على مسبح asyncpg بالدور المقيَّد
(``SAHOOL_TEST_PGROLE``، NOBYPASSRLS). والمخطّط يُبنى في قاعدةٍ مؤقّتة من ملفّات الهجرة
نفسها — ``v10_command_store_lifecycle.sql`` و``v25_irrigation.sql`` حرفيّاً، و``fields``
و``update_updated_at_column`` و``_sahool_apply_tenant_rls`` مقتطَعةً من ``v9_*``. الحدّ
المُعلَن: ``iot_devices`` هنا عمودٌ واحد (هدف المفتاح الأجنبيّ فقط)، ولا جدول أحداث،
فإصدار الحدث غير الحرج يرتدّ في نقطة حفظه كما يفعل حين يغيب الجدول.

ما يُقاس (مصفوفة القبول):

* R05 — طلبان متزامنان بالمفتاح نفسه، والأوّل يلتزم: الثاني **ينتظر قفل المفتاح في القاعدة**
  (مقيس من ``pg_stat_activity``) ثمّ يُعيد الناتج نفسه؛ صفّ جدول واحد وصفّ أمر واحد.
* R06 — الأوّل يرتدّ بعد إدراج الجدول: يرتدّ صفّ الأمر معه (معاملة واحدة)، والثاني ينفّذ.
* R07 — المفتاح نفسه بحمولةٍ مختلفة: 409 ``payload_mismatch`` بلا صفّ إضافيّ ولا تعديل.
* R13 — بعد مدّة الاحتفاظ: 409 ``retention_expired``، ولا تنفيذ ثانٍ ولا صفّ جديد.
* R14 — صمّام/حقل مستأجرٍ آخر: 404 مطابق حرفيّاً لغير الموجود، تحت الدور المقيَّد **وتحت
  المالك** الذي يتجاوز RLS؛ وصمّام حقلٍ يخالف ``field_id`` المُرسَل: 422 بلا صفّ.
* R15 — جدول بلا صمّام ولا حقل: 201 غير مرتبط (OD-1)، ولا يظهر في قائمة أيّ حقل.

التشغيل: ``SAHOOL_TEST_PGHOST=localhost PGPASSWORD=… pytest -m integration <this file>``.
بلا قاعدة ⇒ تخطٍّ مُعلَن؛ ومع ``SAHOOL_REQUIRE_LIVE_PG=1`` ⇒ فشل لا تخطٍّ.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")
from fastapi import Request  # noqa: E402 — بعد importorskip؛ يحتاجه حلّ تعليق override

_ROOT = Path(__file__).resolve().parent.parent
_PLATFORM = _ROOT / "services" / "sahool-platform"
_MIGRATIONS = _ROOT / "migrations"

_DB = os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool")
_HOST = os.environ.get("SAHOOL_TEST_PGHOST", "/var/run/postgresql")
_PORT = int(os.environ.get("SAHOOL_TEST_PGPORT", "5432"))
_APP_ROLE = os.environ.get("SAHOOL_TEST_PGROLE", "sahool_app")
_OWNER_ROLE = os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user")
_REQUIRE = os.environ.get("SAHOOL_REQUIRE_LIVE_PG") == "1"

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
_SCHED = "/api/v1/irrigation/schedules"
_BODY = {"name": "ريّ الفجر", "start_time": "06:30", "duration_min": 30, "enabled": True}


async def _probe() -> tuple[bool, str]:
    try:
        conn = await asyncpg.connect(host=_HOST, port=_PORT, user=_OWNER_ROLE, database=_DB)
    except Exception as exc:  # noqa: BLE001 — أيّ تعذّر اتّصال يُعلَن سبباً للتخطّي
        return False, f"{type(exc).__name__}: {exc}"
    try:
        restricted = await conn.fetchval(
            "SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname = $1", _APP_ROLE
        )
    finally:
        await conn.close()
    if not restricted:
        return False, f"الدور {_APP_ROLE} غائب أو يتجاوز RLS — لا يُقاس عليه عزل"
    return True, ""


_LIVE, _WHY = asyncio.run(_probe())
if _REQUIRE and not _LIVE:
    raise RuntimeError("SAHOOL_REQUIRE_LIVE_PG=1 والقاعدة غير متاحة: " + _WHY)
pytestmark.append(pytest.mark.skipif(not _LIVE, reason=f"تخطٍّ مُعلَن (ليس نجاحاً): {_WHY}"))


# ── المخطّط من ملفّات الهجرة ────────────────────────────────────────────


def _cut(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.S)
    assert match, f"{path.name}: لم يُعثر على {pattern}"
    return match.group(0)


def _schema_sql() -> str:
    foundation = _MIGRATIONS / "v9_foundation.sql"
    rls = _MIGRATIONS / "v9_rls_tenant_isolation.sql"
    return "\n".join(
        [
            _cut(
                foundation,
                r"CREATE OR REPLACE FUNCTION update_updated_at_column\(\).*?LANGUAGE plpgsql;",
            ),
            _cut(foundation, r"CREATE TABLE IF NOT EXISTS fields \(.*?\);"),
            "CREATE TABLE IF NOT EXISTS iot_devices (device_id VARCHAR(64) PRIMARY KEY);",
            _cut(
                rls,
                r"CREATE OR REPLACE FUNCTION _sahool_apply_tenant_rls\(p_table TEXT\).*?LANGUAGE plpgsql;",
            ),
            "SELECT _sahool_apply_tenant_rls('fields');",
            (_MIGRATIONS / "v10_command_store_lifecycle.sql").read_text(encoding="utf-8"),
            # v9_rls_tenant_isolation يضيف FORCE على commands (سياستها من v10).
            "ALTER TABLE commands FORCE ROW LEVEL SECURITY;",
            (_MIGRATIONS / "v25_irrigation.sql").read_text(encoding="utf-8"),
            f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE};",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_APP_ROLE};",
        ]
    )


@pytest.fixture(scope="module")
def scratch_db():
    name = f"sahool_d4d5_{uuid.uuid4().hex[:10]}"

    async def create():
        admin = await asyncpg.connect(host=_HOST, port=_PORT, user=_OWNER_ROLE, database=_DB)
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()
        conn = await asyncpg.connect(host=_HOST, port=_PORT, user=_OWNER_ROLE, database=name)
        try:
            await conn.execute(_schema_sql())
        finally:
            await conn.close()

    async def drop():
        admin = await asyncpg.connect(host=_HOST, port=_PORT, user=_OWNER_ROLE, database=_DB)
        try:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1", name
            )
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        finally:
            await admin.close()

    asyncio.run(create())
    try:
        yield name
    finally:
        asyncio.run(drop())


def _platform():
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    import api.main as main
    from api.routers import irrigation

    return main, irrigation


# ── تشغيل المسار الحقيقيّ ───────────────────────────────────────────────


class Live:
    """مسبح بدورٍ مُعطى + تطبيق ASGI بالموجِّه الحقيقيّ + اتّصال مالكٍ للقياس."""

    def __init__(self, db: str, monkeypatch, role: str = _APP_ROLE):
        self.db, self.role, self.mp = db, role, monkeypatch
        self.main, self.mod = _platform()
        self.hooks: list = []  # ما يجري داخل _work بعد إدراج الجدول، بترتيب الطلبات

    async def __aenter__(self):
        from api.main import get_current_user
        from core.canonical_schemas import UserRole, UserSchema
        from fastapi import FastAPI

        self.pool = await asyncpg.create_pool(
            host=_HOST, port=_PORT, user=self.role, database=self.db, min_size=1, max_size=6
        )
        self.owner = await asyncpg.connect(
            host=_HOST, port=_PORT, user=_OWNER_ROLE, database=self.db
        )
        self.mp.setattr(self.main, "_DB_POOL", self.pool)
        real_emit = self.mod._emit_domain_event

        async def emit(conn, user, event_type, *a, **kw):
            if event_type == "IRRIGATION_SCHEDULE_CREATED" and self.hooks:
                await self.hooks.pop(0)()
            return await real_emit(conn, user, event_type, *a, **kw)

        self.mp.setattr(self.mod, "_emit_domain_event", emit)

        def user(request: Request):
            return UserSchema(
                user_id="u-live",
                tenant_id=request.headers.get("x-test-tenant", TENANT_A),
                role=UserRole.MANAGER,
                name_ar="مدير",
            )

        app = FastAPI()
        app.include_router(self.mod.router)
        app.dependency_overrides[get_current_user] = user
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://live")
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        await self.owner.close()
        await self.pool.close()

    async def post(self, body, *, key=None, tenant=TENANT_A, raw: str | None = None):
        headers = {"x-test-tenant": tenant}
        if key:
            headers["Idempotency-Key"] = key
        if raw is not None:
            headers["Content-Type"] = "application/json"
            return await self.client.post(_SCHED, content=raw.encode(), headers=headers)
        return await self.client.post(_SCHED, json=body, headers=headers)

    async def get(self, *, field_id=None, tenant=TENANT_A):
        params = {"field_id": field_id} if field_id else None
        return await self.client.get(_SCHED, params=params, headers={"x-test-tenant": tenant})

    async def schedules(self, tenant=TENANT_A) -> list:
        return await self.owner.fetch(
            "SELECT schedule_id, field_id, valve_id FROM irrigation_schedules "
            "WHERE tenant_id = $1::uuid ORDER BY created_at",
            tenant,
        )

    async def command(self, key):
        return await self.owner.fetchrow(
            "SELECT command_type, status, result, created_at FROM commands WHERE command_id = $1",
            uuid.UUID(key),
        )

    async def reset(self):
        await self.owner.execute(
            "TRUNCATE irrigation_schedules, irrigation_valves, commands CASCADE"
        )
        await self.owner.execute("DELETE FROM fields")

    async def seed(self):
        await self.reset()
        for fid, tenant in (("fA", TENANT_A), ("fA2", TENANT_A), ("fB", TENANT_B)):
            await self.owner.execute(
                "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
                fid,
                tenant,
            )
        for vid, fid, tenant in (("vA", "fA", TENANT_A), ("vB", "fB", TENANT_B)):
            await self.owner.execute(
                "INSERT INTO irrigation_valves (valve_id, tenant_id, name, field_id) "
                "VALUES ($1, $2::uuid, $1, $3)",
                vid,
                tenant,
                fid,
            )


def _run(coro):
    return asyncio.run(coro)


def _result(row) -> dict:
    value = row["result"]
    return value if isinstance(value, dict) else json.loads(value)


# ── R05 / R06 / R07 ─────────────────────────────────────────────────────


def test_r05_concurrent_same_key_waits_on_the_db_and_returns_the_committed_result(
    scratch_db, monkeypatch
):
    key = str(uuid.uuid4())

    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()
            entered, release = asyncio.Event(), asyncio.Event()

            async def hold_first():
                entered.set()
                await release.wait()  # معاملة الأوّل مفتوحة بعد إدراج الجدول والأمر

            live.hooks.append(hold_first)
            first = asyncio.create_task(live.post({**_BODY, "valve_id": "vA"}, key=key))
            await asyncio.wait_for(entered.wait(), 10)
            second = asyncio.create_task(live.post({**_BODY, "valve_id": "vA"}, key=key))
            waiting = 0
            for _ in range(50):
                await asyncio.sleep(0.05)
                waiting = await live.owner.fetchval(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = $1 "
                    "AND wait_event_type = 'Lock' AND query ILIKE '%INSERT INTO commands%'",
                    scratch_db,
                )
                if waiting:
                    break
            assert waiting == 1, "الطلب الثاني لم ينتظر قفل المفتاح في القاعدة"
            assert not second.done()
            release.set()
            r1, r2 = await first, await second
            assert r1.status_code == 201, r1.text
            assert r2.status_code == 201, r2.text
            assert r1.json() == r2.json()
            rows = await live.schedules()
            assert [r["schedule_id"] for r in rows] == [r1.json()["schedule_id"]]
            cmd = await live.command(key)
            assert cmd["status"] == "succeeded" and _result(cmd) == r1.json()

    _run(scenario())


def test_r06_first_rolls_back_with_its_command_row_then_the_second_executes(
    scratch_db, monkeypatch
):
    key = str(uuid.uuid4())

    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()
            entered, release = asyncio.Event(), asyncio.Event()

            async def fail_first():
                entered.set()
                await release.wait()
                raise RuntimeError("فشلٌ بعد إدراج الجدول وصفّ الأمر")

            live.hooks.append(fail_first)
            first = asyncio.create_task(live.post(_BODY, key=key))
            await asyncio.wait_for(entered.wait(), 10)
            second = asyncio.create_task(live.post(_BODY, key=key))
            await asyncio.sleep(0.3)
            assert not second.done(), "الثاني لم ينتظر التزام الأوّل أو ارتداده"
            release.set()
            r1, r2 = await first, await second
            assert r1.status_code == 500
            assert r2.status_code == 201, r2.text
            rows = await live.schedules()
            assert [r["schedule_id"] for r in rows] == [r2.json()["schedule_id"]]
            cmd = await live.command(key)
            assert _result(cmd) == r2.json()

    _run(scenario())


def test_r06_a_failed_request_leaves_neither_the_schedule_nor_the_command(scratch_db, monkeypatch):
    """التغيير وسجلّ النتيجة في معاملةٍ واحدة: الفشل لا يُبقي «أمراً ناجحاً» بلا جدول."""
    key = str(uuid.uuid4())

    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()

            async def boom():
                raise RuntimeError("فشلٌ بعد الإدراج")

            live.hooks.append(boom)
            resp = await live.post(_BODY, key=key)
            assert resp.status_code == 500
            assert await live.schedules() == []
            assert await live.command(key) is None
            retry = await live.post(_BODY, key=key)
            assert retry.status_code == 201, retry.text
            assert len(await live.schedules()) == 1

    _run(scenario())


def test_r07_same_key_other_payload_is_a_reasoned_conflict_without_a_new_row(
    scratch_db, monkeypatch
):
    key = str(uuid.uuid4())

    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()
            first = await live.post(_BODY, key=key)
            assert first.status_code == 201
            # الحمولة المؤثّرة نفسها بترتيب مفاتيح آخر وبالثواني ⇒ إعادة صادقة.
            same = await live.post(
                None,
                key=key,
                raw='{"enabled":true,"duration_min":30,"start_time":"06:30:00","name":"ريّ الفجر"}',
            )
            assert same.status_code == 201 and same.json() == first.json()
            other = await live.post({**_BODY, "duration_min": 45}, key=key)
            assert other.status_code == 409
            assert other.json()["detail"]["reason"] == "payload_mismatch"
            assert "مفتاحاً جديداً" not in other.text
            rows = await live.schedules()
            assert [r["schedule_id"] for r in rows] == [first.json()["schedule_id"]]
            assert _result(await live.command(key)) == first.json()

    _run(scenario())


# ── R13 ─────────────────────────────────────────────────────────────────


def test_r13_after_retention_the_key_reconciles_and_never_executes_again(scratch_db, monkeypatch):
    monkeypatch.delenv("SAHOOL_IDEMPOTENCY_RETENTION_DAYS", raising=False)
    key = str(uuid.uuid4())

    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()
            first = await live.post(_BODY, key=key)
            assert first.status_code == 201
            await live.owner.execute(
                "UPDATE commands SET created_at = now() - interval '31 days' WHERE command_id = $1",
                uuid.UUID(key),
            )
            late = await live.post(_BODY, key=key)
            assert late.status_code == 409, late.text
            assert late.json()["detail"]["reason"] == "retention_expired"
            assert late.json()["detail"]["retention_days"] == 30
            assert first.json()["schedule_id"] not in late.text
            assert len(await live.schedules()) == 1  # لا تنفيذ ثانٍ ولا صفّ جديد

    _run(scenario())


# ── R14 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["app", "owner"])
def test_r14_foreign_valve_and_field_are_indistinguishable_from_missing(
    scratch_db, monkeypatch, role
):
    """تحت المالك (يتجاوز RLS) كان صمّام B يُقبَل لمستأجر A ويُشتقّ منه حقل B."""

    async def scenario():
        async with Live(
            scratch_db, monkeypatch, _APP_ROLE if role == "app" else _OWNER_ROLE
        ) as live:
            await live.seed()
            foreign_valve = await live.post({**_BODY, "valve_id": "vB"})
            missing_valve = await live.post({**_BODY, "valve_id": "v-none"})
            assert foreign_valve.status_code == missing_valve.status_code == 404
            assert foreign_valve.json() == missing_valve.json()
            foreign_field = await live.post({**_BODY, "field_id": "fB"})
            missing_field = await live.post({**_BODY, "field_id": "f-none"})
            assert foreign_field.status_code == missing_field.status_code == 404
            assert foreign_field.json() == missing_field.json()
            assert "fB" not in foreign_valve.text + foreign_field.text
            assert await live.schedules(TENANT_A) == []

    _run(scenario())


def test_r14_valve_of_another_field_contradicting_field_id_is_rejected(scratch_db, monkeypatch):
    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()
            resp = await live.post({**_BODY, "valve_id": "vA", "field_id": "fA2"})
            assert resp.status_code == 422
            assert await live.schedules() == []
            linked = await live.post({**_BODY, "valve_id": "vA"})
            assert linked.status_code == 201
            assert [r["field_id"] for r in await live.schedules()] == ["fA"]

    _run(scenario())


# ── R15 + OD-1 ──────────────────────────────────────────────────────────


def test_r15_unlinked_schedule_is_201_and_never_listed_under_a_field(scratch_db, monkeypatch):
    async def scenario():
        async with Live(scratch_db, monkeypatch) as live:
            await live.seed()
            unlinked = await live.post(_BODY, key=str(uuid.uuid4()))
            assert unlinked.status_code == 201, unlinked.text
            linked = await live.post({**_BODY, "name": "صمّام الحقل", "valve_id": "vA"})
            assert linked.status_code == 201
            stored = {r["schedule_id"]: r["field_id"] for r in await live.schedules()}
            assert stored[unlinked.json()["schedule_id"]] is None
            for field_id in ("fA", "fA2"):
                listed = await live.get(field_id=field_id)
                assert listed.status_code == 200
                ids = [s["schedule_id"] for s in listed.json()]
                assert unlinked.json()["schedule_id"] not in ids
            assert [s["schedule_id"] for s in (await live.get(field_id="fA")).json()] == [
                linked.json()["schedule_id"]
            ]
            everything = {s["schedule_id"]: s for s in (await live.get()).json()}
            assert everything[unlinked.json()["schedule_id"]]["field_id"] is None

    _run(scenario())
