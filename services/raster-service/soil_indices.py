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

# الصيغ (توثيق + مرجع للتنفيذ) — تُطابق _INDICATOR_FORMULAS في main.py
SOIL_INDEX_FORMULAS = {
    "bsi": "((SWIR2 + RED) - (NIR + BLUE)) / ((SWIR2 + RED) + (NIR + BLUE))",
    "bi": "sqrt((RED^2 + GREEN^2) / 2)",
    "bi2": "sqrt((RED^2 + GREEN^2 + NIR^2) / 3)",
    "ndti": "(SWIR1 - SWIR2) / (SWIR1 + SWIR2)",
    "dbsi": "((SWIR1 - GREEN) / (SWIR1 + GREEN)) - NDVI",
    "ndsi": "(RED - NIR) / (RED + NIR)",
    "satvi": "((SWIR1 - RED) / (SWIR1 + RED + L)) * (1 + L) - (SWIR2 / 2)",
}

# عتبات تصنيف تقديريّة (تحتاج معايرة ميدانيّة)
SOIL_INDEX_THRESHOLDS = {
    "bsi": {"bare_soil": 0.1},  # > 0.1 تربة عارية واضحة
    "ndti": {"untilled": 0.1, "tilled": 0.0},
    "ndsi": {"saline": 0.1},  # > 0.1 ملوحة عالية
    "nbr2": {"reliable_soil": 0.075},  # < 0.075 بكسل تربة موثوق
}


def _eps(arr, _np):
    """يتجنّب القسمة على صفر بإضافة epsilon صغير للمقام."""
    return _np.where(arr == 0, 1e-10, arr)


# ─── المؤشّرات السبعة ────────────────────────────────────────────
def compute_bsi(blue, red, nir, swir2, _np):
    """Bare Soil Index — فصل التربة العارية عن النبات والمباني."""
    num = (swir2 + red) - (nir + blue)
    den = _eps((swir2 + red) + (nir + blue), _np)
    return num / den


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
    """Normalized Difference Tillage Index — الحراثة/بقايا المحاصيل."""
    return (swir1 - swir2) / _eps(swir1 + swir2, _np)


def compute_dbsi(green, swir1, ndvi, _np):
    """Dry Bare Soil Index — التربة الجافّة العارية (مهمّ لليمن الجافّ)."""
    return ((swir1 - green) / _eps(swir1 + green, _np)) - ndvi


def compute_ndsi(red, nir, _np):
    """Normalized Difference Salinity Index — الملوحة (حرج للسياق اليمني)."""
    return (red - nir) / _eps(red + nir, _np)


def compute_satvi(red, swir1, swir2, _np, L: float = 0.5):
    """Soil-Adjusted Total Vegetation Index — يفصل تأثير التربة."""
    return ((swir1 - red) / _eps(swir1 + red + L, _np)) * (1 + L) - (swir2 / 2.0)


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
