"""اختبارات سجلّ تدقيق الرفض الأمنيّ (core.tenant_audit) — نقيّ offline."""

import asyncio
import json
from datetime import datetime

import pytest
from core.tenant_audit import (
    AUDIT,
    DENIAL_STORE,
    DenialRecord,
    DenialStore,
    TenantAuditLog,
    denial_row,
)

pytestmark = pytest.mark.unit


def test_record_recent_newest_first_and_summary():
    log = TenantAuditLog(maxlen=50)
    log.record(
        "tenant_scope",
        user_id="u1",
        tenant_id="t1",
        resource="field",
        action="read",
        reason_ar="خارج النطاق",
    )
    log.record(
        "permission",
        user_id="u2",
        tenant_id="t1",
        action="harvest:authorize",
        reason_ar="صلاحية غير كافية",
    )
    log.record("auth", user_id="u3", reason_ar="توكن غير صالح")
    recent = log.recent()
    assert [r["kind"] for r in recent] == ["auth", "permission", "tenant_scope"]  # الأجدد أوّلاً
    s = log.summary()
    assert s["total"] == 3
    assert s["by_kind"] == {"tenant_scope": 1, "permission": 1, "auth": 1}
    assert s["last_at"] is not None


def test_ring_buffer_caps_at_maxlen():
    log = TenantAuditLog(maxlen=3)
    for i in range(5):
        log.record("permission", user_id=f"u{i}", action="x")
    assert log.summary()["total"] == 3  # أقدم اثنين أُسقطا
    users = [r["user_id"] for r in log.recent()]
    assert users == ["u4", "u3", "u2"]


def test_recent_limit():
    log = TenantAuditLog()
    for i in range(5):
        log.record("auth", user_id=f"u{i}")
    assert len(log.recent(limit=2)) == 2


def test_record_never_raises_on_missing_fields():
    log = TenantAuditLog()
    rec = log.record("tenant_scope")  # كلّ الحقول الاختياريّة None
    assert isinstance(rec, DenialRecord)
    assert rec.user_id is None and rec.detail == {}


def test_unknown_kind_normalizes_to_permission():
    log = TenantAuditLog()
    rec = log.record("garbage")
    assert rec.kind == "permission"


def test_clear_empties():
    log = TenantAuditLog()
    log.record("auth", user_id="u")
    log.clear()
    assert log.summary()["total"] == 0


def test_record_carries_no_secret_fields():
    # خصوصيّة: حقول السجلّ مُعرّفات فقط — لا token/secret/password.
    fields = set(DenialRecord.__dataclass_fields__.keys())
    assert fields == {
        "at",
        "kind",
        "user_id",
        "tenant_id",
        "resource",
        "action",
        "reason_ar",
        "detail",
    }
    for forbidden in ("token", "secret", "password", "jwt", "authorization"):
        assert forbidden not in fields


def test_module_singleton_usable():
    AUDIT.clear()
    AUDIT.record(
        "tenant_scope", user_id="u", tenant_id="t", resource="field", action="read", reason_ar="x"
    )
    assert AUDIT.summary()["total"] == 1
    AUDIT.clear()


def test_tenant_scope_hides_other_tenants_and_global_events():
    log = TenantAuditLog()
    log.record("permission", user_id="uA", tenant_id="tenant-A", action="read")
    log.record("permission", user_id="uB", tenant_id="tenant-B", action="write")
    log.record("auth", user_id="system")
    assert [r["user_id"] for r in log.recent(tenant_id="tenant-A")] == ["uA"]
    assert log.summary(tenant_id="tenant-A")["total"] == 1
    assert log.summary(tenant_id="tenant-B")["total"] == 1
    assert log.summary(tenant_id="unknown")["total"] == 0
    assert log.summary()["total"] == 3


def test_tenant_limit_applies_after_scope_filter():
    log = TenantAuditLog()
    log.record("permission", user_id="a1", tenant_id="A")
    log.record("permission", user_id="b1", tenant_id="B")
    log.record("permission", user_id="a2", tenant_id="A")
    assert [r["user_id"] for r in log.recent(limit=1, tenant_id="A")] == ["a2"]


# ─── الإدامة (DenialStore): منطق الطابور والصفّ — سلوك القاعدة يُثبَت حيّاً في
# tests_v9/test_platform_denial_log_persistent_live_pg.py (لا اتّصال وهميّ هنا) ───

_TENANT = "1b4e28ba-2fa1-41d2-883f-0016d3cca427"


def test_singleton_records_into_the_shared_store():
    assert AUDIT.store is DENIAL_STORE


def test_unbound_store_queues_nothing_so_memory_behaviour_is_unchanged():
    store = DenialStore()
    log = TenantAuditLog(store=store)
    log.record("permission", user_id="u", tenant_id=_TENANT)
    assert store.stats()["pending"] == 0
    assert log.summary()["total"] == 1


def test_bound_store_queues_each_record_without_io():
    store = DenialStore()
    store.bind(lambda: None)
    log = TenantAuditLog(store=store)
    log.record("permission", user_id="u1", tenant_id=_TENANT)
    log.record("auth", user_id="u2")
    assert store.stats()["pending"] == 2


def test_queue_is_bounded_and_counts_what_it_drops():
    store = DenialStore(maxlen=3)
    store.bind(lambda: None)
    log = TenantAuditLog(store=store)
    for i in range(5):
        log.record("permission", user_id=f"u{i}", tenant_id=_TENANT)
    assert store.stats()["pending"] == 3
    assert store.stats()["dropped"] == 2


def test_record_never_raises_when_the_store_fails():
    class Broken(DenialStore):
        def enqueue(self, rec):
            raise RuntimeError("store down")

    log = TenantAuditLog(store=Broken())
    rec = log.record("permission", user_id="u", tenant_id=_TENANT)
    assert rec.kind == "permission"
    assert log.summary()["total"] == 1


def test_flush_without_a_pool_writes_nothing_and_keeps_the_queue():
    store = DenialStore()
    store.bind(lambda: None)
    TenantAuditLog(store=store).record("permission", tenant_id=_TENANT)
    assert asyncio.run(store.flush()) == 0
    assert store.stats()["pending"] == 1


def test_flush_survives_a_pool_getter_that_raises():
    def getter():
        raise RuntimeError("no pool")

    store = DenialStore()
    store.bind(getter)
    TenantAuditLog(store=store).record("permission", tenant_id=_TENANT)
    assert asyncio.run(store.flush()) == 0


def test_unbound_durable_read_returns_none_so_the_endpoint_uses_memory():
    store = DenialStore()

    def connect():
        raise AssertionError("must not connect when unbound")

    assert asyncio.run(store.read_durable(connect, _TENANT, None, capacity=200)) is None


def test_durable_read_failure_degrades_to_none():
    store = DenialStore()
    store.bind(lambda: None)

    def connect():
        raise RuntimeError("database unavailable")

    assert asyncio.run(store.read_durable(connect, _TENANT, 5, capacity=200)) is None


def test_stop_unbinds_and_clears_the_queue():
    store = DenialStore()
    store.bind(lambda: None)
    TenantAuditLog(store=store).record("permission", tenant_id=_TENANT)

    async def run():
        store.start()
        await store.stop()

    asyncio.run(run())
    assert store.stats()["bound"] is False
    assert store.stats()["pending"] == 0


def test_row_for_an_attributed_denial():
    rec = TenantAuditLog().record(
        "permission", user_id="42", tenant_id=_TENANT.upper(), action="audit:view", reason_ar="x"
    )
    tenant, (action, user_id, details, tenant_arg, created_at) = denial_row(rec)
    assert tenant == tenant_arg == _TENANT  # canonical UUID text
    assert action == "denial:permission"
    assert user_id == 42
    assert isinstance(created_at, datetime) and created_at.isoformat() == rec.at
    assert json.loads(details) == rec.to_dict()  # the response item, verbatim


@pytest.mark.parametrize("tenant", [None, "", "tenant-A", "not-a-uuid"])
def test_row_without_a_uuid_tenant_is_stored_unattributed(tenant):
    rec = TenantAuditLog().record("tenant_scope", user_id="den-viewer-1", tenant_id=tenant)
    stored_tenant, args = denial_row(rec)
    assert stored_tenant is None and args[3] is None
    assert args[1] is None  # a non-numeric subject never reaches the integer FK column
    assert json.loads(args[2])["tenant_id"] == tenant  # the claimed value stays readable


def test_action_fits_the_audit_log_column():
    for kind in ("tenant_scope", "permission", "auth"):
        rec = TenantAuditLog().record(kind)
        assert len(denial_row(rec)[1][0]) <= 50  # audit_log.action VARCHAR(50)
