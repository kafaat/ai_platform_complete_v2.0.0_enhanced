"""api/routers/scouting.py — تصنيف المشاهدات (Scouting Taxonomy)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الكتالوجات/الدوالّ النقيّة (``api.scouting_pins``) تُستورَد مباشرةً من وحدتها — وهي
نفس الكائنات التي كانت في ``main`` (``make_pin`` يبقى مُستورَداً هناك لنقطة الـpins).
أمّا التبعية ``get_current_user``/``UserSchema`` فتبقى في ``main`` وتُستورَد من
``api.main`` حفظاً لاستيرادات الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.

نقطة القراءة الدائمة (v94): ``GET /api/v1/scouting/pins?field_id=…`` تُرجِع الدبابيس
المُثبَّتة في ``scouting_pins`` (التي تكتبها نقطة POST ``/fields/{id}/pins``)، معزولةً
بالمستأجِر عبر RLS (نفس نمط قراءات الحقول). صدق: القاعدة غير مفعّلة ⇒ قائمة فارغة
صريحة مع سبب (لا اختراع مشاهدات).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api import main as api_main
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    get_current_user,
    require_permission,
    tenant_connection,
)
from api.scouting_pins import (
    NUTRIENT_DEFICIENCY_GUIDE,
    YEMEN_CROP_ISSUES,
    get_crop_issues,
)

router = APIRouter()

# أعمدة القراءة لجدول scouting_pins (v94) — مطابقة لـ ScoutingPin.to_dict تماماً
# (pin_id هو المعرّف القانوني للدبّوس). created_at يُنسَّق ISO في المُحوِّل أدناه.
_PIN_SELECT_COLS = (
    "pin_id, field_id, lat, lng, issue_category, severity, status, persistence, "
    "crop, issue_code, note_ar, photo_uri, color, created_by, created_at"
)


def _row_to_pin(row) -> dict:
    """يحوّل صفّ scouting_pins إلى dict مطابق لـ ScoutingPin.to_dict (مفتاح pin_id).

    نقيّ (لا I/O) ليُختبَر بـunit بلا قاعدة حيّة. ``created_at`` (timestamptz) يُنسَّق
    ISO؛ إن كان نصّاً أصلاً (mock) يُمرَّر كما هو.
    """
    created = row["created_at"]
    created_iso = created.isoformat() if hasattr(created, "isoformat") else (created or "")
    return {
        "pin_id": row["pin_id"],
        "field_id": row["field_id"],
        "lat": row["lat"],
        "lng": row["lng"],
        "issue_category": row["issue_category"],
        "severity": row["severity"],
        "status": row["status"],
        "persistence": row["persistence"],
        "crop": row["crop"],
        "issue_code": row["issue_code"],
        "note_ar": row["note_ar"],
        "photo_uri": row["photo_uri"],
        "color": row["color"],
        "created_by": row["created_by"],
        "created_at": created_iso,
    }


@router.get("/api/v1/scouting/pins")
async def list_scouting_pins(
    field_id: str = Query(..., description="معرّف الحقل لجلب دبابيسه"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """دبابيس مشاهدة الحقل المُخزَّنة (الأحدث أوّلاً) — معزولة بالمستأجِر (RLS).

    تقرأ من ``scouting_pins`` (v94) ما تكتبه نقطة POST ``/fields/{id}/pins`` — فتُغلِق
    الفجوة التي أبقت الواجهة الدبابيس محلّيّة للجلسة. تتحقّق أوّلاً أنّ الحقل يخصّ
    المستأجِر (404 وإلّا) عبر RLS، ثمّ تُرجِع ``{field_id, pins, total}``. صدق: القاعدة
    غير مفعّلة (``DATABASE_URL``) ⇒ قائمة فارغة + سبب (لا مشاهدات مخترَعة)؛ تعذّر
    القاعدة أثناء التنفيذ ⇒ 503 موثَّق.
    """
    if api_main._DB_POOL is None:
        return {
            "field_id": field_id,
            "pins": [],
            "total": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا دبابيس مُخزَّنة",
        }
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_PIN_SELECT_COLS} FROM scouting_pins "
                "WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا اختراع تاريخ)
        raise _db_unavailable("جلب دبابيس الاستطلاع", e) from e
    pins = [_row_to_pin(r) for r in rows]
    return {"field_id": field_id, "pins": pins, "total": len(pins)}


@router.get("/api/v1/scouting/taxonomy")
def scouting_taxonomy(
    crop: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """قوائم المشاكل (للقوائم المنسدلة). لو crop معطى، يُرجع مشاكله فقط."""
    if crop:
        return {"crop": crop, "issues": get_crop_issues(crop)}
    return {
        "crops": list(YEMEN_CROP_ISSUES.keys()),
        "all_issues": YEMEN_CROP_ISSUES,
        "nutrient_guide": NUTRIENT_DEFICIENCY_GUIDE,
    }
