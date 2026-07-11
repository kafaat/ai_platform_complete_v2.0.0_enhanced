"""api/routers/gdd.py — تتبّع GDD (Growing Degree Days Tracking)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

WS-C.1c: نواة GDD اليوميّة من **محرّك الطقس** (المصدر الوحيد)، لا تُحسب محلّيّاً.
سياسة المراحل (عتبات ``GDD_CROP_PARAMS``) تبقى هنا (Season) وتُطبَّق على تراكميّ
المحرّك عبر ``stage_result_from_cumulative``. تعذّر المحرّك ⇒ 503 (لا GDD محلّيّ بديل).
WS-C.1c Zero-Legacy: أُزيلت المقارنة الظلّيّة ونواة GDD المحلّيّة (المحرّك مصدر وحيد).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.gdd_tracker import (
    GDD_CROP_PARAMS,
    stage_result_from_cumulative,
)
from api.main import (
    GDDRequest,
    UserSchema,
    get_current_user,
)
from api.weather_service_client import get_gdd_product

router = APIRouter()

_ENGINE_DOWN_CODES = (502, 503, 504)
# gdd_tracker يستخدم طريقة المتوسّط بقصّ tmax فقط = الطريقة الكنسيّة "simple".
_TRACKER_METHOD = "simple"


async def _engine_gdd(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method):
    """نواة GDD من محرّك الطقس — نقطة وصل قابلة للـmonkeypatch (تُثبِت الاستهلاك)."""
    return await get_gdd_product(
        daily_t_min=daily_t_min,
        daily_t_max=daily_t_max,
        base_c=base_c,
        upper_cutoff_c=upper_cutoff_c,
        method=method,
    )


@router.post("/api/v1/gdd/track")
async def gdd_track(
    req: GDDRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتراكم GDD (نواة المحرّك) ويحدّد مرحلة المحصول + المتبقّي للتالية (سياسة محلّيّة)."""
    params = GDD_CROP_PARAMS.get(req.crop)
    if params is None:
        raise HTTPException(
            status_code=422,
            detail=f"محصول غير معروف لـGDD: {req.crop}. المتاح: {list(GDD_CROP_PARAMS)}",
        )
    t_base = params["t_base"]
    t_upper = params["t_upper"]
    daily_t_min = [t.t_min_c for t in req.temps]
    daily_t_max = [t.t_max_c for t in req.temps]

    # النواة من المحرّك (المصدر الوحيد). تعذّره ⇒ fail-closed 503 (لا حساب محلّيّ).
    try:
        engine = await _engine_gdd(
            daily_t_min=daily_t_min,
            daily_t_max=daily_t_max,
            base_c=t_base,
            upper_cutoff_c=t_upper,
            method=_TRACKER_METHOD,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503,
                detail="weather-engine GDD unavailable — fail-closed (no local GDD fallback)",
            ) from exc
        raise

    engine_cum = engine.get("accumulated_gdd")
    if engine_cum is None:
        raise HTTPException(
            status_code=422,
            detail={"reason": "gdd_insufficient", "limitations": engine.get("limitations")},
        )

    # سياسة المراحل تُطبَّق على تراكميّ المحرّك (العتبات تبقى في المنصّة/الموسم).
    result = stage_result_from_cumulative(req.crop, float(engine_cum), len(req.temps)).to_dict()

    # WS-C.1c Zero-Legacy: أُزيلت المقارنة الظلّيّة (المحرّك هو مصدر GDD الوحيد الآن — لا
    # ``track_gdd``/``daily_gdd`` محلّيّ يُقارَن به). النَّسَب من المحرّك مباشرة.
    result["gdd_provenance"] = {
        "source": "weather-engine",
        "calculation_version": engine.get("calculation_version"),
        "thresholds_used": engine.get("thresholds_used"),
        "valid_period": engine.get("valid_period"),
    }
    return result
