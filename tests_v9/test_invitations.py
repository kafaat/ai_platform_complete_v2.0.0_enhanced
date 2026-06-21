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

import importlib
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_AUTH_DIR = str(ROOT / "services" / "auth")
_MIGRATION = ROOT / "migrations" / "v89_invitations.sql"


def _load_auth_main():
    """يُحمّل main.py الخاصّ بخدمة auth، ويتخطّى الاختبار إن غابت تبعيّاتها."""
    if _AUTH_DIR not in sys.path:
        sys.path.insert(0, _AUTH_DIR)
    try:
        return importlib.import_module("main")
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
        return (pathlib.Path(_AUTH_DIR) / "main.py").read_text(encoding="utf-8")

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
