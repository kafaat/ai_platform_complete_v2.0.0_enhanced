"""self_checks.py — فحوص ذاتيّة حقيقيّة لحزمة الـWorkflow (الشريحة B) — منطق صرف.

فحوص لا شكليّة: CRS/الدقّة/تاريخ الالتقاط موجودة، nodata/valid-pixel ضمن الحدّ، قيم
المؤشّر ضمن مداه (NDVI∈[-1,1])، والامتداد يغطّي الهدف. كلّ فحص يُرجِع نتيجة صريحة
(``passed`` True/False/None-متخطّى + ``detail``). لا I/O.

**التصنيف (severity):** ``required`` (فشلها ⇒ الحزمة failed) مقابل ``quality`` (فشلها ⇒
degraded لا failed). صدق: ما لا يمكن تقييمه (بيانات غائبة) ⇒ ``passed=None`` متخطّى بسبب،
لا نجاح مُفترَض ولا فشل تعسّفيّ.
"""

from __future__ import annotations

from typing import Any

_INDEX_BOUNDS: dict[str, tuple[float, float]] = {
    "ndvi": (-1.0, 1.0),
    "ndmi": (-1.0, 1.0),
    "ndwi": (-1.0, 1.0),
    "evi": (-1.0, 1.0),
    "savi": (-1.5, 1.5),
}
_MAX_NODATA_RATIO = 0.5
_MIN_VALID_PIXEL_RATIO = 0.5


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _result(name: str, severity: str, passed: bool | None, detail: str) -> dict[str, Any]:
    return {"name": name, "severity": severity, "passed": passed, "detail": detail}


def check_crs_present(meta: dict[str, Any]) -> dict[str, Any]:
    crs = meta.get("crs")
    ok = isinstance(crs, str) and bool(crs.strip())
    return _result("crs_present", "required", ok, str(crs) if ok else "CRS غير مُعلَن")


def check_resolution_present(meta: dict[str, Any]) -> dict[str, Any]:
    r = _num(meta.get("resolution_m"))
    ok = r is not None and r > 0
    return _result("resolution_present", "quality", ok, f"{r} م" if ok else "الدقّة غير مُعلَنة")


def check_acquisition_date_present(meta: dict[str, Any]) -> dict[str, Any]:
    d = meta.get("acquisition_date")
    ok = isinstance(d, str) and bool(d.strip())
    return _result(
        "acquisition_date_present", "quality", ok, str(d) if ok else "تاريخ الالتقاط غائب"
    )


def check_nodata_ratio(stats: dict[str, Any], *, max_ratio: float = _MAX_NODATA_RATIO) -> dict:
    r = _num(stats.get("nodata_ratio"))
    if r is None:
        return _result("nodata_ratio", "quality", None, "nodata_ratio غير متاح (تخطٍّ)")
    ok = r <= max_ratio
    return _result(
        "nodata_ratio", "quality", ok, f"{r:.2f} ≤ {max_ratio}" if ok else f"{r:.2f} مرتفع"
    )


def check_valid_pixel_ratio(
    meta: dict[str, Any], stats: dict[str, Any], *, min_ratio: float = _MIN_VALID_PIXEL_RATIO
) -> dict[str, Any]:
    r = _num(meta.get("valid_pixel_ratio"))
    if r is None:
        r = _num(stats.get("valid_pixel_ratio"))
    if r is None:
        return _result("valid_pixel_ratio", "quality", None, "غير متاح (تخطٍّ)")
    ok = r >= min_ratio
    return _result(
        "valid_pixel_ratio", "quality", ok, f"{r:.2f} ≥ {min_ratio}" if ok else f"{r:.2f} منخفض"
    )


def check_value_range(index: str, stats: dict[str, Any]) -> dict[str, Any]:
    bounds = _INDEX_BOUNDS.get(str(index).lower())
    if bounds is None:
        return _result("value_range", "required", None, f"لا حدود معروفة لـ{index} (تخطٍّ)")
    lo, hi = bounds
    vmin, vmax = _num(stats.get("min")), _num(stats.get("max"))
    if vmin is None or vmax is None:
        return _result("value_range", "required", None, "إحصاءات القيمة غير متاحة (تخطٍّ)")
    ok = lo <= vmin and vmax <= hi
    detail = (
        f"[{vmin:.3f}, {vmax:.3f}] ⊆ [{lo}, {hi}]"
        if ok
        else f"[{vmin:.3f}, {vmax:.3f}] خارج [{lo}, {hi}]"
    )
    return _result("value_range", "required", ok, detail)


def check_extent_covers_target(meta: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """امتداد الراستر يغطّي bbox الهدف؟ كلاهما ``[minlon,minlat,maxlon,maxlat]``.

    أيّهما غائب ⇒ متخطٍّ (لا فشل تعسّفيّ). quality (لا يُفشِل الحزمة وحده).
    """
    ext = meta.get("extent")
    tb = target.get("bbox")
    if not (
        isinstance(ext, (list, tuple))
        and len(ext) == 4
        and isinstance(tb, (list, tuple))
        and len(tb) == 4
    ):
        return _result("extent_covers_target", "quality", None, "الامتداد/الهدف غير مُعرَّف (تخطٍّ)")
    e = [_num(x) for x in ext]
    t = [_num(x) for x in tb]
    if any(v is None for v in e + t):
        return _result("extent_covers_target", "quality", None, "قيم امتداد غير رقميّة (تخطٍّ)")
    ok = e[0] <= t[0] and e[1] <= t[1] and e[2] >= t[2] and e[3] >= t[3]
    return _result(
        "extent_covers_target", "quality", ok, "يغطّي الهدف" if ok else "لا يغطّي الهدف كاملاً"
    )


def run_self_checks(
    spec: dict[str, Any], meta: dict[str, Any], stats: dict[str, Any]
) -> dict[str, Any]:
    """يجمع كلّ الفحوص ويشتقّ حالة الجودة. ``passed`` = لا فشل في أيّ فحص ``required``.

    ``quality``: ``good`` (لا فشل) · ``degraded`` (فشل quality فقط) · ``failed`` (فشل required).
    """
    meta = meta if isinstance(meta, dict) else {}
    stats = stats if isinstance(stats, dict) else {}
    index = (spec.get("analysis") or {}).get("index", "")
    target = spec.get("target") or {}
    checks = [
        check_crs_present(meta),
        check_resolution_present(meta),
        check_acquisition_date_present(meta),
        check_nodata_ratio(stats),
        check_valid_pixel_ratio(meta, stats),
        check_value_range(index, stats),
        check_extent_covers_target(meta, target),
    ]
    failed_required = [c for c in checks if c["severity"] == "required" and c["passed"] is False]
    failed_quality = [c for c in checks if c["severity"] == "quality" and c["passed"] is False]
    if failed_required:
        quality = "failed"
    elif failed_quality:
        quality = "degraded"
    else:
        quality = "good"
    return {
        "checks": checks,
        "passed": not failed_required,
        "quality": quality,
        "n_failed_required": len(failed_required),
        "n_failed_quality": len(failed_quality),
    }
