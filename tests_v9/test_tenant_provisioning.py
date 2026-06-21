"""اختبارات وحدة لمسار تهيئة مستأجِر جديد + أوّل مالك (مدير المنصّة، B2B).

تُغطّي المنطق النقيّ + حُرّاس المصدر دون قاعدة بيانات/Redis/شبكة:
  (أ) النقطة محميّة بـrequire_role("admin") — مدير المنصّة فقط يُهيّئ
      (غيره 403). الحارس: الاعتماديّة require_role("admin") على المعالِج.
  (ب) المستخدِم المُهيَّأ يحصل على الدور 'owner' حصراً (مكتوب نصّاً، لا من
      العميل) ومستأجِر جديد معزول (tenant_id افتراضيّ gen_random_uuid — لا
      يُمرَّر في INSERT، نفس نمط register).
  (ج) البريد المكرّر مرفوض (409) عبر التقاط UniqueViolationError.
  (د) نموذج الطلب لا يسمح للعميل باختيار role/password/tenant_id.

يُحمَّل services/auth/main.py عبر importlib؛ يُتخطّى الاختبار بأمان إن غابت
تبعيّات الخدمة (fastapi/asyncpg…) في بيئة الوحدات بـCI (allow_module_level،
نفس نمط test_auth_mfa_enforcement / test_invitations).
"""

from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_AUTH_DIR = str(ROOT / "services" / "auth")


def _load_auth_main():
    """يُحمّل main.py الخاصّ بخدمة auth، ويتخطّى الاختبار إن غابت تبعيّاتها."""
    if _AUTH_DIR not in sys.path:
        sys.path.insert(0, _AUTH_DIR)
    try:
        return importlib.import_module("main")
    except ImportError as e:
        pytest.skip(f"auth main.py غير قابل للاستيراد (تبعيّة ناقصة): {e}", allow_module_level=True)


main = _load_auth_main()


def _provision_src() -> str:
    """جسم دالّة provision_tenant تقريبيّاً (من تعريفها حتى نقطة الدعوات)."""
    src = (pathlib.Path(_AUTH_DIR) / "main.py").read_text(encoding="utf-8")
    start = src.index("async def provision_tenant")
    end = src.index("# ── Tenant member invitations", start)
    return src[start:end]


# ── (د) نموذج الطلب: العميل لا يختار role/password/tenant_id ──────────
@pytest.mark.unit
class TestProvisionRequestModel:
    def test_fields_are_only_owner_email_full_name_and_tenant_name(self):
        fields = set(main.TenantProvisionRequest.model_fields.keys())
        assert fields == {"owner_email", "owner_full_name", "tenant_name"}

    def test_no_role_password_or_tenant_id_field(self):
        """العميل (مدير المنصّة) لا يُمرّر دوراً/كلمة مرور/مستأجِراً — كلّها مفروضة
        خادميّاً (الدور 'owner'، كلمة المرور عشوائيّة، المستأجِر gen_random_uuid)."""
        fields = set(main.TenantProvisionRequest.model_fields.keys())
        assert "role" not in fields
        assert "password" not in fields
        assert "tenant_id" not in fields

    def test_tenant_name_optional(self):
        m = main.TenantProvisionRequest(owner_email="o@x.io", owner_full_name="مالك جديد")
        assert m.tenant_name is None


# ── (أ) الحارس: النقطة محميّة بـadmin حصراً (مدير المنصّة) ─────────────
@pytest.mark.unit
@pytest.mark.security
class TestAdminOnlyGuard:
    def test_handler_depends_on_require_role_admin(self):
        """provision_tenant يعتمد require_role("admin") — مدير المنصّة فقط (غيره 403)."""
        body = _provision_src()
        assert 'require_role("admin")' in body, "النقطة غير محميّة بدور admin"

    def test_require_role_rejects_non_admin(self):
        """require_role دالّة نقيّة: تُنشئ تابعاً يرفض الأدوار خارج المسموح بـ403."""
        # require_role("admin") يبني فاحصاً؛ نتحقّق أنّ owner/expert ليسوا admin.
        import asyncio

        from fastapi import HTTPException

        checker = main.require_role("admin")
        for role in ("owner", "expert", "farmer", "viewer", ""):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(checker(user={"role": role}))
            assert exc.value.status_code == 403
        # admin يمرّ
        out = asyncio.run(checker(user={"role": "admin", "sub": "1"}))
        assert out["role"] == "admin"


# ── (ب) الدور 'owner' + مستأجِر جديد معزول (حارس مصدر) ────────────────
@pytest.mark.unit
@pytest.mark.security
class TestOwnerRoleAndFreshTenant:
    def test_insert_hardcodes_owner_role(self):
        """INSERT users يكتب role='owner' نصّاً — لا من العميل (لا req.role)."""
        body = _provision_src()
        assert "'owner'" in body, "الدور 'owner' ليس مكتوباً نصّاً في INSERT"
        assert "req.role" not in body  # العميل لا يختار الدور

    def test_tenant_id_not_passed_uses_default_gen_random_uuid(self):
        """tenant_id لا يُمرَّر في INSERT ⇒ يأخذ الافتراضيّ gen_random_uuid (مستأجِر
        جديد معزول). لا req.tenant_id (العميل لا يختار المستأجِر — منع تصادم/تصعيد)."""
        body = _provision_src()
        # عمود tenant_id لا يَرِد في قائمة أعمدة INSERT (الافتراضيّ يتكفّل به).
        assert "INSERT INTO users (email, password_hash, full_name, role)" in body
        assert "req.tenant_id" not in body

    def test_returns_fresh_tenant_and_owner_user_id(self):
        """الاستجابة تُعيد tenant_id الجديد + owner_user_id (عقد B2B onboarding)."""
        body = _provision_src()
        assert '"tenant_id"' in body
        assert '"owner_user_id"' in body


# ── (ج) البريد المكرّر مرفوض 409 ─────────────────────────────────────
@pytest.mark.unit
class TestDuplicateEmailRejected:
    def test_unique_violation_maps_to_409(self):
        body = _provision_src()
        assert "asyncpg.UniqueViolationError" in body
        assert "HTTP_409_CONFLICT" in body


# ── إعداد كلمة المرور عبر آليّة إعادة التعيين القائمة (لا كلمة من المُهيِّئ) ──
@pytest.mark.unit
@pytest.mark.security
class TestPasswordSetupReusesResetMechanism:
    def test_uses_reset_redis_key_and_send_reset_email(self):
        """المالك يضبط كلمته عبر رمز إعادة التعيين (sahool:reset:) + send_reset_email
        — لا كلمة مرور مسبقة يعرفها المُهيِّئ (أوّليّة عشوائيّة غير قابلة للاستعمال)."""
        body = _provision_src()
        assert "sahool:reset:" in body, "لا يعيد استخدام آليّة إعادة التعيين"
        assert "send_reset_email" in body
        # كلمة مرور أوّليّة عشوائيّة (token_urlsafe) ⇒ غير قابلة للاستعمال.
        assert "secrets.token_urlsafe" in body

    def test_audit_action_is_tenant_provisioned(self):
        body = _provision_src()
        assert '"tenant_provisioned"' in body
