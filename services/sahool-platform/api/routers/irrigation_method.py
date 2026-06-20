"""api/routers/irrigation_method.py — كشف أثر طريقة الريّ (#387)

يكشف ملامح طرق الريّ (كفاءة/بلل/Ke/سقف دفعة/طاقة) وتحويل الصافي ⇒ الإجماليّ المسحوب.
GET للملامح + POST /gross للتحويل. الكفاءات افتراضات FAO عامّة موسومة calibrated=False.

محفوظ النمط: مُسجَّل في main (يمرّ حارس التفكيك)، `Depends(get_current_user)`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.irrigation_method import (
    METHOD_NAMES_AR,
    gross_irrigation_mm,
    method_profile,
)
from api.main import UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/irrigation-method")
def list_methods(user: UserSchema = Depends(get_current_user)):
    """كلّ ملامح طرق الريّ (غمر/أخاديد/مرشّات/محوري/تقطير)."""
    return {"methods": [method_profile(m) for m in METHOD_NAMES_AR]}


@router.get("/api/v1/irrigation-method/{method}")
def get_method(method: str, user: UserSchema = Depends(get_current_user)):
    """ملامح طريقة واحدة (يطبّع العربيّة؛ المجهولة ⇒ عامّ موسوم)."""
    return method_profile(method)


class GrossRequest(BaseModel):
    net_mm: float
    method: str | None = None
    application_efficiency: float | None = None


@router.post("/api/v1/irrigation-method/gross")
def compute_gross(req: GrossRequest, user: UserSchema = Depends(get_current_user)):
    """الماء الإجماليّ المسحوب = الصافي ÷ كفاءة التطبيق (للتكلفة/سعة الآبار، لا الصافي)."""
    prof = method_profile(req.method)
    gross_mm = gross_irrigation_mm(req.net_mm, req.method, req.application_efficiency)
    return {
        "net_mm": round(req.net_mm, 2),
        "gross_mm": gross_mm,
        "gross_m3_ha": round(gross_mm * 10.0, 2),  # 1 مم = 10 م³/هكتار
        "application_efficiency": req.application_efficiency or prof["application_efficiency"],
        "method": prof["method"],
        "pressurized": prof["pressurized"],
        "calibrated": False,
    }
