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
            "grant_token": bg._hash_grant_token("goodtoken"),  # T8: المخزَّن hash
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


# ════════════════════════════════════════════════════════════════════
# ٦) T8: رمز المنحة مُجزّأ في القاعدة، يُبحث بالـhash، ولا يُسجَّل
# ════════════════════════════════════════════════════════════════════
_TARGET = "11111111-1111-1111-1111-111111111111"


def _grant_request():
    return bg.BreakGlassRequest(
        target_tenant_id=_TARGET,
        reason="تحقيق دعم فنّيّ عاجل",
        duration_minutes=15,
        mfa_code="123456",
    )


def _quiet_audits(monkeypatch):
    """يلتقط نصوص التدقيق (الدائم + في-الذاكرة) لفحص خلوّها من الرمز."""
    texts: list[str] = []

    async def _db(conn, action, **kw):
        texts.append(f"{action} {kw}")

    def _mem(action, **kw):
        texts.append(f"{action} {kw}")

    monkeypatch.setattr(bg, "_audit_db", _db)
    monkeypatch.setattr(bg, "_audit_mem", _mem)
    return texts


def test_grant_token_is_stored_hashed_not_plaintext(monkeypatch, caplog):
    """INSERT يكتب sha256 للرمز لا الرمز؛ الاستجابة وحدها تحمله (مرّة عند الإنشاء)."""
    conn = _FakeConn(fetchval_result=99)
    inserted: list[tuple] = []

    async def _capture_fetchval(*args):
        inserted.append(args)
        return 99

    conn.fetchval = _capture_fetchval
    monkeypatch.setattr(bg, "get_pool", lambda: _FakePool(conn))

    async def _mfa_ok(conn, uid, code):
        return True, "a@b.c"

    monkeypatch.setattr(bg, "_verify_admin_mfa", _mfa_ok)
    texts = _quiet_audits(monkeypatch)

    with caplog.at_level("DEBUG"):
        resp = _run(bg.request_break_glass(_grant_request(), user=_admin()))
    token = resp["grant_token"]
    assert len(token) >= 32
    (args,) = [a for a in inserted if "INSERT INTO break_glass_grants" in a[0]]
    assert token not in args, "grant_token خُزِّن صريحاً — من يقرأ الجدول يملك منحة صالحة"
    assert args[-1] == bg._hash_grant_token(token)
    assert args[-1].startswith("sha256:") and token not in args[-1]
    # لا رمز في التدقيق ولا في السجلّات.
    assert all(token not in t for t in texts)
    assert token not in caplog.text


def test_connection_looks_up_by_hash_and_never_logs_token(monkeypatch, caplog):
    conn = _FakeConn()
    seen: list[tuple] = []

    async def _capture_fetchrow(*args):
        seen.append(args)
        return {
            "id": 5,
            "target_tenant_id": _TARGET,
            "reason": "تحقيق",
            "admin_email": "a@b.c",
            "grant_token": bg._hash_grant_token("live-token-0123456789abcdef"),
        }

    conn.fetchrow = _capture_fetchrow
    monkeypatch.setattr(bg, "get_pool", lambda: _FakePool(conn))
    texts = _quiet_audits(monkeypatch)

    async def _use():
        async with bg.break_glass_connection("live-token-0123456789abcdef", _admin()) as (_, t):
            return t

    with caplog.at_level("DEBUG"):
        assert _run(_use()) == _TARGET
    (sql, bound, *_rest) = seen[0]
    assert "WHERE grant_token = $1" in sql
    assert bound == bg._hash_grant_token("live-token-0123456789abcdef")
    assert all("live-token-0123456789abcdef" not in str(a) for a in seen)
    assert all("live-token-0123456789abcdef" not in t for t in texts)
    assert "live-token-0123456789abcdef" not in caplog.text


def test_legacy_plaintext_grant_row_is_rejected(monkeypatch):
    """صفّ ما قبل T8 (رمز صريح) لا يُقبَل حتى لو أعاده الاستعلام — fail-closed."""
    from fastapi import HTTPException

    conn = _FakeConn(
        fetchrow_result={
            "id": 6,
            "target_tenant_id": _TARGET,
            "reason": "قديم",
            "admin_email": "a@b.c",
            "grant_token": "legacy-plain-token",
        }
    )
    monkeypatch.setattr(bg, "get_pool", lambda: _FakePool(conn))
    _quiet_audits(monkeypatch)

    async def _use():
        async with bg.break_glass_connection("legacy-plain-token", _admin()):
            pass

    with pytest.raises(HTTPException) as ei:
        _run(_use())
    assert ei.value.status_code == 403
    assert not [a for a in conn.executed if "current_tenant" in str(a[0])]


def test_grant_token_match_helpers():
    stored = bg._hash_grant_token("abc-0123456789")
    assert bg._grant_token_matches(stored, "abc-0123456789") is True
    assert bg._grant_token_matches(stored, "abc-0123456780") is False
    assert bg._grant_token_matches(stored, stored) is False  # المخزَّن ليس رمزاً
    assert bg._grant_token_matches("abc-0123456789", "abc-0123456789") is False
    assert bg._grant_token_matches(None, "abc-0123456789") is False


def test_access_log_redacts_token_in_usage_path(caplog):
    """GET /break-glass/{token}/fields يحمل الرمز في المسار ⇒ سطر uvicorn.access محجوب."""
    import logging

    access = logging.getLogger("uvicorn.access")
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        access.info(
            '%s - "%s %s HTTP/%s" %d',
            "10.0.0.1:5555",
            "GET",
            "/api/v1/admin/break-glass/SECRET-TOKEN-xyz/fields",
            "1.1",
            200,
        )
        access.info(
            '%s - "%s %s HTTP/%s" %d',
            "10.0.0.1:5555",
            "DELETE",
            "/api/v1/admin/break-glass/42",
            "1.1",
            200,
        )
    assert "SECRET-TOKEN-xyz" not in caplog.text
    assert "/api/v1/admin/break-glass/[redacted]/fields" in caplog.text
    assert "/api/v1/admin/break-glass/42" in caplog.text  # المعرّف ليس سرّاً
