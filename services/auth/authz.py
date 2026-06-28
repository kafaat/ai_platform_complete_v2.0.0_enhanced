"""SAHOOL v9.1 — services/auth/authz.py

طبقة قرارات التفويض/السياسة النقيّة (pure authorization policy) المستخرَجة من
main.py. كلّ ما هنا دوالّ/ثوابت **نقيّة**: تقرأ os.getenv عند التحميل أو تعمل على
وسائطها فقط — لا تعتمد على حالة الخدمة (_redis/_pool/app) ولا على decorators المسارات.
هذا يجعلها قابلة للاختبار وحدةً في CI دون رفع الخدمة، ويقلّص main.py.

main.py يعيد تصدير هذه الأسماء (from authz import ...) فتبقى متاحة كـmain.<name>
(سلوك محفوظ؛ نفس مفاتيح البيئة والتوقيعات والقيم).

ملاحظة: _is_production و_admin_stepup_required بقيا في main.py عمداً (حُرّاس مصدريّة
نصّيّة تتطلّب تعريفهما هناك + تكامل lifespan/نقاط admin).
"""

from __future__ import annotations

import os

# ── أدوار الدعوة (governance: انضمام بأدوار أدنى) ───────────────────
# الأدوار التي يجوز **الدعوة** إليها: الأدنى/غير المميَّزة حصراً. owner/admin
# **مستبعَدان عمداً** (منع تصعيد الصلاحيّات: لا يُنشَأ مالك/مشرف عبر دعوة — المالك
# عبر التسجيل الذاتيّ فقط، والمشرف عبر إجراء إداريّ منفصل). دالّة التحقّق نقيّة كي
# تُختبَر وحدةً دون رفع الخدمة (CI).
INVITEABLE_ROLES: frozenset[str] = frozenset({"expert", "farmer", "viewer"})
# الأدوار التي يحقّ لها **توجيه** دعوة (مالك المستأجِر أو مشرف المنصّة فقط).
INVITER_ROLES: frozenset[str] = frozenset({"owner", "admin"})


def is_inviteable_role(role: str | None) -> bool:
    """هل يجوز الدعوة لهذا الدور؟ True فقط لـ{expert,farmer,viewer}.

    fail-closed: None/فراغ/أيّ دور مميَّز (owner/admin) ⇒ False (منع تصعيد).
    دالّة نقيّة (لا I/O) لتُختبَر وحدةً في CI دون تبعيّات الخدمة.
    """
    return (role or "").strip().lower() in INVITEABLE_ROLES


def can_invite(role: str | None) -> bool:
    """هل يحقّ لهذا الدور توجيه دعوات؟ True لـowner/admin فقط. fail-closed."""
    return (role or "").strip().lower() in INVITER_ROLES


# ── فرض MFA للأدوار الحسّاسة (governance #411) ─────────────────────
# الأدوار التي يجب أن تملك MFA مفعّلاً قبل أن تُمنح جلسة. تُحلَّل مرّة واحدة
# عند التحميل (fail-safe). الافتراضيّ 'admin' (المشرف الأعلى للمنصّة).
def _parse_required_mfa_roles(raw: str | None) -> frozenset[str]:
    """يحوّل قائمة أدوار مفصولة بفواصل إلى مجموعة مُطبَّعة (lowercase, trimmed)."""
    if not raw:
        raw = "admin"
    return frozenset(r.strip().lower() for r in raw.split(",") if r.strip())


REQUIRE_MFA_ROLES = _parse_required_mfa_roles(os.getenv("REQUIRE_MFA_ROLES"))
# مفتاح رئيسيّ: الفرض مُفعَّل افتراضيّاً للأدوار الحسّاسة؛ عطّله صراحةً في CI/التطوير عبر ENFORCE_SENSITIVE_MFA=false عند الحاجة.
# يبقى مفروضاً في الإنتاج عبر SAHOOL_ENV=production حتى لو نُسي الضبط.
_ENFORCE_SENSITIVE_MFA = os.getenv("ENFORCE_SENSITIVE_MFA", "true").lower() == "true"
_IS_PRODUCTION = os.getenv("SAHOOL_ENV", "").lower() == "production"
MFA_ENFORCEMENT_ENABLED = _ENFORCE_SENSITIVE_MFA or _IS_PRODUCTION


def _mfa_required_but_missing(
    role: str | None,
    mfa_enabled: bool,
    *,
    enforcement_enabled: bool = MFA_ENFORCEMENT_ENABLED,
    required_roles: frozenset[str] = REQUIRE_MFA_ROLES,
) -> bool:
    """قرار نقيّ: هل يجب رفض الدخول لأنّ دوراً حسّاساً لا يملك MFA؟

    يُرجِع True فقط حين يكون الفرض مُفعَّلاً والدور ضمن القائمة وMFA غير مفعّل.
    افتراضيّاً (لا بيئة) ⇒ enforcement_enabled=False ⇒ يُرجِع False دائماً
    (لا تغيير في السلوك، يبقى CI أخضر).
    """
    if not enforcement_enabled:
        return False
    if mfa_enabled:
        return False
    return (role or "").strip().lower() in required_roles
