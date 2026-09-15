"""api/field_context.py — اشتقاق السياق الزراعيّ للحقل (Field agronomic context) — تفكيك B1.

عنقود مساعِدات مشترَك مُستخرَج من الوحدة الضخمة ``api/main.py``: اشتقاق سياق الحقل
الذي تحتاجه عدّة موجِّهات (ريّ/أمراض/توصيات موحَّدة/اكتمال البيانات) قبل تشغيل المنطق
النقيّ:

  • ``_growth_stage`` — مرحلة النموّ التقديريّة من العمر (FAO-56) — دالّة نقيّة.
  • ``_field_weather_context`` — (lat, lon, crop, stage, days_since_sowing) للحقل + موسمه.
  • ``_field_season_context`` — يوسّعها بإرجاع sowing_date (لنافذة الحصاد).
  • ``_latest_soil_moisture`` — أحدث قراءة رطوبة تربة صالحة (أو None).
  • ``_historical_rain_3d_mm`` — مطر تراكميّ تاريخيّ ٣ أيّام (لمخاطر الأمراض).
  • ``_resolve_recommendation_policy`` / ``_load_recommendation_policy`` — سياسة محرّكات
    التوصيات لكلّ مستأجِر (best-effort؛ غياب ⇒ None ⇒ السلوك الافتراضيّ).

**بلا تبعيّة على ``api.main``:** كلّ الدوالّ المعتمدة على القاعدة تستقبل ``conn`` كمعامل
(لا تدير اتّصالاً)، وكلّ الاستيرادات الثقيلة (``api.soil_telemetry`` ·
``api.recommendations_hub`` · ``core.season_phenology`` · ``api.connectors.openmeteo``)
كسولة داخل الدوالّ — فلا دورة استيراد. تُعاد هذه الأسماء إلى فضاء ``api.main`` (إعادة
تصدير) كي تبقى نقاط الاستدعاء القائمة (``from api.main import …`` في الموجِّهات) صحيحة
دون تغيير سلوكيّ.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from fastapi import HTTPException

# مراحل النموّ التقريبيّة بالأيّام منذ البذار (FAO-56 — initial/dev/mid/late).
# ⚠ تقدير عامّ يحتاج معايرة لكلّ محصول؛ يُستخدم فقط لاختيار Kc حين توفّر sowing_date.
_STAGE_DAY_BOUNDS = ((30, "initial"), (60, "development"), (120, "mid"))


def _growth_stage(days_since_sowing: int | None) -> str | None:
    """يُرجع مرحلة النموّ من عدد الأيّام منذ البذار. None/غير معروف ⇒ None."""
    if days_since_sowing is None or days_since_sowing < 0:
        return None
    for bound, stage in _STAGE_DAY_BOUNDS:
        if days_since_sowing <= bound:
            return stage
    return "late"


async def _field_weather_context(
    conn, field_id: str
) -> tuple[float, float, str | None, str | None, int | None]:
    """Weather and recommendations use the same active season and crop card."""
    lat, lon, crop, stage, sowing_date = await _field_season_context(conn, field_id)
    if lat is None or lon is None:
        raise HTTPException(
            status_code=422,
            detail="الحقل بلا إحداثيّات (lat/lon) — لا يمكن جلب الطقس. حدّد موقع الحقل أوّلاً.",
        )
    age = (date.today() - sowing_date).days if sowing_date is not None else None
    return lat, lon, crop, stage, age


async def _latest_soil_moisture(conn, field_id: str):
    """أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل، أو None إن لا قراءة صالحة.

    يجلب قراءات soil_moisture من مخزن soil_observations القانوني ضمن سياق
    المستأجِر (RLS)، ثمّ يلتقط أحدثها الصالحة عبر
    المنطق النقيّ pick_latest_soil_moisture (يتجاهل القيم خارج النطاق المعقول).
    يُعيد كائن SoilMoistureReading أو None — لا يرفع استثناء عند غياب البيانات
    (القرار يتدبّر None برشاقة: يعتمد احتياج الريّ بدلاً منها).
    """
    from api.soil_telemetry import pick_latest_soil_moisture

    rows = await conn.fetch(
        """SELECT value_json AS value, unit, observed_at AS recorded_at,
                  source_id AS device_id,
                  observation_id, quality_status, calibration_id, confidence,
                  depth_from_cm, depth_to_cm
             FROM soil_observations
            WHERE field_id = $1
              AND property = 'soil_moisture'
              AND source_type = 'sensor'
              AND quality_status <> 'rejected'
            ORDER BY observed_at DESC
            LIMIT 50""",
        field_id,
    )
    return pick_latest_soil_moisture([dict(r) for r in rows])


async def _field_season_context(conn, field_id: str):
    """يجلب (lat, lon, crop, stage, sowing_date) للحقل + موسمه النشط (404 إن غاب).

    يوسّع _field_weather_context بإرجاع sowing_date (لنافذة الحصاد). يرفع 404 إن
    غاب الحقل. lat/lon قد يكونان None هنا (الطقس اختياريّ في التوصيات الموحَّدة).
    """
    row = await conn.fetchrow("SELECT lat, lon, crop FROM fields WHERE field_id = $1", field_id)
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    season = await conn.fetchrow(
        "SELECT crops, sowing_date FROM seasons "
        "WHERE field_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    crop: str | None = row["crop"]
    stage = None
    sowing_date = None
    if season is not None:
        import json as _json

        crops = season["crops"]
        if isinstance(crops, str):
            try:
                crops = _json.loads(crops)
            except (ValueError, TypeError):
                crops = []
        if isinstance(crops, list) and crops:
            crop = str(crops[0])
        sowing_date = season["sowing_date"]
        if sowing_date is not None:
            from core.season_phenology import current_stage, resolve_crop_id

            age = (date.today() - sowing_date).days
            phase = current_stage(resolve_crop_id(crop), age) if age >= 0 else None
            stage = phase["stage"] if phase else _growth_stage(age)
    lat = float(row["lat"]) if row["lat"] is not None else None
    lon = float(row["lon"]) if row["lon"] is not None else None
    return lat, lon, crop, stage, sowing_date


def alert_rain_context(current, forecast) -> tuple[float | None, float | None, float | None]:
    """مطرُ التنبيهات: (الآنيّ، مجموعُ ٤٨ ساعة، مجموعُ ٣ أيّام) — و`None` **مجهولٌ** لا «لا مطر».

    استُخرِجت من `main.py` لا تجميلاً: الملفُّ تحت راتشِت تفكيكٍ يهبط ولا يصعد،
    والمنطقُ الذي لا يخصّ التوجيه موضعُه هنا مع `_historical_rain_3d_mm`. فالحدُّ
    يُخدَم بإخراج المنطق لا بضغط تعليقاته.

    والحكمُ نفسُه ليس هنا — يُفوَّض إلى `weather_advice.complete_rain_total`،
    السياسةُ الواحدة التي يسألها كلُّ سطح.
    """
    from api.weather_advice import complete_rain_total

    total_48h, _ = complete_rain_total(
        [f.precipitation_mm for f in forecast[1:3]], expected_count=2
    )
    total_3d, _ = complete_rain_total([f.precipitation_mm for f in forecast[:3]], expected_count=3)
    return current.precipitation_mm, total_48h, total_3d


#: نافذةُ المطر التاريخيّ بالأيّام — يقرؤها الاستعلامُ وشرطُ الاكتمال معاً،
#: فلا ينحرف أحدُهما عن الآخر.
_HISTORICAL_RAIN_DAYS = 3


async def _historical_rain_3d_mm(
    lat: float, lon: float, forecast_fallback: float | None
) -> float | None:
    """مطر تراكمي آخر ٣ أيام (تاريخيّ ERA5) — لمخاطر الأمراض تُعدّ رطوبة الأيام
    السابقة لا المطر المستقبليّ. fallback لمجموع التوقّع إن تعذّر التاريخيّ.

    **ويُعيد `None` حين لا يكتمل المرصود** بدل مجموعٍ جزئيٍّ يُقدَّم كاملاً:
    `sum(... or 0.0)` كان يُنقِص المطرَ المُبلَّغ فيُنقِص خطرَ المرض المحسوب — أي
    ينحاز إلى **عدم** التحذير. والصفرُ الصريح يبقى رصداً.
    """
    from datetime import timedelta as _td

    from api.connectors.openmeteo import fetch_historical

    try:
        today = datetime.now(UTC).date()
        hist = await fetch_historical(
            lat,
            lon,
            (today - _td(days=_HISTORICAL_RAIN_DAYS)).isoformat(),
            (today - _td(days=1)).isoformat(),
        )
        from api.weather_advice import complete_rain_total

        # **`expected_count` ثابتٌ لا مُشتقٌّ من الرَّدّ.** كتبتُ أوّلاً
        # `expected_count=len(hist)`، وأمسكها مراجعٌ آليّ: الأيّامُ الناقصةُ من
        # أرشيف ERA5 (يتأخّر ~٥ أيّام) **تُحذَف من القائمة** ولا تصل `None` — فيصير
        # المتوقَّعُ مساوياً للمرصود دائماً، ويمرّ مجموعٌ جزئيٌّ بوصفه ثلاثةَ أيّام.
        # وذلك يُبطِل الخاصّيّةَ التي بُنيت السياسةُ لأجلها، ويُناقض اختبارَها
        # `complete_rain_total([1.0], expected_count=3) == (None, [1, 2])`.
        # والاستعلامُ يطلب ثلاثةَ أيّامٍ بعينها (`today-3` .. `today-1`)، فالعددُ ٣.
        total, _missing = complete_rain_total(
            [d.precipitation_mm for d in hist], expected_count=_HISTORICAL_RAIN_DAYS
        )
        if not hist or total is None:
            return None if forecast_fallback is None else round(forecast_fallback, 1)
        return round(total, 1)
    except Exception:  # noqa: BLE001 — تعذّر التاريخيّ ⇒ fallback للتوقّع
        logging.exception("historical 3-day rain fetch failed; using forecast fallback")
        return None if forecast_fallback is None else round(forecast_fallback, 1)


async def _resolve_recommendation_policy(raw_value) -> set[str] | None:
    """يحوّل قيمة السياسة الخام (JSONB) إلى مجموعة مُعرّفات مُفعَّلة، أو None.

    دالّة نقيّة (لا قاعدة): تُفصَل عن القراءة كي يُعاد استخدامها في نقطة الاستبطان.
    تدعم شكلين متبادلين حصريّاً:
      • {"disabled": [...]} ⇒ المُفعَّل = كلّ المحرّكات المعروفة ناقص المُعطَّلة.
      • {"enabled":  [...]} ⇒ المُفعَّل = هذه المُعرّفات فقط (مقاطَعة مع المعروفة).
    أيّ شكل آخر (الاثنان معاً/لا شيء/فارغ/مُشوَّه) ⇒ None ⇒ «كلّ الافتراضيّ» (دون تغيير).
    """
    from api.recommendations_hub import list_engines

    if not isinstance(raw_value, dict):
        return None
    known = {e["id"] for e in list_engines()}
    has_disabled = "disabled" in raw_value
    has_enabled = "enabled" in raw_value
    # الشكلان حصريّان: وجود الاثنين أو غيابهما معاً ⇒ سياسة غير محدَّدة ⇒ None.
    if has_disabled == has_enabled:
        return None
    if has_disabled:
        disabled = raw_value.get("disabled")
        if not isinstance(disabled, list) or not disabled:
            return None
        return known - {str(x) for x in disabled}
    enabled = raw_value.get("enabled")
    if not isinstance(enabled, list) or not enabled:
        return None
    return known & {str(x) for x in enabled}


async def _load_recommendation_policy(conn) -> set[str] | None:
    """يقرأ سياسة محرّكات التوصيات للمستأجِر من جدول settings (best-effort).

    يستعلم الاتّصال المنطاقيّ (RLS يحصره بالمستأجِر): scope='platform',
    key='recommendation_engines'. القيمة JSONB قد تعود dict أو نصّاً (نُحلّله).
    أيّ خطأ (لا قاعدة، لا جدول، JSON مُشوَّه) ⇒ None — لا نرفع أبداً في مسار الطلب،
    فيبقى السلوك مطابقاً لليوم عند غياب السياسة.
    """
    import json as _json

    try:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE scope = 'platform' AND key = 'recommendation_engines'"
        )
        if row is None:
            return None
        value = row["value"]
        if isinstance(value, str):
            value = _json.loads(value)
        return await _resolve_recommendation_policy(value)
    except Exception:  # noqa: BLE001 — best-effort: أيّ خطأ ⇒ None (سلوك افتراضيّ)
        logging.exception("recommendation policy load failed; defaulting to all engines")
        return None


async def read_ai_context_active_season(conn, field_id, tenant_id):
    async with conn.transaction():  # savepoint: an optional read must not abort the pack
        row = await conn.fetchrow(
            """
            SELECT to_jsonb(s.*) AS payload
            FROM seasons s
            WHERE s.field_id = $1 AND s.tenant_id = $2::uuid
              AND COALESCE(s.status, 'active') IN ('active', 'current', 'in_progress')
            ORDER BY s.created_at DESC NULLS LAST, s.season_id
            LIMIT 1
            """,
            field_id,
            tenant_id,
        )
    return row


async def read_ai_context_events(conn, field_id, tenant_id, limit):
    async with conn.transaction():  # savepoint: an optional read must not abort the pack
        rows = await conn.fetch(
            """
            SELECT event_id, event_type, payload, actor_id, occurred_at
            FROM events
            WHERE tenant_id = $2::uuid
              AND (entity_id = $1 OR payload->>'field_id' = $1)
            ORDER BY occurred_at DESC
            LIMIT $3
            """,
            field_id,
            tenant_id,
            limit,
        )
    return rows


async def read_ai_context_drawings(conn, field_id, tenant_id):
    async with conn.transaction():  # savepoint: an optional read must not abort the pack
        rows = await conn.fetch(
            """
            SELECT feature_id, kind, workflow, properties, measurements, validation, version, updated_at
            FROM drawing_features
            WHERE tenant_id = $1::uuid AND field_id = $2 AND deleted_at IS NULL
            ORDER BY updated_at DESC
            LIMIT 200
            """,
            tenant_id,
            field_id,
        )
    return rows


async def read_ai_context_alerts(conn, field_id, tenant_id):
    async with conn.transaction():  # savepoint: an optional read must not abort the pack
        rows = await conn.fetch(
            """
            SELECT to_jsonb(a.*) AS payload
            FROM alerts a
            WHERE a.tenant_id = $1::uuid AND a.field_id = $2
            ORDER BY COALESCE(a.created_at, a.updated_at) DESC NULLS LAST
            LIMIT 50
            """,
            tenant_id,
            field_id,
        )
    return rows


async def read_ai_context_recommendations(conn, field_id, tenant_id):
    async with conn.transaction():  # savepoint: an optional read must not abort the pack
        rows = await conn.fetch(
            """
            SELECT to_jsonb(r.*) AS payload
            FROM recommendations r
            WHERE r.tenant_id = $1::uuid AND r.field_id = $2
            ORDER BY COALESCE(r.issued_at, r.created_at) DESC NULLS LAST
            LIMIT 50
            """,
            tenant_id,
            field_id,
        )
    return rows
