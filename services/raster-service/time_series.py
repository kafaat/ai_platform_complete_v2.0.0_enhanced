"""
time_series.py — التحليل الزمني للمؤشّرات (سدّ فجوة P0 من تقرير المقارنة).

الممارسة العالميّة (Sentinel-2): سلاسل NDVI الزمنيّة + تركيب الوسيط الشهري
(monthly median compositing) لكشف الإجهاد ومنحنيات النموّ (phenology) وتخفيف
تباين الغلاف الجوّي. هذه الوحدة تجمّع المشاهد عبر فترة، تجمّعها شهريّاً، وتحسب
اتّجاه المؤشّر — دون مكتبات ثقيلة (يعمل على إحصاءات المشاهد).

تعتمد على دالّة معالجة لكلّ مشهد (تُحقَن) لإعادة استخدام منطق band-math نفسه.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable


def _month_key(iso_dt: str) -> str:
    """يستخرج YYYY-MM من طابع ISO (للتجميع الشهري)."""
    try:
        return iso_dt[:7]  # YYYY-MM
    except Exception:
        return "unknown"


def monthly_composite(
    scene_stats: list[dict],
    value_key: str = "mean",
) -> list[dict]:
    """تركيب الوسيط الشهري (monthly median compositing).

    المدخل: قائمة إحصاءات مشاهد، كلّ عنصر {datetime, mean, ...}.
    المخرج: قيمة وسيط (median) لكلّ شهر — يخفّف أثر الغيوم/الشذوذ.
    median لا mean: مقاوم للقيم الشاذّة (سحابة متبقّية) — ممارسة معياريّة.
    """
    by_month: dict[str, list[float]] = defaultdict(list)
    for s in scene_stats:
        v = s.get(value_key)
        dt = s.get("datetime", "")
        if v is not None and dt:
            by_month[_month_key(dt)].append(float(v))

    out = []
    for month in sorted(by_month):
        vals = by_month[month]
        if not vals:
            continue
        out.append(
            {
                "month": month,
                "median": round(statistics.median(vals), 4),
                "mean": round(statistics.fmean(vals), 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "scene_count": len(vals),
            }
        )
    return out


def _month_index(month: str) -> int | None:
    """YYYY-MM ⇒ رقم شهر مطلق (السنة×12 + الشهر)؛ None إن تعذّر."""
    try:
        year, mon = month.split("-")[:2]
        y, m = int(year), int(mon)
    except (AttributeError, ValueError):
        return None
    if not 1 <= m <= 12:
        return None
    return y * 12 + (m - 1)


# حدّ «الملاءمة الخطّيّة ضعيفة»: R² أدنى من هذا مع ≥4 نقاط ⇒ المنحنى غير خطّي، والميل
# وحده يُخفي التذبذب (درسُ سلاسل InSAR: سرعةٌ ملاءَمة لا تساوي حركةً منتظمة).
_NONLINEAR_R2 = 0.5


def linear_trend(composite: list[dict], value_key: str = "median") -> dict:
    """اتّجاه خطّي (least-squares) على محور زمنيّ حقيقيّ بالأشهر.

    المحور x هو رقم الشهر الفعليّ لا ترتيبه في القائمة: شهرٌ مفقود (غيوم كاملة) لا
    يُطوى، فلا يتضخّم الميل. ``slope`` بوحدة المؤشّر/شهر. يُعاد معه ما يلزم لقراءته
    بصدق: المدى الزمنيّ، الأشهر المفقودة، جذر متوسّط مربّع البواقي، R²، وجودة الملاءمة
    (``fit_quality``: linear | nonlinear | undetermined). وصفٌ لا تنبّؤ.
    """
    pts: list[tuple[int, float, str]] = []
    for m in composite:
        v = m.get(value_key)
        idx = _month_index(m.get("month", ""))
        if v is None or idx is None:
            continue
        pts.append((idx, float(v), m["month"]))
    n = len(pts)
    if n < 2:
        return {"slope": None, "direction": "insufficient_data", "points": n}

    x0 = pts[0][0]
    xs = [x - x0 for x, _, _ in pts]
    ys = [y for _, y, _ in pts]
    span = xs[-1]
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    denom = n * sxx - sx * sx
    if denom == 0:
        return {"slope": None, "direction": "flat", "points": n}

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    ss_res = sum(r * r for r in residuals)
    mean_y = sy / n
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = None if ss_tot == 0 else round(1 - ss_res / ss_tot, 4)
    if n < 4 or r2 is None:
        fit_quality = "undetermined"
    elif r2 < _NONLINEAR_R2:
        fit_quality = "nonlinear"
    else:
        fit_quality = "linear"

    if abs(slope) < 1e-4:
        direction = "stable"
    elif slope > 0:
        direction = "improving"  # تحسّن (نموّ صحّي)
    else:
        direction = "declining"  # تدهور (إجهاد محتمل)
    present = set(xs)
    return {
        "slope": round(slope, 6),
        "slope_unit": "index_per_month",
        "direction": direction,
        "points": n,
        "first": ys[0],
        "last": ys[-1],
        "first_month": pts[0][2],
        "last_month": pts[-1][2],
        "span_months": span,
        "missing_months": span + 1 - len(present),
        "residual_rms": round((ss_res / n) ** 0.5, 6),
        "r2": r2,
        "fit_quality": fit_quality,
    }


def detect_anomalies(
    composite: list[dict], value_key: str = "median", z_threshold: float = 1.5
) -> list[dict]:
    """يكشف الأشهر الشاذّة (انخفاض/ارتفاع حادّ) عبر z-score.

    انخفاض NDVI حادّ قد يشير لإجهاد/آفة (الأدبيّات). عتبة z=1.5 افتراضيّة.
    """
    vals = [m[value_key] for m in composite if m.get(value_key) is not None]
    if len(vals) < 3:
        return []
    mu = statistics.fmean(vals)
    sd = statistics.pstdev(vals)
    if sd == 0:
        return []
    anomalies = []
    for m in composite:
        v = m.get(value_key)
        if v is None:
            continue
        z = (v - mu) / sd
        if abs(z) >= z_threshold:
            anomalies.append(
                {
                    "month": m["month"],
                    "value": v,
                    "z_score": round(z, 2),
                    "type": "drop" if z < 0 else "spike",
                }
            )
    return anomalies


def build_time_series(
    scene_list: list[dict],
    process_scene: Callable[[dict], float | None] | None = None,
    value_key: str = "mean",
) -> dict:
    """يبني تحليلاً زمنيّاً كاملاً من قائمة مشاهد STAC.

    إن مُرّرت process_scene (تحسب مؤشّر المشهد فعليّاً)، تُستخدَم؛ وإلّا يُتوقّع
    أنّ كلّ مشهد يحمل إحصاءه مسبقاً (مفتاح value_key). صدق: لا يخترع قيماً.
    """
    scene_stats = []
    for sc in scene_list:
        dt = sc.get("datetime") or sc.get("date", "")
        val = None
        if process_scene is not None:
            val = process_scene(sc)
        elif value_key in sc:
            val = sc[value_key]
        if val is not None and dt:
            scene_stats.append({"datetime": dt, "mean": float(val)})

    composite = monthly_composite(scene_stats, value_key="mean")
    return {
        "scenes_used": len(scene_stats),
        "monthly_composite": composite,
        "trend": linear_trend(composite),
        "anomalies": detect_anomalies(composite),
        "note": "median شهري يخفّف الغيوم؛ الاتّجاه وصفي لا تنبّؤي",
    }


async def build_time_series_parallel(
    scene_list: list[dict],
    process_scene_async: Callable,
    max_concurrency: int = 4,
    value_key: str = "mean",
) -> dict:
    """يحسب مؤشّر كلّ مشهد بالتوازي (محدود) ثمّ يبني التحليل الزمني.

    معالجة المشاهد المتعدّدة بالتوازي تسرّع التحليل الزمني بشدّة (بدل تسلسلي).
    semaphore يحدّ التزامن (لا يُغرق المصدر/الذاكرة) — أفضل ممارسة backpressure.
    عزل فشل كلّ مشهد (مشهد فاشل لا يُسقط السلسلة).

    process_scene_async: دالّة async تأخذ مشهداً وتُرجِع قيمة المؤشّر (أو None).
    """
    import asyncio

    sem = asyncio.Semaphore(max(1, max_concurrency))
    failed = 0

    async def _one(sc: dict):
        nonlocal failed
        async with sem:  # حدّ التزامن (backpressure)
            try:
                val = await process_scene_async(sc)
                dt = sc.get("datetime") or sc.get("date", "")
                if val is not None and dt:
                    return {"datetime": dt, "mean": float(val)}
            except Exception:  # noqa: BLE001 — عزل لكلّ مشهد
                failed += 1
            return None

    results = await asyncio.gather(*[_one(sc) for sc in scene_list])
    scene_stats = [r for r in results if r is not None]

    composite = monthly_composite(scene_stats, value_key="mean")
    return {
        "scenes_used": len(scene_stats),
        "scenes_failed": failed,
        "max_concurrency": max_concurrency,
        "monthly_composite": composite,
        "trend": linear_trend(composite),
        "anomalies": detect_anomalies(composite),
        "note": "معالجة متوازية محدودة (semaphore)؛ median شهري يخفّف الغيوم",
    }


# ── القناع المشترك (common valid mask) ───────────────────────────────────────
# متوسّط كلّ مشهد على بكسلاته الصالحة وحدها يخلط تغيّر التغطية المكانيّة بالتغيّر الزمنيّ:
# مشهدٌ غطّت الغيومُ 70% منه يُقاس على جزءٍ آخر من الحقل. ممارسة سلاسل InSAR (DefoEye):
# تُحسب السلسلة على البكسلات الصالحة في **كلّ** مشهد مستعمَل فقط، ويُعلَن ما بقي منها.
COMMON_MASK_MIN_COVERAGE = 0.5  # أدنى حصّة من بكسلات الحقل في القناع المشترك لإعلان اتّجاه
COMMON_MASK_MIN_SCENE_COVERAGE = 0.5  # مشهدٌ صالحُه أقلّ من هذا من الحقل يُستبعد أوّلاً
COMMON_MASK_MIN_SCENES = 2  # لا يُستبعد مشهد إن نزل العدد تحت هذا
COMMON_MASK_RULE = (
    "1) a scene that cannot be read or aligned to the field grid, or has no valid pixel inside "
    "the field, is excluded (its reason is kept); "
    "2) a scene whose own valid pixels cover less than min_scene_coverage of the field is "
    "excluded (scene_valid_coverage_below_min); "
    "3) while common coverage < min_common_coverage and more than min_scenes remain, the scene "
    "whose removal adds the most common pixels is excluded (shrinks_common_mask); ties go to "
    "the scene with fewer own valid pixels, then the later one; stop when no removal helps; "
    "4) common coverage still below min_common_coverage, or fewer than min_scenes scenes, "
    "returns trend direction insufficient_common_coverage with no slope"
)


def select_common_mask(
    valid_masks: list,
    field_mask,
    *,
    preset_reasons: list[str | None] | None = None,
    min_common_coverage: float = COMMON_MASK_MIN_COVERAGE,
    min_scene_coverage: float = COMMON_MASK_MIN_SCENE_COVERAGE,
    min_scenes: int = COMMON_MASK_MIN_SCENES,
) -> dict:
    """يختار المشاهد ويبني القناع المشترك وفق ``COMMON_MASK_RULE`` (حتميّ).

    ``valid_masks``: مصفوفات منطقيّة على شبكة الحقل الثابتة نفسها، بترتيب زمنيّ. ``field_mask``:
    بكسلات داخل حدّ الحقل. يُرجِع القناع المشترك والمستعمَل والمستبعَد مع السبب.
    """
    import numpy as np

    field = np.asarray(field_mask, dtype=bool)
    field_pixels = int(field.sum())
    n = len(valid_masks)
    reasons: list[str | None] = list(preset_reasons or [None] * n)
    valid = [
        None if reasons[i] else (np.asarray(m, dtype=bool) & field)
        for i, m in enumerate(valid_masks)
    ]
    own = [0 if v is None else int(v.sum()) for v in valid]
    for i in range(n):
        if reasons[i] is None and field_pixels and own[i] == 0:
            reasons[i] = "no_valid_pixels_in_field"
        elif reasons[i] is None and field_pixels and own[i] / field_pixels < min_scene_coverage:
            reasons[i] = "scene_valid_coverage_below_min"
    kept = [i for i in range(n) if reasons[i] is None]

    def _common(idx: list[int]):
        if not idx:
            return np.zeros_like(field)
        return np.logical_and.reduce([valid[i] for i in idx])

    common = _common(kept)
    while (
        field_pixels
        and common.sum() / field_pixels < min_common_coverage
        and len(kept) > max(min_scenes, 1)
    ):
        count = np.sum([valid[i] for i in kept], axis=0)
        k = len(kept)
        # بدون المشهد s يصير البكسل مشتركاً إن صلح في الباقين كلّهم: count==k-1 و s غير صالح فيه.
        gains = [(int(((count == k - 1) & ~valid[s]).sum()), -own[s], s) for s in kept]
        best_gain, _, best = max(gains)
        if best_gain == 0:
            break
        reasons[best] = "shrinks_common_mask"
        kept.remove(best)
        common = _common(kept)

    common_pixels = int(common.sum()) if kept else 0
    ratio = (common_pixels / field_pixels) if field_pixels else 0.0
    if not field_pixels:
        status, reason = "insufficient_common_coverage", "field_mask_empty"
    elif len(kept) < min_scenes:
        status, reason = "insufficient_common_coverage", "too_few_scenes"
    elif ratio < min_common_coverage:
        status, reason = "insufficient_common_coverage", "common_coverage_below_min"
    else:
        status, reason = "ok", None
    return {
        "status": status,
        "reason": reason,
        "mask": common,
        "kept": kept,
        "reasons": reasons,
        "own_valid_pixels": own,
        "field_pixels": field_pixels,
        "common_valid_pixels": common_pixels,
        "common_coverage_ratio": round(ratio, 6),
    }


def _insufficient_trend(reason: str, points: int, ratio: float | None, threshold: float) -> dict:
    return {
        "slope": None,
        "direction": "insufficient_common_coverage",
        "points": points,
        "reason": reason,
        "common_coverage_ratio": ratio,
        "min_common_coverage": threshold,
    }


def build_common_mask_series(
    scenes: list[dict],
    field_mask,
    *,
    field_mask_basis: str,
    grid: dict | None = None,
    min_common_coverage: float = COMMON_MASK_MIN_COVERAGE,
    min_scene_coverage: float = COMMON_MASK_MIN_SCENE_COVERAGE,
    min_scenes: int = COMMON_MASK_MIN_SCENES,
) -> dict:
    """سلسلة زمنيّة على القناع المشترك: متوسّط كلّ مشهد على تقاطع البكسلات الصالحة وحده.

    ``scenes``: ``[{datetime, values (2D على شبكة الحقل، NaN = غير صالح), scene_id?,
    excluded_reason?}]``. البكسل صالح إن كان منتهياً وداخل الحقل. يُرجِع ``monthly_composite``
    و``trend`` و``anomalies`` المحسوبة على القناع، و``common_mask`` بالعدّ والتغطية والأسباب.
    """
    import numpy as np

    ordered = sorted(range(len(scenes)), key=lambda i: str(scenes[i].get("datetime") or ""))
    field = np.asarray(field_mask, dtype=bool)
    masks, preset = [], []
    for i in ordered:
        sc = scenes[i]
        vals = sc.get("values")
        if sc.get("excluded_reason") or vals is None:
            masks.append(np.zeros_like(field))
            preset.append(sc.get("excluded_reason") or "scene_unreadable")
        else:
            masks.append(np.isfinite(np.asarray(vals, dtype="float64")))
            preset.append(None)
    sel = select_common_mask(
        masks,
        field,
        preset_reasons=preset,
        min_common_coverage=min_common_coverage,
        min_scene_coverage=min_scene_coverage,
        min_scenes=min_scenes,
    )
    field_pixels = sel["field_pixels"]
    per_scene: list[dict] = [{} for _ in scenes]
    scene_stats: list[dict] = []
    for pos, i in enumerate(ordered):
        sc = scenes[i]
        own = sel["own_valid_pixels"][pos]
        entry = {
            "datetime": sc.get("datetime"),
            "scene_id": sc.get("scene_id"),
            "valid_pixels": own,
            "valid_coverage_ratio": round(own / field_pixels, 6) if field_pixels else None,
            "status": "used" if pos in sel["kept"] else "excluded",
            "reason": sel["reasons"][pos],
            "common_mean": None,
        }
        if pos in sel["kept"] and sel["common_valid_pixels"]:
            mean = float(np.asarray(sc["values"], dtype="float64")[sel["mask"]].mean())
            entry["common_mean"] = round(mean, 6)
            if sc.get("datetime"):
                scene_stats.append({"datetime": sc["datetime"], "mean": mean})
        per_scene[i] = entry

    composite = monthly_composite(scene_stats, value_key="mean")
    if sel["status"] == "ok":
        trend = linear_trend(composite)
        anomalies = detect_anomalies(composite)
    else:
        trend = _insufficient_trend(
            sel["reason"], len(composite), sel["common_coverage_ratio"], min_common_coverage
        )
        anomalies = []
    used = len(sel["kept"])
    return {
        "scenes_used": len(scene_stats),
        "monthly_composite": composite,
        "trend": trend,
        "anomalies": anomalies,
        "common_mask": {
            "status": sel["status"],
            "reason": sel["reason"],
            "field_mask_basis": field_mask_basis,
            "grid": grid,
            "field_pixels": field_pixels,
            "common_valid_pixels": sel["common_valid_pixels"],
            "common_coverage_ratio": sel["common_coverage_ratio"],
            "scenes_used": used,
            "scenes_excluded": len(scenes) - used,
            "exclusions": [e for e in per_scene if e.get("status") == "excluded"],
            "scenes": per_scene,
            "min_common_coverage": min_common_coverage,
            "min_scene_coverage": min_scene_coverage,
            "min_scenes": min_scenes,
            "rule": COMMON_MASK_RULE,
        },
    }


def apply_common_mask(
    analysis: dict,
    points: list[dict],
    aligned: dict | None,
    *,
    min_common_coverage: float = COMMON_MASK_MIN_COVERAGE,
) -> dict:
    """يستبدل اتّجاه متوسّطات المشاهد الخاصّة باتّجاه القناع المشترك (إضافيّ، عند الطلب).

    الاتّجاه السابق يبقى في ``unmasked_trend``؛ وكلّ نقطة تحمل ``common_mask_mean``. تعذّر بناء
    الشبكة المشتركة ⇒ ``insufficient_common_coverage`` صراحةً، لا العودة الصامتة للمتوسّطات الخاصّة.
    """
    out = dict(analysis)
    out["unmasked_trend"] = analysis.get("trend")
    if not aligned or aligned.get("error"):
        reason = (aligned or {}).get("error") or "common_mask_unavailable"
        out["trend"] = _insufficient_trend(reason, 0, None, min_common_coverage)
        out["anomalies"] = []
        out["common_mask"] = {
            "status": "unavailable",
            "reason": reason,
            "rule": COMMON_MASK_RULE,
            "min_common_coverage": min_common_coverage,
        }
        for p in points:
            p["common_mask_mean"] = None
        return out
    res = build_common_mask_series(
        aligned["scenes"],
        aligned["field_mask"],
        field_mask_basis=aligned["field_mask_basis"],
        grid=aligned.get("grid"),
        min_common_coverage=min_common_coverage,
    )
    for p, entry in zip(points, res["common_mask"]["scenes"], strict=False):
        p["common_mask_mean"] = entry.get("common_mean")
    out.update(res)
    return out
