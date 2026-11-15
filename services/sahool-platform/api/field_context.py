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


def _season_stage(crop: str | None, age: int) -> str | None:
    """مرحلة الموسم: من بطاقة المحصول، أو تقدير الأيّام العامّ لمحصول **معروف** فقط.

    محصول غير مُعرَّف ⇒ None: حدود الأيّام العامّة لا تخصّه، والمرحلة المُختلَقة تقود
    Kc/التسميد المرحليّ. البطاقة المعروفة بلا مرحلة جارية ⇒ تقدير عامّ (السلوك السابق).
    """
    from core.season_phenology import current_stage, resolve_crop_id

    crop_id = resolve_crop_id(crop)
    phase = current_stage(crop_id, age) if age >= 0 else None
    if phase:
        return phase["stage"]
    return _growth_stage(age) if crop_id else None


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


_RAINFED_ALIASES = frozenset(
    {"rainfed", "rain-fed", "rain_fed", "rain fed", "dryland", "مطري", "بعلي"}
)


def normalize_irrigation_type(raw) -> str | None:
    """seasons/fields.irrigation_type normalised (case, whitespace, rainfed aliases); blank ⇒ None.

    None means unknown. The recommendation then keeps the irrigated path and reports
    ``irrigation_type = None`` so the caller can see the method was not established.
    """
    value = str(raw).strip().lower() if raw is not None else ""
    if value in _RAINFED_ALIASES:
        return "rainfed"
    return value or None


async def field_irrigation_type(conn, field_id: str, season) -> str | None:
    """The active season's irrigation method, else the field's registered one; None = unknown.

    Unknown is reported as None. It is not inferred to be rainfed, so the irrigated path
    still applies and the response says the method is unknown.
    """
    method = normalize_irrigation_type(season.get("irrigation_type") if season else None)
    if method is None:
        row = await conn.fetchrow(
            "SELECT irrigation_type FROM fields WHERE field_id = $1", field_id
        )
        method = normalize_irrigation_type(row.get("irrigation_type") if row else None)
    return method


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
            stage = _season_stage(crop, (date.today() - sowing_date).days)
    lat = float(row["lat"]) if row["lat"] is not None else None
    lon = float(row["lon"]) if row["lon"] is not None else None
    return lat, lon, crop, stage, sowing_date


def alert_rain_context(forecast) -> tuple[float | None, float | None, float | None]:
    """مطرُ التنبيهات: (الأخيرُ المرصود، نافذةُ التوقّع، مجموعُ ٣ أيّام) — و`None` **مجهولٌ** لا «لا مطر».

    استُخرِجت من `main.py` لا تجميلاً: الملفُّ تحت راتشِت تفكيكٍ يهبط ولا يصعد،
    والمنطقُ الذي لا يخصّ التوجيه موضعُه هنا مع `_historical_rain_3d_mm`. فالحدُّ
    يُخدَم بإخراج المنطق لا بضغط تعليقاته.

    والحكمُ نفسُه ليس هنا — يُفوَّض إلى `weather_advice.complete_rain_total`،
    السياسةُ الواحدة التي يسألها كلُّ سطح. و«الأخير» (G8) نفسُ ``irrigation_rain_window`` التي
    تسألها مساراتُ الريّ: مجموعُ اليوم توقّعٌ لا رصد فلا يُخصَم (مراجعة #1329).
    """
    from api.weather_advice import complete_rain_total, irrigation_rain_window

    recent, total_48h, _ = irrigation_rain_window([f.precipitation_mm for f in forecast[:3]])
    total_3d, _ = complete_rain_total([f.precipitation_mm for f in forecast[:3]], expected_count=3)
    return recent, total_48h, total_3d


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


# ─── بوّابة PHI على تسجيل الحصاد (create_activity[harvest] + create_harvest_lot) ───
# آخر رشّات الحقل المنفَّذة حتى تاريخ الحصاد (RLS عبر conn المستأجِر). سقف 200 صفّاً:
# أحدث الرشّات هي ما يحكم فترة الأمان، والأقدم انقضت فترته عمليّاً.
_DONE_SPRAYS_SQL = """
    SELECT activity_id, performed_on, details
    FROM activities
    WHERE field_id = $1 AND activity_type = 'spraying' AND status = 'done'
      AND performed_on IS NOT NULL AND performed_on <= $2
    ORDER BY performed_on DESC, created_at DESC
    LIMIT 200
"""


def _details_dict(raw) -> dict:
    if isinstance(raw, str):
        import json as _json

        try:
            raw = _json.loads(raw)
        except (TypeError, ValueError):
            return {}
    return raw if isinstance(raw, dict) else {}


def phi_override_record(user, check, override, reason) -> dict:
    """حصاد داخل فترة الأمان: 409 ما لم يُطلَب تجاوز صريح بسبب ومن صاحب صلاحيّة
    ``HARVEST_AUTHORIZE`` (المالك حصراً). يُرجع سجلّ التجاوز ليُحفَظ مع الحصاد."""
    from core.authorization import Permission, has_permission

    blocking = check.blocking_spray
    if override is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "message_ar": check.message_ar,
                "code": "phi_not_elapsed",
                "product": blocking.product if blocking else None,
                "spray_date": blocking.performed_on.isoformat() if blocking else None,
                "phi_days": blocking.phi_days if blocking else None,
                "days_since_spray": check.days_since_spray,
                "earliest_safe_date": (
                    check.earliest_safe_date.isoformat() if check.earliest_safe_date else None
                ),
            },
        )
    reason_text = reason.strip() if isinstance(reason, str) else ""
    if len(reason_text) < 3:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "تجاوز بوّابة PHI يتطلّب سبباً صريحاً (phi_override_reason)",
                "code": "phi_override_reason_required",
            },
        )
    if not has_permission(user, Permission.HARVEST_AUTHORIZE):
        raise HTTPException(
            status_code=403,
            detail={
                "message_ar": "تجاوز بوّابة PHI صلاحيّة المالك حصراً (harvest:authorize)",
                "code": "phi_override_forbidden",
            },
        )
    return {
        "reason": reason_text[:500],
        "by": str(getattr(user, "user_id", "") or ""),
        "at": datetime.now(UTC).isoformat(),
    }


async def harvest_phi_check(conn, user, field_id, harvest_date, override=False, reason=None):
    """يقيّم PHI لحصاد الحقل في ``harvest_date`` (None ⇒ لا تاريخ ⇒ لا فحص ⇒ None).

    يرفع 409/422/403 (انظر ``phi_override_record``)؛ وإلّا يُرجع نتيجة الفحص كقاموس
    (``limitations`` تحمل ``phi_unknown`` حين لا PHI لآخر رشّة، و``override`` حين تُجووِز).
    خطأ القاعدة يتسرّب إلى معالِج المسار ⇒ 503 (لا حصاد بلا فحص — فشل مغلق)."""
    from core.engines.pesticide import (
        SprayRecord,
        evaluate_harvest_phi,
        phi_days_from_details,
        spray_product_from_details,
    )

    if harvest_date is None:
        return None
    rows = await conn.fetch(_DONE_SPRAYS_SQL, field_id, harvest_date)
    sprays = []
    for r in rows:
        d = _details_dict(r["details"])
        sprays.append(
            SprayRecord(
                performed_on=r["performed_on"],
                phi_days=phi_days_from_details(d),
                product=spray_product_from_details(d),
                activity_id=r["activity_id"],
            )
        )
    check = evaluate_harvest_phi(harvest_date, sprays)
    out = check.to_dict()
    if not check.allowed:
        out["override"] = phi_override_record(user, check, override, reason)
    return out


async def activity_details_with_phi_gate(conn, user, field_id, req) -> dict:
    """تفاصيل نشاط ``create_activity`` بعد بوّابة PHI: غير الحصاد يمرّ كما هو؛ الحصاد
    (تاريخ التنفيذ أو المُجدوَل) يُفحَص، والتجاوز يُطلَب في التفاصيل نفسها
    (``phi_override: true`` + ``phi_override_reason``) ويُسجَّل فيها تحت ``phi_check``."""
    details = dict(req.details or {})
    if req.activity_type != "harvest":
        return details
    raw_date = req.performed_on or req.scheduled_for
    harvest_date = date.fromisoformat(raw_date.strip()) if raw_date else None
    override, reason = details.get("phi_override"), details.get("phi_override_reason")
    phi = await harvest_phi_check(conn, user, field_id, harvest_date, override, reason)
    if phi is None:
        return details
    details["phi_check"] = phi  # يكتب فوق أيّ phi_check من العميل: الخادم مصدره الوحيد
    if phi["limitations"]:
        prior = details.get("limitations")
        prior = [x for x in prior if isinstance(x, str)] if isinstance(prior, list) else []
        details["limitations"] = sorted(set(prior) | set(phi["limitations"]))
    return details


async def harvest_lot_phi_check(conn, user, req, harvest_date):
    """بوّابة PHI لـ``create_harvest_lot`` (التجاوز من حقلَي الطلب phi_override/_reason)."""
    return await harvest_phi_check(
        conn, user, req.field_id, harvest_date, req.phi_override, req.phi_override_reason
    )
