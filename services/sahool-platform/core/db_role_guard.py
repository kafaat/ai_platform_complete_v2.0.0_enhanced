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

# استعلام probe (يُجريه المُنادي): دور الاتّصال الحاليّ وقدرته على تجاوز RLS.
ROLE_PROBE_SQL = "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"


def role_can_bypass_rls(rolsuper, rolbypassrls) -> bool:
    """هل يتجاوز دور الاتّصال RLS؟ superuser أو BYPASSRLS ⇒ العزل مُبطَل (نقيّ)."""
    return bool(rolsuper) or bool(rolbypassrls)


def enforcement_enabled(env_value: str | None) -> bool:
    """هل فرض دور RLS مُفعَّل؟ (SAHOOL_ENFORCE_RLS_ROLE) — مُطفأ ⇒ تحذير لا رفض."""
    return (env_value or "").strip().lower() in _TRUTHY


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
