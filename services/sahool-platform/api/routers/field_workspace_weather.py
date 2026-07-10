"""api/routers/field_workspace_weather.py — Field Workspace weather façade (UI-27).

يوحّد endpoints الطقس التي تحتاجها صفحة Field Workspace حول field_id، بدلاً من أن
تعرف الواجهة lat/lon أو تجمع مصادر متعددة بنفسها. لا توجد توصيات وهمية: عند فشل
مصدر الطقس نرجع 503/502 واضحاً، وعند غياب الحقل نرجع 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    _field_weather_context,
    _latest_soil_moisture,
    require_permission,
    tenant_connection,
)
from api.weather_service_client import (
    get_chill_accumulation,
    get_lodging_risk,
    get_operation_plan,
    get_pollination_risk,
    get_thermal_stress,
)

router = APIRouter()


def _score_to_suitability(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.8:
        return "optimal"
    if score >= 0.55:
        return "acceptable"
    if score >= 0.3:
        return "poor"
    return "unsafe"


def _window_from_operation(item: dict[str, Any]) -> dict[str, Any]:
    best = item.get("best") if isinstance(item.get("best"), dict) else {}
    decision = best.get("operation") if isinstance(best.get("operation"), dict) else {}
    score_raw = decision.get("score") if isinstance(decision, dict) else None
    try:
        score = float(score_raw) if score_raw is not None else None
    except Exception:  # noqa: BLE001 — upstream value malformed
        score = None
    limiting = decision.get("limiting_factors") if isinstance(decision, dict) else None
    return {
        "operation": item.get("operation"),
        "start_at": best.get("time") or best.get("weather_time"),
        "end_at": None,
        "suitability": _score_to_suitability(score),
        "score": score,
        "limiting_factors": limiting if isinstance(limiting, list) else [],
        "confidence": None,
        "advice_ar": item.get("advice_ar"),
        "recommended": bool(item.get("recommended")),
    }


@router.get("/api/v1/fields/{field_id}/weather/thermal-stress")
async def field_weather_thermal_stress(
    field_id: str,
    days: int = Query(3, ge=1, le=16),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الإجهاد الحراريّ المركّب (حرّ نهار × برد ليل) للحقل مشروطاً بالمحصول/المرحلة.

    الخادم يستنتج lat/lon والمحصول/المرحلة من سياق الحقل ثم يطلب منتج الطقس الحتميّ
    من weather-service (منطق الطقس لا يُحسب في المتصفّح). صدق: غياب المحصول/المرحلة
    ⇒ الخدمة تُرجِع insufficient_context (دور supporting، لا حجب قرار).
    """
    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق طقس الحقل", exc) from exc

    try:
        product = await get_thermal_stress(
            lat, lon, crop=crop, stage=stage, days=days, model="best_match"
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب منتج الإجهاد الحراريّ من خدمة الطقس. حاول لاحقاً.",
        ) from exc

    return {"field_id": field_id, "crop": crop, "growth_stage": stage, **product}


@router.get("/api/v1/fields/{field_id}/weather/crop-stress")
async def field_weather_crop_stress(
    field_id: str,
    plant_height_cm: float | None = Query(None, ge=0, le=1000),
    chill_start_date: str | None = Query(None, min_length=10, max_length=10),
    chill_end_date: str | None = Query(None, min_length=10, max_length=10),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """عائلة إجهاد المحصول للحقل في نداء واحد: الرقود + التلقيح + تراكم البرودة.

    مُجمَّع كي لا يُنمّي عدد راوترات المنصّة (فلسفة التفكيك)؛ منطق الطقس كلّه في
    weather-service. كلّ منتج **best-effort**: تعذّر أحدها يُسجَّل خطأً مُعلَناً لا يُسقِط
    الباقي. المحصول/المرحلة يُمرَّران من سياق الحقل (شرط التصنيف؛ fail-closed عند الغياب).
    """
    from datetime import UTC, datetime, timedelta

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق طقس الحقل", exc) from exc

    if not (chill_start_date and chill_end_date):
        today = datetime.now(UTC).date()
        chill_end_date = (today - timedelta(days=1)).isoformat()
        chill_start_date = (today - timedelta(days=121)).isoformat()

    products: dict[str, Any] = {}
    errors: dict[str, str] = {}

    async def _collect(name: str, coro):
        try:
            products[name] = await coro
        except Exception as exc:  # noqa: BLE001 — best-effort: خطأ منتج لا يُسقِط الباقي
            errors[name] = str(exc)[:200]

    await _collect(
        "lodging_risk",
        get_lodging_risk(
            lat, lon, crop=crop, stage=stage, plant_height_cm=plant_height_cm, model="best_match"
        ),
    )
    await _collect(
        "pollination_weather_risk",
        get_pollination_risk(lat, lon, crop=crop, stage=stage, model="best_match"),
    )
    await _collect(
        "chill_accumulation",
        get_chill_accumulation(
            lat, lon, crop=crop, start_date=chill_start_date, end_date=chill_end_date
        ),
    )

    if not products:
        raise HTTPException(status_code=503, detail="تعذّر جلب منتجات إجهاد المحصول من خدمة الطقس.")
    return {
        "field_id": field_id,
        "crop": crop,
        "growth_stage": stage,
        "products": products,
        "partial": bool(errors),
        "errors": errors,
    }


@router.get("/api/v1/fields/{field_id}/weather/operation-windows")
async def field_weather_operation_windows(
    field_id: str,
    season_id: str | None = Query(None),
    horizon_hours: int = Query(48, ge=1, le=168),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """نوافذ العمليات الزراعية للحقل من weather-service.

    الواجهة تمرّر field_id فقط؛ الخادم يستنتج lat/lon من الحقل ضمن المستأجر ثم يطلب
    خطة تشغيل من weather-service. لا يتم حساب النوافذ في المتصفح.
    """
    try:
        async with tenant_connection(user) as conn:
            lat, lon, _crop, _stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق طقس الحقل", exc) from exc

    hours = "0,1,3,6,12,24,48"
    if horizon_hours > 48:
        hours = "0,1,3,6,12,24,48,72,96,120,144,168"
    try:
        plan = await get_operation_plan(
            lat,
            lon,
            operations="spraying,irrigation,harvesting,sowing,fertilizing",
            hours=hours,
            model="best_match",
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب نوافذ العمليات من خدمة الطقس. حاول لاحقاً.",
        ) from exc

    operations = plan.get("operations") if isinstance(plan, dict) else []
    windows = [_window_from_operation(op) for op in operations if isinstance(op, dict)]
    return {
        "field_id": field_id,
        "season_id": season_id,
        "windows": windows,
        "degraded": bool(plan.get("partial")) if isinstance(plan, dict) else False,
        "warning_ar": "بعض مصادر الطقس تعذّرت؛ النتيجة جزئية."
        if isinstance(plan, dict) and plan.get("partial")
        else None,
        "source": plan.get("source") if isinstance(plan, dict) else "weather-service",
    }


@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")
async def field_irrigation_advice_facade(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """توصية ريّ خادمية من ET0/Kc/المطر ورطوبة التربة إن توفرت."""
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import irrigation_advice

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, _days = await _field_weather_context(conn, field_id)
            soil_reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق الحقل", exc) from exc

    try:
        forecast = await fetch_daily_forecast(lat, lon, days=3)
        current = await fetch_current(lat, lon)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="تعذّر جلب الطقس من Open-Meteo.") from exc

    today = forecast[0] if forecast else None
    et0 = today.et0_mm if today and today.et0_mm is not None else None
    if et0 is None:
        raise HTTPException(status_code=503, detail="بيانات ET₀ غير متوفّرة حالياً.")
    forecast_rain = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
    soil_pct = soil_reading.value_pct if soil_reading is not None else None
    advice = irrigation_advice(
        et0_mm=et0,
        crop=crop,
        stage=stage,
        rain_recent_mm=current.precipitation_mm or 0.0,
        forecast_rain_mm=forecast_rain,
        soil_moisture_pct=soil_pct,
    )
    advice.update(
        {
            "field_id": field_id,
            "crop": crop,
            "stage": stage,
            "source": "open-meteo",
            "soil_moisture_pct": soil_pct,
            "soil_moisture_at": soil_reading.recorded_at.isoformat()
            if soil_reading is not None
            else None,
        }
    )
    return advice


@router.get("/api/v1/fields/{field_id}/weather/disease-risk")
async def field_disease_risk_facade(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مخاطر أمراض فطرية من بيانات الطقس فقط، بدون تخمين من الواجهة."""
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import disease_risk

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, _stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق الحقل", exc) from exc

    try:
        current = await fetch_current(lat, lon)
        forecast = await fetch_daily_forecast(lat, lon, days=3)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="تعذّر جلب الطقس من Open-Meteo.") from exc

    rain_3d = sum(f.precipitation_mm or 0.0 for f in forecast[:3])
    risk = disease_risk(
        temp_c=current.temperature_c,
        humidity_pct=current.humidity_pct,
        rain_mm_3d=rain_3d,
        crop=crop,
    )
    risk.update(
        {
            "field_id": field_id,
            "crop": crop,
            "temperature_c": round(current.temperature_c, 1),
            "humidity_pct": round(current.humidity_pct, 1),
            "rain_mm_3d": round(rain_3d, 1),
            "source": "open-meteo",
        }
    )
    return risk
