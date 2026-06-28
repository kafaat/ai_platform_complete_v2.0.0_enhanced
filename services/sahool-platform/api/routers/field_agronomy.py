"""api/routers/field_agronomy.py — مسارات الإرشاد الزراعيّ (Agronomy Advisory) للحقل.

شريحة مُستخرَجة من ``api/routers/fields.py`` (تفكيك تدريجيّ محفوظ-السلوك للملفّ الأكبر):
نُقلت المعالِجات الأربع للإرشاد الزراعيّ حرفيّاً — بنفس المسارات/الطلبات/المخرجات/الأذونات/
مخطّط OpenAPI — دون أيّ تغيير في السلوك:

  • ``GET /api/v1/fields/{field_id}/soil-moisture``               → ``field_soil_moisture``
  • ``GET /api/v1/fields/{field_id}/weather/irrigation-advice``   → ``field_irrigation_advice``
  • ``GET /api/v1/fields/{field_id}/weather/disease-risk``        → ``field_disease_risk``
  • ``GET /api/v1/fields/{field_id}/recommendations``             → ``field_recommendations``

التسجيل تلقائيّ عبر ``api.router_registry.register_routers`` (حلقة ``pkgutil`` على
``api/routers/`` — أيّ وحدة تُصدّر ``router`` تُضمّ). بما أنّ المسارات نُقلت (لا نُسخت)
من ``fields.py`` فلا تكرار (مسار، طريقة).

الاعتماديّات: الرموز المشتركة تُستورَد من مصادرها الأصليّة نفسها كما في ``fields.py``
(``api.main`` للتبعيات/المساعِدات؛ والمحرّكات النقيّة تُستورَد محليّاً داخل الدوال كما
كانت). لتفادي الاستيراد الدائريّ: ``api.main`` يُستورَد هنا، وحلقة التسجيل تُنفَّذ في
نهاية ``main.py`` بعد اكتمال تعريف كلّ تلك الرموز.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    _field_season_context,
    _field_weather_context,
    _historical_rain_3d_mm,
    _latest_soil_moisture,
    _load_recommendation_policy,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/fields/{field_id}/soil-moisture")
async def field_soil_moisture(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل من telemetry الحيّ، أو null.

    يقرأ من device_telemetry (الأجهزة المرتبطة بالحقل عبر iot_devices.field_id)
    ضمن سياق المستأجِر (RLS) بعد تأكيد أنّ الحقل يخصّه (404). يردّ القراءة + زمنها
    + الجهاز المصدر، أو reading=null إن لا قراءة صالحة (لا بيانات وهميّة). 503 إن
    تعذّرت القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة رطوبة التربة", e) from e
    return {
        "field_id": field_id,
        "reading": reading.as_dict() if reading is not None else None,
    }


@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")
async def field_irrigation_advice(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """توصية ريّ بنمط FAO-56 للحقل من الطقس الحيّ ومحصول الموسم النشط.

    يحسب ET₀ × Kc − المطر الفعّال (api.weather_advice، نقيّ ومُختبَر). يجلب ET₀
    والمطر من Open-Meteo (نفس مصدر /api/v1/weather). 404 إن غاب الحقل، 503 إن
    تعذّر الطقس (لا بيانات وهميّة).
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import irrigation_advice

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, _days = await _field_weather_context(conn, field_id)
            # رطوبة تربة حيّة من telemetry الأجهزة (إن وُجدت) — تُغذّي إلحاح التوصية.
            soil_reading = await _latest_soil_moisture(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        forecast = await fetch_daily_forecast(lat, lon, days=3)
        current = await fetch_current(lat, lon)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    today = forecast[0] if forecast else None
    et0 = today.et0_mm if today and today.et0_mm is not None else None
    if et0 is None:
        raise HTTPException(
            status_code=503,
            detail="بيانات ET₀ غير متوفّرة من مصدر الطقس حاليّاً. حاول لاحقاً.",
        )
    # المطر المتوقّع خلال ٤٨ ساعة القادمة (يومان قادمان من التوقّع).
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
            "soil_moisture_at": (
                soil_reading.recorded_at.isoformat() if soil_reading is not None else None
            ),
        }
    )
    return advice


@router.get("/api/v1/fields/{field_id}/weather/disease-risk")
async def field_disease_risk(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """مخاطر أمراض فطريّة (agro-met) للحقل من الرطوبة/الحرارة/المطر.

    منطق التهديف نقيّ (api.weather_advice، مُختبَر offline). يجلب الطقس الحالي +
    مطر آخر ٣ أيّام من Open-Meteo. 404 إن غاب الحقل، 503 إن تعذّر الطقس.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.weather_advice import disease_risk

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, _stage, _days = await _field_weather_context(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل", e) from e

    try:
        current = await fetch_current(lat, lon)
        forecast = await fetch_daily_forecast(lat, lon, days=3)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس (مصدر Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

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


@router.get("/api/v1/fields/{field_id}/recommendations")
async def field_recommendations(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """عمود التوصيات الموحَّد للحقل: ريّ + تسميد + أمراض + حصاد، مفروز بالأولويّة.

    التجميع نقيّ (api.recommendations_hub، مُختبَر offline). يجمع سياق الموسم من
    القاعدة (404 إن غاب الحقل، 503 إن تعذّرت القاعدة) والطقس من Open-Meteo. تدهور
    رشيق: عند تعذّر الطقس (أو غياب إحداثيّات الحقل) نُرجع توصيات التسميد/الحصاد
    فقط — لا بيانات وهميّة. 503 فقط إن لم تتوفّر أيّة توصية.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.field_state_projection import recompute_field_state
    from api.recommendations_hub import RecommendationContext, build_recommendations

    try:
        async with tenant_connection(user) as conn:
            lat, lon, crop, stage, sowing_date = await _field_season_context(conn, field_id)
            # Canonical Field State: التوصيات تمرّ عبر الحالة القانونيّة الموحّدة —
            # نُحدِّث الإسقاط ونرفق صلاحيّة القرار + نمط التنفيذ بالاستجابة (مصدر حقيقة
            # واحد يحكم: تلقائيّ أم مراجعة بشريّة)، بدل قرار متفرّق لكلّ توصية.
            field_state = (await recompute_field_state(conn, field_id))["state"]
            # سياسة محرّكات التوصيات لكلّ مستأجِر — قراءة صغيرة عبر نفس الاتّصال
            # المنطاقيّ (RLS). None ⇒ لا سياسة ⇒ السلوك مطابق لليوم تماماً.
            enabled_ids = await _load_recommendation_policy(conn)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياق الحقل للتوصيات", e) from e

    ctx = RecommendationContext(
        field_id=field_id,
        crop=crop,
        stage=stage,
        today=date.today(),
        sowing_date=sowing_date,
    )
    # Stage F (تغذية آمنة): مرّر مرجعيّة النواة الزراعيّة الموحّدة للمُجمِّع — تصعيد/
    # تنبيه فقط (تنبيه ملوحة حرجة) لا استبدال أرقام. صدق: غياب الحقائق ⇒ لا تصعيد.
    _agro_truths = (field_state.get("agronomic") or {}).get("operational_truths") or {}
    ctx.salinity_class = _agro_truths.get("salinity_class")
    ctx.crop_vigor = _agro_truths.get("crop_vigor")

    # الطقس اختياريّ: نملأ سياقه إن توفّرت الإحداثيّات والمصدر. تعذّره لا يُسقط
    # الطلب — نكتفي بالتوصيات التي لا تحتاجه (تدهور رشيق، لا تلفيق).
    weather_available = False
    if lat is not None and lon is not None:
        try:
            forecast = await fetch_daily_forecast(lat, lon, days=3)
            current = await fetch_current(lat, lon)
            today = forecast[0] if forecast else None
            et0 = today.et0_mm if today and today.et0_mm is not None else None
            ctx.et0_mm = et0
            ctx.rain_recent_mm = current.precipitation_mm or 0.0
            ctx.forecast_rain_mm = sum(f.precipitation_mm or 0.0 for f in forecast[1:3])
            ctx.temp_c = current.temperature_c
            ctx.humidity_pct = current.humidity_pct
            ctx.rain_mm_3d = await _historical_rain_3d_mm(
                lat, lon, sum(f.precipitation_mm or 0.0 for f in forecast[:3])
            )
            weather_available = True
        except Exception:  # noqa: BLE001 — تعذّر الطقس ⇒ تدهور رشيق لا فشل
            logging.exception("recommendations: weather unavailable for %s", field_id)

    # enabled_ids=None ⇒ تُفعَّل كلّ المحرّكات بحسب default_enabled (سلوك مطابق لليوم).
    recs = build_recommendations(ctx, enabled_ids=enabled_ids)
    if not recs:
        # لا توصية أمكن توليدها (لا طقس، لا محصول، لا بذار) — فشل صادق.
        raise HTTPException(
            status_code=503,
            detail="تعذّر توليد توصيات (لا طقس ولا سياق موسم كافٍ). حدّد موقع الحقل وموسمه.",
        )

    return {
        "field_id": field_id,
        "crop": crop,
        "stage": stage,
        "weather_available": weather_available,
        # الحالة القانونيّة الموحّدة تحكم تطبيق التوصيات (مصدر حقيقة واحد): نمط
        # التنفيذ != auto ⇒ requires_review (تحتاج تأكيد المهندس/المزارع قبل التنفيذ).
        "field_state": {
            "validity": field_state["validity"],
            "execution_mode": field_state["execution_mode"],
            "confidence_level": field_state.get("confidence_level"),
            "reasons_ar": field_state.get("reasons_ar", []),
        },
        "requires_review": field_state["execution_mode"] != "auto",
        "recommendations": [r.to_dict() for r in recs],
    }
