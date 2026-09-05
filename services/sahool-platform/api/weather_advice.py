"""
api/weather_advice.py — منطق صرف (pure) لتوصية الريّ ومخاطر الأمراض من الطقس.

خارطة الطريق: Sprint 5a — الجدولة الذكيّة للريّ + مخاطر الأمراض على مستوى الحقل.

المبدأ:
  • منطق التهديف هنا **نقيّ** (لا شبكة، لا قاعدة) — يُختبَر offline.
  • نُعيد استخدام رياضيّات FAO-56 الموجودة (water_balance.KC_BY_CROP_STAGE +
    _effective_rain) بدل إعادة اختراعها — مصدر واحد للحقيقة لمعاملات Kc.
  • النواة (main.py) تجلب ET₀/الطقس من Open-Meteo (نفس مصدر /api/v1/weather)
    ثمّ تُمرّره لهذه الدوالّ. عند تعذّر الطقس ⇒ 503 صريح في الـendpoint.

⚠ معاملات Kc تقديريّة (FAO-56) — تحتاج معايرة محلّيّة يمنيّة. كلّ heuristic
موسوم بمرجعه. لا ثوابت مُختلقة.
"""

from __future__ import annotations

# H5 — تصحيح ملوحة محافظ: نُعيد استخدام رياضيّات Maas-Hoffman من نواة FAO-56
# (مصدر واحد للحقيقة) وعتبة الملوحة المتوسّطة الموحّدة من core.thresholds.
# لا نُعيد كتابة الصيغة هنا، ولا نضيف غسيلاً (لا مصدر موثوق لـECw).
from core.engines.fao56 import salinity_stress_ks as _salinity_stress_ks
from core.thresholds import SALINITY_MODERATE_ECE as _SALINITY_MODERATE_ECE

from api.water_balance import KC_BY_CROP_STAGE, _effective_rain


class _SaltToleranceShim:
    """غلاف خفيف يحمل سمتَي الملوحة اللتين تحتاجهما salinity_stress_ks فقط
    (salt_tolerance_ece, salt_slope_pct) — كي نُعيد استخدام دالّة النواة بلا
    إعادة كتابة معادلة Maas-Hoffman ولا بناء CropKcProfile كامل."""

    __slots__ = ("salt_tolerance_ece", "salt_slope_pct")

    def __init__(self, salt_tolerance_ece: float, salt_slope_pct: float) -> None:
        self.salt_tolerance_ece = float(salt_tolerance_ece)
        self.salt_slope_pct = float(salt_slope_pct)


# ميل Maas-Hoffman الافتراضيّ (% فقد غلّة لكلّ dS/m فوق العتبة) حين لا يُمرَّر ميل
# المحصول. 7.1 قيمة معتدلة (قمح، FAO-56 T23) — تُستخدم فقط كـfallback محافظ.
_DEFAULT_SALT_SLOPE_PCT = 7.1

# منحنى Kc عامّ حين يكون المحصول غير مُعرّف — نفس fallback في water_balance.
_DEFAULT_KC = {"initial": 0.4, "development": 0.8, "mid": 1.1, "late": 0.6}

# عتبات رطوبة التربة (% من السعة الحقليّة المتاحة) لضبط الإلحاح.
# المرجع: FAO-56 — الريّ يُستحسن قبل استنزاف الماء المتاح المسموح (MAD ~50٪).
_SOIL_CRITICAL_PCT = 30.0  # تحت هذا الحدّ: إجهاد مائيّ وشيك
_SOIL_COMFORTABLE_PCT = 60.0  # فوق هذا الحدّ: التربة رطبة، لا داعي للاستعجال


# ─── اكتمالُ المطر — سياسةٌ واحدة، لأنّ الغيابَ هنا يُنتِج أمرَ ريّ ───────
#
# **العطلُ مقيسٌ بالتنفيذ لا موصوفٌ:** مطرٌ غائبٌ يصل الحسابَ صفراً فيُعطي
# `recommended_mm=7.5` و`urgency=moderate` و«خلال ٢٤ ساعة» — **أمرَ ريٍّ صريحاً**؛
# وبالقراءة الحقيقيّة (١٢مم) يُعطي `0.0` و«لا حاجة للريّ». والانحيازُ في اتّجاهِ
# الإذن: غيابُ القياس يُنتِج ريّاً لا منعاً. وأسوأُ من الرقم أنّ `rationale_ar`
# **لا يذكر المطرَ بحرفٍ** عند الصفر، فيُقرأ «حُسِب ولا مطرَ يُخصَم» لا «لا نعلم».
#
# **ولمَ هنا لا في كلّ مسار:** الحكمُ كان مكتوباً في `field_workspace_weather.py`
# وحدَه (`_complete_precipitation_total`)، بينما `fields.py` و`main.py` تجمعان
# `sum(... or 0.0)` بلا حارس — أي **علاجٌ ضيّقٌ تحت فجوةٍ عريضة**. فاستُخرِج
# الحكمُ إلى `list[float | None]` مُجرَّدةٍ من الشكل: القاموسُ والكائنُ المُصنَّف
# يستخرج كلٌّ قراءاتِه ثمّ يسأل **نفسَ** السياسة. تعريفٌ واحد لا ثلاثة تتّفق اليوم.
#
# **و`0.0` الصريح يبقى رصداً** — «لا مطر» قياسٌ مشروع. الناقصُ وحدَه هو `None`
# أو فترةٌ غائبةٌ عن سلسلةٍ أقصر من المتوقَّع.
def complete_rain_total(
    readings: list[float | None], *, expected_count: int
) -> tuple[float | None, list[int]]:
    """مجموعُ مطرٍ **فقط** إذا رُصِدت كلُّ فترةٍ متوقَّعة، وإلّا تُسمّى الفترات الناقصة.

    تُعيد ``(total, missing_indices)``. وجودُ أيّ ناقصٍ ⇒ ``(None, [...])`` —
    فلا يُجمَع نصفُ سلسلةٍ ويُقدَّم مجموعاً كاملاً.
    """
    missing: list[int] = []
    values: list[float] = []
    for index in range(expected_count):
        value = readings[index] if index < len(readings) else None
        if value is None:
            missing.append(index)
        else:
            values.append(value)
    if missing:
        return None, missing
    return sum(values), []


def precipitation_incomplete_detail(*, context: str, missing_intervals: list[int]) -> dict:
    """جسمُ الخطأ الفاشل مغلقاً — **بياناً لا استثناءً**، فتبقى هذه الوحدة نقيّة.

    كلُّ مسارٍ يلفّه بـ``HTTPException(503, detail=...)``؛ والشكلُ واحدٌ هنا كي لا
    يُبلَّغ العطلُ نفسُه برمزين مختلفين في مسارين.
    """
    return {
        "code": "WEATHER_PRECIPITATION_INCOMPLETE",
        "message_ar": "بيانات المطر غير مكتملة؛ لا يمكن إصدار تقدير زراعي آمن.",
        "context": context,
        "missing_intervals": missing_intervals,
    }


def resolve_kc(crop: str | None, stage: str) -> tuple[float, bool, str]:
    """يُرجع (kc, crop_known, kc_source_ar) لمحصول/مرحلة.

    يُعيد استخدام KC_BY_CROP_STAGE (FAO-56). عند غياب المحصول/المرحلة يستخدم
    منحنى عامّاً ويوسمه بصدق (تقدير يحتاج معايرة).
    """
    key = (crop or "").strip().lower()
    crop_known = key in KC_BY_CROP_STAGE
    kc_map = KC_BY_CROP_STAGE.get(key, _DEFAULT_KC)
    kc = kc_map.get(stage, kc_map.get("mid", 1.0))
    if crop_known:
        source = f"محصول مُعرّف ({key}) — FAO-56"
    else:
        source = "منحنى Kc عامّ (المحصول غير مُعرّف) — تقدير، عايِر ميدانيّاً"
    return float(kc), crop_known, source


def irrigation_advice(
    et0_mm: float,
    crop: str | None,
    stage: str = "mid",
    rain_recent_mm: float = 0.0,
    forecast_rain_mm: float = 0.0,
    soil_moisture_pct: float | None = None,
    kc_override: float | None = None,
    soil_ece: float | None = None,
    crop_salt_tolerance_ece: float | None = None,
    salt_slope_pct: float | None = None,
) -> dict:
    """توصية ريّ بنمط FAO-56 — دالّة نقيّة (تُختبَر offline).

    الحساب:
      ETc = ET₀ × Kc  (الاحتياج المائي للمحصول)
      الاحتياج الصافي (recommended_mm) = ETc − المطر الفعّال الأخير فقط.
      المطر المتوقّع (forecast_rain_mm) لا يدخل في الكمّيّة — يُستخدم فقط لخفض
      الإلحاح/تأخير الريّ (لتفادي خصم مطر قد لا يهطل). رطوبة التربة تضبط الإلحاح.

    مصدر Kc:
      افتراضيّاً يُشتقّ Kc من (المحصول، المرحلة) عبر resolve_kc (جدول FAO-56
      الخشِن على مستوى المرحلة). عند تمرير kc_override نُفضّله ونستخدمه مباشرةً
      بوصفه معامل المحصول — وهو Kc الدقيق المحسوب من فينولوجيا المحصول حسب العمر
      (FAO-56 phenology-stage، عبر النواة: season_phenology.stage_kc). في هذه
      الحالة يدخل الـoverride في كلّ ما يليه (ETc = ET₀ × Kc، recommended_mm…).
      حين يكون kc_override = None يبقى السلوك مطابقاً تماماً للمسار القديم.

    Args:
        et0_mm: التبخّر-نتح المرجعي اليومي (mm) — من Open-Meteo (FAO-56).
        crop: المحصول (lowercase). None/غير مُعرّف ⇒ منحنى Kc عامّ.
        stage: مرحلة النموّ initial|development|mid|late.
        rain_recent_mm: مطر فعليّ في النافذة الأخيرة (mm).
        forecast_rain_mm: مطر متوقّع خلال ٤٨ ساعة القادمة (mm) — يؤخّر الريّ.
        soil_moisture_pct: رطوبة التربة المتاحة % (اختياري) — يضبط الإلحاح.
        kc_override: معامل المحصول Kc الدقيق من الفينولوجيا (FAO-56 حسب العمر).
            عند تمريره يُستخدم بدل اشتقاق (المحصول، المرحلة). None ⇒ المسار القديم.
        soil_ece: ملوحة التربة المُتحقَّقة ECe (dS/m). None ⇒ لا تصحيح ملوحة.
        crop_salt_tolerance_ece: عتبة تحمّل المحصول للملوحة ECe (dS/m، FAO-56 T23).
            None ⇒ تحمّل المحصول مجهول ⇒ لا تصحيح ملوحة (محافظ، لا نخمّن عتبة).
        salt_slope_pct: ميل Maas-Hoffman (% فقد لكلّ dS/m فوق العتبة). None ⇒
            افتراضيّ محافظ 7.1٪. يُستخدم فقط حين يُطبَّق التصحيح.

    تصحيح الملوحة (H5 — محافظ، بلا غسيل):
        يُطبَّق Ks = salinity_stress_ks(Maas-Hoffman) على ETc (وبالتالي الاحتياج
        الصافي) **فقط** حين تتوفّر ملوحة تربة مُتحقَّقة ≥ العتبة المتوسّطة
        (SALINITY_MODERATE_ECE) **و** عتبة تحمّل المحصول معلومة. الملوحة تخفض
        امتصاص النبات للماء ⇒ احتياج صافٍ أقل (يخدم توفير الماء). لا يُضاف عمق
        غسيل (لا مصدر موثوق لـECw). إن غابت أيّ شرط ⇒ السلوك مطابق تماماً للقديم
        (salinity_ks = 1.0).

    Returns:
        {recommended_mm, urgency, timing_ar, et0, kc, kc_used, kc_source,
         salinity_ks, rationale_ar}
        urgency ∈ {none, low, moderate, high}
        kc_used: قيمة Kc المستخدمة فعليّاً في الحساب.
        kc_source: مصدرها — "phenology_fao56" عند تمرير kc_override، وإلّا الوسم
        المعتمِد على المرحلة من resolve_kc.
        salinity_ks: معامل إجهاد الملوحة المُطبَّق (0..1). 1.0 ⇒ لا تصحيح (صريح
        ومُتتبَّع، غير مخفيّ).
    """
    et0 = max(0.0, float(et0_mm))
    kc, _known, kc_source = resolve_kc(crop, stage)
    if kc_override is not None:
        kc = float(kc_override)
        kc_source = "phenology_fao56"
    etc = et0 * kc

    reasons: list[str] = [
        f"ETc = ET₀ ({et0:.1f} مم) × Kc ({kc:.2f}) = {etc:.1f} مم؛ {kc_source}.",
    ]

    # ── تصحيح ملوحة محافظ (H5، Maas-Hoffman) — بلا غسيل ──
    # يُطبَّق فقط حين: ملوحة تربة مُتحقَّقة موجودة ≥ العتبة المتوسّطة، وعتبة تحمّل
    # المحصول معلومة. غير ذلك ⇒ Ks = 1.0 (السلوك القديم تماماً، صريح في الـpayload).
    salinity_ks = 1.0
    if (
        soil_ece is not None
        and crop_salt_tolerance_ece is not None
        and float(soil_ece) >= _SALINITY_MODERATE_ECE
    ):
        slope = _DEFAULT_SALT_SLOPE_PCT if salt_slope_pct is None else float(salt_slope_pct)
        shim = _SaltToleranceShim(crop_salt_tolerance_ece, slope)
        # نُعيد استخدام دالّة النواة (مصدر واحد لرياضيّات Maas-Hoffman) ثمّ نُثبّت
        # النتيجة في [0,1] دفاعيّاً (الدالّة تُرجِع ≥0؛ نقصّ السقف احترازاً).
        salinity_ks = max(0.0, min(1.0, _salinity_stress_ks(shim, float(soil_ece))))
        if salinity_ks < 1.0:
            etc = etc * salinity_ks
            reasons.append(
                f"تصحيح ملوحة محافظ: ECe التربة {float(soil_ece):.1f} dS/m يتجاوز عتبة "
                f"المحصول {float(crop_salt_tolerance_ece):.1f} dS/m ⇒ Ks={salinity_ks:.2f} "
                f"خفّض ETc إلى {etc:.1f} مم (الملوحة تقلّل امتصاص الماء؛ لا غسيل مضاف)."
            )

    # المطر الفعّال من المطر الأخير (USDA-SCS مبسّط، مُعاد استخدامه).
    eff_rain = _effective_rain(max(0.0, rain_recent_mm))
    net = max(0.0, etc - eff_rain)

    if eff_rain > 0:
        reasons.append(f"المطر الفعّال الأخير {eff_rain:.1f} مم خُصِم من الاحتياج.")

    # تحديد الإلحاح: يبدأ من حجم الاحتياج الصافي، ثمّ يُعدَّل بالتربة والمطر القادم.
    if net <= 0:
        urgency = "none"
    elif net < 4:
        urgency = "low"
    elif net < 8:
        urgency = "moderate"
    else:
        urgency = "high"

    recommended_mm = round(net, 1)

    # رطوبة التربة (إن توفّرت): التربة الرطبة تخفّض الإلحاح، والجافّة ترفعه.
    if soil_moisture_pct is not None:
        sm = float(soil_moisture_pct)
        if sm >= _SOIL_COMFORTABLE_PCT and urgency in {"low", "moderate"}:
            urgency = "low" if urgency == "moderate" else "none"
            reasons.append(
                f"رطوبة التربة مريحة ({sm:.0f}٪ ≥ {_SOIL_COMFORTABLE_PCT:.0f}٪) — يُمكن تأجيل الريّ."
            )
        elif sm < _SOIL_CRITICAL_PCT and net > 0:
            urgency = "high"
            reasons.append(
                f"رطوبة التربة حرجة ({sm:.0f}٪ < {_SOIL_CRITICAL_PCT:.0f}٪) — "
                "إجهاد مائيّ وشيك، رُيّ عاجلاً."
            )

    # المطر المتوقّع قريباً: يؤجّل الريّ إن كان يغطّي جزءاً معتبراً من الاحتياج.
    #
    # **و`forecast_hold` استخراجٌ لهذا الحكم عينِه، لا حكمٌ ثانٍ.** الشرطُ والعتبةُ
    # كما هما منذ كُتِبا؛ المتغيّرُ الوحيد أنّ نتيجتَهما صارت **حقلاً** بدل أن تعيش في
    # `urgency` و`reasons` وحدَهما. وسببُ الاستخراج أنّ مستهلكاً أعلى (قرارُ الإطلاق
    # من الاستنزاف) كان يبتلع الإلحاضَ المخفوض فيختفي التأجيلُ بلا أثر.
    forecast_hold = forecast_rain_mm >= 5 and net > 0 and urgency != "high"
    if forecast_hold:
        urgency = "low"
        reasons.append(f"مطر متوقّع ({forecast_rain_mm:.0f} مم خلال ٤٨ ساعة) — انتظِر قبل الريّ.")

    timing_map = {
        "none": "لا حاجة للريّ الآن",
        "low": "خلال الأيّام ٢-٣ القادمة",
        "moderate": "خلال ٢٤ ساعة",
        "high": "اليوم — لا تؤخّر",
    }
    timing_ar = timing_map[urgency]

    if recommended_mm <= 0:
        rationale_ar = "لا حاجة للريّ — المطر يغطّي الاحتياج. " + " ".join(reasons)
        recommended_mm = 0.0
    else:
        rationale_ar = f"الاحتياج الصافي {recommended_mm:.1f} مم. " + " ".join(reasons)

    return {
        "recommended_mm": recommended_mm,
        "urgency": urgency,
        "timing_ar": timing_ar,
        "et0": round(et0, 2),
        "kc": round(kc, 2),
        "kc_used": round(kc, 2),
        "kc_source": kc_source,
        "salinity_ks": round(salinity_ks, 3),
        "rationale_ar": rationale_ar,
        "forecast_hold": forecast_hold,
    }


# ─── مخاطر الأمراض الفطريّة (agro-met) ────────────────────────────
# المرجع: مبادئ علم الأوبئة النباتيّة (Agrios, Plant Pathology) — معظم الفطريّات
# تحتاج رطوبة ورقيّة طويلة (رطوبة نسبيّة عالية + ندى) وحرارة معتدلة للإنبات.
# هذه heuristics مبسّطة موسومة بمصدرها — ليست نموذجاً تنبّؤيّاً مُعايَراً.
_HUMID_THRESHOLD = 80.0  # رطوبة نسبيّة عالية تُطيل بلل الورقة
_MILD_TEMP_LOW = 15.0  # نطاق حرارة مثاليّ لإنبات أبواغ كثير من الفطريّات
_MILD_TEMP_HIGH = 28.0
_WET_RAIN_3D = 10.0  # مطر تراكميّ ٣ أيّام يُبقي المظلّة رطبة


def disease_risk(
    temp_c: float,
    humidity_pct: float,
    rain_mm_3d: float = 0.0,
    crop: str | None = None,
) -> dict:
    """تقييم بسيط لمخاطر الأمراض الفطريّة من نوافذ الرطوبة/الحرارة/المطر.

    منطق نقيّ (يُختبَر offline). الحساب يجمع عوامل البيئة المُهيّئة للفطريّات:
      • رطوبة نسبيّة عالية (≥ ٨٠٪) → بلل ورقيّ مُطوَّل.
      • حرارة معتدلة (١٥-٢٨°م) → مثاليّة لإنبات الأبواغ.
      • مطر تراكميّ ٣ أيّام (≥ ١٠ مم) → رطوبة مظلّة مستمرّة.
    كلّ عامل متحقّق يرفع الدرجة. الحرارة العالية جدّاً (> ٣٥°م) تكبح الفطريّات.

    Returns:
        {risk_level, diseases_ar:[...], advice_ar}
        risk_level ∈ {low, moderate, high}
    """
    t = float(temp_c)
    rh = float(humidity_pct)
    rain = max(0.0, float(rain_mm_3d))

    score = 0
    factors: list[str] = []

    humid = rh >= _HUMID_THRESHOLD
    mild = _MILD_TEMP_LOW <= t <= _MILD_TEMP_HIGH
    wet = rain >= _WET_RAIN_3D

    if humid:
        score += 1
        factors.append(f"رطوبة نسبيّة عالية ({rh:.0f}٪)")
    if mild:
        score += 1
        factors.append(f"حرارة معتدلة ({t:.0f}°م)")
    if wet:
        score += 1
        factors.append(f"مطر تراكميّ ({rain:.0f} مم/٣ أيّام)")

    # الحرارة العالية جدّاً تكبح أغلب الفطريّات (تجفيف + توقّف الإنبات).
    if t > 35:
        score = max(0, score - 1)
        factors.append("حرارة عالية (> ٣٥°م) تكبح الفطريّات")

    if score >= 3:
        risk_level = "high"
    elif score == 2:
        risk_level = "moderate"
    else:
        risk_level = "low"

    # أمراض محتملة وفق البيئة (موسومة كاحتمال لا تشخيص).
    diseases_ar: list[str] = []
    if humid and mild:
        diseases_ar.append("اللفحة المتأخّرة (Late blight)")
        diseases_ar.append("البياض الزغبيّ (Downy mildew)")
    if humid and wet:
        diseases_ar.append("تبقّع الأوراق الفطريّ (Leaf spot)")
        diseases_ar.append("الصدأ (Rust)")
    if rh >= 70 and not wet and 20 <= t <= 30:
        diseases_ar.append("البياض الدقيقيّ (Powdery mildew)")
    # إزالة التكرار مع الحفاظ على الترتيب.
    diseases_ar = list(dict.fromkeys(diseases_ar))

    if risk_level == "high":
        advice_ar = (
            "خطر مرتفع: "
            + "، ".join(factors)
            + ". افحص المحصول ميدانيّاً، وفكّر في رشّ وقائيّ مناسب وتحسين التهوية، "
            "وتجنّب الريّ المسائيّ الذي يُطيل بلل الورقة."
        )
    elif risk_level == "moderate":
        advice_ar = (
            "خطر متوسّط: "
            + "، ".join(factors)
            + ". راقب الحقل عن كثب وكُن مستعدّاً للرشّ الوقائيّ إن ساءت الظروف."
        )
    else:
        advice_ar = "خطر منخفض حاليّاً — الظروف الجوّيّة غير مُهيّئة لتفشٍّ فطريّ. تابع المراقبة الدوريّة."

    return {
        "risk_level": risk_level,
        "diseases_ar": diseases_ar,
        "advice_ar": advice_ar,
    }
