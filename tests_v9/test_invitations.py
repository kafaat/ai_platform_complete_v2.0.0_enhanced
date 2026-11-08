"""اختبارات وحدة لمسار دعوات أعضاء المستأجِر (governance: انضمام بأدوار أدنى).

تُغطّي المنطق النقيّ + حُرّاس المصدر/الهجرة دون قاعدة بيانات/Redis/شبكة:
  (أ) التحقّق من الدور يرفض owner/admin (منع تصعيد الصلاحيّات).
  (ب) القبول يُسنِد الدور والمستأجِر من **صفّ الدعوة فقط** (حارس مصدر:
      INSERT users يستخدم inv["role"]/inv["tenant_id"] لا قيمةً من العميل).
  (ج) الهجرة v89 تحوي tenant_id + FORCE + سياسة (نفس نمط test_v87).

يُحمَّل services/auth/main.py عبر importlib؛ يُتخطّى بأمان إن غابت تبعيّاته
(fastapi/asyncpg…) في بيئة وحدات CI (allow_module_level مثل test_auth_mfa_enforcement).
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_AUTH_DIR = str(ROOT / "services" / "auth")
_MIGRATION = ROOT / "migrations" / "v89_invitations.sql"


def _load_auth_main():
    """يُحمّل main.py الخاصّ بخدمة auth، ويتخطّى الاختبار إن غابت تبعيّاتها.

    In the full suite another auth test may already import services/auth/main.py as
    ``main``. Reusing that module avoids duplicate prometheus metric registration;
    using a unique spec name only when needed avoids accidentally returning a
    different service module named ``main``.
    """
    auth_main_path = str(pathlib.Path(_AUTH_DIR) / "main.py")
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) == auth_main_path:
            return module
    if _AUTH_DIR not in sys.path:
        sys.path.insert(0, _AUTH_DIR)
    try:
        spec = importlib.util.spec_from_file_location(
            "sahool_auth_main_for_invitation_tests", auth_main_path
        )
        if spec is None or spec.loader is None:
            raise ImportError("cannot build import spec for auth main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = (
            module  # allow Pydantic forward-ref resolution under from __future__ annotations
        )
        spec.loader.exec_module(module)
        return module
    except ImportError as e:
        pytest.skip(f"auth main.py غير قابل للاستيراد (تبعيّة ناقصة): {e}", allow_module_level=True)


main = _load_auth_main()


# ── (أ) التحقّق من الدور — يرفض owner/admin، يقبل الأدوار الأدنى ──────
@pytest.mark.unit
class TestInviteableRole:
    def test_inviteable_roles_are_the_low_privilege_set(self):
        assert main.INVITEABLE_ROLES == frozenset({"expert", "farmer", "viewer"})

    @pytest.mark.parametrize("role", ["expert", "farmer", "viewer"])
    def test_low_roles_accepted(self, role):
        assert main.is_inviteable_role(role) is True

    @pytest.mark.parametrize("role", ["owner", "admin", "OWNER", "Admin"])
    def test_privileged_roles_rejected(self, role):
        # حجر الزاوية الأمنيّ: لا يُدعى أحد بدور مالك/مشرف (منع تصعيد الصلاحيّات).
        assert main.is_inviteable_role(role) is False

    @pytest.mark.parametrize("role", [None, "", "  ", "superuser", "root"])
    def test_unknown_or_empty_rejected_fail_closed(self, role):
        assert main.is_inviteable_role(role) is False

    def test_case_and_whitespace_normalized(self):
        assert main.is_inviteable_role("  Expert  ") is True


@pytest.mark.unit
class TestCanInvite:
    @pytest.mark.parametrize("role", ["owner", "admin", "OWNER"])
    def test_inviter_roles_allowed(self, role):
        assert main.can_invite(role) is True

    @pytest.mark.parametrize("role", ["expert", "farmer", "viewer", None, "", "manager"])
    def test_non_inviter_roles_blocked(self, role):
        assert main.can_invite(role) is False


# ── (ب) حارس مصدر: القبول يأخذ الدور+المستأجِر من صفّ الدعوة فقط ──────
@pytest.mark.unit
class TestAcceptSourceGuard:
    @property
    def _src(self) -> str:
        # بعد تفكيك مسارات auth انتقل accept_invitation إلى routers/invitations.py (سلوك
        # محفوظ). نمسح المصدر المُسلسَل (main.py + routers/*.py) كي يبقى الحارس صحيحاً.
        from auth_route_source import auth_combined_source

        return auth_combined_source(str(ROOT))

    def test_accept_inserts_user_with_invitation_role_and_tenant(self):
        """INSERT users في accept يستخدم inv["role"] و inv["tenant_id"] — لا قيمةً
        من العميل (لا req.role / لا req.tenant_id). يثبت عدم سماح العميل باختيارهما."""
        src = self._src
        # نلتقط جسم دالّة accept_invitation تقريبيّاً (حتى نهاية الملفّ كافٍ هنا).
        idx = src.index("async def accept_invitation")
        body = src[idx : idx + 2500]
        assert 'inv["role"]' in body, "القبول لا يستعمل دور الدعوة"
        assert 'inv["tenant_id"]' in body, "القبول لا يستعمل مستأجِر الدعوة"
        # العميل لا يُمرّر دوراً/مستأجِراً (لا حقول كهذه في InvitationAcceptRequest).
        assert "req.role" not in body
        assert "req.tenant_id" not in body

    def test_accept_request_model_has_no_role_or_tenant_field(self):
        """InvitationAcceptRequest لا يحوي role/tenant_id — العميل لا يختارهما."""
        fields = set(main.InvitationAcceptRequest.model_fields.keys())
        assert "role" not in fields
        assert "tenant_id" not in fields
        assert fields == {"token", "password", "full_name"}

    def test_create_request_role_literal_excludes_privileged(self):
        """InvitationCreateRequest.role من نوع Literal يستبعد owner/admin."""
        import typing

        ann = main.InvitationCreateRequest.model_fields["role"].annotation
        allowed = set(typing.get_args(ann))
        assert allowed == {"expert", "farmer", "viewer"}
        assert "owner" not in allowed and "admin" not in allowed


# ── (ج) حارس الهجرة v89 — tenant_id + FORCE + سياسة (نمط test_v87) ──
@pytest.mark.unit
@pytest.mark.security
class TestMigrationV89:
    @property
    def _sql(self) -> str:
        return _MIGRATION.read_text(encoding="utf-8")

    def test_migration_exists(self):
        assert _MIGRATION.exists()

    def test_creates_invitations_with_tenant_id(self):
        sql = self._sql
        assert re.search(r"CREATE TABLE\b.*\binvitations\b", sql, re.I)
        assert re.search(r"\btenant_id\s+UUID\b", sql, re.I)

    def test_enables_and_forces_rls(self):
        sql = self._sql
        assert re.search(r"ALTER TABLE\s+invitations\s+ENABLE ROW LEVEL SECURITY", sql, re.I)
        # FORCE إلزاميّ: الجدول لاحق لـv9_rls_force_all ⇒ المالك يتجاوز بلا FORCE صريح.
        assert re.search(r"ALTER TABLE\s+invitations\s+FORCE ROW LEVEL SECURITY", sql, re.I)

    def test_tenant_scoped_policy_present(self):
        sql = self._sql
        assert re.search(r"CREATE POLICY\s+\w+\s+ON\s+invitations", sql, re.I)
        assert "current_setting('app.current_tenant'" in sql
        assert "WITH CHECK" in sql  # عزل الكتابة (write isolation)

    def test_in_manifest(self):
        manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
        assert "v89_invitations.sql" in manifest


# ── (د) T8: الرمز يُخزَّن مُجزّأً، يُبحث بالـhash، والقديم الصريح لا يُقبَل ──
_ROUTER_SRC = ROOT / "services" / "auth" / "routers" / "invitations.py"


def _inv_router():
    """وحدة routers/invitations.py كما حمّلها main (register_routers) — بالمسار لا بالاسم.

    في الجناح الكامل قد يكون ``routers`` حزمةَ خدمة أخرى؛ فإن لم تُحمَّل وحدة auth بعدُ
    نُنفّذ مساعِدات T8 النقيّة (hashlib/secrets فقط) من مصدرها نفسه بلا ``import main``.
    """
    import ast
    import types

    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) == str(_ROUTER_SRC):
            return module
    tree = ast.parse(_ROUTER_SRC.read_text(encoding="utf-8"))
    keep = {"INVITATION_TOKEN_HASH_PREFIX", "hash_invitation_token", "invitation_token_matches"}
    body = [
        n
        for n in tree.body
        if (isinstance(n, ast.FunctionDef) and n.name in keep)
        or (isinstance(n, ast.Assign) and {getattr(t, "id", "") for t in n.targets} & keep)
    ]
    ns = types.ModuleType("_invitations_t8_helpers")
    exec("import hashlib, secrets", ns.__dict__)  # noqa: S102 — مصدر المستودع نفسه
    exec(compile(ast.Module(body=body, type_ignores=[]), str(_ROUTER_SRC), "exec"), ns.__dict__)  # noqa: S102
    return ns


def _handler(name: str):
    import ast

    tree = ast.parse(_ROUTER_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} غائب عن routers/invitations.py")


def _db_calls_on(fn, table_marker: str):
    """استدعاءات conn.fetchrow/execute التي يحوي SQL الأوّل فيها table_marker."""
    import ast

    out = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"fetchrow", "fetch", "execute", "fetchval"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and table_marker in str(node.args[0].value)
        ):
            out.append(node)
    return out


@pytest.mark.unit
@pytest.mark.security
class TestInvitationTokenHashedAtRest:
    def test_stored_value_is_not_the_token(self):
        r = _inv_router()
        token = "tok_" + "A" * 40
        stored = r.hash_invitation_token(token)
        assert stored != token
        assert token not in stored
        assert stored.startswith("sha256:") and len(stored) == len("sha256:") + 64
        # حتميّ (البحث بالفهرس الفريد القائم يتطلّب ذلك).
        assert stored == r.hash_invitation_token(token)
        assert stored != r.hash_invitation_token(token + "x")

    def test_matches_only_the_right_token(self):
        r = _inv_router()
        stored = r.hash_invitation_token("right-token-0123456789")
        assert r.invitation_token_matches(stored, "right-token-0123456789") is True
        assert r.invitation_token_matches(stored, "wrong-token-0123456789") is False
        # تقديم القيمة المخزَّنة نفسها رمزاً (من قرأ الجدول) لا يطابق.
        assert r.invitation_token_matches(stored, stored) is False

    @pytest.mark.parametrize("legacy", ["plain-legacy-token-0123456789", "", None])
    def test_legacy_plaintext_row_never_matches(self, legacy):
        """صفّ ما قبل T8 (رمز صريح) يُعامَل منتهياً — حتى لو قُدِّم الرمز نفسه."""
        r = _inv_router()
        assert r.invitation_token_matches(legacy, legacy or "x" * 20) is False

    def test_compare_is_constant_time(self):
        import ast

        fn = next(
            n
            for n in ast.walk(ast.parse(_ROUTER_SRC.read_text(encoding="utf-8")))
            if isinstance(n, ast.FunctionDef) and n.name == "invitation_token_matches"
        )
        assert "compare_digest" in ast.unparse(fn)

    def test_create_stores_hash_not_token(self):
        import ast

        (insert,) = _db_calls_on(_handler("create_invitation"), "INSERT INTO invitations")
        assert ast.unparse(insert.args[1]) == "hash_invitation_token(token)", (
            "INSERT invitations يكتب الرمز صريحاً — من يقرأ الجدول يملك دعوة صالحة"
        )

    def test_accept_looks_up_by_hash_and_confirms(self):
        import ast

        fn = _handler("accept_invitation")
        (select,) = _db_calls_on(fn, "FROM invitations")
        assert "WHERE token = $1" in select.args[0].value
        assert ast.unparse(select.args[1]) == "hash_invitation_token(req.token)"
        assert "invitation_token_matches(inv['token'], req.token)" in ast.unparse(fn)

    def test_list_marks_legacy_pending_as_expired(self):
        (sel,) = _db_calls_on(_handler("list_invitations"), "FROM invitations")
        sql = sel.args[0].value
        assert "CASE WHEN token LIKE 'sha256:%' THEN status ELSE 'expired' END AS status" in sql

    def test_token_never_logged_or_listed(self):
        """الرمز لا يمرّ إلى audit_log/logger، ولا يظهر في السرد بعد الإنشاء."""
        import ast

        tree = ast.parse(_ROUTER_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = ast.unparse(node.func)
            if callee.endswith("audit_log") or callee.split(".")[0] in {"logger", "logging"}:
                names = {
                    n.id
                    for a in node.args + [k.value for k in node.keywords]
                    for n in ast.walk(a)
                    if isinstance(n, ast.Name)
                }
                attrs = {
                    ast.unparse(n)
                    for a in node.args + [k.value for k in node.keywords]
                    for n in ast.walk(a)
                    if isinstance(n, ast.Attribute)
                }
                assert "token" not in names and "req.token" not in attrs, callee
        listed = ast.unparse(_handler("list_invitations"))
        assert "'token'" not in listed and '"token"' not in listed
