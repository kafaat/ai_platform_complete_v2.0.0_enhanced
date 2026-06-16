"""اختبارات سجلّ تدقيق الرفض الأمنيّ (core.tenant_audit) — نقيّ offline."""

import pytest
from core.tenant_audit import AUDIT, DenialRecord, TenantAuditLog

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
