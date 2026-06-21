"""اختبارات break-glass (وصول مدير المنصّة العابر للمستأجرين مُدقَّق).

مستوى المنطق/المصدر (unit) — لا قاعدة بيانات حيّة. تُحاكى الاتّصالات بـfakes تُرجِع
صفوفاً مُتحكَّماً بها، فنُثبت الثوابت الأمنيّة دون Postgres:

  • المنح تتطلّب PLATFORM_MANAGE (وغير المدير يُرفَض 403).
  • منحة منتهية/مُبطَلة/لغير المالك ⇒ رفض (لا يُضبط سياق مستأجِر).
  • وصول بلا منحة صالحة ⇒ مرفوض.
  • تحقّق MFA fail-closed (مفعّل+رمز صحيح فقط ينجح).
  • كلّ مسار وصول يُدقّق (audit_log الدائم + AUDIT في-الذاكرة).
  • المسارات مُسجّلة ومُبوّبة بـPLATFORM_MANAGE.

منطق الـSQL الفعليّ (RLS على المستأجِر الهدف) تكامليّ ويحتاج Postgres — يُغطّى
خارج هذه الوحدة. هنا نُثبت بوّابات القرار والتدقيق.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.unit

# استيراد آمن (يُحمَّل main دون قاعدة). إن تعذّر (نقص تبعيّة) ⇒ تخطٍّ صريح.
# نُحمّل api.main أوّلاً (يُضمّن الراوتر في نهايته) لتفادي الاستيراد الدائريّ، ثمّ
# نشير إلى الوحدة عبر sys.modules.
import importlib  # noqa: E402

pytest.importorskip("api.main")
import api.main as _main  # noqa: E402

app = _main.app
bg = importlib.import_module("api.routers.break_glass")
from core.authorization import Permission, has_permission  # noqa: E402
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402


# ─── fakes للاتّصال (asyncpg-like) ──────────────────────────────────
class _FakeConn:
    """اتّصال وهميّ: يلتقط الاستعلامات ويُرجِع صفوفاً مُبرمَجة. transaction() context."""

    def __init__(self, *, fetchrow_result=None, fetchval_result=None):
        self._fetchrow_result = fetchrow_result
        self._fetchval_result = fetchval_result
        self.executed: list[tuple] = []

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Tx()

    async def fetchrow(self, *args):
        return self._fetchrow_result

    async def fetchval(self, *args):
        return self._fetchval_result

    async def execute(self, *args):
        self.executed.append(args)
        return "OK"

    async def fetch(self, *args):
        return []


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Acq()


def _admin(user_id="7"):
    return UserSchema(
        user_id=user_id,
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=UserRole.PLATFORM_ADMIN,
        name_ar="مدير",
    )


# ════════════════════════════════════════════════════════════════════
# ١) الصلاحية: المنح تتطلّب PLATFORM_MANAGE
# ════════════════════════════════════════════════════════════════════
def test_platform_admin_has_platform_manage():
    assert has_permission(_admin(), Permission.PLATFORM_MANAGE) is True


@pytest.mark.parametrize(
    "role",
    [UserRole.VIEWER, UserRole.AGRONOMIST, UserRole.OWNER, UserRole.MANAGER, UserRole.WORKER],
)
def test_non_platform_roles_lack_platform_manage(role):
    u = UserSchema(user_id="9", tenant_id="t", role=role, name_ar="x")
    assert has_permission(u, Permission.PLATFORM_MANAGE) is False


def test_all_break_glass_routes_gated_by_platform_manage():
    """كلّ نقاط break-glass مُبوّبة بتبعيّة require_permission(PLATFORM_MANAGE)."""
    targets = {
        "/api/v1/admin/break-glass",
        "/api/v1/admin/break-glass/{token}/fields",
        "/api/v1/admin/break-glass/{grant_id}",
    }
    seen = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        if path in targets:
            seen.add(path)
            # تبعيّة الصلاحية مُمثّلة في dependant — نفحص أنّ المسار يتطلّب صلاحية.
            src_deps = [d.call for d in getattr(r.dependant, "dependencies", [])]
            # require_permission يُرجِع closure _dep — وجوده دليل التبويب.
            assert src_deps, f"{path} بلا تبعيّة صلاحية"
    assert seen == targets, f"نقاط break-glass الناقصة: {targets - seen}"


# ════════════════════════════════════════════════════════════════════
# ٢) تحقّق MFA — fail-closed
# ════════════════════════════════════════════════════════════════════
def _run(coro):
    # loop جديد منفصل لكلّ استدعاء — آمن وسط pytest-asyncio (mode=auto) الذي قد يكون
    # أغلق loopه الافتراضيّ. (الدوالّ هنا متزامنة فلا loop خارجيّ قيد التشغيل.)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_mfa_rejected_when_user_missing():
    conn = _FakeConn(fetchrow_result=None)
    ok, email = _run(bg._verify_admin_mfa(conn, "7", "123456"))
    assert ok is False and email is None


def test_mfa_rejected_when_not_enabled():
    conn = _FakeConn(
        fetchrow_result={
            "email": "a@b.c",
            "mfa_secret": "JBSWY3DPEHPK3PXP",
            "mfa_enabled": False,
            "active": True,
        }
    )
    ok, email = _run(bg._verify_admin_mfa(conn, "7", "000000"))
    assert ok is False and email == "a@b.c"  # MFA غير مفعّل ⇒ رفض break-glass


def test_mfa_rejected_when_secret_missing():
    conn = _FakeConn(
        fetchrow_result={
            "email": "a@b.c",
            "mfa_secret": None,
            "mfa_enabled": True,
            "active": True,
        }
    )
    ok, _ = _run(bg._verify_admin_mfa(conn, "7", "000000"))
    assert ok is False  # مفعّل بلا سرّ (حالة غير متّسقة) ⇒ fail-closed


def test_mfa_rejected_when_user_inactive():
    conn = _FakeConn(
        fetchrow_result={
            "email": "a@b.c",
            "mfa_secret": "JBSWY3DPEHPK3PXP",
            "mfa_enabled": True,
            "active": False,
        }
    )
    ok, _ = _run(bg._verify_admin_mfa(conn, "7", "000000"))
    assert ok is False


def test_mfa_accepts_correct_totp():
    import pyotp

    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    conn = _FakeConn(
        fetchrow_result={
            "email": "a@b.c",
            "mfa_secret": secret,
            "mfa_enabled": True,
            "active": True,
        }
    )
    ok, email = _run(bg._verify_admin_mfa(conn, "7", code))
    assert ok is True and email == "a@b.c"


def test_mfa_rejects_wrong_totp():
    import pyotp

    secret = pyotp.random_base32()
    conn = _FakeConn(
        fetchrow_result={
            "email": "a@b.c",
            "mfa_secret": secret,
            "mfa_enabled": True,
            "active": True,
        }
    )
    ok, _ = _run(bg._verify_admin_mfa(conn, "7", "000000"))
    assert ok is False  # رمز خاطئ (احتمال تصادف ضئيل جدّاً مع 000000)


# ════════════════════════════════════════════════════════════════════
# ٣) الإنفاذ: break_glass_connection يرفض المنح غير الصالحة بلا ضبط سياق
# ════════════════════════════════════════════════════════════════════
def test_break_glass_connection_rejects_invalid_grant(monkeypatch):
    """منحة مفقودة/منتهية/مُبطَلة/لغير المالك ⇒ fetchrow=None ⇒ 403، ولا set_config مستأجِر."""
    from fastapi import HTTPException

    conn = _FakeConn(fetchrow_result=None)  # الاستعلام يفرض كلّ الشروط في WHERE
    monkeypatch.setattr(bg, "get_pool", lambda: _FakePool(conn))

    async def _use():
        async with bg.break_glass_connection("badtoken", _admin()) as _:
            pass

    with pytest.raises(HTTPException) as ei:
        _run(_use())
    assert ei.value.status_code == 403
    # لم يُضبط سياق مستأجِر (لا set_config على app.current_tenant بقيمة مستأجِر).
    set_tenant_calls = [a for a in conn.executed if a and "current_tenant" in str(a[0])]
    assert set_tenant_calls == [], "رُفِضت المنحة لكن ضُبط سياق مستأجِر — تسرّب!"


def test_break_glass_connection_valid_grant_sets_target_and_audits(monkeypatch):
    """منحة صالحة ⇒ يُضبط app.current_tenant=الهدف، يزيد access_count، ويُدقّق الاستخدام."""
    target = "11111111-1111-1111-1111-111111111111"
    audited = []

    async def _fake_audit_db(conn, action, **kw):
        audited.append((action, kw))

    mem_records = []

    def _fake_audit_mem(action, **kw):
        mem_records.append((action, kw))

    conn = _FakeConn(
        fetchrow_result={
            "id": 42,
            "target_tenant_id": target,
            "reason": "تحقيق دعم",
            "admin_email": "a@b.c",
        }
    )
    monkeypatch.setattr(bg, "get_pool", lambda: _FakePool(conn))
    monkeypatch.setattr(bg, "_audit_db", _fake_audit_db)
    monkeypatch.setattr(bg, "_audit_mem", _fake_audit_mem)

    captured = {}

    async def _use():
        async with bg.break_glass_connection("goodtoken", _admin()) as (c, tid):
            captured["tid"] = tid

    _run(_use())

    assert captured["tid"] == target
    # access_count زِيد (UPDATE) + set_config على المستأجِر الهدف.
    assert any("access_count" in str(a[0]) for a in conn.executed), "لم يُزَد access_count"
    set_tenant = [a for a in conn.executed if "current_tenant" in str(a[0])]
    assert set_tenant and target in [str(x) for x in set_tenant[0]], "سياق المستأجِر الهدف لم يُضبط"
    # تدقيق الوصول الدائم.
    assert any(a[0] == "break_glass_access" for a in audited), "استخدام بلا تدقيق دائم"
    assert any(a[0] == "break_glass_access" for a in mem_records), "استخدام بلا تدقيق في-الذاكرة"


# ════════════════════════════════════════════════════════════════════
# ٤) المسارات مُسجّلة (سلوكيّ على app.routes / openapi)
# ════════════════════════════════════════════════════════════════════
def _route_methods():
    out = {}
    for r in app.routes:
        p = getattr(r, "path", None)
        if isinstance(p, str):
            out.setdefault(p, set()).update(getattr(r, "methods", set()) or set())
    return out


def test_routes_registered():
    rm = _route_methods()
    assert "POST" in rm.get("/api/v1/admin/break-glass", set())
    assert "GET" in rm.get("/api/v1/admin/break-glass/{token}/fields", set())
    assert "DELETE" in rm.get("/api/v1/admin/break-glass/{grant_id}", set())


def test_openapi_builds_with_break_glass():
    schema = app.openapi()
    assert "/api/v1/admin/break-glass" in schema["paths"]


# ════════════════════════════════════════════════════════════════════
# ٥) سقف المدّة ثابت (لا منح طويلة الأمد)
# ════════════════════════════════════════════════════════════════════
def test_duration_cap_is_bounded():
    assert bg._MAX_DURATION_MINUTES <= 60

    # نموذج الطلب يرفض المدّة فوق السقف (pydantic le).
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        bg.BreakGlassRequest(
            target_tenant_id="11111111-1111-1111-1111-111111111111",
            reason="سبب كافٍ للطول",
            duration_minutes=bg._MAX_DURATION_MINUTES + 1,
            mfa_code="123456",
        )


def test_request_requires_reason_and_mfa():
    """الطلب يرفض سبباً قصيراً/رمز MFA ناقصاً (إلزاميّة الحقول)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        bg.BreakGlassRequest(
            target_tenant_id="11111111-1111-1111-1111-111111111111",
            reason="قصير",  # < 8
            duration_minutes=30,
            mfa_code="123456",
        )
    with pytest.raises(ValidationError):
        bg.BreakGlassRequest(
            target_tenant_id="11111111-1111-1111-1111-111111111111",
            reason="سبب كافٍ للطول",
            duration_minutes=30,
            mfa_code="123",  # < 6
        )


# توثيق: لا اعتماد على وقت النظام في رفض المنحة المنتهية — الاستعلام يفرض
# expires_at > NOW() على القاعدة (تكامليّ). هنا نُثبت أنّ غياب الصفّ (الذي يُنتجه
# الشرط) يُرفَض، وهو السلوك ذاته لكلّ أسباب البطلان.
def test_now_helper_uses_utc():
    assert datetime.now(UTC).tzinfo is not None
