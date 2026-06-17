"""shared/db_role_guard.py — حارس دور قاعدة البيانات العالميّ (لينشين عزل المستأجرين).

تدقيق أمنيّ (FINDING-001): كلّ عزل المستأجرين (RLS + FORCE + السياسات + ضبط
app.current_tenant) ينهار **صامتاً** إذا اتّصل التطبيق بدور قاعدة يتجاوز RLS
(superuser أو BYPASSRLS) — مثل sahool_user (مالك الجداول) أو postgres. عندها يقرأ
أيّ مستأجِر بيانات الجميع بلا أيّ خطأ ظاهر. هذا اللينشين هو الوحيد الذي يحمل صرح
العزل كلّه — فيجب أن يُفحَص عند إقلاع **كلّ** خدمة تتّصل بالقاعدة.

بخلاف الحارس السابق (الخاصّ بـsahool-platform، opt-in)، هذا الحارس:
  • مشترَك (في shared/ المنسوخ إلى كلّ صورة خدمة) ⇒ يُستعمَل من أيّ خدمة.
  • **fail-closed افتراضيّاً**: يرفض الإقلاع على دور يتجاوز RLS ما لم يُعطَّل صراحةً
    (SAHOOL_ALLOW_RLS_BYPASS_ROLE=1 للتطوير المحلّيّ فقط) — تحويل «انحدار أمنيّ صامت»
    إلى «فشل صريح عند الإقلاع».

نقيّ بالكامل عدا الدالّة async الفاحصة (تقرأ pg_roles لدور الاتّصال الحاليّ).
"""

from __future__ import annotations

import logging

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

# probe: دور الاتّصال الحاليّ وقدرته على تجاوز RLS (يقرأ صفّه هو — متاح لأيّ دور).
ROLE_PROBE_SQL = "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"


def role_can_bypass_rls(rolsuper, rolbypassrls) -> bool:
    """هل يتجاوز دور الاتّصال RLS؟ superuser أو BYPASSRLS ⇒ العزل مُبطَل (نقيّ)."""
    return bool(rolsuper) or bool(rolbypassrls)


def enforcement_active(allow_bypass_env: str | None, enforce_env: str | None = None) -> bool:
    """هل فرض دور RLS مُفعَّل؟ **fail-closed افتراضيّاً** (نقيّ).

    يُفرَض (True) إلّا إذا:
      • SAHOOL_ALLOW_RLS_BYPASS_ROLE صريحاً truthy (مهرب التطوير المحلّيّ)، أو
      • SAHOOL_ENFORCE_RLS_ROLE صريحاً falsy (تعطيل توافقيّ خلفيّ).
    الغياب ⇒ يُفرَض (عكس الحارس القديم opt-in). فالإنتاج آمن دون ضبط.
    """
    if (allow_bypass_env or "").strip().lower() in _TRUTHY:
        return False
    if (enforce_env or "").strip().lower() in _FALSY:
        return False
    return True


def should_refuse_startup(role_unsafe: bool, enforce: bool) -> bool:
    """يقرّر رفض الإقلاع: دور يتجاوز RLS + الفرض مُفعَّل ⇒ رفض (fail-closed)، نقيّ."""
    return bool(role_unsafe) and bool(enforce)


def role_guard_message(rolsuper, rolbypassrls, refused: bool, service: str = "") -> str:
    """رسالة تشخيص صريحة (للسجلّ) — تشرح المخاطرة والإصلاح."""
    why = "superuser" if rolsuper else "BYPASSRLS"
    action = "رُفِض الإقلاع (fail-closed)" if refused else "تحذير فقط (الفرض مُعطَّل صراحةً)"
    svc = f"[{service}] " if service else ""
    return (
        f"{svc}دور قاعدة البيانات يتجاوز RLS ({why}) — عزل المستأجرين مُعطَّل صامتاً! "
        f"{action}. الإصلاح: اتّصل بدور مقيّد (sahool_app: NOSUPERUSER NOBYPASSRLS) "
        f"لا بمالك الجداول/superuser. للتطوير المحلّيّ فقط: SAHOOL_ALLOW_RLS_BYPASS_ROLE=1."
    )


async def assert_db_role_rls_safe(pool_or_conn, *, service: str = "") -> None:
    """يفحص دور الاتّصال عند الإقلاع ويرفض (fail-closed) إن تجاوز RLS والفرض مُفعَّل.

    `pool_or_conn`: asyncpg Pool (يُكتسَب منه اتّصال) أو Connection مباشر.
    يرفع RuntimeError عند الرفض (لا يُبتلَع — يجب أن يوقف إقلاع الخدمة).
    تعذّر الفحص نفسه (لا pg_roles/خطأ عابر) لا يحجب الإقلاع (لا يكسر بيئات الاختبار)؛
    لكنّ دوراً يتجاوز RLS فعليّاً = رفض. الاستيراد متأخّر لـos تفادياً لتلوّث النقاء.
    """
    import os

    try:
        if hasattr(pool_or_conn, "acquire"):
            async with pool_or_conn.acquire() as conn:
                row = await conn.fetchrow(ROLE_PROBE_SQL)
        else:
            row = await pool_or_conn.fetchrow(ROLE_PROBE_SQL)
    except Exception as e:  # noqa: BLE001 — تعذّر الفحص ⇒ لا يحجب الإقلاع
        logging.getLogger(service or "db_role_guard").debug("تعذّر فحص دور RLS: %s", e)
        return
    if row is None:
        return
    unsafe = role_can_bypass_rls(row["rolsuper"], row["rolbypassrls"])
    if not unsafe:
        return
    enforce = enforcement_active(
        os.getenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE"), os.getenv("SAHOOL_ENFORCE_RLS_ROLE")
    )
    refuse = should_refuse_startup(unsafe, enforce)
    msg = role_guard_message(row["rolsuper"], row["rolbypassrls"], refuse, service)
    logging.getLogger(service or "db_role_guard").critical("🔓 %s", msg)
    if refuse:
        raise RuntimeError(msg)


async def assert_dsn_role_rls_safe(dsn: str, *, service: str = "") -> None:
    """نسخة DSN لخدمات بلا pool دائم عند الإقلاع (اتّصال per-call): تفتح اتّصالاً
    واحداً للفحص ثمّ تُغلقه. ترفع RuntimeError عند رفض الدور؛ تعذّر الاتّصال نفسه
    (قاعدة غير متاحة) لا يحجب الإقلاع (best-effort). بلا DSN ⇒ لا عمل."""
    if not dsn:
        return
    try:
        import asyncpg
    except Exception:  # noqa: BLE001 — لا asyncpg ⇒ لا فحص
        return
    try:
        conn = await asyncpg.connect(dsn, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001 — تعذّر الاتّصال ⇒ لا يحجب الإقلاع
        logging.getLogger(service or "db_role_guard").debug("تعذّر اتّصال فحص RLS: %s", e)
        return
    try:
        await assert_db_role_rls_safe(conn, service=service)
    finally:
        await conn.close()
