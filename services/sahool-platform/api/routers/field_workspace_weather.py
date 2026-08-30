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
    get_current_weather,
    get_lodging_risk,
    get_operation_plan,
    get_pollination_risk,
    get_thermal_stress,
    get_weather_forecast,
)

router = APIRouter()


# ─── مُحوِّلُ غلافِ خدمة الطقس ──────────────────────────────────────
#
# **لمَ مُحوِّلٌ أصلاً:** موصّلُ المزوّد (`api.connectors.openmeteo`) يُعيد **كائناتٍ
# مُصنَّفة** (`CurrentWeather` · `list[DailyForecast]`) فيقرأ منها المستدعي بالنقطة،
# بينما `weather_service_client` يُعيد **قاموساً** هو مشاهدةٌ من
# `CanonicalWeatherState`: الآنُ مُسطَّحٌ في المستوى الأعلى، والتوقّعُ تحت المفتاح
# `days`. فالفرقُ ليس في المفاتيح — **هي متطابقة حرفيّاً** (`temperature_c` ·
# `humidity_pct` · `precipitation_mm` · `et0_mm` · `date`) — بل في **شكل الوصول**
# وفي أنّ المفتاحَ قد يغيب رأساً.
#
# **والناقصُ يصل `None` مُسمّى، لا صفراً:** مقيسٌ بالتنفيذ على المسار الحقيقيّ —
# رطوبةٌ غائبةٌ عن المزوّد ⇒ `humidity_pct: None` في المشاهدة، واسمُها في
# `missing_fields`، و`quality_status: degraded`. فالخدمةُ **تُصرِّح** بما غاب بدل
# أن تُصفّره؛ والخطرُ كلُّه في المستهلك: `sum(... or 0.0)` بلا فحصٍ يُعيد الكذبَ
# الذي أزالته الخدمة. ولذلك يُعيد `_reading` قيمةً أو `None` ويقرّر كلُّ مسارٍ
# صراحةً — لا يُخفي القسرَ داخل المُحوِّل.


def _forecast_days(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """أيّامُ التوقّع من غلاف `forecast_view` — لا من جذر الردّ.

    `forecast_view` مجموعةٌ فائقة: `days`/`range`/`model`/`timezone`/`location`
    مع غلافِ الجودة (`quality_status`/`day_count`/`days_missing_fields`). فالقائمةُ
    تحت `days`، وقراءتُها من الجذر تُعطي فراغاً صامتاً.
    """
    days = payload.get("days") if isinstance(payload, dict) else None
    if not isinstance(days, list):
        return []
    return [day for day in days if isinstance(day, dict)]


def _reading(source: dict[str, Any] | None, key: str) -> float | None:
    """قراءةٌ رقميّة أو `None` — **ولا افتراضَ صفريّ هنا**.

    الصفرُ قراءةٌ فيزيائيّة مشروعة (`0.0 mm` = لا مطر)، فلا يُميَّز من الغياب
    بعد القسر. يُعيدُها المُحوِّلُ صادقةً ويقرّر كلُّ مسارٍ ما يفعله بالمفقود.
    """
    if not isinstance(source, dict):
        return None
    value = source.get(key)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _complete_precipitation_total(
    sources: list[dict[str, Any]], *, expected_count: int
) -> tuple[float | None, list[int]]:
    """Return a rain total only when every expected interval is observed.

    The index list names missing intervals, including intervals absent from a
    short forecast.  An explicit ``0.0`` remains an observation; only ``None``
    or an absent interval makes the aggregate incomplete.
    """
    missing: list[int] = []
    values: list[float] = []
    for index in range(expected_count):
        value = _reading(sources[index], "precipitation_mm") if index < len(sources) else None
        if value is None:
            missing.append(index)
        else:
            values.append(value)
    if missing:
        return None, missing
    return sum(values), []


def _precipitation_incomplete(*, context: str, missing_intervals: list[int]) -> HTTPException:
    """Stable fail-closed API error for safety-relevant missing rain."""
    return HTTPException(
        status_code=503,
        detail={
            "code": "WEATHER_PRECIPITATION_INCOMPLETE",
            "message_ar": "بيانات المطر غير مكتملة؛ لا يمكن إصدار تقدير زراعي آمن.",
            "context": context,
            "missing_intervals": missing_intervals,
        },
    )


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


# سُلَّمُ الإزاحات الذي تعمل به خدمةُ الطقس — كثيفٌ قريباً ومتباعدٌ بعيداً.
_HORIZON_LADDER = (0, 1, 3, 6, 12, 24, 48, 72, 96, 120, 144, 168)


def _series_for_horizon(horizon_hours: int) -> str:
    """يبني سلسلةَ الإزاحات من الأفق المطلوب — **لا من عتبةٍ ثنائيّة**.

    كان الأفقُ يُقبَل ويُتحقَّق منه (`ge=1, le=168`) ثمّ يُستعمَل قيمةً منطقيّةً
    وحدها (`> 48`): **١٦٨ قيمةً مقبولة تُكرِم سلوكين**، فـ`49` و`168` يُنتِجان
    الطلبَ نفسَه حرفيّاً. مُعامِلٌ يَعِد بأفقٍ ويُسلّم إحدى دلوَين يكذب على
    مستهلكه بلا أن يُخطئ.

    والتعميمُ **يحفظ السلوكين القائمين عند نقطتيهما بالضبط**: `48` يُعطي
    `0,1,3,6,12,24,48` كما كان، و`168` يُعطي السلسلةَ الطويلةَ كما كانت. وما
    بينهما — وما دونهما — صار له سلسلتُه: آخرُ نقطةٍ هي الأفقُ المطلوب نفسُه، فمن
    طلب `49` ساعةً حصل على إطارٍ عندها لا عند `48`.
    """
    points = [h for h in _HORIZON_LADDER if h < horizon_hours]
    points.append(horizon_hours)
    return ",".join(str(h) for h in points)


def _window_from_operation(item: dict[str, Any]) -> dict[str, Any]:
    best = item.get("best") if isinstance(item.get("best"), dict) else {}
    decision = best.get("operation") if isinstance(best.get("operation"), dict) else {}
    score_raw = decision.get("score") if isinstance(decision, dict) else None
    try:
        score = float(score_raw) if score_raw is not None else None
    except Exception:  # noqa: BLE001 — upstream value malformed
        score = None
    limiting = decision.get("limiting_factors") if isinstance(decision, dict) else None
    # `best` يحمل مفتاحين: `time` **رمزيّ** (`"now"` / `"+72h"` من
    # `tiles.time_key_from_hour`) و`weather_time` **طابعٌ زمنيٌّ حقيقيّ** من
    # المزوّد. وكانت الأولويّةُ للرمزيّ — فحقلٌ اسمُه `start_at` يحمل `"+72h"`،
    # ويُصيَّر كما هو للمزارع في `FieldWorkspaceWeatherPanel.tsx` («`+72h` → —»).
    # وأحدُهم لاحظ التناقضَ فعالج **تسميةَ العَرَض** («وقتُ البدء — أفقٌ ساعيّ»)
    # بدل المصدر.
    #
    # فالأولويّةُ انعكست: `start_at` طابعٌ زمنيٌّ أو `None`، ولا يحمل رمزاً أبداً.
    # والإزاحةُ لم تُفقَد — لها حقلُها المُسمّى `start_offset_hours`. حقلٌ يَعِد
    # بوقتٍ ويُسلّم رمزاً يكذب على كلّ مَن يُحلّله.
    start_at = best.get("weather_time")
    return {
        "operation": item.get("operation"),
        "start_at": start_at if isinstance(start_at, str) else None,
        "start_offset_hours": best.get("hour_offset"),
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

    hours = _series_for_horizon(horizon_hours)
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
        forecast = await get_weather_forecast(lat, lon, days=3)
        current = await get_current_weather(lat, lon)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="تعذّر جلب الطقس من خدمة الطقس.") from exc

    days = _forecast_days(forecast)
    et0 = _reading(days[0], "et0_mm") if days else None
    if et0 is None:
        raise HTTPException(status_code=503, detail="بيانات ET₀ غير متوفّرة حالياً.")
    current_rain = _reading(current, "precipitation_mm")
    forecast_rain, missing_forecast = _complete_precipitation_total(days[1:3], expected_count=2)
    missing_rain = ([0] if current_rain is None else []) + [index + 1 for index in missing_forecast]
    if missing_rain:
        raise _precipitation_incomplete(
            context="irrigation_advice",
            missing_intervals=missing_rain,
        )
    assert current_rain is not None and forecast_rain is not None
    soil_pct = soil_reading.value_pct if soil_reading is not None else None
    advice = irrigation_advice(
        et0_mm=et0,
        crop=crop,
        stage=stage,
        rain_recent_mm=current_rain,
        forecast_rain_mm=forecast_rain,
        soil_moisture_pct=soil_pct,
    )
    advice.update(
        {
            "field_id": field_id,
            "crop": crop,
            "stage": stage,
            "source": "weather-service",
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
    from api.weather_advice import disease_risk

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, _stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق الحقل", exc) from exc

    try:
        current = await get_current_weather(lat, lon)
        forecast = await get_weather_forecast(lat, lon, days=3)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="تعذّر جلب الطقس من خدمة الطقس.") from exc

    # مُدخَلا الخطر إلزاميّان، والفحصُ هنا يُغلِق **عطلين سابقين** للموصّل معاً
    # (`openmeteo.py:279-280`: `c.get("temperature_2m", 0)`):
    #   • مفتاحٌ **غائب** ⇒ `0` صامت. و`0°م` مع `0٪` رطوبةً ليسا خطأً واضحاً بل
    #     قراءةً تخفض خطرَ الأمراض إلى `low` — **جوابٌ مطمئنٌّ من لا-بيانات**.
    #   • مفتاحٌ **حاضرٌ بقيمة null** ⇒ `None` ⇒ `float(None)` في `disease_risk`
    #     ⇒ `TypeError` غيرَ ملتقَط ⇒ ٥٠٠.
    # فالمُدخَلُ الواحدُ كان يُنتِج كذبةً أو انهياراً حسب شكلِ نقصِه. وخدمةُ الطقس
    # تُصرِّح بالناقص (`missing_fields`)، فيصير الجوابُ الصادقُ ٥٠٣ يُسمّيه.
    temp_c = _reading(current, "temperature_c")
    humidity_pct = _reading(current, "humidity_pct")
    if temp_c is None or humidity_pct is None:
        missing = [
            name
            for name, value in (("الحرارة", temp_c), ("الرطوبة", humidity_pct))
            if value is None
        ]
        raise HTTPException(
            status_code=503,
            detail=f"قياسات الطقس ناقصة ({' و'.join(missing)}) — لا يمكن تقدير مخاطر الأمراض.",
        )

    rain_3d, missing_rain = _complete_precipitation_total(
        _forecast_days(forecast)[:3], expected_count=3
    )
    if missing_rain:
        raise _precipitation_incomplete(
            context="disease_risk",
            missing_intervals=missing_rain,
        )
    assert rain_3d is not None
    risk = disease_risk(
        temp_c=temp_c,
        humidity_pct=humidity_pct,
        rain_mm_3d=rain_3d,
        crop=crop,
    )
    risk.update(
        {
            "field_id": field_id,
            "crop": crop,
            "temperature_c": round(temp_c, 1),
            "humidity_pct": round(humidity_pct, 1),
            "rain_mm_3d": round(rain_3d, 1),
            "source": "weather-service",
        }
    )
    return risk
