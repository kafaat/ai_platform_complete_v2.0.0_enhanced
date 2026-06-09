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


def linear_trend(composite: list[dict], value_key: str = "median") -> dict:
    """اتّجاه خطّي بسيط (انحدار least-squares) عبر الأشهر.

    يكشف: هل المؤشّر يتحسّن (slope>0) أم يتدهور (slope<0)؟ مفيد لكشف
    الإجهاد التدريجي. لا يدّعي تنبّؤاً — وصف اتّجاه فقط.
    """
    pts = [(i, m[value_key]) for i, m in enumerate(composite) if m.get(value_key) is not None]
    n = len(pts)
    if n < 2:
        return {"slope": None, "direction": "insufficient_data", "points": n}

    sx = sum(x for x, _ in pts)
    sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts)
    sxy = sum(x * y for x, y in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        return {"slope": None, "direction": "flat", "points": n}

    slope = (n * sxy - sx * sy) / denom
    if abs(slope) < 1e-4:
        direction = "stable"
    elif slope > 0:
        direction = "improving"  # تحسّن (نموّ صحّي)
    else:
        direction = "declining"  # تدهور (إجهاد محتمل)
    return {
        "slope": round(slope, 6),
        "direction": direction,
        "points": n,
        "first": composite[0].get(value_key),
        "last": composite[-1].get(value_key),
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
