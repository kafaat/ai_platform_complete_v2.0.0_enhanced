"""
cog_writer.py — كتابة Cloud-Optimized GeoTIFF محسّنة (تحسين تخزين القلب).

الممارسة العالميّة لـCOG جيّد: مبلّط داخليّاً + أهرامات (overviews) داخل
الملفّ + ضغط. هذا يقلّل الحجم بشدّة ويسرّع القراءة الجزئيّة (windowed) التي
يعتمد عليها TiTiler/MapLibre. بلا تحسين، COG "يفتح لكن يتصرّف كقرص بطيء".

إعدادات مختارة وفق توصيات COG:
  - ضغط DEFLATE (بلا فقد، جيّد للمؤشّرات float) أو ZSTD إن توفّر
  - PREDICTOR=2/3 (يحسّن الضغط للبيانات المتدرّجة)
  - بلاطات داخليّة 512×512
  - أهرامات (overviews) داخل الملفّ (2,4,8,16) بإعادة عيّنة average

⚠ يتطلّب rasterio في بيئة التشغيل. عند غيابه، يُبلّغ بصدق.
"""

from __future__ import annotations

import os

# إعدادات COG محسّنة (وفق أفضل الممارسات)
COG_PROFILE = {
    "driver": "GTiff",
    "dtype": "float32",
    "compress": "DEFLATE",  # بلا فقد — مهمّ للمؤشّرات (NDVI دقيق)
    "predictor": 3,  # 3 للعائم (floating point) — يحسّن الضغط
    "tiled": True,
    "blockxsize": 512,
    "blockysize": 512,
    "BIGTIFF": "IF_SAFER",
}

OVERVIEW_LEVELS = [2, 4, 8, 16]


DEFAULT_NODATA = -9999.0


def write_cog(
    array,
    output_path: str,
    transform,
    crs: str = "EPSG:4326",
    nodata: float = DEFAULT_NODATA,
) -> dict:
    """يكتب مصفوفة مؤشّر كـCOG محسّن (ضغط + بلاطات + أهرامات داخليّة).

    يُرجِع {written, path, size_bytes, compression, overviews}. صدق: يكتب
    فعليّاً عند توفّر rasterio؛ وإلّا يُبلّغ بأنّه غير متاح (لا يدّعي كتابة).
    """
    try:
        import rasterio
        from rasterio.enums import Resampling
    except ImportError:
        return {"written": False, "reason": "rasterio غير متوفّر — يُكتب في التشغيل"}

    try:
        import numpy as np
    except ImportError:
        return {"written": False, "reason": "numpy غير متوفّر — يُكتب في التشغيل"}

    # صدق: مدخل بلا مصفوفة ثنائيّة صالحة (None/بلا shape) ⇒ مظروف فشل صريح لا انهيار.
    # الـdocstring يعِد بـ«لا يدّعي كتابة»؛ NoneType.shape كان يكسر ذلك (تدقيق 2026-07-05).
    if array is None or not hasattr(array, "shape") or len(getattr(array, "shape", ())) != 2:
        return {"written": False, "reason": "مصفوفة غير صالحة (متوقَّع مصفوفة ثنائيّة الأبعاد)"}

    h, w = array.shape
    # نكتب قيم NaN كما هي للحفاظ على توافق مسار الإحصاء/الاختبارات، لكن لا نعتمد
    # على NaN كـnodata tag. نضيف mask داخلياً كي يتعامل GDAL/overviews/tiles مع
    # خارج الحقل كمنطقة شفافة لا كقيم صالحة قد تُنتج حوافاً أو شرائط.
    write_array = np.asarray(array, dtype="float32")
    valid_mask = np.isfinite(write_array)
    if isinstance(nodata, float) and np.isnan(nodata):
        nodata = DEFAULT_NODATA
    profile = {
        **COG_PROFILE,
        "height": h,
        "width": w,
        "count": 1,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(write_array, 1)
        dst.write_mask(valid_mask.astype("uint8") * 255)
        # أهرامات داخليّة (overviews) — قراءة سريعة عند التكبير/التصغير
        dst.build_overviews(OVERVIEW_LEVELS, Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")

    size = os.path.getsize(output_path)
    return {
        "written": True,
        "path": output_path,
        "size_bytes": size,
        "size_mb": round(size / 1e6, 2),
        "compression": "DEFLATE+predictor3",
        "overviews": OVERVIEW_LEVELS,
        "block_size": "512x512",
        # توحيد main↔cert: ندمج تدقيق COG في ردّ الكتابة (سلوك main) — تدقيق فوريّ بعد
        # الكتابة (مبلّط + أهرامات) دون استدعاء منفصل. يطابقه حارس test_cog_writer_internal_mask.
        "validation": validate_cog(output_path),
    }


def validate_cog(path: str) -> dict:
    """يتحقّق أنّ ملفّاً COG صالح (مبلّط + له أهرامات). للتدقيق بعد الكتابة."""
    try:
        import rasterio
    except ImportError:
        return {"valid": None, "reason": "rasterio غير متوفّر"}
    if not os.path.exists(path):
        return {"valid": False, "reason": "الملفّ غير موجود"}
    with rasterio.open(path) as src:
        is_tiled = src.profile.get("tiled", False)
        has_overviews = len(src.overviews(1)) > 0
        return {
            "valid": bool(is_tiled and has_overviews),
            "tiled": is_tiled,
            "overviews": src.overviews(1),
            "compression": str(src.profile.get("compress", "none")),
            "note": "COG جيّد = مبلّط + أهرامات داخليّة (قراءة جزئيّة سريعة)",
        }
