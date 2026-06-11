"""
band_math.py — صيغ المؤشّرات الطيفيّة كدوالّ نقيّة قابلة للاختبار (offline).

تُحقن numpy من المُستدعي (نفس نمط soil_indices.py) كي تبقى الوحدة بلا تبعيّة
ثقيلة عند الاستيراد. الدوالّ تعمل على مصفوفات numpy (NaN=خارج الحقل) أو على
أعداد عاديّة (للاختبار البسيط)، وتُرجِع نفس شكل المدخل.

تسدّ امتداد المؤشّرات (Sprint 5b): NDRE/MSAVI/EVI/moisture على مسار
indicator-grid + tiles، إضافةً للمؤشّرات السابقة.

ملاحظة علميّة: الصيغ من أدبيّات الاستشعار؛ التفسير الزراعي يحتاج معايرة
ميدانيّة محلّيّة (لا قرار ريّ/تسميد بقيمة قمر وحدها).
"""

from __future__ import annotations


def _eps(arr, _np):
    """يتجنّب القسمة على صفر بإبدال المقام الصفري بـepsilon صغير."""
    return _np.where(arr == 0, 1e-10, arr)


def ndvi(red, nir, _np):
    """NDVI = (NIR - RED) / (NIR + RED) — الغطاء النباتي."""
    return (nir - red) / _eps(nir + red, _np)


def ndre(nir, rededge, _np):
    """NDRE = (NIR - REDEDGE) / (NIR + REDEDGE) — النيتروجين/الكلوروفيل."""
    return (nir - rededge) / _eps(nir + rededge, _np)


def evi(blue, red, nir, _np):
    """EVI = 2.5·(NIR-RED) / (NIR + 6·RED - 7.5·BLUE + 1) — غطاء محسّن."""
    return 2.5 * (nir - red) / _eps(nir + 6.0 * red - 7.5 * blue + 1.0, _np)


def msavi(red, nir, _np):
    """MSAVI2 — تصحيح تربة ذاتي (L ديناميكي) أمتن من SAVI للكثافة المنخفضة.

    MSAVI = (2·NIR + 1 - sqrt((2·NIR+1)² - 8·(NIR-RED))) / 2

    الجذر يُقصَّ عند صفر (الجذع تحت الجذر قد يصبح سالباً لقيم شاذّة) لتفادي NaN
    غير مقصود.
    """
    term = 2.0 * nir + 1.0
    radicand = term * term - 8.0 * (nir - red)
    radicand = _np.where(radicand < 0, 0.0, radicand)
    return (term - _np.sqrt(radicand)) / 2.0


def moisture(nir, swir1, _np):
    """مؤشّر الرطوبة (NDMI-style) = (NIR - SWIR1) / (NIR + SWIR1).

    اسم الواجهة "moisture"؛ رياضيّاً = NDMI (رطوبة محتوى النبات/التربة). قيمة
    عالية = رطوبة أعلى (عكس MSI الذي تعلو قيمته مع الإجهاد).
    """
    return (nir - swir1) / _eps(nir + swir1, _np)


# توجيه اسم المؤشّر → (الدالّة، أسماء النطاقات المطلوبة) لمسار band-math الجديد.
# يُستخدم في _process_pixels لتجنّب تكرار الفروع وتسهيل الاختبار.
NEW_INDEX_BANDS = {
    "ndre": ("nir", "rededge"),
    "evi": ("blue", "red", "nir"),
    "msavi": ("red", "nir"),
    "moisture": ("nir", "swir1"),
}


def compute(index: str, bands: dict, _np):
    """يحسب مؤشّراً جديداً من قاموس النطاقات {اسم: مصفوفة}. يرمي ValueError
    عند غياب نطاق مطلوب (صدق: لا اختراع نطاق).

    bands: {"red":..,"nir":..,"blue":..,"rededge":..,"swir1":..}
    """
    if index == "ndre":
        _require(bands, ("nir", "rededge"), index)
        return ndre(bands["nir"], bands["rededge"], _np)
    if index == "evi":
        _require(bands, ("blue", "red", "nir"), index)
        return evi(bands["blue"], bands["red"], bands["nir"], _np)
    if index == "msavi":
        _require(bands, ("red", "nir"), index)
        return msavi(bands["red"], bands["nir"], _np)
    if index == "moisture":
        _require(bands, ("nir", "swir1"), index)
        return moisture(bands["nir"], bands["swir1"], _np)
    raise ValueError(f"مؤشّر غير مدعوم في band_math: {index}")


def _require(bands: dict, needed, index: str) -> None:
    missing = [b for b in needed if bands.get(b) is None]
    if missing:
        raise ValueError(f"{index} يتطلّب نطاقات: {', '.join(missing)}")
