"""api/routers/field_completeness.py — درجة اكتمال بيانات الحقل (per-field
DATA-COMPLETENESS).
===============================================================================
موجِّه واحد يكشف ``GET /api/v1/fields/{field_id}/data-completeness``: يقرأ صفّ
الحقل + موسمه النشط + حضور تحليل تربة مخبريّ + آخر متوسّط NDVI ضمن سياق المستأجِر
(RLS)، يُجمّع قاموس إشارات الحضور المسطّح، ثمّ يستدعي المنطق النقيّ
``core.field_completeness.score_field_completeness`` ويُرجِع نتيجته (درجة + مستوى +
الحاضر/الناقص + إرشاد التحسين العمليّ).

صدق: الدرجة تقيس **حضور بيانات الحقل** (مُمَكِّن لثقة القرار) لا صحّة المحصول —
يُوضَّح في ``note_ar`` العائد من النواة النقيّة.

نمط مطابق لـ``api/routers/fields.py``: يستورد التبعيّات المشتركة من ``api.main``
(``tenant_connection``/``_db_unavailable``/``Permission``/``UserSchema``/
``require_permission``)، 404 لو الحقل ليس للمستأجِر، 503 عند تعذّر القاعدة.

ملاحظة: هذا الموجِّه **غير مُسجَّل** في ``api/main.py`` — يُسجّله المسؤول (lead).
"""

from __future__ import annotations

from core.field_completeness import score_field_completeness
from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


async def _ndvi_present(conn, field_id: str) -> bool:
    """هل لهذا الحقل متوسّط NDVI محسوب (استشعار عن بُعد)؟ — قراءة دفاعيّة.

    أعمدة ``imagery_automation_fields.last_ndvi_mean`` (Stage D/v54) قد لا تكون
    مطبّقة في نشر متدرّج ⇒ نُحيط الاستعلام بـSAVEPOINT (transaction متداخلة) كي لا
    يكسر فشلُه (UndefinedColumn/UndefinedTable) المعاملةَ الخارجيّة، ونتراجع
    رشيقاً إلى «غائب» (صدق: لا قيمة لا اختراع). نفس نمط gather_field_freshness.
    """
    try:
        async with conn.transaction():  # SAVEPOINT
            val = await conn.fetchval(
                "SELECT last_ndvi_mean FROM imagery_automation_fields WHERE field_id = $1",
                field_id,
            )
        return val is not None
    except Exception:  # noqa: BLE001 — v54 غير مطبّقة/جدول غائب ⇒ تخطٍّ آمن (غائب)
        return False


@router.get("/api/v1/fields/{field_id}/data-completeness")
async def field_data_completeness(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """درجة اكتمال بيانات الحقل: ما يملكه الحقل من أبعاد بيانات وما ينقصه.

    يقرأ ضمن سياق المستأجِر (RLS): صفّ الحقل (الهندسة + lat/lon)، الموسم النشط
    (وجوده + تاريخ البذار)، حضور تحليل تربة مخبريّ معتمَد/منشور، آخر متوسّط NDVI،
    وأحدث قراءة رطوبة تربة (telemetry). يُجمّع منها إشارات الحضور ويستدعي المنطق
    النقيّ ``score_field_completeness``. 404 لو الحقل ليس للمستأجِر، 503 عند تعذّر
    القاعدة.

    الأعمدة/الجداول المقروءة:
      - ``fields(geometry, lat, lon)`` — الهندسة + الإحداثيّات.
      - ``seasons(season_id, sowing_date)`` حيث ``status='active'`` — الموسم النشط
        + تاريخ البذار.
      - ``soil_lab_tests`` حيث ``status IN ('approved','published')`` — حضور تحليل
        تربة مخبريّ معتمَد.
      - ``imagery_automation_fields.last_ndvi_mean`` — قراءة دفاعيّة (قد تغيب).
      - أجهزة رطوبة التربة عبر ``_latest_soil_moisture`` (device_telemetry).
    """
    from api.main import _assert_field_in_tenant, _latest_soil_moisture

    try:
        async with tenant_connection(user) as conn:
            # 404 لو الحقل ليس للمستأجِر — قبل أيّ قراءة أخرى.
            await _assert_field_in_tenant(conn, field_id)

            field_row = await conn.fetchrow(
                "SELECT geometry, lat, lon FROM fields WHERE field_id = $1",
                field_id,
            )
            # نادر: سُحب الحقل بين التأكيد والقراءة ⇒ 404 صادق.
            if field_row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")

            # الموسم النشط (أحدث active) — وجوده + تاريخ بذاره.
            season_row = await conn.fetchrow(
                "SELECT season_id, sowing_date FROM seasons "
                "WHERE field_id = $1 AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                field_id,
            )

            # حضور تحليل تربة مخبريّ معتمَد/منشور لهذا الحقل (وجوده فقط).
            soil_lab = await conn.fetchval(
                "SELECT 1 FROM soil_lab_tests "
                "WHERE field_id = $1 AND status IN ('approved', 'published') LIMIT 1",
                field_id,
            )

            ndvi_present = await _ndvi_present(conn, field_id)

            soil_moisture = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة اكتمال بيانات الحقل", e) from e

    signals = {
        "has_geometry": field_row["geometry"] is not None,
        "has_coords": field_row["lat"] is not None and field_row["lon"] is not None,
        "has_soil_lab": soil_lab is not None,
        "has_active_season": season_row is not None,
        "has_sowing_date": season_row is not None and season_row["sowing_date"] is not None,
        "has_ndvi": ndvi_present,
        "has_soil_moisture": soil_moisture is not None,
    }

    result = score_field_completeness(signals)
    result["field_id"] = field_id
    return result
