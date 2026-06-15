"""api/routers/seasons.py — محاكاة الموسم (Seasons / season_simulation)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

⚠ هذا الموجِّه للمسار ``/api/v1/seasons/{season_id}/simulate`` فقط؛ المسار المرتبط
بالحقل ``/api/v1/fields/{id}/seasons`` يبقى ضمن نطاق الحقول (routers/fields.py).

النموذج ``SeasonSimResponse`` والثابت ``_SIM_MAX_WINDOW_DAYS`` والمساعِد
``_db_unavailable`` تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا. الاستيرادات
الكسولة داخل الدالّة (openmeteo/season_simulation) تبقى كما هي. لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _SIM_MAX_WINDOW_DAYS,
    Permission,
    SeasonSimResponse,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/seasons/{season_id}/simulate", response_model=SeasonSimResponse)
async def simulate_season_endpoint(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يشغّل محاكاة محصوليّة (RUE/FAO-56) للموسم ويحفظ الناتج على صفّه.

    يؤكّد أنّ الموسم يخصّ المستأجِر (404 وإلّا)، يجمع المحصول/التواريخ من القاعدة
    والطقس التاريخي من Open-Meteo لنافذة الموسم (sowing→end أو آخر ~160 يوماً)،
    يستدعي api.season_simulation.simulate_season (نقيّ)، يكتب sim_* + sim_ran_at،
    ويردّ النتيجة (تقديرات بنطاق وثقة). 503 إن تعذّرت القاعدة أو الطقس.
    """
    import json as _json

    from api.connectors.openmeteo import fetch_historical
    from api.season_simulation import DayWeather, SimContext, simulate_season

    # ١) سياق الموسم من القاعدة (+ تأكيد المستأجِر عبر RLS ⇒ 404 إن غاب).
    try:
        async with tenant_connection(user) as conn:
            srow = await conn.fetchrow(
                "SELECT s.season_id, s.field_id, s.crops, s.sowing_date, s.season_end, "
                "f.lat, f.lon FROM seasons s JOIN fields f ON f.field_id = s.field_id "
                "WHERE s.season_id = $1",
                season_id,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة الموسم للمحاكاة", e) from e
    if srow is None:
        raise HTTPException(status_code=404, detail="الموسم غير موجود ضمن هذا المستأجِر")
    if srow["lat"] is None or srow["lon"] is None:
        raise HTTPException(
            status_code=422,
            detail="حقل الموسم بلا إحداثيّات (lat/lon) — لا يمكن جلب الطقس للمحاكاة.",
        )

    crops = srow["crops"]
    if isinstance(crops, str):
        try:
            crops = _json.loads(crops)
        except (ValueError, TypeError):
            crops = []
    crop = str(crops[0]) if isinstance(crops, list) and crops else None

    # ٢) نافذة المحاكاة: من البذار إلى نهاية الموسم (أو اليوم)، بحدّ أقصى.
    today = datetime.now(UTC).date()
    sow = srow["sowing_date"]
    end = srow["season_end"]
    start = sow if sow is not None else (today - timedelta(days=_SIM_MAX_WINDOW_DAYS))
    win_end = min(end, today) if end is not None else today
    if win_end <= start:
        win_end = min(start + timedelta(days=_SIM_MAX_WINDOW_DAYS), today)
    if (win_end - start).days > _SIM_MAX_WINDOW_DAYS:
        win_end = start + timedelta(days=_SIM_MAX_WINDOW_DAYS)
    # ERA5 التاريخي يتأخّر ~5 أيّام — لا نطلب أحدث من ذلك.
    win_end = min(win_end, today - timedelta(days=5))
    if win_end <= start:
        raise HTTPException(
            status_code=422,
            detail="نافذة الموسم قصيرة جدّاً أو في المستقبل — لا بيانات طقس تاريخيّة كافية للمحاكاة.",
        )

    # ٣) الطقس التاريخي (ERA5) من Open-Meteo — تعذّره ⇒ 503 صريح.
    try:
        days = await fetch_historical(
            float(srow["lat"]),
            float(srow["lon"]),
            start.isoformat(),
            win_end.isoformat(),
        )
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس التاريخي (Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    weather = [
        DayWeather(
            t_min_c=d.temp_min_c,
            t_max_c=d.temp_max_c,
            solar_mj_m2=None,  # غير مطلوب من المصدر الحالي — يُقدَّر في النموذج
            et0_mm=d.et0_mm,
            rain_mm=d.precipitation_mm or 0.0,
        )
        for d in days
    ]

    # ٤) المحاكاة النقيّة.
    result = simulate_season(
        SimContext(crop=crop, sowing_date=sow, season_end=end, weather=weather)
    )

    # ٥) حفظ النتائج على صفّ الموسم (+ وقت التشغيل).
    ran_at = datetime.now(UTC)
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                "UPDATE seasons SET sim_yield_kg_ha = $2, sim_biomass_kg_ha = $3, "
                "sim_gdd_total = $4, sim_lai_max = $5, sim_water_mm = $6, sim_ran_at = $7 "
                "WHERE season_id = $1",
                season_id,
                result.yield_kg_ha,
                result.biomass_kg_ha,
                result.gdd_total,
                result.lai_max,
                result.water_need_mm,
                ran_at,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حفظ نتائج المحاكاة", e) from e

    return SeasonSimResponse(
        season_id=season_id,
        crop=result.crop,
        crop_recognized=result.crop_recognized,
        days_simulated=result.days_simulated,
        gdd_total=result.gdd_total,
        gdd_to_maturity=result.gdd_to_maturity,
        maturity_reached=result.maturity_reached,
        lai_max=result.lai_max,
        biomass_kg_ha=result.biomass_kg_ha,
        yield_kg_ha=result.yield_kg_ha,
        yield_low_kg_ha=result.yield_low_kg_ha,
        yield_high_kg_ha=result.yield_high_kg_ha,
        water_need_mm=result.water_need_mm,
        water_supply_mm=result.water_supply_mm,
        water_stress_factor=result.water_stress_factor,
        confidence=result.confidence,
        rationale_ar=result.rationale_ar,
        assumptions_ar=result.assumptions_ar,
        warnings_ar=result.warnings_ar,
        sim_ran_at=ran_at.isoformat(),
    )
