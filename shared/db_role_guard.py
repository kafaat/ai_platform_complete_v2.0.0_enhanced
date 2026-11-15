"""shared/db_role_guard.py — حارس دور قاعدة البيانات العالميّ (لينشين عزل المستأجرين).

تدقيق أمنيّ (FINDING-001): كلّ عزل المستأجرين (RLS + FORCE + السياسات + ضبط
app.current_tenant) ينهار **صامتاً** إذا اتّصل التطبيق بدور قاعدة يتجاوز RLS
(superuser أو BYPASSRLS) — مثل sahool_user (مالك الجداول) أو postgres. عندها يقرأ
أيّ مستأجِر بيانات الجميع بلا أيّ خطأ ظاهر. هذا اللينشين هو الوحيد الذي يحمل صرح
العزل كلّه — فيجب أن يُفحَص عند إقلاع **كلّ** خدمة تتّصل بالقاعدة.

بخلاف الحارس السابق (الخاصّ بـsahool-platform، opt-in)، هذا الحارس:
  • مشترَك (في shared/ المنسوخ إلى كلّ صورة خدمة) ⇒ يُستعمَل من أيّ خدمة.
  • **fail-closed افتراضيّاً**: يرفض الإقلاع على دور يتجاوز RLS — أو دورٍ تعذّر إثبات
    سلامته (خطأ/مهلة/لا صفّ في الفحص) — ما لم يُعطَّل صراحةً
    (SAHOOL_ALLOW_RLS_BYPASS_ROLE=1 للتطوير المحلّيّ فقط) — تحويل «انحدار أمنيّ صامت»
    إلى «فشل صريح عند الإقلاع».

نقيّ بالكامل عدا الدوالّ async الفاحصة (تقرأ pg_roles لدور الاتّصال الحاليّ).
"""

from __future__ import annotations

import asyncio
import logging

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

# probe: دور الاتّصال الحاليّ وقدرته على تجاوز RLS (يقرأ صفّه هو — متاح لأيّ دور).
ROLE_PROBE_SQL = "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"

# الفحص على مسار الإقلاع الحرج ⇒ محدود زمنيّاً (يُضبَط بالبيئة؛ غير الموجب/غير الرقميّ ⇒ الافتراض).
PROBE_TIMEOUT_ENV = "SAHOOL_RLS_ROLE_PROBE_TIMEOUT_SECONDS"
DEFAULT_PROBE_TIMEOUT_SECONDS = 10.0


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


def probe_timeout_seconds() -> float:
    """مهلة فحص الدور (اكتساب الاتّصال + الاستعلام). الفحص على مسار الإقلاع الحرج:
    قاعدةٌ تقبل الاتّصال وتتوقّف عند الاستعلام لا يجوز أن تُعلِّق الإقلاع بلا نهاية."""
    import os

    raw = os.getenv(PROBE_TIMEOUT_ENV, "").strip()
    try:
        value = float(raw) if raw else DEFAULT_PROBE_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_PROBE_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_PROBE_TIMEOUT_SECONDS


async def _fetch_role_row(pool_or_conn):
    if hasattr(pool_or_conn, "acquire"):
        async with pool_or_conn.acquire() as conn:
            return await conn.fetchrow(ROLE_PROBE_SQL)
    return await pool_or_conn.fetchrow(ROLE_PROBE_SQL)


async def assert_db_role_rls_safe(pool_or_conn, *, service: str = "") -> None:
    """يفحص دور الاتّصال عند الإقلاع ويرفض (fail-closed) إن لم تُثبَت سلامته والفرض مُفعَّل.

    `pool_or_conn`: asyncpg Pool (يُكتسَب منه اتّصال) أو Connection مباشر.
    يرفع RuntimeError عند الرفض (لا يُبتلَع — يجب أن يوقف إقلاع الخدمة):
      • دورٌ يتجاوز RLS (superuser/BYPASSRLS)؛
      • أو تعذّر الفحص نفسه (خطأ/مهلة ``probe_timeout_seconds``/لا صفّ) — دورٌ مجهول
        غير آمن ما دام الفرض مُفعَّلاً (LIFE-01: كان يُسجَّل DEBUG ويُكمِل الإقلاع).
    تجاوز التطوير الصريح وحده (SAHOOL_ALLOW_RLS_BYPASS_ROLE=1 أو SAHOOL_ENFORCE_RLS_ROLE=0)
    يسمح بفحص متعذّر — بتحذير يحمل اسم صنف الاستثناء فقط (رسائل السائق قد تحمل الـDSN).
    """
    import os

    log = logging.getLogger(service or "db_role_guard")
    svc = f"[{service}] " if service else ""
    enforce = enforcement_active(
        os.getenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE"), os.getenv("SAHOOL_ENFORCE_RLS_ROLE")
    )
    try:
        row = await asyncio.wait_for(_fetch_role_row(pool_or_conn), probe_timeout_seconds())
    except Exception as e:  # noqa: BLE001 — دورٌ مجهول غير آمن ما دام الفرض مُفعَّلاً
        if enforce:
            raise RuntimeError(
                f"{svc}RLS database role verification failed ({type(e).__name__})"
            ) from e
        log.warning("تعذّر فحص دور RLS مع تجاوز صريح: %s", type(e).__name__)
        return
    if row is None:
        if enforce:
            raise RuntimeError(f"{svc}RLS database role verification returned no role")
        log.warning("فحص دور RLS لم يُرجِع دوراً (تجاوز صريح)")
        return
    unsafe = role_can_bypass_rls(row["rolsuper"], row["rolbypassrls"])
    if not unsafe:
        return
    refuse = should_refuse_startup(unsafe, enforce)
    msg = role_guard_message(row["rolsuper"], row["rolbypassrls"], refuse, service)
    log.critical("🔓 %s", msg)
    if refuse:
        raise RuntimeError(msg)


async def assert_dsn_role_rls_safe(dsn: str, *, service: str = "") -> None:
    """نسخة DSN لخدمات بلا pool دائم عند الإقلاع (اتّصال per-call): تفتح اتّصالاً
    واحداً للفحص ثمّ تُغلقه. ترفع RuntimeError عند رفض الدور أو تعذّر فحصه بعد الاتّصال
    (كـassert_db_role_rls_safe). تعذّر الاتّصال نفسه (قاعدة غير متاحة بعد) يبقى
    best-effort — هذه الخدمات تُقلِع بلا قاعدة وتتّصل لكلّ طلب — لكنّه يُسجَّل WARNING
    لا DEBUG، ومحدودٌ بمهلة الفحص. بلا DSN ⇒ لا عمل."""
    if not dsn:
        return
    try:
        import asyncpg
    except Exception:  # noqa: BLE001 — لا asyncpg ⇒ لا فحص
        return
    try:
        conn = await asyncpg.connect(dsn, statement_cache_size=0, timeout=probe_timeout_seconds())
    except Exception as e:  # noqa: BLE001 — تعذّر الاتّصال ⇒ لا يحجب الإقلاع
        logging.getLogger(service or "db_role_guard").warning(
            "تعذّر اتّصال فحص دور RLS عند الإقلاع: %s", type(e).__name__
        )
        return
    try:
        await assert_db_role_rls_safe(conn, service=service)
    finally:
        await conn.close()
