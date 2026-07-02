"""quality_metrics.py — مقاييس جودة الصور (v131) لأصول الراستر.

دوالّ نقيّة (بلا قاعدة/شبكة/rasterio) تحسب إشارات الثقة التي تقرّر ما إذا كان COG
مؤشّر صالحاً لبناء VRA/المناطق:

- ``valid_pixel_ratio`` = خلايا صالحة (ليست NaN/None/nodata/لا نهائيّة) ÷ إجماليّ الخلايا، في [0,1].
- ``coverage_ratio``    = نسبة تغطية بصمة الحقل ببيانات صالحة.
  **تقريب صادق:** عندما تتوفّر الشبكة فقط (لا هندسة حقل مرجعيّة) نساوي التغطية بنسبة
  الخلايا الصالحة (valid/total)؛ فالشبكة مقصوصة أصلاً على مضلّع الحقل، فالخلايا
  غير الصالحة داخلها = فجوات تغطية فعليّة. متى توفّرت تغطية هندسيّة أدقّ مرّرها صراحةً.
- ``index_quality_flags`` = قائمة أعلام نصّيّة حتميّة (deterministic).

القاعدة الذهبيّة (لا اختراع): إذا غابت الشبكة أو كانت فارغة تُعاد ``None`` للنسب — لا ``0.0``.
"""

from __future__ import annotations

import math

# عتبات الأعلام (حتميّة، قابلة للضبط بوسائط صريحة عند الحاجة).
HIGH_CLOUD_PCT = 35.0  # cloud_pct > 35 ⇒ "high_cloud"
SPARSE_VALID_RATIO = 0.7  # valid_pixel_ratio < 0.7 ⇒ "sparse_valid_pixels"


def _is_valid_cell(value: object, nodata: float | None) -> bool:
    """خليّة صالحة = رقم منتهٍ ليس None/NaN/±inf ولا يساوي nodata."""
    if value is None:
        return False
    try:
        f = float(value)  # الشبكات رقميّة؛ النصوص/الكائنات غير القابلة للتحويل = غير صالحة
    except (TypeError, ValueError):
        return False
    if math.isnan(f) or math.isinf(f):
        return False
    if nodata is not None and f == nodata:
        return False
    return True


def _iter_cells(grid: object):
    """يبسّط شبكة (قائمة متداخلة / مصفوفة numpy / مُكرّر) إلى خلايا مفردة."""
    if grid is None:
        return
    # numpy/أيّ كائن يعرض tolist() → قائمة بايثونيّة عاديّة
    tolist = getattr(grid, "tolist", None)
    if callable(tolist):
        grid = tolist()
    stack = [grid]
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(reversed(item))
        else:
            yield item


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def valid_pixel_ratio_from_grid(grid: object, nodata: float | None = None) -> float | None:
    """نسبة الخلايا الصالحة في الشبكة، في [0,1]. ``None`` إن غابت/فرغت الشبكة."""
    total = 0
    valid = 0
    for cell in _iter_cells(grid):
        total += 1
        if _is_valid_cell(cell, nodata):
            valid += 1
    if total == 0:
        return None
    return _clamp01(valid / total)


def _quality_flags(
    valid_pixel_ratio: float | None,
    cloud_pct: float | None,
    *,
    sparse_threshold: float = SPARSE_VALID_RATIO,
    high_cloud_threshold: float = HIGH_CLOUD_PCT,
) -> list[str]:
    """أعلام حتميّة بترتيب ثابت. لا نعلّم ما لا نعرفه (نسبة/غيوم = None ⇒ لا علم)."""
    flags: list[str] = []
    if cloud_pct is not None and float(cloud_pct) > high_cloud_threshold:
        flags.append("high_cloud")
    if valid_pixel_ratio is not None and float(valid_pixel_ratio) < sparse_threshold:
        flags.append("sparse_valid_pixels")
    return flags


def compute_quality_metrics(
    *,
    grid: object = None,
    valid_pixels: int | None = None,
    total_pixels: int | None = None,
    cloud_pct: float | None = None,
    nodata: float | None = None,
    coverage_ratio: float | None = None,
    sparse_threshold: float = SPARSE_VALID_RATIO,
    high_cloud_threshold: float = HIGH_CLOUD_PCT,
) -> dict:
    """يحسب مقاييس جودة v131 من شبكة مؤشّر **أو** من عدّادات بكسلات.

    مصدر ``valid_pixel_ratio`` (بالأولويّة):
      1. ``grid`` صريحة ⇒ خلايا صالحة/إجماليّة.
      2. ``valid_pixels`` + ``total_pixels`` ⇒ عدّادات جاهزة (مسار الكاتب من stats).
    غياب المصدرين (أو إجماليّ = 0) ⇒ ``None`` (لا اختراع).

    ``coverage_ratio``: يُستخدم الممرَّر صراحةً إن وُجد، وإلّا تقريب = ``valid_pixel_ratio``
    (انظر docstring الوحدة). ``index_quality_flags`` حتميّة.

    يُرجِع dict بمفاتيح: valid_pixel_ratio, coverage_ratio, index_quality_flags.
    """
    ratio: float | None = None
    if grid is not None:
        ratio = valid_pixel_ratio_from_grid(grid, nodata=nodata)
    elif valid_pixels is not None and total_pixels is not None and total_pixels > 0:
        ratio = _clamp01(valid_pixels / total_pixels)

    coverage: float | None
    if coverage_ratio is not None:
        coverage = _clamp01(coverage_ratio)
    else:
        coverage = ratio  # تقريب صادق: التغطية = نسبة الخلايا الصالحة داخل بصمة الحقل

    flags = _quality_flags(
        ratio,
        cloud_pct,
        sparse_threshold=sparse_threshold,
        high_cloud_threshold=high_cloud_threshold,
    )
    return {
        "valid_pixel_ratio": ratio,
        "coverage_ratio": coverage,
        "index_quality_flags": flags,
    }
