"""core/db_role_guard.py — حارس دور قاعدة البيانات: لينشين عزل المستأجرين (نقيّ).

تدقيق أمنيّ موجَّه (عزل متعدّد المستأجرين): كلّ العزل (RLS + FORCE + السياسات + ضبط
app.current_tenant من توكن موثوق) ينهار **صامتاً** إذا اتّصل التطبيق بدور قاعدة يتجاوز
RLS (superuser أو BYPASSRLS) — مثل sahool_user (مالك) أو postgres. عندها يقرأ أيّ مستأجِر
بيانات الجميع بلا أيّ خطأ ظاهر. هذا هو **اللينشين الوحيد** الذي يحمل صرح العزل كلّه.

هذه الوحدة نقيّة (قرار فقط)؛ يُجري الفحص الفعليّ مُنادٍ يقرأ pg_roles عند الإقلاع، ويرفض
بدء الخدمة (fail-closed) إن كان الدور يتجاوز RLS والفرض مُفعَّل — فيتحوّل اللينشين من
«مفترَض» إلى «مُثبَت عند كلّ إقلاع».
"""

from __future__ import annotations

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

# استعلام probe (يُجريه المُنادي): دور الاتّصال الحاليّ وقدرته على تجاوز RLS.
ROLE_PROBE_SQL = "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"


def role_can_bypass_rls(rolsuper, rolbypassrls) -> bool:
    """هل يتجاوز دور الاتّصال RLS؟ superuser أو BYPASSRLS ⇒ العزل مُبطَل (نقيّ)."""
    return bool(rolsuper) or bool(rolbypassrls)


def enforcement_enabled(env_value: str | None) -> bool:
    """[مُتقادِم] دلالة opt-in القديمة (SAHOOL_ENFORCE_RLS_ROLE) — مُبقاة للتوافق.
    استعمل enforcement_active (fail-closed افتراضيّاً) للمنطق الجديد."""
    return (env_value or "").strip().lower() in _TRUTHY


def enforcement_active(allow_bypass_env: str | None, enforce_env: str | None = None) -> bool:
    """هل فرض دور RLS مُفعَّل؟ **fail-closed افتراضيّاً** (FINDING-001، نقيّ).

    يُفرَض إلّا إذا SAHOOL_ALLOW_RLS_BYPASS_ROLE صريحاً truthy (مهرب التطوير) أو
    SAHOOL_ENFORCE_RLS_ROLE صريحاً falsy. الغياب ⇒ يُفرَض (آمن في الإنتاج دون ضبط)."""
    if (allow_bypass_env or "").strip().lower() in _TRUTHY:
        return False
    if (enforce_env or "").strip().lower() in _FALSY:
        return False
    return True


def should_refuse_startup(role_unsafe: bool, enforce: bool) -> bool:
    """يقرّر رفض الإقلاع: دور يتجاوز RLS + الفرض مُفعَّل ⇒ رفض (fail-closed)، نقيّ."""
    return bool(role_unsafe) and bool(enforce)


def role_guard_message(rolsuper, rolbypassrls, refused: bool) -> str:
    """رسالة تشخيص صريحة (للسجلّ) — تشرح المخاطرة والإصلاح."""
    why = "superuser" if rolsuper else "BYPASSRLS"
    action = "رُفِض الإقلاع (fail-closed)" if refused else "تحذير فقط (الفرض مُطفأ)"
    return (
        f"دور قاعدة البيانات يتجاوز RLS ({why}) — عزل المستأجرين مُعطَّل صامتاً! "
        f"{action}. الإصلاح: اتّصل بدور مقيّد (sahool_app: NOSUPERUSER NOBYPASSRLS) "
        f"لا بمالك الجداول/superuser. لِفرض الرفض اضبط SAHOOL_ENFORCE_RLS_ROLE=1."
    )
