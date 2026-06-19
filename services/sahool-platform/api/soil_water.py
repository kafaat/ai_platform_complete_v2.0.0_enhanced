"""api/soil_water.py — خصائص ماء التربة حسب النسيج (FAO-56 Table 19)

الطبقة الثالثة في خطّ «مركز المحاصيل» (#374 — Soil-Aware Irrigation Need):
`root_zone_balance` و`crop_twin` يتطلّبان `taw_mm` (الماء الكلّيّ المتاح) كمُدخَل —
هذا المصدر الموحّد يشتقّه من **نسيج التربة × عمق الجذور** بدل تمريره أرقاماً سحريّة.

الفصل المفاهيميّ (صدق علميّ):
  • TAW (سعة الاحتفاظ) **خاصّيّة تربة** ⇐ النسيج (FAO-56 Table 19).
  • p (نسبة الاستنفاد المتاح بيُسر، raw_fraction) **خاصّيّة محصول** (FAO-56 Table 22)
    لا نسيج — لذا تُمرَّر من المحصول (افتراض 0.5)، لا نختلقها من النسيج.

نقيّ حتميّ (لا I/O). يدعم مفاتيح النسيج الإنجليزيّة والعربيّة (اتّساقاً مع
soil_recommendations). ⚠ قيم TAW أوّليّة من منتصفات FAO-56 Table 19 — تحتاج معايرة
يمنيّة (تربة كلسيّة، بنية مختلفة). موسومة calibrated=False.
"""

from __future__ import annotations

# الماء الكلّيّ المتاح TAW (مم/متر عمق) حسب النسيج — منتصفات FAO-56 Table 19.
# ⚠ غير معايَر يمنيّاً. المفاتيح إنجليزيّة؛ العربيّة عبر _TEXTURE_ALIASES.
_TAW_MM_PER_M: dict[str, float] = {
    "sand": 65.0,
    "loamy_sand": 90.0,
    "sandy_loam": 125.0,
    "loam": 175.0,
    "silt_loam": 200.0,
    "silt": 200.0,
    "silty_clay_loam": 175.0,
    "clay_loam": 165.0,
    "silty_clay": 150.0,
    "clay": 135.0,
}

# مرادفات عربيّة/مبسّطة → مفتاح قانونيّ (يطابق فئات soil_recommendations).
_TEXTURE_ALIASES: dict[str, str] = {
    "رملي": "sand",
    "رملية": "sand",
    "طمي-رملي": "sandy_loam",
    "طميي-رملي": "sandy_loam",
    "طمية رملية": "sandy_loam",
    "طميي": "loam",
    "طمية": "loam",
    "طيني": "clay",
    "طينية": "clay",
    "sandy": "sand",
    "loamy": "loam",
}

# عمق جذور افتراضيّ حين يغيب (م) — متوسّط آمن، موسوم. لا اختلاق عمق دقيق.
_DEFAULT_ROOT_DEPTH_M = 0.6
# p (raw_fraction) عامّ من FAO-56 حين لا يمرّره المحصول.
_DEFAULT_RAW_FRACTION = 0.5
# TAW احتياطيّ لنسيج مجهول (منتصف النطاق ~loam) — موسوم texture_known=False.
_FALLBACK_TAW_MM_PER_M = 150.0


def _taw_per_m(texture: str | None) -> tuple[float, bool]:
    """TAW (مم/م) من النسيج ⇒ (القيمة، هل النسيج معروف). يطبّع العربيّة والحالة."""
    if not texture:
        return _FALLBACK_TAW_MM_PER_M, False
    key = texture.strip().lower()
    key = _TEXTURE_ALIASES.get(texture.strip(), _TEXTURE_ALIASES.get(key, key))
    if key in _TAW_MM_PER_M:
        return _TAW_MM_PER_M[key], True
    return _FALLBACK_TAW_MM_PER_M, False


def soil_water_params(
    texture: str | None,
    root_depth_m: float | None = None,
    raw_fraction: float = _DEFAULT_RAW_FRACTION,
) -> dict:
    """يشتقّ `taw_mm` و`raw_mm` من النسيج وعمق الجذور — مُدخَل لـ root_zone_balance.

    TAW = TAW(نسيج) × عمق الجذور؛ RAW = p × TAW (p خاصّيّة محصول تُمرَّر، لا نسيج).
    صدق: النسيج المجهول يستعمل قيمة احتياطيّة موسومة (texture_known=False)؛ عمق غائب
    ⇒ افتراض موسوم؛ القيم غير معايَرة يمنيّاً (calibrated=False).
    """
    warnings_ar: list[str] = [
        "TAW من منتصفات FAO-56 Table 19 غير معايَرة يمنيّاً (تربة كلسيّة) — قدِّر بحذر",
    ]
    taw_per_m, known = _taw_per_m(texture)
    if not known:
        warnings_ar.append("نسيج غير معروف — TAW احتياطيّ (متوسّط)؛ مرّر نسيجاً للدقّة")

    depth = root_depth_m
    if depth is None or depth <= 0:
        depth = _DEFAULT_ROOT_DEPTH_M
        warnings_ar.append(f"عمق الجذور غائب — افتراض {depth} م (موسوم)")

    p = max(0.0, min(1.0, raw_fraction))
    taw_mm = taw_per_m * depth
    raw_mm = p * taw_mm
    return {
        "texture": (texture or "").strip().lower() or None,
        "texture_known": known,
        "taw_mm_per_m": round(taw_per_m, 1),
        "root_depth_m": round(depth, 2),
        "taw_mm": round(taw_mm, 2),
        "raw_fraction": round(p, 3),
        "raw_mm": round(raw_mm, 2),
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
