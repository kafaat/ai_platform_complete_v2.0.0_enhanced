"""api/routers/scenario.py — سيناريوهات "ماذا لو" الفيزيائيّة (What-If)
=======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

حساب فيزيائي offline فوق ميزان الماء/GDD — لا توأم رقمي، لا M2M، لا ML.
الدوالّ المساعِدة (``whatif_*``) والمحوّلات (``DailyTemp``/``WeatherInput``)
تُستورَد مباشرةً من وحداتها الأصليّة (نفس الكائنات التي كان ``main`` يستوردها —
نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدوالّ). نماذج الطلب تبقى
مُعرَّفةً في ``main`` وتُستورَد من ``api.main`` حفظاً لـ``_rebuild_pydantic_models``
واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه
في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.gdd_tracker import GDD_CROP_PARAMS, stage_result_from_cumulative
from api.main import (
    UserSchema,
    WhatIfPlantingRequest,
    WhatIfRainRequest,
    WhatIfTempRequest,
    get_current_user,
)
from api.scenario_whatif import (
    whatif_planting_date,
    whatif_rainfall_change,
    whatif_temperature_shift,
)
from api.water_balance import WeatherInput as _WInput
from api.water_twin import (
    DayPlan,
    compare_scenarios,
    delay_irrigation,
    scale_irrigation,
)
from api.weather_service_client import get_gdd_product

router = APIRouter()


# ─── Water Twin: مسار رطوبة التربة الأماميّ (ماذا لو أخّرتُ/خفّضتُ الريّ؟) ───────
# نماذج الطلب مُعرَّفة محليّاً (لا تحتاج _rebuild_pydantic_models) — إضافة لراوتر
# مُفكَّك قائم (يبقى حارس التفكيك أخضر؛ لا توسيع main.py).
class _WaterTwinDay(BaseModel):
    """خطّة يوم: ETc المحتمَل + مطر فعّال + ريّ مُطبَّق (مم، غير سالبة)."""

    etc_mm: float = Field(..., ge=0)
    rain_mm: float = Field(default=0.0, ge=0)
    irrigation_mm: float = Field(default=0.0, ge=0)


class WaterTwinRequest(BaseModel):
    """طلب محاكاة Water Twin: حالة التربة + جدول الأساس + تحويل البديل.

    البديل إمّا تحويل على جدول الأساس (تأجيل/تحجيم الريّ) أو جدول صريح (``explicit``).
    حالة التربة (TAW/RAW/النضوب الابتدائيّ) تأتي من دفتر المياه اليوميّ (v98) أو تُمرَّر صراحةً.
    """

    taw_mm: float = Field(..., gt=0, description="إجماليّ الماء المتاح في منطقة الجذور")
    raw_mm: float = Field(..., gt=0, description="الماء المتاح بسهولة (= p·TAW)")
    initial_depletion_mm: float = Field(default=0.0, ge=0)
    days: list[_WaterTwinDay] = Field(..., min_length=1, description="جدول الأساس اليوميّ")
    scenario_kind: Literal["delay", "scale", "explicit"] = "delay"
    delay_days: int = Field(default=0, ge=0, description="أيّام تأجيل الريّ (kind=delay)")
    scale_factor: float = Field(default=1.0, ge=0, description="معامل عمق الريّ (kind=scale)")
    scenario_days: list[_WaterTwinDay] | None = Field(
        default=None, description="جدول البديل الصريح (kind=explicit)"
    )


@router.post("/api/v1/scenario/water-twin")
def scenario_water_twin(
    req: WaterTwinRequest,
    user: UserSchema = Depends(get_current_user),
):
    """توأم المياه: يحاكي مسار نضوب الجذور لجدولَي ريّ ويقارن أيّام الإجهاد/استهلاك الماء.

    حساب FAO-56 فيزيائيّ offline (لا غلّة مُلفّقة). مدخل غير صالح (TAW/RAW/قيم سالبة) ⇒ 422.
    """
    baseline = [DayPlan(d.etc_mm, d.rain_mm, d.irrigation_mm) for d in req.days]
    if req.scenario_kind == "delay":
        scenario = delay_irrigation(baseline, req.delay_days)
    elif req.scenario_kind == "scale":
        scenario = scale_irrigation(baseline, req.scale_factor)
    else:  # explicit
        if not req.scenario_days:
            raise HTTPException(
                status_code=422,
                detail="scenario_days مطلوب عندما scenario_kind=explicit.",
            )
        scenario = [DayPlan(d.etc_mm, d.rain_mm, d.irrigation_mm) for d in req.scenario_days]
    try:
        return compare_scenarios(
            req.taw_mm, req.raw_mm, req.initial_depletion_mm, baseline, scenario
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/api/v1/scenario/temperature")
def scenario_temperature(
    req: WhatIfTempRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو تغيّرت الحرارة؟ أثر فيزيائي على ET0 والاحتياج المائي."""
    w = _WInput(
        t_min_c=req.t_min_c,
        t_max_c=req.t_max_c,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    return whatif_temperature_shift(w, req.crop, req.stage, req.temp_shift_c, rain_mm=req.rain_mm)


@router.post("/api/v1/scenario/planting-date")
async def scenario_planting_date(
    req: WhatIfPlantingRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو غيّرتُ تاريخ الزراعة؟ أثر على تراكم GDD وبلوغ المراحل.

    WS-C.1c Zero-Legacy: نواة GDD تُحسب في محرّك الطقس (method=simple، نفس الإرث)؛ لا
    ``track_gdd`` محلّيّ. تعذّر المحرّك ⇒ 503 fail-closed. سياسة المراحل تبقى في المنصّة.
    """
    params = GDD_CROP_PARAMS.get(req.crop)
    if params is None:
        raise HTTPException(
            status_code=422,
            detail=f"محصول غير معروف لـGDD: {req.crop}. المتاح: {list(GDD_CROP_PARAMS)}",
        )
    t_base = params["t_base"]
    t_upper = params["t_upper"]

    async def _cumulative(temps: list[dict]) -> float:
        try:
            engine = await get_gdd_product(
                daily_t_min=[t["t_min_c"] for t in temps],
                daily_t_max=[t["t_max_c"] for t in temps],
                base_c=t_base,
                upper_cutoff_c=t_upper,
                method="simple",
            )
        except HTTPException as exc:
            if exc.status_code in (502, 503, 504):
                raise HTTPException(
                    status_code=503,
                    detail="weather-engine GDD unavailable — fail-closed (no local GDD fallback)",
                ) from exc
            raise
        cum = engine.get("accumulated_gdd")
        if cum is None:
            raise HTTPException(
                status_code=422,
                detail={"reason": "gdd_insufficient", "limitations": engine.get("limitations")},
            )
        return float(cum)

    base_cum = await _cumulative(req.temps_baseline)
    scen_cum = await _cumulative(req.temps_scenario)
    base = stage_result_from_cumulative(req.crop, base_cum, len(req.temps_baseline))
    scen = stage_result_from_cumulative(req.crop, scen_cum, len(req.temps_scenario))
    return whatif_planting_date(req.crop, base, scen)


@router.post("/api/v1/scenario/rainfall")
def scenario_rainfall(
    req: WhatIfRainRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو تغيّر المطر الموسمي؟ أثر على صافي الريّ المطلوب."""
    w = _WInput(
        t_min_c=req.t_min_c,
        t_max_c=req.t_max_c,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    return whatif_rainfall_change(
        w, req.crop, req.stage, req.rain_baseline_mm, req.rain_scenario_mm
    )
