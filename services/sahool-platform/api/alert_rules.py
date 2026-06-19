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

from dataclasses import dataclass, replace

from core.thresholds import (
    FROST_CRITICAL_C,
    FROST_RISK_C,
    HEAT_STRESS_CRITICAL_DAILY_TMAX_C,
    HEAT_STRESS_DAILY_TMAX_C,
)

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

# إجهاد حراريّ (حرارة عظمى يوميّة) + خطر صقيع — من المصدر الموحّد core.thresholds
# (نفس القيم؛ التوحيد يمنع الانجراف). أسماء محلّيّة محفوظة لعقد AlertThresholds أدناه.
HEAT_STRESS_TMAX_C = HEAT_STRESS_DAILY_TMAX_C
HEAT_STRESS_CRITICAL_TMAX_C = HEAT_STRESS_CRITICAL_DAILY_TMAX_C
FROST_RISK_TMIN_C = FROST_RISK_C
FROST_RISK_CRITICAL_TMIN_C = FROST_CRITICAL_C

# إجهاد الغطاء النباتيّ (NDVI-drop): هبوط مؤشّر NDVI الحاليّ تحت خطّ الأساس
# المتوقَّع/الصحّيّ (يُورّده النواة: أرضيّة متوقّعة للطور أو قراءة سابقة) بمقدار
# مطلق فوق هذه العتبات ⇒ إشارة استشعار عن بُعد لإجهاد محتمل.
# ⚠ هبوط NDVI **إشارة كشف ميدانيّ** (scouting trigger) لا تشخيص: قد يدلّ على
# إجهاد مائيّ/مرض/آفة/نقص مغذّيات — يحتاج معاينةً ميدانيّة لتحديد السبب.
# المرجع: NDVI صحّيّ للمحاصيل النشطة ٠٫٦–٠٫٩؛ هبوط مطلق ~٠٫١٠ ملحوظ، ~٠٫٢٠ كبير.
NDVI_DROP_WARN = 0.10  # هبوط مطلق تحت خطّ الأساس ⇒ تحذير (كشف ميدانيّ)
NDVI_DROP_CRITICAL = 0.20  # هبوط مطلق كبير ⇒ خطورة حرجة

# طور التكاثر/التزهير (FAO-56 stage = "mid") — الأكثر حسّاسيّة للإجهاد:
# إجهاد الحرارة أو الماء عنده يُسبّب تساقط الأزهار/القرون ⇒ نُصعّد الخطورة.
_REPRODUCTIVE_STAGE = "mid"


@dataclass(frozen=True)
class AlertThresholds:
    """عتبات محرّك التنبيهات قابلة للضبط بسياسة (policy) — افتراضاتها == اليوم.

    كلّ حقل هنا يطابق ثابتاً موثَّقاً من ثوابت الوحدة أعلاه، وقيمته الافتراضيّة
    هي نفسها قيمة ذلك الثابت — فالسلوك الافتراضيّ (thresholds=None) مطابق تماماً
    للسلوك السابق. الثوابت أعلاه تبقى مصدر الحقيقة وأسماءً متوافقة للخلف.

    ⚠ هذه heuristics agro-met مبسّطة موسومة بمرجعها — ليست نموذجاً مُعايَراً
    يمنيّاً، وتحتاج معايرة ميدانيّة.
    """

    # رطوبة منخفضة: رطوبة التربة المتاحة تحت هذا الحدّ ⇒ إجهاد مائيّ وشيك.
    # المرجع: FAO-56 (MAD ~50٪)؛ نتبنّى عتبة weather_advice._SOIL_CRITICAL_PCT (30٪).
    LOW_MOISTURE_SOIL_PCT: float = LOW_MOISTURE_SOIL_PCT
    # بديل حين تغيب قراءة رطوبة التربة: احتياج ريّ صافٍ مرتفع (mm) يدلّ على جفاف.
    LOW_MOISTURE_IRRIGATION_MM: float = LOW_MOISTURE_IRRIGATION_MM
    # أمطار غزيرة: مطر متوقّع (mm) فوق هذا الحدّ ⇒ خطر جريان/تشبّع.
    # المرجع: تصنيفات هطول عامّة — ≥ ٢٠ مم/يوم مطر غزير يضرّ المحاصيل.
    HEAVY_RAIN_MM: float = HEAVY_RAIN_MM
    # هطول شديد ⇒ خطورة حرجة.
    HEAVY_RAIN_CRITICAL_MM: float = HEAVY_RAIN_CRITICAL_MM
    # إجهاد حراريّ: حرارة عظمى متوقّعة فوق هذا الحدّ ⇒ إجهاد حراريّ للنبات.
    # المرجع: معظم محاصيل الحقل تعاني فوق ٣٥°م؛ ٤٠°م إجهاد شديد.
    HEAT_STRESS_TMAX_C: float = HEAT_STRESS_TMAX_C
    HEAT_STRESS_CRITICAL_TMAX_C: float = HEAT_STRESS_CRITICAL_TMAX_C
    # خطر صقيع: حرارة صغرى متوقّعة تحت هذا الحدّ ⇒ خطر صقيع/تجمّد.
    # المرجع: الصقيع يبدأ قرب ٢°م سطحيّاً؛ تحت ٠°م تجمّد مؤكَّد ⇒ خطورة حرجة.
    FROST_RISK_TMIN_C: float = FROST_RISK_TMIN_C
    FROST_RISK_CRITICAL_TMIN_C: float = FROST_RISK_CRITICAL_TMIN_C
    # إجهاد الغطاء النباتيّ: هبوط NDVI المطلق تحت خطّ الأساس فوق هذا الحدّ ⇒ تحذير.
    # المرجع: هبوط مطلق ~٠٫١٠ ملحوظ، ~٠٫٢٠ كبير. إشارة كشف ميدانيّ لا تشخيص.
    NDVI_DROP_WARN: float = NDVI_DROP_WARN
    # هبوط NDVI مطلق كبير ⇒ خطورة حرجة.
    NDVI_DROP_CRITICAL: float = NDVI_DROP_CRITICAL


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
    # طور النموّ (FAO-56): "initial"/"development"/"mid"/"late"؛ None ⇒ مجهول.
    # 'mid' هو طور التكاثر/التزهير — الأكثر حسّاسيّة للإجهاد (الحرارة والماء)؛
    # عنده يُصعَّد إجهاد الحرارة/الرطوبة إلى "critical" حتى تحت العتبة الحرجة العامّة.
    growth_stage: str | None = None
    # متوسّط NDVI الحاليّ للحقل (استشعار عن بُعد، المدى -1..1). None ⇒ لا تقييم.
    ndvi_current: float | None = None
    # خطّ أساس NDVI المتوقَّع/الصحّيّ للمقارنة — يُورّده النواة (أرضيّة متوقّعة
    # لطور النموّ أو قراءة سابقة). None ⇒ لا تقييم (لا نُلفّق مرجعاً غائباً).
    ndvi_baseline: float | None = None


@dataclass(frozen=True)
class GeneratedAlert:
    """تنبيه مُولَّد — يطابق أعمدة جدول alerts (v36) القابلة للإدراج."""

    alert_type: str
    severity: str
    title_ar: str
    message_ar: str


def _low_moisture(ctx: FieldAlertContext, t: AlertThresholds) -> GeneratedAlert | None:
    """رطوبة منخفضة: رطوبة تربة حرجة أو احتياج ريّ مرتفع ⇒ إجهاد مائيّ."""
    sm = ctx.soil_moisture_pct
    need = ctx.irrigation_need_mm
    fired = False
    reason = ""
    if sm is not None and sm < t.LOW_MOISTURE_SOIL_PCT:
        fired = True
        reason = (
            f"رطوبة التربة المتاحة ({sm:.0f}٪) دون الحدّ الحرج ({t.LOW_MOISTURE_SOIL_PCT:.0f}٪)."
        )
    elif sm is None and need is not None and need >= t.LOW_MOISTURE_IRRIGATION_MM:
        fired = True
        reason = (
            f"احتياج الريّ الصافي مرتفع ({need:.0f} مم ≥ {t.LOW_MOISTURE_IRRIGATION_MM:.0f} مم) "
            "ولا قراءة رطوبة تربة."
        )
    if not fired:
        return None
    severity = "warning"
    message_ar = reason + " رُيّ الحقل عاجلاً لتفادي إجهاد المحصول."
    # تصعيد عند التزهير: الإجهاد المائيّ في طور التكاثر يُسقط الأزهار/القرون.
    if ctx.growth_stage == _REPRODUCTIVE_STAGE:
        severity = "critical"
        message_ar += " المحصول في طور التزهير ⇒ إجهاد مائيّ يُسقط الأزهار/القرون."
    return GeneratedAlert(
        alert_type="low_moisture",
        severity=severity,
        title_ar="رطوبة تربة منخفضة",
        message_ar=message_ar,
    )


def _heavy_rain(ctx: FieldAlertContext, t: AlertThresholds) -> GeneratedAlert | None:
    """أمطار غزيرة: مطر متوقّع فوق العتبة ⇒ خطر جريان/تشبّع/غرق."""
    rain = ctx.forecast_rain_mm
    if rain is None or rain < t.HEAVY_RAIN_MM:
        return None
    critical = rain >= t.HEAVY_RAIN_CRITICAL_MM
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


def _disease_risk(ctx: FieldAlertContext, t: AlertThresholds) -> GeneratedAlert | None:
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


def _heat_stress(ctx: FieldAlertContext, t: AlertThresholds) -> GeneratedAlert | None:
    """إجهاد حراريّ: حرارة عظمى متوقّعة فوق العتبة."""
    tmax = ctx.tmax_c
    if tmax is None or tmax < t.HEAT_STRESS_TMAX_C:
        return None
    critical = tmax >= t.HEAT_STRESS_CRITICAL_TMAX_C
    severity = "critical" if critical else "warning"
    message_ar = (
        f"حرارة عظمى متوقّعة {tmax:.0f}°م (فوق {t.HEAT_STRESS_TMAX_C:.0f}°م). "
        "زِد الريّ صباحاً/مساءً وتجنّب العمليّات وقت الذروة لحماية المحصول."
    )
    # تصعيد عند التزهير: الإجهاد الحراريّ في طور التكاثر أشدّ ضرراً ⇒ critical
    # حتى تحت العتبة الحرجة العامّة (يبقى critical إن كان قد تجاوزها أصلاً).
    if not critical and ctx.growth_stage == _REPRODUCTIVE_STAGE:
        severity = "critical"
        message_ar += " المحصول في طور التزهير ⇒ الحرارة أشدّ ضرراً على العقد."
    return GeneratedAlert(
        alert_type="heat_stress",
        severity=severity,
        title_ar="إجهاد حراريّ متوقّع",
        message_ar=message_ar,
    )


def _frost_risk(ctx: FieldAlertContext, t: AlertThresholds) -> GeneratedAlert | None:
    """خطر صقيع: حرارة صغرى متوقّعة تحت العتبة."""
    tmin = ctx.tmin_c
    if tmin is None or tmin > t.FROST_RISK_TMIN_C:
        return None
    critical = tmin <= t.FROST_RISK_CRITICAL_TMIN_C
    severity = "critical" if critical else "warning"
    return GeneratedAlert(
        alert_type="frost_risk",
        severity=severity,
        title_ar="خطر صقيع متوقّع",
        message_ar=(
            f"حرارة صغرى متوقّعة {tmin:.0f}°م (تحت {t.FROST_RISK_TMIN_C:.0f}°م). "
            "احمِ المحصول الحسّاس (تغطية/ريّ وقائيّ) لتفادي ضرر التجمّد."
        ),
    )


def _vegetation_stress(ctx: FieldAlertContext, t: AlertThresholds) -> GeneratedAlert | None:
    """إجهاد الغطاء النباتيّ: هبوط NDVI الحاليّ تحت خطّ الأساس المتوقَّع.

    يتطلّب **كلتا** القيمتين (الحاليّة وخطّ الأساس)؛ غياب أيّهما ⇒ None
    (صدق: لا نُقيّم بلا مرجع). الهبوط = الأساس − الحاليّ؛ تحت عتبة التحذير ⇒
    لا تنبيه. هذا **إشارة كشف ميدانيّ** لا تشخيص — نؤطّره صراحةً كذلك.
    """
    cur = ctx.ndvi_current
    base = ctx.ndvi_baseline
    if cur is None or base is None:
        return None
    drop = base - cur
    if drop < t.NDVI_DROP_WARN:
        return None
    critical = drop >= t.NDVI_DROP_CRITICAL
    severity = "critical" if critical else "warning"
    message_ar = (
        f"هبوط في مؤشّر الغطاء النباتيّ NDVI بمقدار {drop:.2f} "
        f"(من {base:.2f} إلى {cur:.2f}). قد يدلّ على إجهاد مائيّ أو مرض/آفة أو "
        "نقص مغذّيات — هذه إشارة تستلزم كشفاً ميدانيّاً لتحديد السبب، وليست "
        "تشخيصاً نهائيّاً."
    )
    # تصعيد عند التزهير: طور التكاثر أشدّ حسّاسيّة ⇒ critical حتى تحت العتبة الحرجة.
    if not critical and ctx.growth_stage == _REPRODUCTIVE_STAGE:
        severity = "critical"
        message_ar += " المحصول في طور التزهير ⇒ الإجهاد أشدّ ضرراً على العقد."
    return GeneratedAlert(
        alert_type="vegetation_stress",
        severity=severity,
        title_ar="إجهاد محتمل في الغطاء النباتيّ (هبوط NDVI)",
        message_ar=message_ar,
    )


# ترتيب التقييم ثابت — يحدّد ترتيب التنبيهات المُولَّدة (متوقَّع في الاختبارات).
_RULES = (
    _low_moisture,
    _heavy_rain,
    _disease_risk,
    _heat_stress,
    _frost_risk,
    _vegetation_stress,
)


def evaluate_field_alerts(
    ctx: FieldAlertContext,
    thresholds: AlertThresholds | None = None,
) -> list[GeneratedAlert]:
    """يُقيّم كلّ قواعد التنبيه على سياق حقل ويُرجع التنبيهات المُطلَقة.

    منطق نقيّ بالكامل (يُختبَر offline). كلّ قاعدة تُرجع GeneratedAlert واحداً
    أو None (لم تُطلَق). الترتيب ثابت حسب _RULES.

    العتبات تأتي من thresholds؛ حين تكون None نستخدم AlertThresholds()
    (== الافتراضات الموثَّقة) فيكون السلوك مطابقاً تماماً للسابق.
    """
    t = thresholds or AlertThresholds()
    out: list[GeneratedAlert] = []
    for rule in _RULES:
        alert = rule(ctx, t)
        if alert is not None:
            out.append(alert)
    return out


def thresholds_from_policy(policy: dict | None) -> AlertThresholds:
    """يبني AlertThresholds من قاموس تجاوزات (overrides) فوق الافتراضات.

    مفاتيح policy = أسماء حقول AlertThresholds؛ المفاتيح المجهولة تُتجاهل،
    والقيم غير الرقميّة/المُشوّهة تُتجاهل (نرجع لافتراض ذلك الحقل). policy
    فارغ/None ⇒ كلّ الافتراضات. منطق نقيّ لا يرفع استثناءً أبداً.

    ملاحظة: هذا يُغذّى مستقبلاً بسياسة إعدادات لكلّ مستأجِر (per-tenant)
    تُربط في main.py في خطوة لاحقة — لا نربط main.py هنا.
    """
    defaults = AlertThresholds()
    if not policy or not isinstance(policy, dict):
        return defaults
    overrides: dict[str, float] = {}
    for name in defaults.__dataclass_fields__:
        if name not in policy:
            continue
        raw = policy[name]
        # نتجاهل bool (isinstance(True, int)) والقيم غير الرقميّة/المُشوّهة.
        if isinstance(raw, bool):
            continue
        try:
            overrides[name] = float(raw)
        except (TypeError, ValueError):
            continue
    if not overrides:
        return defaults
    return replace(defaults, **overrides)


# ─── تشكيل ملخّص التشغيل الدوريّ لكلّ الحقول (منطق نقيّ — يُختبَر offline) ──
def field_run_summary(
    field_id: str,
    *,
    created: int = 0,
    skipped: int = 0,
    error: str | None = None,
) -> dict:
    """يبني سطر ملخّص تقييم تنبيهات حقل واحد ضمن تشغيل «كلّ الحقول».

    منطق نقيّ (لا شبكة/قاعدة) — يُختبَر offline. الحقل المتعثّر يُسجَّل بـerror
    وقيم created/skipped=0 (تدهور رشيق: لا يُسقط بقيّة الحقول).
    """
    row: dict = {"field_id": field_id, "created": int(created), "skipped": int(skipped)}
    if error is not None:
        row["error"] = error
    return row


def summarize_run(rows: list[dict]) -> dict:
    """يُجمّع نتائج تشغيل «كلّ الحقول» في إجماليّات + تفصيل لكلّ حقل.

    منطق نقيّ (يُختبَر offline). يُرجع fields_total/evaluated/failed،
    created_total، skipped_total، وper_field (الصفوف كما هي).
    """
    failed = sum(1 for r in rows if r.get("error"))
    return {
        "fields_total": len(rows),
        "fields_evaluated": len(rows) - failed,
        "fields_failed": failed,
        "created_total": sum(int(r.get("created", 0)) for r in rows),
        "skipped_total": sum(int(r.get("skipped", 0)) for r in rows),
        "per_field": rows,
    }
