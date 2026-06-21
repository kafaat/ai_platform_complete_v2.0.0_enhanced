"""market_db_authz.py — تفويض ملكيّة الموارد لخادم Market MCP (fail-closed).

يغلق فجوتَي IDOR في أدوات الكتابة:
  • `tool_create_procurement`: ربط `field_id` لمستأجِر آخر بأمر شراء.
  • `tool_create_sales_listing`: ربط `batch_id` لمستأجِر آخر بعرض بيع.

نمط التعاقُد مطابق لـ`services/raster-service/db_persist.py`:
  - بلا `DATABASE_URL` (وضع بلا قاعدة/CI مقصود) ⇒ يُعيد None ⇒ لا حجب
    (لا مصدر ملكيّة؛ نُبقي CI أخضر ولا نبدأ بحجبٍ قاسٍ).
  - `DATABASE_URL` **مضبوط** لكن تعذّر الاتّصال/الاستعلام ⇒ يرفع
    `OwnerLookupUnavailable` ⇒ يقرّر المنادي fail-closed (لا نخدم بلا إثبات).
  - وُجد المصدر ⇒ يُعيد قيمة الملكيّة الحقيقيّة.

اتّصال قصير العمر لكلّ فحص (لا pool مُخزَّن) تفادياً لكسر الحلقات عبر event loops
(نفس مبرّر raster db_persist) — الفحص نادر (مرّة لكلّ كتابة).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("market-mcp.authz")

DATABASE_URL = os.getenv("DATABASE_URL", "")


class OwnerLookupUnavailable(Exception):
    """تعذّر إثبات الملكيّة رغم أنّ القاعدة **مُهيّأة** (DATABASE_URL مضبوط) —
    اتّصال/استعلام فاشل أو الدالّة/الجدول غائب. يُميَّز عن «وضع بلا قاعدة»
    (DATABASE_URL غير مضبوط) كي تستطيع أدوات الكتابة fail-closed عند تعذّر الإثبات
    فقط، دون كسر التشغيل المقصود بلا قاعدة (CI)."""


async def _connect():
    """يفتح اتّصالاً جديداً قصير العمر. None ⇒ بلا قاعدة (DATABASE_URL غير مضبوط)."""
    if not DATABASE_URL:
        return None
    try:
        import asyncpg
    except ImportError:
        return None
    # DATABASE_URL مضبوط: فشل الاتّصال يُرفَع (لا fail-safe صامت) — يقرّره المنادي.
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


async def field_owner_tenant(field_id: str) -> str | None:
    """مالك الحقل (tenant_id نصّاً) عبر دالّة SECURITY DEFINER الموثوقة
    `sahool_field_owner_tenant` (تتجاوز RLS على fields، تُعيد المعرّف فقط).

    تعاقُد الإرجاع (مطابق لـraster db_persist):
    - نصّ المالك إن وُجد الحقل.
    - None إن: (أ) DATABASE_URL غير مضبوط (بلا قاعدة) أو (ب) الحقل غير موجود فعلاً.
    - يرفع OwnerLookupUnavailable إن كان DATABASE_URL مضبوطاً لكن تعذّر الإثبات."""
    if not DATABASE_URL:
        return None  # وضع بلا قاعدة مقصود — لا مصدر ملكيّة
    try:
        conn = await _connect()
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكنّ الاتّصال فشل
        raise OwnerLookupUnavailable(f"connect failed for field {field_id}: {e}") from e
    if conn is None:
        raise OwnerLookupUnavailable(f"connect failed for field {field_id}")
    try:
        owner = await conn.fetchval("SELECT sahool_field_owner_tenant($1)", field_id)
        return str(owner) if owner else None  # مالك، أو None = غير موجود فعلاً
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكن الاستعلام/الدالّة تعذّرا
        logger.warning("field_owner_tenant unavailable (%s): %s", field_id, type(e).__name__)
        raise OwnerLookupUnavailable(str(e)) from e
    finally:
        await conn.close()


async def batch_visible_under_tenant(batch_id: str, tenant_id: str | None) -> bool | None:
    """هل الدفعة `batch_id` مرئيّة/مملوكة تحت سياق RLS لمستأجِر `tenant_id`؟

    مصدر الملكيّة: جدول `inventory_batches` (يحمل tenant_id وعليه عزل RLS لكلّ
    مستأجِر، v22). نضبط `app.current_tenant` ثمّ نستعلم الدفعة؛ إن لم يُعِد RLS صفّاً
    فهي غير مرئيّة للمستأجِر ⇒ يرفض المنادي (دفعة مستأجِر آخر أو غير موجودة).

    تعاقُد الإرجاع:
    - True  ⇒ الدفعة مرئيّة تحت RLS لهذا المستأجِر (مسموح).
    - False ⇒ القاعدة مُهيّأة والاستعلام نجح لكن لا صفّ تحت RLS (ارفض fail-closed).
    - None  ⇒ DATABASE_URL غير مضبوط (بلا قاعدة) ⇒ لا حجب (CI أخضر).
    - يرفع OwnerLookupUnavailable إن كان DATABASE_URL مضبوطاً لكن تعذّر الإثبات."""
    if not DATABASE_URL:
        return None  # وضع بلا قاعدة مقصود — لا مصدر ملكيّة
    try:
        conn = await _connect()
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكنّ الاتّصال فشل
        raise OwnerLookupUnavailable(f"connect failed for batch {batch_id}: {e}") from e
    if conn is None:
        raise OwnerLookupUnavailable(f"connect failed for batch {batch_id}")
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)",
            str(tenant_id) if tenant_id else "",
        )
        # RLS يقصر الرؤية على دفعات المستأجِر الحاليّ ⇒ صفّ مرئيّ = ملكيّة مُثبَتة.
        row = await conn.fetchval(
            "SELECT 1 FROM inventory_batches WHERE batch_id = $1 LIMIT 1",
            str(batch_id),
        )
        return row is not None
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكن الاستعلام/الجدول تعذّرا
        logger.warning(
            "batch_visible_under_tenant unavailable (%s): %s", batch_id, type(e).__name__
        )
        raise OwnerLookupUnavailable(str(e)) from e
    finally:
        await conn.close()
