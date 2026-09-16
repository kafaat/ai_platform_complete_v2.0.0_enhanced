"""M4: مخزنُ مهامّ التهيئة على جدول processing_jobs القائم.

مصدرُه حزمةُ استئناف B6/M4 المُسلَّمة من المالك؛ نُقِل إلى المستودع كي **يحجب الدمج**
بدل أن يبقى في حزمةٍ خارجيّة لا يُشغّلها أحد. أُعيد توجيه مسارات المصدر إلى مواضعها
بعد التطبيق: الشظايا التي كانت في `append/` صارت داخل ملفّات الخدمات نفسها.
"""

import copy
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from test_b6m4_field_bootstrap import FIELD, GEOMETRY, NOW, OTHER, TENANT, journal

from shared.field_bootstrap import ClaimedJob, LeaseLost

pytestmark = pytest.mark.unit


def module():
    path = Path(__file__).resolve().parents[1] / "services/sahool-platform/api/onboarding.py"
    spec = importlib.util.spec_from_file_location("platform_store_extension", path)
    result = importlib.util.module_from_spec(spec)
    # التسجيل قبل التنفيذ: الوحدةُ صارت ملفَّ خدمةٍ كاملاً فيه dataclasses، و`_is_type`
    # تقرأ `sys.modules[cls.__module__]` عند حلّ التلميحات ⇒ None بلا تسجيل.
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


class Connection:
    def __init__(self, tenant=TENANT, transaction=True):
        self.tenant = tenant
        self.transaction = transaction
        self.calls = []
        self.existing = None
        self.write_result = 11
        self.row = None
        self.created_at = NOW
        self.rows = [{"id": 11}]
        self.fail_insert = False

    def is_in_transaction(self):
        return self.transaction

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        if "current_setting" in sql:
            return self.tenant
        if "SELECT created_at" in sql:
            return self.created_at
        if sql.startswith("SELECT id"):
            return self.existing
        if sql.startswith("INSERT") and self.fail_insert:
            raise RuntimeError("database failure")
        return self.write_result

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return copy.deepcopy(self.row)

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.rows


class Connections:
    def __init__(self, conn):
        self.conn = conn
        self.exits = 0

    @asynccontextmanager
    async def __call__(self):
        yield self.conn
        self.exits += 1


@pytest.mark.parametrize("tenant,active", [(OTHER, True), (None, True), (TENANT, False)])
@pytest.mark.asyncio
async def test_enqueue_requires_existing_tenant_transaction(tenant, active):
    conn = Connection(tenant, active)
    with pytest.raises(RuntimeError, match="requires"):
        await module().enqueue_field_bootstrap(
            conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, created_at=NOW
        )
    assert not any(sql.startswith("INSERT") for _, sql, _ in conn.calls)


@pytest.mark.asyncio
async def test_enqueue_serializes_missing_row_without_nonexistent_unique_key():
    conn = Connection()
    out = await module().enqueue_field_bootstrap(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, created_at=NOW
    )
    assert out == 11
    names = [sql for _, sql, _ in conn.calls]
    lock = next(i for i, sql in enumerate(names) if "pg_advisory_xact_lock" in sql)
    lookup = next(i for i, sql in enumerate(names) if sql.startswith("SELECT id"))
    insert = next(i for i, sql in enumerate(names) if sql.startswith("INSERT"))
    assert lock < lookup < insert
    assert (
        "RETURNING id" in names[insert]
    )  # job_id has no uniqueness constraint in the existing schema.
    assert not any(sql.upper().startswith(("COMMIT", "ROLLBACK", "SET ")) for sql in names)


@pytest.mark.asyncio
async def test_existing_scope_is_not_inserted_again():
    conn = Connection()
    conn.existing = 19
    result = await module().enqueue_field_bootstrap(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, created_at=NOW
    )
    assert result == 19
    assert not any(sql.startswith("INSERT") for _, sql, _ in conn.calls)


@pytest.mark.asyncio
async def test_enqueue_failure_is_not_softened():
    conn = Connection()
    conn.fail_insert = True
    with pytest.raises(RuntimeError, match="database failure"):
        await module().enqueue_field_bootstrap(
            conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, created_at=NOW
        )


@pytest.mark.asyncio
async def test_rollout_off_does_not_touch_database(monkeypatch):
    monkeypatch.delenv("FIELD_BOOTSTRAP_ENABLED", raising=False)
    conn = Connection()
    result = await module().maybe_enqueue_field_bootstrap(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY
    )
    assert result is None and conn.calls == []


@pytest.mark.asyncio
async def test_rollout_uses_persisted_field_creation_time(monkeypatch):
    monkeypatch.setenv("FIELD_BOOTSTRAP_ENABLED", "true")
    conn = Connection()
    await module().maybe_enqueue_field_bootstrap(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY
    )
    read = next(args for _, sql, args in conn.calls if sql.startswith("SELECT created_at"))
    assert read == (FIELD, TENANT)
    write = next(args for _, sql, args in conn.calls if sql.startswith("INSERT"))
    assert journal()["scope_key"] in write[3]


@pytest.mark.asyncio
async def test_missing_field_timestamp_fails_atomic_enqueue(monkeypatch):
    monkeypatch.setenv("FIELD_BOOTSTRAP_ENABLED", "true")
    conn = Connection()
    conn.created_at = None
    with pytest.raises(RuntimeError, match="creation_time_unavailable"):
        await module().maybe_enqueue_field_bootstrap(
            conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY
        )


@pytest.mark.asyncio
async def test_due_query_excludes_live_leases_and_future_retry_rows():
    conn = Connection()
    factory = Connections(conn)
    store = module().PlatformBootstrapStore(factory, tenant_id=TENANT)
    assert await store.due_job_ids() == [11]
    sql, args = next((sql, args) for kind, sql, args in conn.calls if kind == "fetch")
    assert "tenant_id=$1::uuid" in sql and args[:2] == (TENANT, "field_bootstrap_v1")
    assert "next_attempt_at" in sql and "expires_at" in sql and "clock_timestamp()" in sql
    assert factory.exits == 1


@pytest.mark.asyncio
async def test_claim_commits_before_exposing_ephemeral_token():
    conn = Connection()
    j = journal()
    conn.row = {
        "id": 11,
        "field_id": FIELD,
        "result": {"journal": j, "lease": None},
        "parameters": {"scope_key": j["scope_key"]},
    }
    factory = Connections(conn)
    store = module().PlatformBootstrapStore(factory, tenant_id=TENANT)
    claimed = await store.claim(11)
    assert isinstance(claimed, ClaimedJob) and claimed.job_id == 11 and len(claimed.token) == 36
    assert factory.exits == 1
    sql = next(sql for kind, sql, _ in conn.calls if kind == "fetchrow")
    assert "FOR UPDATE SKIP LOCKED" in sql and "tenant_id=$2::uuid" in sql


@pytest.mark.asyncio
async def test_claimed_row_scope_is_checked_again():
    conn = Connection()
    j = journal()
    conn.row = {
        "id": 11,
        "field_id": "wrong",
        "result": {"journal": j},
        "parameters": {"scope_key": j["scope_key"]},
    }
    store = module().PlatformBootstrapStore(Connections(conn), tenant_id=TENANT)
    with pytest.raises(RuntimeError, match="stored_scope_mismatch"):
        await store.claim(11)
    assert not any(sql.startswith("UPDATE") for _, sql, _ in conn.calls)


@pytest.mark.asyncio
async def test_expired_or_replaced_token_cannot_checkpoint():
    conn = Connection()
    conn.write_result = None
    store = module().PlatformBootstrapStore(Connections(conn), tenant_id=TENANT)
    with pytest.raises(LeaseLost):
        await store.checkpoint(11, "old-token", journal())
    sql, args = next((sql, args) for _, sql, args in conn.calls if sql.startswith("UPDATE"))
    assert "result->'lease'->>'token'=$4" in sql and "clock_timestamp()" in sql
    assert "parameters->>'scope_key'=$9" in sql and args[1] == TENANT


@pytest.mark.asyncio
async def test_foreign_journal_is_rejected_before_database():
    conn = Connection()
    store = module().PlatformBootstrapStore(Connections(conn), tenant_id=OTHER)
    with pytest.raises(RuntimeError, match="tenant_mismatch"):
        await store.finish(11, "worker", journal())
    assert conn.calls == []


@pytest.mark.parametrize("lease", [0, 59, 301, True])
def test_lease_bounds_reject_invalid_settings(lease):
    with pytest.raises(ValueError):
        module().PlatformBootstrapStore(
            Connections(Connection()), tenant_id=TENANT, lease_seconds=lease
        )


@pytest.mark.asyncio
async def test_scheduler_rollout_off_cannot_claim_or_discover_tenants(monkeypatch):
    monkeypatch.delenv("FIELD_BOOTSTRAP_ENABLED", raising=False)
    conn = Connection()
    result = await module().run_field_bootstrap_once(
        connection_factory=Connections(conn),
        tenant_id=TENANT,
        handlers={},
        load_current_geometry_digest=None,
    )
    assert result["enabled"] is False and result["claimed"] == 0 and conn.calls == []


@pytest.mark.asyncio
async def test_persisted_progress_tracks_completed_steps_not_agronomy_readiness():
    from test_b6m4_field_bootstrap import handlers, run

    j = journal()
    completed, _ = await run(j, handlers(j))
    conn = Connection()
    store = module().PlatformBootstrapStore(Connections(conn), tenant_id=TENANT)
    await store.finish(11, "worker", completed)
    sql, args = next((sql, args) for _, sql, args in conn.calls if sql.startswith("UPDATE"))
    assert "progress=$10" in sql and args[9] == 100
    assert completed["agronomy_ready"] is False


@pytest.mark.asyncio
async def test_creation_wrapper_keeps_existing_imagery_tracking_when_bootstrap_off(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    monkeypatch.delenv("FIELD_BOOTSTRAP_ENABLED", raising=False)
    package = ModuleType("api")
    package.__path__ = []
    imagery = ModuleType("api.imagery_automation")
    # العقدُ المدموج: الحزمةُ الأصليّة كانت تمرّر `guarded_bbox` وتسجّل الصورَ ومهمّةَ
    # التهيئة، و`main` كانت تسجّل الصورَ **والطقس** عبر `register_field_tracking_intents`
    # (#1009). المدخلُ الواحد يستدعي ذاك ثمّ مهمّةَ التهيئة، فلا يسقط عملُ أيّ طرف.
    intents = AsyncMock(return_value={"imagery": True, "weather": True})
    imagery.register_field_tracking_intents = intents
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.imagery_automation", imagery)
    conn = Connection()
    result = await module().register_field_creation_intents(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, lat=15.0, lon=44.0
    )
    intents.assert_awaited_once_with(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, lat=15.0, lon=44.0
    )
    # الرايةُ مطفأة ⇒ لا مهمّةَ تهيئة، ولا كتابةَ إضافيّة على الاتّصال.
    assert result == {"imagery": True, "weather": True, "bootstrap": False}
    assert conn.calls == []


@pytest.mark.asyncio
async def test_creation_wrapper_without_a_centroid_still_registers_tracking(monkeypatch):
    """بلا إحداثيّة مركز يبقى تسجيلُ الصور ويُعلَن غيابُ الطقس — لا يُختلَق موقع."""
    from types import ModuleType
    from unittest.mock import AsyncMock

    monkeypatch.delenv("FIELD_BOOTSTRAP_ENABLED", raising=False)
    package = ModuleType("api")
    package.__path__ = []
    imagery = ModuleType("api.imagery_automation")
    intents = AsyncMock(return_value={"imagery": True, "weather": False})
    imagery.register_field_tracking_intents = intents
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.imagery_automation", imagery)
    conn = Connection()
    result = await module().register_field_creation_intents(
        conn, tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, lat=None, lon=None
    )
    assert result == {"imagery": True, "weather": False, "bootstrap": False}
    assert conn.calls == []
