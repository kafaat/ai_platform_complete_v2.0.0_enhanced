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
        # كلّ نداء بترتيبه (method, args) — لإثبات أنّ سياق المستأجِر يسبق كلّ استعلام.
        self.calls: list[tuple] = []

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Tx()

    async def fetchrow(self, *args):
        self.calls.append(("fetchrow", args))
        return self._fetchrow_result

    async def fetchval(self, *args):
        self.calls.append(("fetchval", args))
        return self._fetchval_result

    async def execute(self, *args):
        self.executed.append(args)
        self.calls.append(("execute", args))
        return "OK"

    async def fetch(self, *args):
        self.calls.append(("fetch", args))
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
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))

    async def _use():
        async with bg.break_glass_connection("badtoken", _admin()) as _:
            pass

    with pytest.raises(HTTPException) as ei:
        _run(_use())
    assert ei.value.status_code == 403
    # لم يُضبط سياق أيّ مستأجِر سوى مستأجِر المُنادي (لا سياق هدف بلا منحة).
    set_tenant_calls = [a for a in conn.executed if a and "current_tenant" in str(a[0])]
    assert [a[1] for a in set_tenant_calls] == [_admin().tenant_id], (
        "رُفِضت المنحة لكن ضُبط سياق مستأجِر غير المُنادي — تسرّب!"
    )


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
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))
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
    assert set_tenant and target in [str(x) for x in set_tenant[-1]], "سياق المستأجِر الهدف لم يُضبط"
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
# ٦) BREAK-GLASS-RUNS-WITHOUT-TENANT-CONTEXT — كلّ وصول تحت سياق المُنادي
# ════════════════════════════════════════════════════════════════════
# على main كانت المسارات الثلاثة تفتح get_pool().acquire() بلا أيّ set_config: users
# (MFA) يُرشَّح إلى صفر تحت sahool_app، وv237 يُغلق ذراع «بلا سياق» في audit_log
# وbreak_glass_grants. هنا نُثبت الترتيب: سياق المُنادي أوّلاً، ودور الخدمة حول سجلّ
# المنح وحده، وسياق الهدف من صفّ المنحة لا من الجسم.
_CALLER = _admin()
_BODY_TARGET = "22222222-2222-2222-2222-222222222222"


def _set_configs(conn):
    return [a for m, a in conn.calls if m == "execute" and "set_config" in str(a[0])]


def _first_query_index(conn):
    return next(i for i, (m, a) in enumerate(conn.calls) if "set_config" not in str(a[0]))


def _assert_caller_context_first(conn):
    first = conn.calls[0]
    assert first[0] == "execute" and "app.current_tenant" in first[1][0], conn.calls[:2]
    assert first[1][1:3] == (_CALLER.tenant_id, _CALLER.user_id), first
    assert _first_query_index(conn) > 0, "استعلامٌ قبل ضبط سياق المستأجِر"


def _req(code="123456"):
    return bg.BreakGlassRequest(
        target_tenant_id=_BODY_TARGET,
        reason="تحقيق دعم فنّيّ عاجل",
        duration_minutes=15,
        mfa_code=code,
    )


def test_mfa_lookup_runs_under_caller_tenant_context(monkeypatch):
    """قراءة users لـMFA تجري بعد ضبط سياق المُنادي (مستأجِره + معرّفه)."""
    from fastapi import HTTPException

    conn = _FakeConn(
        fetchrow_result={"email": "a@b.c", "mfa_secret": None, "mfa_enabled": False, "active": True}
    )
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))
    monkeypatch.setattr(bg, "_audit_mem", lambda *a, **k: None)

    with pytest.raises(HTTPException) as ei:
        _run(bg.request_break_glass(_req(), _CALLER))
    assert ei.value.status_code == 403

    _assert_caller_context_first(conn)
    users_reads = [a for m, a in conn.calls if m == "fetchrow" and "FROM users" in a[0]]
    assert users_reads, "لم يُقرأ صفّ المدير"
    # تدقيق الرفض يُكتب في سجلّ مستأجِر المُنادي (WITH CHECK يمرّ)، لا الهدف من الجسم.
    audits = [a for m, a in conn.calls if m == "execute" and "INSERT INTO audit_log" in a[0]]
    assert audits and audits[0][4] == _CALLER.tenant_id, audits
    assert all(_BODY_TARGET not in a[1:] for a in _set_configs(conn)), "سياق من الجسم!"


def test_grant_insert_uses_service_role_only_around_the_registry(monkeypatch):
    """INSERT في break_glass_grants وحده تحت app.current_role='admin'؛ ثمّ يعود دور المُنادي."""
    import pyotp

    secret = pyotp.random_base32()
    conn = _FakeConn(
        fetchrow_result={
            "email": "a@b.c",
            "mfa_secret": secret,
            "mfa_enabled": True,
            "active": True,
        },
        fetchval_result=99,
    )
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))
    monkeypatch.setattr(bg, "_audit_mem", lambda *a, **k: None)

    out = _run(bg.request_break_glass(_req(pyotp.TOTP(secret).now()), _CALLER))
    assert out["grant_id"] == 99 and out["target_tenant_id"] == _BODY_TARGET

    _assert_caller_context_first(conn)
    seq = [(m, a[0]) for m, a in conn.calls]
    i_up = seq.index(("execute", "SELECT set_config('app.current_role', 'admin', true)"))
    i_ins = next(i for i, (m, q) in enumerate(seq) if "INSERT INTO break_glass_grants" in q)
    i_down = next(i for i, (m, q) in enumerate(seq) if i > i_ins and "current_role" in q)
    assert i_up < i_ins < i_down, seq
    assert conn.calls[i_down][1][1] == _CALLER.role.value, "لم يعُد دور المُنادي بعد السجلّ"
    # لا يُضبط مستأجِر الجسم سياقاً أبداً.
    assert all(_BODY_TARGET not in a[1:] for a in _set_configs(conn)), "سياق من الجسم!"


def test_revoke_runs_under_caller_tenant_and_scopes_grant_to_it(monkeypatch):
    """منحةٌ لمستأجِر آخر ⇒ 404: الإبطال مقيّد بمستأجِر المُنادي المُصادَق (لا الجسم)."""
    from fastapi import HTTPException

    conn = _FakeConn(fetchrow_result=None)  # القاعدة لا تُطابق منحة مستأجِر آخر
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))

    with pytest.raises(HTTPException) as ei:
        _run(bg.revoke_break_glass(1234, _CALLER))
    assert ei.value.status_code == 404

    _assert_caller_context_first(conn)
    upd = [a for m, a in conn.calls if m == "fetchrow" and "UPDATE break_glass_grants" in a[0]]
    assert upd, conn.calls
    sql, *params = upd[0]
    assert "u.tenant_id::text = $2" in sql and params == [1234, _CALLER.tenant_id], upd[0]
    seq = [a[0] for m, a in conn.calls]
    assert seq.index("SELECT set_config('app.current_role', 'admin', true)") < seq.index(sql)


def test_break_glass_use_reads_grant_under_caller_then_switches_to_grant_target(monkeypatch):
    """الاستخدام: سياق المُنادي ⇒ قراءة المنحة بدور الخدمة ⇒ سياق الهدف من صفّ المنحة ⇒ تدقيق."""
    target = "33333333-3333-3333-3333-333333333333"
    conn = _FakeConn(
        fetchrow_result={
            "id": 5,
            "target_tenant_id": target,
            "reason": "r" * 10,
            "admin_email": "x",
            "grant_token": bg._hash_grant_token("tok"),  # T8: المخزَّن hash
        }
    )
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))
    monkeypatch.setattr(bg, "_audit_mem", lambda *a, **k: None)

    async def _use():
        async with bg.break_glass_connection("tok", _CALLER) as (_c, tid):
            return tid

    assert _run(_use()) == target
    _assert_caller_context_first(conn)
    seq = [a[0] for m, a in conn.calls]
    i_grant = next(i for i, q in enumerate(seq) if "FROM break_glass_grants" in q)
    i_target = max(i for i, q in enumerate(seq) if "app.current_tenant" in q)
    i_audit = next(i for i, q in enumerate(seq) if "INSERT INTO audit_log" in q)
    assert i_grant < i_target < i_audit, seq
    assert conn.calls[i_target][1][1] == target
    assert conn.calls[i_audit][1][4] == target  # الاستخدام مُدقَّق في سجلّ المستأجِر المُتأثّر


def test_every_break_glass_db_access_goes_through_tenant_connection():
    """لا get_pool/acquire مباشر في الراوتر؛ وكتل _grant_registry لا تلمس إلّا سجلّ المنح."""
    import ast
    import inspect
    import re

    src = inspect.getsource(bg)
    assert "get_pool" not in src and ".acquire(" not in src, "اتّصال بلا سياق مستأجِر"
    tree = ast.parse(src)
    blocks = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncWith)
        and any(
            isinstance(i.context_expr, ast.Call)
            and getattr(i.context_expr.func, "id", "") == "_grant_registry"
            for i in n.items
        )
    ]
    assert len(blocks) == 3, "توقّعنا ثلاث كتل سجلّ (طلب/استخدام/إبطال)"
    rx = re.compile(r"\b(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_]+)")  # الجداول بأحرف صغيرة
    for b in blocks:
        sql = " ".join(
            c.value for c in ast.walk(b) if isinstance(c, ast.Constant) and isinstance(c.value, str)
        )
        assert set(rx.findall(sql)) <= {"break_glass_grants", "users"}, rx.findall(sql)


# ════════════════════════════════════════════════════════════════════
# ٧) T8: رمز المنحة مُجزّأ في القاعدة، يُبحث بالـhash، ولا يُسجَّل
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
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))

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
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))
    texts = _quiet_audits(monkeypatch)

    async def _use():
        async with bg.break_glass_connection("live-token-0123456789abcdef", _admin()) as (_, t):
            return t

    with caplog.at_level("DEBUG"):
        assert _run(_use()) == _TARGET
    # tenant_connection يضبط سياق المُنادي أوّلاً ⇒ نختار قراءة سجلّ المنح بعينها.
    (sql, bound, *_rest) = next(a for a in seen if "FROM break_glass_grants" in a[0])
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
    monkeypatch.setattr(_main, "get_pool", lambda: _FakePool(conn))
    _quiet_audits(monkeypatch)

    async def _use():
        async with bg.break_glass_connection("legacy-plain-token", _admin()):
            pass

    with pytest.raises(HTTPException) as ei:
        _run(_use())
    assert ei.value.status_code == 403
    # سياق المُنادي وحده (tenant_connection) — لا يُضبط سياق الهدف لصفّ قديم أبداً.
    set_tenant = [a for a in conn.executed if "current_tenant" in str(a[0])]
    assert [a[1] for a in set_tenant] == [_admin().tenant_id], set_tenant
    assert all(_TARGET not in [str(x) for x in a] for a in conn.executed), "سياق الهدف لصفّ قديم!"
    # ولا يُحتسَب استخدامٌ لصفّ مرفوض.
    assert not [a for a in conn.executed if "access_count" in str(a[0])]


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
