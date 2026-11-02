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


def normalized_difference(a, b, _np):
    """(A − B) / (A + B) — the shared normalized-difference kernel (NDVI/NDRE/NDWI…).

    Promote before arithmetic (no integer wrap / float32 overflow). Invalid
    pixels become NaN (NoData) and so leave every downstream statistic:
      * nonfinite input or intermediate;
      * **negative input reflectance** — Sentinel-2 L2A baseline ≥04.00 applies
        BOA_ADD_OFFSET −1000 (−0.1), so dark/water pixels go below zero; with
        mixed signs A + B → 0 and the epsilon guard used to emit ±6e7 (G4);
      * result outside [-1, 1] (impossible for valid non-negative inputs).
    For non-negative inputs the denominator is 0 only when both bands are 0;
    that pixel keeps the legacy epsilon contract (→ 0, numerator is also 0).
    سالب الانعكاس أو ناتج خارج [-1،1] ⇒ NaN (لا قيمة مختلَقة تُفسد المتوسّط).
    """
    a = _np.asarray(a, dtype="float64")
    b = _np.asarray(b, dtype="float64")
    with _np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        numerator = a - b
        denominator = a + b
        result = numerator / _eps(denominator, _np)
        valid = (
            _np.isfinite(a)
            & _np.isfinite(b)
            & (a >= 0)
            & (b >= 0)
            & _np.isfinite(numerator)
            & _np.isfinite(denominator)
            & _np.isfinite(result)
            & (_np.abs(result) <= 1.0)
        )
    return _np.where(valid, result, _np.nan)


# Smallest denominator (reflectance units) that still carries signal: the
# Sentinel-2 L2A surface-reflectance uncertainty spec is 0.005 + 0.05·ρ (CEOS
# ACIX, Doxani et al. 2018, Remote Sens. 10:352). Dividing by less is dividing
# by noise — that is how the 1e-10 epsilon published ±1e7..1e9 (G4).
# مقام أصغر من عدم اليقين الإشعاعيّ = قسمة على ضجيج ⇒ NaN.
MIN_REFLECTANCE_DENOMINATOR = 0.005


def nonnegative_finite(bands, _np):
    """Per-pixel mask: every input band is finite and ≥ 0 (L2A offset −0.1 ⇒ <0)."""
    valid = True
    for band in bands:
        band = _np.asarray(band, dtype="float64")
        valid = valid & _np.isfinite(band) & (band >= 0)
    return valid


def guarded_quotient(
    bands,
    terms,
    _np,
    *,
    valid_range,
    min_denominator=MIN_REFLECTANCE_DENOMINATOR,
):
    """Shared validity kernel for quotient indices (EVI/SAVI/VARI/SIPI/ARVI/CI/MSI).

    ``terms(*bands_f64) -> (numerator, denominator)``. A pixel is NaN (NoData,
    so it leaves every statistic) unless: every band is finite and ≥ 0; the
    denominator is finite and ≥ ``min_denominator`` (a negative or near-zero
    denominator has no physical meaning for these indices); and the result is
    finite and inside ``valid_range`` = (lo, hi), where None means unbounded.
    نفس عقد normalized_difference: لا قيمة مختلَقة تُفسد المتوسّط المنشور.
    """
    missing = [i for i, band in enumerate(bands) if band is None]
    if missing:
        raise ValueError(f"guarded_quotient: missing band(s) at positions {missing}")
    arrs = [_np.asarray(band, dtype="float64") for band in bands]
    lo, hi = valid_range
    with _np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        numerator, denominator = terms(*arrs)
        safe_den = _np.where(denominator >= min_denominator, denominator, _np.nan)
        result = numerator / safe_den
        valid = (
            nonnegative_finite(arrs, _np)
            & _np.isfinite(numerator)
            & _np.isfinite(denominator)
            & (denominator >= min_denominator)
            & _np.isfinite(result)
        )
        if lo is not None:
            valid = valid & (result >= lo)
        if hi is not None:
            valid = valid & (result <= hi)
    return _np.where(valid, result, _np.nan)


def ndvi(red, nir, _np):
    """NDVI = (NIR - RED) / (NIR + RED) — الغطاء النباتي (normalized_difference)."""
    return normalized_difference(nir, red, _np)


def ndre(nir, rededge, _np):
    """NDRE = (NIR - REDEDGE) / (NIR + REDEDGE) — النيتروجين/الكلوروفيل."""
    return normalized_difference(nir, rededge, _np)


def evi(blue, red, nir, _np):
    """EVI = 2.5·(NIR-RED) / (NIR + 6·RED - 7.5·BLUE + 1) — غطاء محسّن.

    Valid range [-1, 1] (Huete et al. 2002, RSE 83:195; MOD13 publishes
    [-0.2, 1]). Bright-blue pixels (cloud edge, haze) drive the denominator
    through 0 and the old epsilon emitted ±1e9 (G4).
    """
    return guarded_quotient(
        (blue, red, nir),
        lambda b, r, n: (2.5 * (n - r), n + 6.0 * r - 7.5 * b + 1.0),
        _np,
        valid_range=(-1.0, 1.0),
    )


def savi(red, nir, _np, L: float = 0.5):
    """SAVI = (1+L)·(NIR-RED) / (NIR + RED + L), L = 0.5 (Huete 1988, RSE 25:295).

    Valid range [-(1+L), 1+L] = [-1.5, 1.5]: the bound for any non-negative
    reflectances. The denominator is ≥ L for valid inputs, so only negative
    (L2A offset) or nonfinite bands are masked in practice.
    """
    return guarded_quotient(
        (red, nir),
        lambda r, n: ((1.0 + L) * (n - r), n + r + L),
        _np,
        valid_range=(-(1.0 + L), 1.0 + L),
    )


def vari(blue, red, green, _np):
    """VARI = (GREEN-RED) / (GREEN + RED - BLUE) (Gitelson et al. 2002, RSE 80:76).

    Mathematically unbounded: the denominator crosses 0 on bluish/grey
    surfaces (water, haze). Operational range [-1, 1]; a denominator below
    MIN_REFLECTANCE_DENOMINATOR or a result outside [-1, 1] ⇒ NaN.
    """
    return guarded_quotient(
        (blue, red, green),
        lambda b, r, g: (g - r, g + r - b),
        _np,
        valid_range=(-1.0, 1.0),
    )


def gli(blue, red, green, _np):
    """GLI = (2·GREEN-RED-BLUE) / (2·GREEN+RED+BLUE) (Louhaichi et al. 2001).

    A normalized difference of 2·GREEN and RED+BLUE: range [-1, 1].
    """
    return guarded_quotient(
        (blue, red, green),
        lambda b, r, g: (2.0 * g - r - b, 2.0 * g + r + b),
        _np,
        valid_range=(-1.0, 1.0),
    )


def sipi(blue, red, nir, _np):
    """SIPI = (NIR-BLUE) / (NIR-RED) (Peñuelas et al. 1995, Photosynthetica 31:221).

    Valid range [0, 2] (green vegetation ≈ 0.8–1.8). NIR ≤ RED (bare soil,
    water) makes the denominator ≤ 0 — SIPI is undefined there ⇒ NaN.
    """
    return guarded_quotient(
        (blue, red, nir),
        lambda b, r, n: (n - b, n - r),
        _np,
        valid_range=(0.0, 2.0),
    )


def arvi(blue, red, nir, _np, gamma: float = 1.0):
    """ARVI = (NIR-RB) / (NIR+RB), RB = RED - γ·(BLUE-RED), γ = 1
    (Kaufman & Tanré 1992, IEEE TGRS 30:261).

    Valid range [-1, 1]. RB may legitimately be < 0 (aerosol-bright blue), so
    the shared normalized_difference (which rejects a negative operand) is not
    used; instead each band must be ≥ 0 and the result must stay in [-1, 1].
    """
    return guarded_quotient(
        (blue, red, nir),
        lambda b, r, n: (
            n - (r - gamma * (b - r)),
            n + (r - gamma * (b - r)),
        ),
        _np,
        valid_range=(-1.0, 1.0),
    )


def chlorophyll_index(nir, reference, _np):
    """CI = NIR/REF - 1 = (NIR-REF)/REF — RECI (REF=B05) / GCI (REF=B03)
    (Gitelson et al. 2003, Geophys. Res. Lett. 30:1248).

    Reflectance ratio ≥ 0 ⇒ valid range [-1, +inf); unbounded above, so the
    denominator floor (MIN_REFLECTANCE_DENOMINATOR) is what prevents ±5e8.
    """
    return guarded_quotient(
        (nir, reference), lambda n, ref: (n - ref, ref), _np, valid_range=(-1.0, None)
    )


def ccci(red, nir, rededge, _np):
    """CCCI ≈ NDRE / NDVI (simplified; Fitzgerald et al. 2006 define CCCI on [0, 1]).

    For vegetation RE ≥ RED, so 0 ≤ NDRE ≤ NDVI ⇒ [0, 1]. NDVI ≤ 0 (water,
    bare soil) leaves canopy chlorophyll undefined ⇒ NaN instead of NDRE·1e10.
    The NDVI floor reuses MIN_REFLECTANCE_DENOMINATOR as a dimensionless floor.
    """
    ndre_v = ndre(nir, rededge, _np)
    ndvi_v = ndvi(red, nir, _np)
    return guarded_quotient(
        (red, nir, rededge),
        lambda r, n, re: (ndre_v, ndvi_v),
        _np,
        valid_range=(0.0, 1.0),
    )


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
    return normalized_difference(nir, swir1, _np)


def msi(nir, swir1, _np):
    """MSI (Moisture Stress Index) = SWIR1 / NIR — الإجهاد المائيّ.

    قيمة عالية = إجهاد مائيّ أكبر (عكس moisture/NDMI). يُستهلَك في تأكيد الإجهاد
    الطيفيّ (canonical_water_stress عبر spectral_stress_bridge).

    Ratio of reflectances: valid range [0, +inf) (Hunt & Rock 1989). NIR below
    MIN_REFLECTANCE_DENOMINATOR (water/shadow) ⇒ NaN, not SWIR1·1e10 (G4).
    """
    return guarded_quotient((nir, swir1), lambda n, s1: (s1, n), _np, valid_range=(0.0, None))


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
