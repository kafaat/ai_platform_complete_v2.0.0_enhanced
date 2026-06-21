"""db_persist.py — وصول قاعدة البيانات لـsoil-service (تفويض ملكيّة الحقل).

يعكس نمط raster-service/db_persist.py بدقّة (لا استيراد عبر الخدمات): يستعلم
مالك الحقل (tenant_id) من المصدر الموثوق (جدول fields) عبر الدالّة
SECURITY DEFINER `sahool_field_owner_tenant` (migration v88) لفرض عزل
المستأجرين على قراءة/استيعاب قراءات التربة بمعرّف الحقل (إغلاق IDOR).

⚠ لا ننشئ الدالّة هنا — نشير إليها (تُنشأ بـmigration v88).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("soil-service.db")

DATABASE_URL = os.getenv("DATABASE_URL", "")


async def _connect():
    """يفتح اتّصالاً قصير العمر لكلّ عمليّة (لا pool مُخزَّن عبر حلقات الحدث).

    يُعيد None إن لم يُضبط DATABASE_URL (وضع بلا قاعدة مقصود — تطوير/CI) أو إن
    غاب asyncpg. غياب القاعدة لا يُفشل المنطق هنا (يُترَك القرار للمنادي)."""
    if not DATABASE_URL:
        return None
    try:
        import asyncpg
    except ImportError:
        return None
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


class OwnerLookupUnavailable(Exception):
    """تعذّر إثبات ملكيّة الحقل رغم أنّ القاعدة **مُهيّأة** (DATABASE_URL مضبوط) —
    اتّصال/استعلام فاشل أو الدالّة غائبة. يُميَّز عن «وضع بلا قاعدة» (DATABASE_URL
    غير مضبوط) كي تستطيع المسارات fail-closed عند تعذّر الإثبات فقط، دون كسر
    التشغيل المقصود بلا قاعدة (CI/تطوير)."""


async def field_owner_tenant(field_id: str) -> str | None:
    """مالك الحقل (tenant_id نصّاً) من المصدر الموثوق: جدول fields.

    يستعلم المالك الحقيقيّ عبر الدالّة SECURITY DEFINER `sahool_field_owner_tenant`
    (تتجاوز RLS/FORCE على fields فتقرأ المالك عبر المستأجرين، وتُعيد المعرّف فقط
    لا بيانات الحقل). field_id مفتاح أساسيّ ⇒ مالك واحد عالميّاً.

    تعاقُد الإرجاع:
    - نصّ المالك إن وُجد الحقل في fields.
    - None إن: (أ) DATABASE_URL غير مضبوط (وضع بلا قاعدة مقصود) أو (ب) الحقل غير
      موجود فعلاً (استعلام نجح بلا صفّ) — الحالتان لا تُوجبان الحجب.
    - يرفع OwnerLookupUnavailable إن كان DATABASE_URL **مضبوطاً** لكن تعذّر الاتّصال/
      الاستعلام/الدالّة غائبة ⇒ لا يمكن إثبات الملكيّة ⇒ يقرّر المنادي fail-closed."""
    if not DATABASE_URL:
        return None  # وضع بلا قاعدة مقصود — لا مصدر ملكيّة (لا حجب)
    try:
        conn = await _connect()
    except Exception as e:  # noqa: BLE001 — DATABASE_URL مضبوط لكن الاتّصال فشل
        logger.warning(
            "field_owner_tenant connect unavailable (%s): %s", field_id, type(e).__name__
        )
        raise OwnerLookupUnavailable(str(e)) from e
    if conn is None:
        # DATABASE_URL مضبوط لكنّ asyncpg غائب ⇒ الإثبات غير متاح (لا fail-safe صامت)
        raise OwnerLookupUnavailable(f"connect unavailable for field {field_id}")
    try:
        owner = await conn.fetchval("SELECT sahool_field_owner_tenant($1)", field_id)
        return str(owner) if owner else None  # مالك، أو None = غير موجود فعلاً
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكن الاستعلام/الدالّة تعذّرا
        logger.warning("field_owner_tenant unavailable (%s): %s", field_id, type(e).__name__)
        raise OwnerLookupUnavailable(str(e)) from e
    finally:
        await conn.close()
