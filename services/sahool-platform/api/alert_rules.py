"""api/alert_rules.py — محرّك توليد التنبيهات الزراعيّة (منطق صرف، pure).

خارطة الطريق: Sprint — توليد تلقائيّ لتنبيهات الحقل من ظروفه الحاليّة.

المبدأ:
  • هذا المنطق **نقيّ** (لا شبكة، لا قاعدة) — يُختبَر offline بالكامل.
  • النواة (main.py) تبني السياق (FieldAlertContext) من مساعِدات الطقس/الحقل
    الموجودة (Open-Meteo + الموسم النشط) ثمّ تُمرّره لـevaluate_field_alerts.
  • نُعيد استخدام weather_advice.disease_risk بدل إعادة اختراع تهديف الأمراض —
    مصدر واحد للحقيقة.
  • النتيجة قائمة GeneratedAlert تُدرَج في جدول alerts (v36) في النواة، مع
    حذف التكرار (dedupe) لنوع التنبيه النشط لكلّ حقل.

⚠ العتبات أدناه heuristics agro-met مبسّطة موسومة بمرجعها — ليست نموذجاً
مُعايَراً يمنيّاً. تحتاج معايرة ميدانيّة. لا ثوابت مُختلقة بلا مبرّر.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.weather_advice import disease_risk

# ─── العتبات الموثَّقة (agro-met heuristics) ─────────────────────────
# رطوبة منخفضة: رطوبة التربة المتاحة تحت هذا الحدّ ⇒ إجهاد مائيّ وشيك.
# المرجع: FAO-56 — يُستحسن الريّ قبل استنزاف الماء المتاح المسموح (MAD ~50٪)؛
# نتبنّى نفس عتبة weather_advice._SOIL_CRITICAL_PCT (30٪) كحدّ حرج.
LOW_MOISTURE_SOIL_PCT = 30.0
# بديل حين تغيب قراءة رطوبة التربة: احتياج ريّ صافٍ مرتفع (mm) يدلّ على جفاف.
LOW_MOISTURE_IRRIGATION_MM = 8.0

# أمطار غزيرة: مطر متوقّع (mm خلال نافذة التوقّع) فوق هذا الحدّ ⇒ خطر جريان/تشبّع.
# المرجع: تصنيفات هطول عامّة — ≥ ٢٠ مم/يوم يُعدّ مطراً غزيراً يضرّ المحاصيل.
HEAVY_RAIN_MM = 20.0
HEAVY_RAIN_CRITICAL_MM = 40.0  # هطول شديد ⇒ خطورة حرجة

# إجهاد حراريّ: حرارة عظمى متوقّعة فوق هذا الحدّ ⇒ إجهاد حراريّ للنبات.
# المرجع: معظم محاصيل الحقل تعاني فوق ٣٥°م؛ ٤٠°م إجهاد شديد.
HEAT_STRESS_TMAX_C = 35.0
HEAT_STRESS_CRITICAL_TMAX_C = 40.0

# خطر صقيع: حرارة صغرى متوقّعة تحت هذا الحدّ ⇒ خطر صقيع/تجمّد.
# المرجع: الصقيع يبدأ قرب ٢°م سطحيّاً (التجمّع الأرضيّ أبرد من المظلّة)؛
# تحت ٠°م تجمّد مؤكَّد ⇒ خطورة حرجة.
FROST_RISK_TMIN_C = 2.0
FROST_RISK_CRITICAL_TMIN_C = 0.0


@dataclass(frozen=True)
class FieldAlertContext:
    """سياق تقييم تنبيهات حقل — قيم الطقس/التربة/الموسم المُجمَّعة في النواة.

    كلّ الحقول اختياريّة عدا المعرّف؛ القاعدة الغائبة قيمتها لا تُطلِق تنبيهها
    (صدق: لا نُلفّق قراءة غير متوفّرة).
    """

    field_id: str
    # رطوبة التربة المتاحة % (إن توفّرت من جهاز/قياس). None ⇒ نستخدم احتياج الريّ.
    soil_moisture_pct: float | None = None
    # احتياج الريّ الصافي (mm) من توصية الريّ (FAO-56) — بديل لرطوبة التربة.
    irrigation_need_mm: float | None = None
    # مطر متوقّع (mm) خلال نافذة التوقّع القادمة.
    forecast_rain_mm: float | None = None
    # حرارة الهواء الحاليّة (°م) — لتهديف مخاطر الأمراض.
    temp_c: float | None = None
    # رطوبة نسبيّة % — لتهديف مخاطر الأمراض.
    humidity_pct: float | None = None
    # مطر تراكميّ آخر ٣ أيّام (mm) — لتهديف مخاطر الأمراض.
    rain_mm_3d: float | None = None
    # حرارة عظمى متوقّعة اليوم (°م) — للإجهاد الحراريّ.
    tmax_c: float | None = None
    # حرارة صغرى متوقّعة الليلة (°م) — لخطر الصقيع.
    tmin_c: float | None = None
    # المحصول (lowercase) إن عُرف — يُمرَّر لتهديف الأمراض.
    crop: str | None = None


@dataclass(frozen=True)
class GeneratedAlert:
    """تنبيه مُولَّد — يطابق أعمدة جدول alerts (v36) القابلة للإدراج."""

    alert_type: str
    severity: str
    title_ar: str
    message_ar: str


def _low_moisture(ctx: FieldAlertContext) -> GeneratedAlert | None:
    """رطوبة منخفضة: رطوبة تربة حرجة أو احتياج ريّ مرتفع ⇒ إجهاد مائيّ."""
    sm = ctx.soil_moisture_pct
    need = ctx.irrigation_need_mm
    fired = False
    reason = ""
    if sm is not None and sm < LOW_MOISTURE_SOIL_PCT:
        fired = True
        reason = f"رطوبة التربة المتاحة ({sm:.0f}٪) دون الحدّ الحرج ({LOW_MOISTURE_SOIL_PCT:.0f}٪)."
    elif sm is None and need is not None and need >= LOW_MOISTURE_IRRIGATION_MM:
        fired = True
        reason = (
            f"احتياج الريّ الصافي مرتفع ({need:.0f} مم ≥ {LOW_MOISTURE_IRRIGATION_MM:.0f} مم) "
            "ولا قراءة رطوبة تربة."
        )
    if not fired:
        return None
    return GeneratedAlert(
        alert_type="low_moisture",
        severity="warning",
        title_ar="رطوبة تربة منخفضة",
        message_ar=reason + " رُيّ الحقل عاجلاً لتفادي إجهاد المحصول.",
    )


def _heavy_rain(ctx: FieldAlertContext) -> GeneratedAlert | None:
    """أمطار غزيرة: مطر متوقّع فوق العتبة ⇒ خطر جريان/تشبّع/غرق."""
    rain = ctx.forecast_rain_mm
    if rain is None or rain < HEAVY_RAIN_MM:
        return None
    critical = rain >= HEAVY_RAIN_CRITICAL_MM
    severity = "critical" if critical else "warning"
    return GeneratedAlert(
        alert_type="heavy_rain",
        severity=severity,
        title_ar="أمطار غزيرة متوقّعة",
        message_ar=(
            f"مطر متوقّع {rain:.0f} مم. أرجئ الريّ والرشّ، وتأكّد من الصرف لتفادي "
            "تشبّع التربة والجريان السطحيّ."
        ),
    )


def _disease_risk(ctx: FieldAlertContext) -> GeneratedAlert | None:
    """خطر مرض: نُعيد استخدام weather_advice.disease_risk؛ نُطلِق عند high فقط."""
    if ctx.temp_c is None or ctx.humidity_pct is None:
        return None
    risk = disease_risk(
        temp_c=ctx.temp_c,
        humidity_pct=ctx.humidity_pct,
        rain_mm_3d=ctx.rain_mm_3d or 0.0,
        crop=ctx.crop,
    )
    # disease_risk يُرجع low|moderate|high. نُطلِق التنبيه عند الخطر المرتفع فقط
    # (high/critical منطقيّاً) لتفادي ضجيج تنبيهات على خطر متوسّط.
    if risk["risk_level"] != "high":
        return None
    diseases = risk.get("diseases_ar") or []
    tail = (" أمراض محتملة: " + "، ".join(diseases) + ".") if diseases else ""
    return GeneratedAlert(
        alert_type="disease_risk",
        severity="critical",
        title_ar="خطر مرتفع لأمراض فطريّة",
        message_ar=risk["advice_ar"] + tail,
    )


def _heat_stress(ctx: FieldAlertContext) -> GeneratedAlert | None:
    """إجهاد حراريّ: حرارة عظمى متوقّعة فوق العتبة."""
    tmax = ctx.tmax_c
    if tmax is None or tmax < HEAT_STRESS_TMAX_C:
        return None
    critical = tmax >= HEAT_STRESS_CRITICAL_TMAX_C
    severity = "critical" if critical else "warning"
    return GeneratedAlert(
        alert_type="heat_stress",
        severity=severity,
        title_ar="إجهاد حراريّ متوقّع",
        message_ar=(
            f"حرارة عظمى متوقّعة {tmax:.0f}°م (فوق {HEAT_STRESS_TMAX_C:.0f}°م). "
            "زِد الريّ صباحاً/مساءً وتجنّب العمليّات وقت الذروة لحماية المحصول."
        ),
    )


def _frost_risk(ctx: FieldAlertContext) -> GeneratedAlert | None:
    """خطر صقيع: حرارة صغرى متوقّعة تحت العتبة."""
    tmin = ctx.tmin_c
    if tmin is None or tmin > FROST_RISK_TMIN_C:
        return None
    critical = tmin <= FROST_RISK_CRITICAL_TMIN_C
    severity = "critical" if critical else "warning"
    return GeneratedAlert(
        alert_type="frost_risk",
        severity=severity,
        title_ar="خطر صقيع متوقّع",
        message_ar=(
            f"حرارة صغرى متوقّعة {tmin:.0f}°م (تحت {FROST_RISK_TMIN_C:.0f}°م). "
            "احمِ المحصول الحسّاس (تغطية/ريّ وقائيّ) لتفادي ضرر التجمّد."
        ),
    )


# ترتيب التقييم ثابت — يحدّد ترتيب التنبيهات المُولَّدة (متوقَّع في الاختبارات).
_RULES = (
    _low_moisture,
    _heavy_rain,
    _disease_risk,
    _heat_stress,
    _frost_risk,
)


def evaluate_field_alerts(ctx: FieldAlertContext) -> list[GeneratedAlert]:
    """يُقيّم كلّ قواعد التنبيه على سياق حقل ويُرجع التنبيهات المُطلَقة.

    منطق نقيّ بالكامل (يُختبَر offline). كلّ قاعدة تُرجع GeneratedAlert واحداً
    أو None (لم تُطلَق). الترتيب ثابت حسب _RULES.
    """
    out: list[GeneratedAlert] = []
    for rule in _RULES:
        alert = rule(ctx)
        if alert is not None:
            out.append(alert)
    return out
