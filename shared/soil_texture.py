"""Particle-size texture classification used by the soil, raster and lab services."""

import math

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
    if not all(math.isfinite(v) and v >= 0 for v in (clay, sand, silt)):
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


# Tashkeel (U+064B..U+0652), superscript alef (U+0670) and tatweel (U+0640) do not change
# the class, so "طمية" and "طميّة" are the same label.
_AR_MARKS = dict.fromkeys([*range(0x064B, 0x0653), 0x0670, 0x0640])


def _fold(text: str) -> str:
    text = text.translate(_AR_MARKS).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


_LABEL_TO_KEY = {_fold(k): k for k in _TEXTURE_AR} | {_fold(v): k for k, v in _TEXTURE_AR.items()}


def normalize_texture_label(label: str | None) -> str | None:
    """The USDA class key a written label names, or ``None`` when it names none.

    Accepts the English key in any case with spaces, underscores or hyphens
    (``Sandy_Loam``) and the Arabic label with or without diacritics.
    """
    if not label:
        return None
    return _LABEL_TO_KEY.get(_fold(label))
