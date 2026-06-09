"""
services/raster-service/raster_provenance.py — أصل ونسخة نتائج الراستر

البند #7 (مراجعة 7/8). المرجع: geospatial_integrity + SOIL_INDICES_RESEARCH.

الهدف: كلّ نتيجة مؤشّر (NDVI، ملوحة...) قابلة لإعادة الإنتاج لاحقاً. بعد 6
أشهر يجب أن تعرف بالضبط: أيّ صورة قمر، أيّ تاريخ التقاط، أيّ معاملات، أيّ
صيغة مؤشّر أنتجت هذا الرقم. بدون ذلك، النتيجة "ثقة زائفة" (المراجعة #7).

ما يُثبَّت (pinning):
  - scene_id / item_id (الصورة المحدّدة من STAC)
  - capture_datetime (وقت التقاط القمر — لا وقت المعالجة)
  - raster source URL(s) (الأصل)
  - indicator + صيغته (نسخة الصيغة)
  - معاملات المعالجة (cloud mask، band mapping، clip polygon hash)
  - CRS + الدقّة
  - provenance_hash: بصمة تجمع كلّ ما سبق → نفس المدخلات = نفس البصمة

ملاحظة صدق: هذا يثبّت **المدخلات** لإعادة الإنتاج. إعادة الإنتاج الفعليّة
البِتّيّة (bit-exact) تتطلّب أيضاً تثبيت نسخة rasterio/GDAL — مُوثّق كحقل،
لكن لا يُفرَض (يحتاج بيئة تشغيل مثبّتة).
"""

from __future__ import annotations

import hashlib
import json

# نسخ صيغ المؤشّرات (تتغيّر الصيغة = تتغيّر النسخة = نتيجة مختلفة)
INDICATOR_FORMULA_VERSION = {
    "ndvi": "1.0",
    "evi": "1.0",
    "savi": "1.0",
    "ndwi": "1.0",
    "ndmi": "1.0",
    "gndvi": "1.0",
    "fapar": "1.0",
    "vari": "1.0",
    "gli": "1.0",
    "tgi": "1.0",
    # مؤشّرات التربة (أحدث)
    "bsi": "1.0",
    "bi": "1.0",
    "bi2": "1.0",
    "ndti": "1.0",
    "dbsi": "1.0",
    "ndsi": "1.0",
    "satvi": "1.0",
}


def _hash_polygon(clip_polygon: dict | None) -> str | None:
    """بصمة ثابتة للمضلّع (لإثبات نفس منطقة القصّ)."""
    if not clip_polygon:
        return None
    canonical = json.dumps(clip_polygon, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_provenance(
    indicator: str,
    *,
    scene_id: str | None = None,
    capture_datetime: str | None = None,
    raster_url: str | None = None,
    source_format: str | None = None,
    crs: str = "EPSG:4326",
    resolution_m: float | None = None,
    apply_cloud_mask: bool = True,
    band_mapping: dict | None = None,
    clip_polygon: dict | None = None,
    rasterio_version: str | None = None,
) -> dict:
    """يبني سجلّ أصل كامل + بصمة إعادة إنتاج لنتيجة مؤشّر.

    البصمة (provenance_hash) تجمع كلّ المدخلات المؤثّرة → نفس المدخلات تُنتج
    نفس البصمة، فيمكن كشف "هل هذه النتيجة من نفس المصدر؟" لاحقاً.
    """
    formula_version = INDICATOR_FORMULA_VERSION.get(indicator, "unknown")
    polygon_hash = _hash_polygon(clip_polygon)

    # المكوّنات المؤثّرة على النتيجة (لا وقت المعالجة — غير مؤثّر)
    reproducibility_inputs = {
        "indicator": indicator,
        "formula_version": formula_version,
        "scene_id": scene_id,
        "capture_datetime": capture_datetime,
        "raster_url": raster_url,
        "crs": crs,
        "resolution_m": resolution_m,
        "apply_cloud_mask": apply_cloud_mask,
        "band_mapping": band_mapping,
        "clip_polygon_hash": polygon_hash,
    }
    canonical = json.dumps(
        reproducibility_inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    provenance_hash = hashlib.sha256(canonical.encode()).hexdigest()

    return {
        "provenance_hash": provenance_hash,  # بصمة إعادة الإنتاج
        "scene_id": scene_id,  # الصورة المثبّتة
        "capture_datetime": capture_datetime,  # وقت التقاط القمر
        "raster_url": raster_url,  # الأصل
        "source_format": source_format,
        "indicator": indicator,
        "formula_version": formula_version,  # نسخة الصيغة
        "crs": crs,
        "resolution_m": resolution_m,
        "apply_cloud_mask": apply_cloud_mask,
        "band_mapping": band_mapping,
        "clip_polygon_hash": polygon_hash,
        # تثبيت نسخة المكتبة (للإعادة البِتّيّة) — مُوثّق لا مفروض
        "rasterio_version": rasterio_version,
        "is_reproducible": bool(scene_id and capture_datetime and raster_url),
        "note_ar": (
            "أصل كامل — نفس المدخلات تُنتج نفس provenance_hash. الإعادة "
            "البِتّيّة تتطلّب تثبيت نسخة rasterio/GDAL أيضاً."
            if scene_id
            else "⚠ أصل ناقص — لا scene_id/تاريخ التقاط. النتيجة غير قابلة "
            "لإعادة الإنتاج بثقة (مصدر غير مثبّت)."
        ),
    }


def verify_provenance_match(prov_a: dict, prov_b: dict) -> bool:
    """هل نتيجتان من نفس المصدر بالضبط؟ (مقارنة البصمة)."""
    return prov_a.get("provenance_hash") == prov_b.get("provenance_hash")
