"""soil_science.py — تفسير علميّ نقيّ للتربة: تصنيف القوام (USDA) + ملاءمة المحصول.

وحدة نقيّة (بلا FastAPI/شبكة/قاعدة) — تُختبَر في طبقة الوحدات. تسدّ فجوة حقيقيّة:
soil-service كان يخزّن قراءات الحسّاسات فقط دون أيّ تفسير زراعيّ. هنا:

  • ``usda_texture_class(clay, sand, silt)`` — مثلّث قوام USDA القياسيّ (12 صنفاً).
  • ``crop_suitability(soil, crop)`` — درجة ملاءمة **شفّافة قائمة على قواعد** (لا نموذج
    مُلفَّق): تُقيّم pH والملوحة (EC) والقوام مقابل نطاقات مُوثَّقة لكلّ محصول، وتُعيد
    درجة [0,1] + تصنيف + العوامل المُقيِّدة. المحاصيل مختارة للسياق اليمنيّ.

الأمانة: القيم عتبات زراعيّة منشورة (FAO/جداول إرشاديّة)، والدرجة تفسيريّة لا تنبّؤيّة —
تُعرَض كإرشاد يحتاج معايرة ميدانيّة، لا كحقيقة مطلقة.
"""

from __future__ import annotations

# ── مثلّث قوام USDA ────────────────────────────────────────────────────────────
# الإدخال نِسَب مئويّة (0..100) للطين (clay) والرمل (sand) والغرين (silt).
# القواعد تتبع خوارزميّة مثلّث USDA القياسيّة (نفس منطق حزمة soiltexture).
_TEXTURE_AR = {
    "sand": "رمليّة",
    "loamy sand": "رمليّة طميّة",
    "sandy loam": "طميّة رمليّة",
    "loam": "طميّة",
    "silt loam": "طميّة غرينيّة",
    "silt": "غرينيّة",
    "sandy clay loam": "طينيّة طميّة رمليّة",
    "clay loam": "طينيّة طميّة",
    "silty clay loam": "طينيّة طميّة غرينيّة",
    "sandy clay": "طينيّة رمليّة",
    "silty clay": "طينيّة غرينيّة",
    "clay": "طينيّة",
}


def usda_texture_class(clay: float, sand: float, silt: float) -> dict:
    """يُصنّف قوام التربة وفق مثلّث USDA. يُعيد {key, label_ar, clay, sand, silt}.

    يُطبِّع النِسَب إلى مجموع 100 إن انحرفت قليلاً (خطأ قياس). يرفع ValueError على
    مدخلات سالبة/غير رقميّة. القواعد حصريّة ومتتابعة (أوّل مطابقة تفوز) كترتيب USDA.
    """
    vals = [clay, sand, silt]
    if any(v is None for v in vals):
        raise ValueError("clay/sand/silt مطلوبة جميعاً")
    clay, sand, silt = (float(v) for v in vals)
    if clay < 0 or sand < 0 or silt < 0:
        raise ValueError("نِسَب القوام يجب أن تكون ≥ 0")
    total = clay + sand + silt
    if total <= 0:
        raise ValueError("مجموع نِسَب القوام يجب أن يكون > 0")
    # تطبيع إلى 100 (يسمح بانحراف قياس بسيط).
    clay, sand, silt = (v * 100.0 / total for v in (clay, sand, silt))

    # خوارزميّة USDA/NRCS القياسيّة (ترتيب حصريّ؛ أوّل مطابقة تفوز).
    s15 = silt + 1.5 * clay
    s2 = silt + 2.0 * clay
    if s15 < 15:
        key = "sand"
    elif s2 < 30:
        key = "loamy sand"
    elif (7 <= clay < 20 and sand > 52 and s2 >= 30) or (clay < 7 and silt < 50 and s2 >= 30):
        key = "sandy loam"
    elif 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        key = "loam"
    elif (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        key = "silt loam"
    elif silt >= 80 and clay < 12:
        key = "silt"
    elif 20 <= clay < 35 and silt < 28 and sand > 45:
        key = "sandy clay loam"
    elif 27 <= clay < 40 and 20 < sand <= 45:
        key = "clay loam"
    elif 27 <= clay < 40 and sand <= 20:
        key = "silty clay loam"
    elif clay >= 35 and sand > 45:
        key = "sandy clay"
    elif clay >= 40 and silt >= 40:
        key = "silty clay"
    elif clay >= 40 and sand <= 45 and silt < 40:
        key = "clay"
    else:
        key = "sandy loam"  # ملاذ أخير لأيّ ثغرة حدوديّة نادرة (لا يترك التصنيف فارغاً)

    return {
        "key": key,
        "label_ar": _TEXTURE_AR[key],
        "clay": round(clay, 1),
        "sand": round(sand, 1),
        "silt": round(silt, 1),
    }


# ── ملاءمة المحصول (قواعد شفّافة، سياق يمنيّ) ───────────────────────────────────
# لكلّ محصول: نطاق pH الأمثل + الحدّ الأقصى المقبول للملوحة (EC dS/m، عتبة تدهور
# الغلّة FAO) + أقوام مفضّلة. القيم إرشاديّة منشورة — تفسير لا تنبّؤ.
CROP_PROFILES: dict[str, dict] = {
    "wheat": {
        "label_ar": "قمح",
        "ph_opt": (6.0, 7.5),
        "ph_ok": (5.5, 8.5),
        "ec_max": 6.0,  # FAO: عتبة تدهور القمح ~6 dS/m
        "textures": {"loam", "clay loam", "silt loam", "silty clay loam"},
    },
    "sorghum": {
        "label_ar": "ذرة رفيعة",
        "ph_opt": (5.5, 7.5),
        "ph_ok": (5.0, 8.5),
        "ec_max": 8.0,  # متحمّل للملوحة والجفاف
        "textures": {"sandy loam", "loam", "clay loam"},
    },
    "tomato": {
        "label_ar": "طماطم",
        "ph_opt": (6.0, 6.8),
        "ph_ok": (5.5, 7.5),
        "ec_max": 2.5,  # حسّاس للملوحة
        "textures": {"loam", "sandy loam", "silt loam"},
    },
    "date_palm": {
        "label_ar": "نخيل التمر",
        "ph_opt": (7.0, 8.5),
        "ph_ok": (6.5, 9.0),
        "ec_max": 12.0,  # شديد التحمّل للملوحة (محصول يمنيّ رئيس)
        "textures": {"sandy loam", "loamy sand", "sand", "loam"},
    },
    "coffee": {
        "label_ar": "بُنّ",
        "ph_opt": (5.5, 6.5),
        "ph_ok": (5.0, 7.0),
        "ec_max": 2.0,  # مرتفعات يمنيّة، حسّاس للملوحة
        "textures": {"loam", "sandy loam", "silt loam"},
    },
}


def _range_score(value: float, opt: tuple[float, float], ok: tuple[float, float]) -> float:
    """1.0 داخل النطاق الأمثل؛ يتناقص خطّيّاً إلى 0 عند حدّ المقبول؛ 0 خارجه."""
    lo_opt, hi_opt = opt
    lo_ok, hi_ok = ok
    if lo_opt <= value <= hi_opt:
        return 1.0
    if value < lo_opt:
        if value <= lo_ok:
            return 0.0
        return (value - lo_ok) / (lo_opt - lo_ok)
    # value > hi_opt
    if value >= hi_ok:
        return 0.0
    return (hi_ok - value) / (hi_ok - hi_opt)


def _salinity_score(ec: float, ec_max: float) -> float:
    """1.0 حتى نصف العتبة؛ يتناقص خطّيّاً إلى 0 عند العتبة (تدهور الغلّة)."""
    if ec <= ec_max * 0.5:
        return 1.0
    if ec >= ec_max:
        return 0.0
    return (ec_max - ec) / (ec_max * 0.5)


def crop_suitability(
    *,
    crop: str,
    ph: float | None = None,
    ec: float | None = None,
    texture_key: str | None = None,
) -> dict:
    """درجة ملاءمة شفّافة [0,1] + تصنيف + العوامل المُقيِّدة.

    الدرجة = أدنى درجة عامل متوفّر (Liebig: العامل المُقيِّد يحكم) — صدق: لا نُخفي
    قيداً بالمتوسّط. العوامل الغائبة تُتخطّى (لا تُخترَع). يرفع ValueError لمحصول مجهول.
    """
    profile = CROP_PROFILES.get(crop)
    if profile is None:
        raise ValueError(f"محصول غير معروف: {crop} (المتاح: {', '.join(CROP_PROFILES)})")

    factors: dict[str, float] = {}
    if ph is not None:
        factors["ph"] = round(_range_score(float(ph), profile["ph_opt"], profile["ph_ok"]), 3)
    if ec is not None:
        factors["salinity"] = round(_salinity_score(float(ec), profile["ec_max"]), 3)
    if texture_key is not None:
        factors["texture"] = 1.0 if texture_key in profile["textures"] else 0.4

    if not factors:
        return {
            "crop": crop,
            "label_ar": profile["label_ar"],
            "score": None,
            "rating_ar": "بيانات غير كافية",
            "factors": {},
            "limiting_ar": "لا توجد بيانات تربة (pH/EC/قوام) للتقييم",
        }

    score = min(factors.values())
    limiting = min(factors, key=lambda k: factors[k])
    _lim_ar = {"ph": "الحموضة (pH)", "salinity": "الملوحة (EC)", "texture": "القوام"}
    if score >= 0.8:
        rating = "ممتاز"
    elif score >= 0.6:
        rating = "جيّد"
    elif score >= 0.4:
        rating = "متوسّط"
    elif score > 0:
        rating = "ضعيف"
    else:
        rating = "غير ملائم"

    return {
        "crop": crop,
        "label_ar": profile["label_ar"],
        "score": round(score, 3),
        "rating_ar": rating,
        "factors": factors,
        "limiting_ar": _lim_ar[limiting] if score < 1.0 else "لا قيد بارز",
    }


def rank_crops(
    *, ph: float | None = None, ec: float | None = None, texture_key: str | None = None
) -> list[dict]:
    """يُرتّب كلّ المحاصيل تنازليّاً بالملاءمة لظروف تربة معطاة (المُقيَّم أوّلاً)."""
    out = [crop_suitability(crop=c, ph=ph, ec=ec, texture_key=texture_key) for c in CROP_PROFILES]
    return sorted(out, key=lambda r: (r["score"] is None, -(r["score"] or 0.0)))
