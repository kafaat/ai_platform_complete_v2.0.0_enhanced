"""api/routers/field_readiness.py — Field Readiness façade for UI-4.

يعرّف ``GET /api/v1/fields/{field_id}/readiness`` كواجهة مستقرة للواجهة حول
"جاهزية الحقل". يعتمد حالياً على عقد ``data-completeness`` الموجود فعلياً، ثم
يطبع النتيجة إلى شكل UI ثابت: score/items/missing/warnings/calibrated.

صدق: الدرجة هنا readiness/data availability وليست حكماً على صحة المحصول. لذلك
``calibrated=false`` حتى تتوفر عينات تحقق ميداني كافية.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission
from api.routers.field_completeness import field_data_completeness

router = APIRouter()

_STATUS_PRESENT = "complete"
_STATUS_MISSING = "missing"

_LABELS_AR = {
    "has_geometry": "حدود الحقل",
    "has_coords": "موقع الحقل",
    "has_soil_lab": "عينة/تحليل تربة",
    "has_active_season": "موسم نشط",
    "has_sowing_date": "تاريخ الزراعة/البذار",
    "has_ndvi": "آخر مؤشر نباتي",
    "has_soil_moisture": "رطوبة التربة",
}

_ACTIONS_AR = {
    "has_geometry": "ارسم أو ارفع حدود الحقل",
    "has_coords": "حدد موقع الحقل على الخريطة",
    "has_soil_lab": "ارفع عينة تربة",
    "has_active_season": "أضف موسماً نشطاً",
    "has_sowing_date": "أكمل تاريخ الزراعة",
    "has_ndvi": "فعّل/حدّث صور القمر الصناعي",
    "has_soil_moisture": "اربط حساس رطوبة أو أدخل قراءة ميدانية",
}


def _readiness_item(key: str, present: bool, improvement: dict | None = None) -> dict:
    return {
        "key": key,
        "label_ar": _LABELS_AR.get(key, key),
        "status": _STATUS_PRESENT if present else _STATUS_MISSING,
        "weight": improvement.get("weight") if improvement else None,
        "reason_ar": (improvement or {}).get("why_ar"),
        "action_label_ar": None if present else _ACTIONS_AR.get(key, "أكمل هذا البند"),
    }


@router.get("/api/v1/fields/{field_id}/readiness")
async def field_readiness(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يرجع جاهزية الحقل بشكل مناسب للواجهة، دون اختراع بيانات.

    يُعيد 404/503 كما يعيدها ``data-completeness`` عند غياب الحقل أو تعطل القاعدة.
    """
    comp = await field_data_completeness(field_id, user)
    present = set(comp.get("present") or [])
    missing = list(comp.get("missing") or [])
    improvements = {i.get("dimension"): i for i in comp.get("improvements_ar") or []}
    keys = list(present) + [k for k in missing if k not in present]
    items = [_readiness_item(k, k in present, improvements.get(k)) for k in keys]
    return {
        "field_id": field_id,
        "score": int(comp.get("score_pct") or comp.get("score") or 0),
        "level": comp.get("level"),
        "calibrated": False,
        "items": items,
        "missing": missing,
        "warnings": [],
        "note_ar": comp.get("note_ar")
        or "درجة الجاهزية تقيس حضور البيانات لا صحة المحصول، ولا تُعدّ مُعايرة بعد.",
    }
