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
