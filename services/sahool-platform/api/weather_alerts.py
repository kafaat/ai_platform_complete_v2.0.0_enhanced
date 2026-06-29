"""api/weather_alerts.py — اشتقاق تنبيهات الطقس الزراعيّة (Pure Logic).
====================================================================
دوالّ نقيّة بلا FastAPI ولا قاعدة بيانات: تأخذ عيّنة Open-Meteo (``sample``)
وخطّة العمليّات الاختياريّة (``plan``) وتشتقّ قائمة تنبيهات زراعيّة قابلة للعرض.

كلّ تنبيه قاموس بالشكل::

    {
        "type": "strong_wind",            # رمز ثابت للتصنيف
        "severity": "warning",            # info | warning | critical
        "title_ar": "رياح قويّة",
        "detail_ar": "...",               # شرح موجز بالعربيّة
        "window": "now",                  # اختياريّ: وسم النافذة/الوقت
    }

تُبقي هذه الوحدة المنطق خارج ``routers/weather.py`` الكثيف التعديل، وتعتمد على
نفس مفاتيح العيّنة المستخدَمة في محرّك الطقس (``temperature_2m_c`` …).

اسم حدث الإشعار المقترَح (للتكامل المستقبليّ مع NATS/AlertManager):
``WEATHER_ALERT_DERIVED`` — انظر TODO في ``routers/weather.py``.
"""

from __future__ import annotations

# عتبات الاشتقاق (محافِظة، متوافقة مع منطق طبقة ذكاء الطقس في SAHOOL).
STRONG_WIND_SPEED_KMH = 25.0  # سرعة رياح مستدامة تُعدّ قويّة
STRONG_WIND_GUST_KMH = 35.0  # هبّة رياح تُعدّ قويّة
SPRAY_WIND_MAX_KMH = 18.0  # حدّ الرياح لنافذة رشّ آمنة
SPRAY_GUST_MAX_KMH = 29.0  # حدّ هبّات الرياح لنافذة رشّ آمنة
RAIN_TRIGGER_MM = 0.1  # هطول يستوجب تأجيل الرشّ
HEAT_WAVE_C = 40.0  # موجة حرّ
HEAT_WARNING_C = 36.0  # حرارة مرتفعة (تحذير)
FROST_C = 0.0  # صقيع
FROST_WARNING_C = 2.0  # قرب الصقيع (تحذير)
SPRAY_HUMIDITY_MAX_PCT = 85.0  # رطوبة مرتفعة تُضعف فرصة الرشّ
DISEASE_HUMIDITY_PCT = 90.0  # رطوبة مرتفعة + اعتدال حراريّ → خطر مرضيّ محتمل
DISEASE_TEMP_LOW_C = 12.0
DISEASE_TEMP_HIGH_C = 30.0


def _num(sample: dict, key: str, default: float | None = None) -> float | None:
    """يستخرج قيمة عدديّة من العيّنة أو يعيد الافتراضيّ بأمان."""
    value = (sample or {}).get(key)
    return value if isinstance(value, (int, float)) else default


def _window_label(sample: dict) -> str:
    """وسم وقت/نافذة العيّنة إن وُجد (وإلّا ``now``)."""
    t = (sample or {}).get("time")
    return str(t) if t else "now"


def derive_weather_alerts(sample: dict, plan: dict | None = None) -> list[dict]:
    """يشتقّ تنبيهات الطقس الزراعيّة من عيّنة Open-Meteo (وخطّة اختياريّة).

    منطق نقيّ تماماً: لا I/O، لا قاعدة بيانات. يصلح للاستدعاء من نقطة عامّة
    أو من اختبارات الوحدة. ``plan`` اختياريّة وتُستخدم لإثراء سياق الرشّ فقط.
    """
    sample = sample or {}
    alerts: list[dict] = []
    window = _window_label(sample)

    temp = _num(sample, "temperature_2m_c")
    wind = _num(sample, "wind_speed_10m_kmh", 0.0) or 0.0
    gust = _num(sample, "wind_gusts_10m_kmh", wind) or wind
    rain = _num(sample, "precipitation_mm", 0.0) or 0.0
    rh = _num(sample, "relative_humidity_2m_pct")

    strong_wind = wind >= STRONG_WIND_SPEED_KMH or gust >= STRONG_WIND_GUST_KMH

    # 1) رياح قويّة
    if strong_wind:
        critical = wind >= STRONG_WIND_SPEED_KMH * 1.4 or gust >= STRONG_WIND_GUST_KMH * 1.4
        alerts.append(
            {
                "type": "strong_wind",
                "severity": "critical" if critical else "warning",
                "title_ar": "رياح قويّة",
                "detail_ar": (
                    f"رياح {round(wind)} كم/س وهبّات {round(gust)} كم/س — "
                    "انجراف عالٍ؛ تجنّب الرشّ والعمليّات الحسّاسة."
                ),
                "window": window,
            }
        )

    # 2) موجة حرّ / حرارة مرتفعة
    if temp is not None and temp >= HEAT_WARNING_C:
        is_wave = temp >= HEAT_WAVE_C
        alerts.append(
            {
                "type": "heat_wave",
                "severity": "critical" if is_wave else "warning",
                "title_ar": "موجة حرّ",
                "detail_ar": (
                    f"حرارة {round(temp)}°م — "
                    + (
                        "أوقِف العمليّات المجهِدة وأعِد جدولة الريّ لتجنّب الإجهاد الحراريّ."
                        if is_wave
                        else "تجنّب العمليّات المجهِدة وقت الذروة وراقب الإجهاد المائيّ."
                    )
                ),
                "window": window,
            }
        )

    # 3) صقيع
    if temp is not None and temp <= FROST_WARNING_C:
        is_frost = temp <= FROST_C
        alerts.append(
            {
                "type": "frost",
                "severity": "critical" if is_frost else "warning",
                "title_ar": "صقيع",
                "detail_ar": (
                    f"حرارة {round(temp)}°م — "
                    + (
                        "خطر صقيع؛ فعّل إجراءات الحماية (ريّ وقائيّ/تغطية) للمحاصيل الحسّاسة."
                        if is_frost
                        else "حرارة قرب الصفر؛ راقب احتمال الصقيع ليلاً."
                    )
                ),
                "window": window,
            }
        )

    # 4) نافذة رشّ: ممتازة أو مؤجَّلة (متعارضة؛ نختار واحدة)
    spray_blocked = (
        rain > RAIN_TRIGGER_MM
        or wind > SPRAY_WIND_MAX_KMH
        or gust > SPRAY_GUST_MAX_KMH
        or (rh is not None and rh > SPRAY_HUMIDITY_MAX_PCT)
        or (temp is not None and (temp >= HEAT_WARNING_C or temp <= FROST_WARNING_C))
    )
    if spray_blocked:
        reasons: list[str] = []
        if rain > RAIN_TRIGGER_MM:
            reasons.append("هطول")
        if wind > SPRAY_WIND_MAX_KMH or gust > SPRAY_GUST_MAX_KMH:
            reasons.append("رياح/هبّات مرتفعة")
        if rh is not None and rh > SPRAY_HUMIDITY_MAX_PCT:
            reasons.append("رطوبة مرتفعة")
        if temp is not None and temp >= HEAT_WARNING_C:
            reasons.append("حرارة مرتفعة")
        if temp is not None and temp <= FROST_WARNING_C:
            reasons.append("حرارة منخفضة")
        alerts.append(
            {
                "type": "postpone_spray",
                "severity": "warning",
                "title_ar": "تأجيل الرشّ",
                "detail_ar": "تأجيل الرشّ مُوصى به بسبب: " + "، ".join(reasons) + ".",
                "window": window,
            }
        )
    else:
        alerts.append(
            {
                "type": "excellent_spray_window",
                "severity": "info",
                "title_ar": "فرصة رشّ ممتازة",
                "detail_ar": (
                    "رياح هادئة وجوّ جافّ — نافذة رشّ ممتازة؛ التزِم بالملصق وإجراءات السلامة."
                ),
                "window": window,
            }
        )

    # 5) مرض محتمل (عامّ/اختياريّ): رطوبة عالية مع اعتدال حراريّ
    if (
        rh is not None
        and rh >= DISEASE_HUMIDITY_PCT
        and temp is not None
        and DISEASE_TEMP_LOW_C <= temp <= DISEASE_TEMP_HIGH_C
    ):
        alerts.append(
            {
                "type": "possible_disease",
                "severity": "info",
                "title_ar": "مرض محتمل",
                "detail_ar": (
                    f"رطوبة {round(rh)}% مع حرارة {round(temp)}°م — "
                    "ظروف قد تشجّع الأمراض الفطريّة؛ راقب الحقل وفكّر في برنامج وقائيّ."
                ),
                "window": window,
            }
        )

    return alerts
