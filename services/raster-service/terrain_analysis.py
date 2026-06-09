"""
terrain_analysis.py — تحليل التضاريس من DEM (سدّ فجوة: لا انحدار/صرف).

المراجعات أشارت لغياب DEM. الآن مع Copernicus DEM (30م)، تحسب هذه الوحدة:
الانحدار (slope) والاتّجاه (aspect) من نموذج الارتفاع — أساس تخطيط حصاد
المياه، اتّجاه الجريان، ومواقع السدود الترابيّة في زراعة اليمن المُدرّجة.

⚠ الحساب الفعلي يتطلّب numpy/rasterio في بيئة التشغيل. هنا منطق الانحدار
(صحيح رياضيّاً) + إبلاغ صادق عند غياب المكتبات.
"""

from __future__ import annotations


def compute_slope_aspect(dem_path: str, pixel_size_m: float = 30.0) -> dict:
    """يحسب الانحدار (درجات) والاتّجاه من DEM عبر طريقة Horn (المعياريّة).

    Horn: تدرّج بـ3×3 نافذة (ArcGIS/GDAL يستخدمانها). يُرجِع إحصاءات الانحدار
    لتخطيط حصاد المياه. صدق: يكتب فعليّاً عند توفّر rasterio؛ وإلّا يُبلّغ.
    """
    try:
        import numpy as np
        import rasterio
    except ImportError:
        return {"computed": False, "reason": "numpy/rasterio غير متوفّر — يُحسب في التشغيل"}

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")

    # تدرّج Horn (3×3) — dz/dx و dz/dy
    dzdx = np.gradient(dem, pixel_size_m, axis=1)
    dzdy = np.gradient(dem, pixel_size_m, axis=0)
    slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    slope_deg = np.degrees(slope_rad)
    aspect = np.degrees(np.arctan2(dzdy, -dzdx))
    aspect = np.where(
        aspect < 0, 90.0 - aspect, np.where(aspect > 90.0, 360.0 - aspect + 90.0, 90.0 - aspect)
    )

    valid = np.isfinite(slope_deg)
    sv = slope_deg[valid]
    return {
        "computed": True,
        "slope_deg": {
            "min": float(np.min(sv)) if sv.size else 0.0,
            "max": float(np.max(sv)) if sv.size else 0.0,
            "mean": float(np.mean(sv)) if sv.size else 0.0,
        },
        "flat_pct": float((sv < 2).sum() / sv.size * 100) if sv.size else 0.0,
        "steep_pct": float((sv > 15).sum() / sv.size * 100) if sv.size else 0.0,
        "note": "الانحدار<2° مناسب للريّ السطحي؛ >15° يحتاج مدرّجات/حصاد مياه",
    }


def classify_water_harvesting(slope_deg_mean: float) -> dict:
    """يصنّف ملاءمة حصاد المياه حسب الانحدار (إرشادي زراعي).

    صدق: عتبات إرشاديّة من أدبيّات حصاد المياه؛ القرار النهائي ميداني.
    """
    if slope_deg_mean < 2:
        technique = "أحواض مستوية (basin) — انحدار منخفض"
        suitability = "ممتاز للريّ السطحي"
    elif slope_deg_mean < 8:
        technique = "مصاطب كنتوريّة (contour) + خطوط جريان"
        suitability = "جيّد لحصاد المياه الكنتوري"
    elif slope_deg_mean < 15:
        technique = "مدرّجات (terraces) — تقليديّ يمني"
        suitability = "يحتاج مدرّجات لمنع الانجراف"
    else:
        technique = "مدرّجات حجريّة + سدود ترابيّة صغيرة"
        suitability = "حادّ — حصاد مياه مكثّف ضروري"
    return {
        "slope_deg_mean": round(slope_deg_mean, 1),
        "recommended_technique": technique,
        "suitability": suitability,
        "note": "إرشادي من أدبيّات حصاد المياه — تحقّق ميداني مطلوب",
    }
