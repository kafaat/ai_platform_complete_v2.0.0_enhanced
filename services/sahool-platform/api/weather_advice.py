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

from api.water_balance import KC_BY_CROP_STAGE, _effective_rain

# منحنى Kc عامّ حين يكون المحصول غير مُعرّف — نفس fallback في water_balance.
_DEFAULT_KC = {"initial": 0.4, "development": 0.8, "mid": 1.1, "late": 0.6}

# عتبات رطوبة التربة (% من السعة الحقليّة المتاحة) لضبط الإلحاح.
# المرجع: FAO-56 — الريّ يُستحسن قبل استنزاف الماء المتاح المسموح (MAD ~50٪).
_SOIL_CRITICAL_PCT = 30.0  # تحت هذا الحدّ: إجهاد مائيّ وشيك
_SOIL_COMFORTABLE_PCT = 60.0  # فوق هذا الحدّ: التربة رطبة، لا داعي للاستعجال


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
) -> dict:
    """توصية ريّ بنمط FAO-56 — دالّة نقيّة (تُختبَر offline).

    الحساب:
      ETc = ET₀ × Kc  (الاحتياج المائي للمحصول)
      الاحتياج الصافي = ETc − المطر الفعّال (الأخير + المتوقّع قريباً)
      → recommended_mm، مع ضبط الإلحاح برطوبة التربة إن توفّرت والمطر المتوقّع.

    Args:
        et0_mm: التبخّر-نتح المرجعي اليومي (mm) — من Open-Meteo (FAO-56).
        crop: المحصول (lowercase). None/غير مُعرّف ⇒ منحنى Kc عامّ.
        stage: مرحلة النموّ initial|development|mid|late.
        rain_recent_mm: مطر فعليّ في النافذة الأخيرة (mm).
        forecast_rain_mm: مطر متوقّع خلال ٤٨ ساعة القادمة (mm) — يؤخّر الريّ.
        soil_moisture_pct: رطوبة التربة المتاحة % (اختياري) — يضبط الإلحاح.

    Returns:
        {recommended_mm, urgency, timing_ar, et0, kc, rationale_ar}
        urgency ∈ {none, low, moderate, high}
    """
    et0 = max(0.0, float(et0_mm))
    kc, _known, kc_source = resolve_kc(crop, stage)
    etc = et0 * kc
    # المطر الفعّال من المطر الأخير (USDA-SCS مبسّط، مُعاد استخدامه).
    eff_rain = _effective_rain(max(0.0, rain_recent_mm))
    net = max(0.0, etc - eff_rain)

    reasons: list[str] = [
        f"ETc = ET₀ ({et0:.1f} مم) × Kc ({kc:.2f}) = {etc:.1f} مم؛ {kc_source}.",
    ]
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
    if forecast_rain_mm >= 5 and net > 0 and urgency != "high":
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
        "rationale_ar": rationale_ar,
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
