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


def to_reflectance(arr, scale, offset, _np):
    """يحوّل قيم النطاق الخام إلى انعكاس [0,1] بتطبيق scale/offset المُعلَن (نقيّ).

    **لماذا**: صيغ EVI/SAVI/MSAVI تحوي ثوابت جمعيّة (‎+1‎، ‎+0.5‎، ‎6·RED−7.5·BLUE‎)
    مُعايَرة لانعكاس [0,1]. مصادر مثل Sentinel-2 L2A تخزّن الانعكاس كأعداد صحيحة
    (DN = انعكاس × 10000، وقد يضاف إزاحة baseline). تمرير DN الخام لهذه المؤشّرات
    يشوّهها بصمت. هذه الدالّة تُطبّق التحويل القانونيّ ‎reflectance = DN·scale + offset‎.

    هويّة آمنة: scale=None/1.0 وoffset=None/0.0 ⇒ تُعيد المصفوفة كما هي (لا انحدار
    للمصادر التي لا تُعلن مقياساً). المؤشّرات النسبيّة (NDVI…) غير متأثّرة بالمقياس،
    لكنّ الإزاحة (offset) تؤثّر فيها أيضاً — فتطبيقها يصحّحها كذلك.
    """
    s = 1.0 if scale is None else float(scale)
    o = 0.0 if offset is None else float(offset)
    if s == 1.0 and o == 0.0:
        return arr
    return arr * s + o


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


def msi(nir, swir1, _np):
    """MSI (Moisture Stress Index) = SWIR1 / NIR — الإجهاد المائيّ.

    قيمة عالية = إجهاد مائيّ أكبر (عكس moisture/NDMI). يُستهلَك في تأكيد الإجهاد
    الطيفيّ (canonical_water_stress عبر spectral_stress_bridge). المقام (NIR) يُحمى
    من الصفر عبر _eps (اتّساقاً مع سائر الصيَغ) — نفس سلوك الفرع السطريّ السابق.
    """
    return swir1 / _eps(nir, _np)


# توجيه اسم المؤشّر → (الدالّة، أسماء النطاقات المطلوبة) لمسار band-math الجديد.
# يُستخدم في _process_pixels لتجنّب تكرار الفروع وتسهيل الاختبار.
NEW_INDEX_BANDS = {
    "ndre": ("nir", "rededge"),
    "evi": ("blue", "red", "nir"),
    "msavi": ("red", "nir"),
    "moisture": ("nir", "swir1"),
    "msi": ("nir", "swir1"),
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
    if index == "msi":
        _require(bands, ("nir", "swir1"), index)
        return msi(bands["nir"], bands["swir1"], _np)
    raise ValueError(f"مؤشّر غير مدعوم في band_math: {index}")


def _require(bands: dict, needed, index: str) -> None:
    missing = [b for b in needed if bands.get(b) is None]
    if missing:
        raise ValueError(f"{index} يتطلّب نطاقات: {', '.join(missing)}")
