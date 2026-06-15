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

from fastapi import APIRouter, Depends, HTTPException

from api.gdd_tracker import DailyTemp as _DTemp
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

router = APIRouter()


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
def scenario_planting_date(
    req: WhatIfPlantingRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ماذا لو غيّرتُ تاريخ الزراعة؟ أثر على تراكم GDD وبلوغ المراحل."""
    base = [_DTemp(t["t_min_c"], t["t_max_c"]) for t in req.temps_baseline]
    scen = [_DTemp(t["t_min_c"], t["t_max_c"]) for t in req.temps_scenario]
    try:
        return whatif_planting_date(req.crop, base, scen)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


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
