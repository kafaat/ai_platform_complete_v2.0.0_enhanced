"""
services/raster-service/soil_indices.py — مؤشّرات استشعار التربة (Sentinel-2)

المرجع: docs/history/SOIL_INDICES_RESEARCH.md (بحث الوكيل المجالي).

الفجوة التي يسدّها: مؤشّرات سهول الـ13 الحاليّة (NDVI/EVI/SAVI...) كلّها
**نباتيّة** — تقيس صحّة الـcanopy لا التربة. هذه الوحدة تضيف 7 مؤشّرات
**للتربة العارية** قابلة للحساب مباشرةً من Sentinel-2 L2A (B2,B3,B4,B8,B11,B12).

المؤشّرات السبعة (القابلة للتطبيق فوراً — 4 أخرى تحتاج hyperspectral/ML مؤجّلة):
  BSI   — Bare Soil Index (فصل التربة العارية)
  BI    — Brightness Index (السطوع → مادّة عضويّة)
  BI2   — Brightness Index 2 (بإضافة NIR)
  NDTI  — Normalized Difference Tillage Index (الحراثة/البقايا)
  DBSI  — Dry Bare Soil Index (مهمّ للسياق اليمني الجافّ)
  NDSI  — Normalized Difference Salinity Index (الملوحة — حرج لليمن)
  SATVI — Soil-Adjusted Total Vegetation Index

ملاحظة بيئة: numpy يُحقن في بيئة التشغيل (مثل rasterio في main.py). الصيغ
موثّقة هنا وتُنفَّذ عند توفّر numpy؛ بنية صحيحة وملاحظة صادقة عند غيابه.

ملاحظة علميّة: الصيغ من أدبيّات الاستشعار، والعتبات تقديريّة تحتاج معايرة
ميدانيّة محلّيّة (عيّنات تربة بإحداثيّات) قبل اعتمادها للقرار الزراعي.
"""

from __future__ import annotations

# Validity (G4): Sentinel-2 L2A baseline ≥04.00 applies BOA_ADD_OFFSET −0.1, so
# dark/water pixels carry negative reflectance; with mixed signs the old
# ``_eps`` (1e-10) published ±6e7. Normalized differences now go through the
# shared band_math kernel (negative/nonfinite band or result outside [-1, 1]
# ⇒ NaN, excluded from stats). سالب الانعكاس ⇒ NaN لا قيمة مختلَقة.
from band_math import nonnegative_finite, normalized_difference

# الصيغ (توثيق + مرجع للتنفيذ) — تُطابق _INDICATOR_FORMULAS في main.py
SOIL_INDEX_FORMULAS = {
    "bsi": "((SWIR2 + RED) - (NIR + BLUE)) / ((SWIR2 + RED) + (NIR + BLUE))",
    "bi": "sqrt((RED^2 + GREEN^2) / 2)",
    "bi2": "sqrt((RED^2 + GREEN^2 + NIR^2) / 3)",
    "ndti": "(SWIR1 - SWIR2) / (SWIR1 + SWIR2)",
    "dbsi": "((SWIR1 - GREEN) / (SWIR1 + GREEN)) - NDVI",
    "ndsi": "(SWIR1 - SWIR2) / (SWIR1 + SWIR2)",
    "satvi": "((SWIR1 - RED) / (SWIR1 + RED + L)) * (1 + L) - (SWIR2 / 2)",
}

# عتبات تصنيف تقديريّة (تحتاج معايرة ميدانيّة)
SOIL_INDEX_THRESHOLDS = {
    "bsi": {"bare_soil": 0.1},  # > 0.1 تربة عارية واضحة
    "ndti": {"untilled": 0.1, "tilled": 0.0},
    "ndsi": {"saline": 0.1},  # > 0.1 ملوحة عالية
    "nbr2": {"reliable_soil": 0.075},  # < 0.075 بكسل تربة موثوق
}


# ─── المؤشّرات السبعة ────────────────────────────────────────────
def compute_bsi(blue, red, nir, swir2, _np):
    """Bare Soil Index — فصل التربة العارية عن النبات والمباني.

    ND of (SWIR2+RED) and (NIR+BLUE) ⇒ range [-1, 1] (Rikimaru et al. 2002).
    Each band is checked on its own: a negative band can hide inside a
    non-negative sum.
    """
    valid = nonnegative_finite((blue, red, nir, swir2), _np)
    swir2, red, nir, blue = (_np.asarray(x, dtype="float64") for x in (swir2, red, nir, blue))
    return _np.where(valid, normalized_difference(swir2 + red, nir + blue, _np), _np.nan)


def compute_bi(red, green, _np):
    """Brightness Index — السطوع (مرتبط بالمادّة العضويّة)."""
    return _np.sqrt((red.astype("float64") ** 2 + green.astype("float64") ** 2) / 2.0)


def compute_bi2(red, green, nir, _np):
    """Brightness Index 2 — السطوع بإضافة NIR."""
    return _np.sqrt(
        (red.astype("float64") ** 2 + green.astype("float64") ** 2 + nir.astype("float64") ** 2)
        / 3.0
    )


def compute_ndti(swir1, swir2, _np):
    """Normalized Difference Tillage Index — الحراثة/بقايا المحاصيل.

    Range [-1, 1] (Van Deventer et al. 1997) via the shared ND kernel.
    """
    return normalized_difference(swir1, swir2, _np)


def compute_dbsi(green, swir1, ndvi, _np):
    """Dry Bare Soil Index — التربة الجافّة العارية (مهمّ لليمن الجافّ).

    ND(SWIR1, GREEN) − NDVI ⇒ range [-2, 2] (Rasul et al. 2018); an invalid
    ND or NDVI pixel stays NaN.
    """
    return normalized_difference(swir1, green, _np) - _np.asarray(ndvi, dtype="float64")


def compute_ndsi(swir1, swir2, _np):
    """Normalized Difference Salinity Index — الملوحة (SWIR1/SWIR2، متّسق مع CDSE).

    Range [-1, 1] via the shared ND kernel.
    """
    return normalized_difference(swir1, swir2, _np)


def compute_satvi(red, swir1, swir2, _np, L: float = 0.5):
    """Soil-Adjusted Total Vegetation Index — يفصل تأثير التربة (Marsett et al. 2006).

    The denominator is ≥ L > 0 for valid bands, so only negative/nonfinite
    bands are masked (L2A offset), matching the other indices.
    """
    valid = nonnegative_finite((red, swir1, swir2), _np)
    red, swir1, swir2 = (_np.asarray(x, dtype="float64") for x in (red, swir1, swir2))
    with _np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        out = ((swir1 - red) / (swir1 + red + L)) * (1 + L) - (swir2 / 2.0)
    return _np.where(valid & _np.isfinite(out), out, _np.nan)


# ─── تصنيف نسيج التربة التلقائي (تقديري — يحتاج معايرة) ──────────
def classify_soil_texture(
    bsi_mean: float, bi_mean: float, ndsi_mean: float, satvi_mean: float
) -> dict:
    """تصنيف أوّلي لنسيج التربة من متوسّطات المؤشّرات.

    ⚠️ تقديري: العتبات من الأدبيّات لا من معايرة ميدانيّة يمنيّة. النتيجة
    اقتراح يحتاج تأكيداً بعيّنة تربة، لا تصنيفاً نهائيّاً.
    """
    alerts = []
    if ndsi_mean > SOIL_INDEX_THRESHOLDS["ndsi"]["saline"]:
        alerts.append("saline_soil_alert")

    if bi_mean > 0.25 and bsi_mean > 0.2:
        texture = "sandy"  # رمليّة (سطوع عالٍ + تربة عارية)
    elif bi_mean < 0.15 and satvi_mean > 0.3:
        texture = "volcanic"  # بركانيّة (شائعة في صعدة/ذمار)
    else:
        texture = "mixed_unclassified"

    return {
        "texture_estimate": texture,
        "alerts": alerts,
        "is_estimate": True,
        "note": "تقديري — يحتاج معايرة بعيّنة تربة ميدانيّة قبل الاعتماد",
        "inputs": {"bsi": bsi_mean, "bi": bi_mean, "ndsi": ndsi_mean, "satvi": satvi_mean},
    }


# المؤشّرات المؤجّلة (تحتاج trigger صريحاً) — موثّقة للشفافيّة
DEFERRED_INDICES = {
    "hbsi": "يحتاج hyperspectral (AVIRIS)، لا Sentinel فقط",
    "endbsi": "يحتاج hyperspectral",
    "mbi": "Modified Bare Soil — يحتاج معايرة إضافيّة",
    "kmeans_clustering": "يحتاج scikit-learn + مناطق تربة متعدّدة لكلّ حقل",
    "spectral_to_texture_model": "يحتاج 100+ عيّنة تربة بإحداثيّات (تدريب)",
}
