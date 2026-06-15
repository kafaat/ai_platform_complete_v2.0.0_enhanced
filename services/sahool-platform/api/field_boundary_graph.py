"""
services/sahool-platform/api/field_boundary_graph.py — بانـي شبكة حدود الحقل

الهدف (#15 — Field Boundary Graph):
    يحسب علاقات الجوار المكانيّة بين حدود حقول المستأجر (الجيران + طول الحافّة
    المشتركة) ويملأ جدول `field_boundary_graph`. هذه الشبكة تُمكّن التحليلات
    الإقليميّة عبر الحقول: انتشار الآفات والأمراض من حقلٍ لجاره، والريّ الجماعيّ
    عبر منطقة ريّ مشتركة، وتجميع الحقول المتلاصقة في وحدات معالجة إقليميّة.

طريقة الحساب (PostGIS حتميّ، ليس تعلّم آلة):
    - الجوار = `ST_Touches(a.geom, b.geom)` (حدّان يتلامسان دون تداخل المساحة).
    - طول الحافّة المشتركة = `ST_Length(ST_Intersection(a.geom, b.geom)::geography)`
      حيث تقاطع مضلّعين متلامسين هو الخطّ الحدوديّ المشترك، والتحويل إلى geography
      يُرجع الطول بالمتر على سطح الأرض (لا بدرجات 4326).

ملاحظة منهجيّة (صادقة):
    هذا حسابٌ هندسيّ حتميّ بالكامل (PostGIS)، وليس نموذجاً تعلّميّاً. القيم
    الأخرى لـ`relation_type` (shares_canal / shares_road / same_irrigation_zone)
    إثراءات مستقبليّة تُشتقّ من بيانات قنوات/طرق/مناطق ريّ — هذا الباني يبني
    علاقة 'adjacent' من الهندسة فقط.

ملاحظة عزل: الاستعلامات تعمل على اتّصال مُنطّق بالمستأجر (RLS مُفعّلة على
كلٍّ من field_boundaries وfield_boundary_graph). نمرّر tenant_id صراحةً إلى
أعمدة الكتابة لأنّ RLS تُرشّح القراءة لكنّها لا تملأ عمود الكتابة تلقائيّاً.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


# ─── SQL النواة (قابل للاختبار بلا قاعدة بيانات) ─────────────────


def adjacency_sql() -> str:
    """
    يُرجع نصّ SQL لبناء علاقات الجوار وكتابتها — دالّة نقيّة قابلة لاختبار الوحدة
    دون Postgres (يكفي التحقّق أنّ النصّ يحوي ST_Touches / ST_Intersection /
    field_boundary_graph / ON CONFLICT).

    تصميم الاستعلام:
      ١. CTE `pairs` يجد كلّ الأزواج المرتّبة من حقول مختلفة تتلامس حدودها.
         الشرط `a.field_id <> b.field_id` (لا الزوج المرتّب a<b) يجعل الاستعلام
         يُصدِر كلا الاتّجاهين a→b و b→a تلقائيّاً — فلا حاجة لإدراج معكوس يدويّ.
         حُرّاس `geom IS NOT NULL` يتجاهلان الحقول بلا هندسة (best-effort).
      ٢. INSERT … SELECT يكتب الصفوف بـrelation_type='adjacent'، وyعالج التضارب
         على القيد الفريد (tenant_id, field_id, neighbor_field_id, relation_type)
         بتحديث طول الحافّة المشتركة (idempotent — إعادة البناء آمنة).
      ٣. tenant_id يُمرَّر معاملاً ($1) ويُكتب صراحةً في كلّ صفّ (للكتابة تحت RLS).

    التحويل ::geography يجعل ST_Length يُرجع الطول بالمتر (geodesic) لا بدرجات.
    """
    return """
    WITH pairs AS (
        SELECT
            a.field_id  AS field_id,
            b.field_id  AS neighbor_field_id,
            -- تقاطع مضلّعين متلامسين = الخطّ الحدوديّ المشترك؛ ::geography ⇒ متر
            ST_Length(ST_Intersection(a.geom, b.geom)::geography) AS shared_edge_length_m
        FROM field_boundaries a
        JOIN field_boundaries b
          ON a.field_id <> b.field_id          -- أزواج مرتّبة بكلا الاتّجاهين
         AND a.geom IS NOT NULL                -- تجاهل الهندسات الفارغة (best-effort)
         AND b.geom IS NOT NULL
         AND ST_Touches(a.geom, b.geom)        -- جوار: تلامس دون تداخل مساحيّ
    )
    INSERT INTO field_boundary_graph
        (tenant_id, field_id, neighbor_field_id, relation_type, shared_edge_length_m)
    SELECT $1::uuid, field_id, neighbor_field_id, 'adjacent', shared_edge_length_m
    FROM pairs
    ON CONFLICT (tenant_id, field_id, neighbor_field_id, relation_type)
    DO UPDATE SET shared_edge_length_m = EXCLUDED.shared_edge_length_m
    """


# ─── المنفّذ (يتطلّب اتّصال asyncpg مُنطّق بالمستأجر) ──────────────


async def rebuild_graph_for_tenant(conn: asyncpg.Connection, tenant_id: str) -> int:
    """
    يعيد بناء شبكة حدود الحقل للمستأجر المعطى على الاتّصال المُنطّق (RLS مُطبَّقة).

    يجد كلّ أزواج الحقول المتجاورة (ST_Touches) ويكتب علاقات 'adjacent' مع طول
    الحافّة المشتركة بالمتر، ثمّ يُرجع عدد العلاقات المكتوبة.

    صادق/أفضل-جهد: لو كانت الهندسات فارغة فالحُرّاس في الاستعلام تتجاهلها فيعود
    العدّ صفراً دون خطأ. لو كان PostGIS غير متاح (لا ST_Touches) يرفع asyncpg
    استثناءً — نسجّله ونعيد رفعه (لا نُخفي عطلاً بنيويّاً).

    ملاحظة: يُمرَّر tenant_id كنصّ ويُحوَّل في SQL عبر $1::uuid (لتفادي اعتماد
    صريح على نوع UUID في طبقة بايثون، مرآةً لبقيّة الوحدات).
    """
    try:
        result = await conn.execute(adjacency_sql(), tenant_id)
    except Exception:  # noqa: BLE001 — نسجّل ثمّ نعيد الرفع (لا نُخفي عطل PostGIS)
        logger.exception(
            "field_boundary_graph: فشل بناء الشبكة للمستأجر %s (PostGIS متاح؟)",
            tenant_id,
        )
        raise

    # asyncpg تُرجع وسماً مثل "INSERT 0 5" — الرقم الأخير هو عدد الصفوف المتأثّرة.
    count = _parse_affected_rows(result)
    logger.info(
        "field_boundary_graph: كُتبت %d علاقة جوار للمستأجر %s",
        count,
        tenant_id,
    )
    return count


def _parse_affected_rows(command_tag: str | None) -> int:
    """
    يستخرج عدد الصفوف المتأثّرة من وسم أمر asyncpg (مثل 'INSERT 0 5' ⇒ 5).
    دالّة نقيّة (قابلة لاختبار الوحدة بلا قاعدة بيانات).
    """
    if not command_tag:
        return 0
    parts = command_tag.strip().split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except ValueError:
        return 0
