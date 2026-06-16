"""core/ndvi_analysis.py — محلّل سلسلة NDVI الزمنيّة عند الطلب (Vegetation health).

تحليل صحّة الغطاء النباتيّ من *سلسلة* قراءات NDVI يوفّرها العميل (تطبيق الجوّال /
تاريخ Sentinel). المنصّة تخزّن أحدث NDVI فقط لكلّ حقل (لا تاريخ على الخادم)، لذا
يُحسَب هذا التحليل عند الطلب على سلسلة مُمرَّرة من العميل. هو دعم قرار صادق
(قرينة)، لا حقيقة مخزّنة.

المبادئ المحفوظة (اتّساقاً مع core.time_series):
  • صفر اختراع: سلسلة فارغة/قصيرة/غير صالحة ⇒ insufficient/unknown + note_ar صريح،
    لا استثناء، لا قيم ملفّقة.
  • شفّافية: النقاط الشاذّة من detect_anomalies (z-score) مع reason_ar.
  • Pure functions: لا I/O، لا state، لا تبعيّات خارج core.time_series + stdlib.

الاتّجاه (trend) — least-squares slope على (index → ndvi) للسلسلة المرتّبة زمنيّاً:
  الميل بوحدة «NDVI لكلّ قراءة». العتبة EPS = 0.005 لكلّ قراءة (نصف ميلّي-NDVI
  تقريباً): تغيّر أصغر من ذلك يُعدّ ضوضاء قياس لا اتجاهاً.
    slope > +EPS  ⇒ greening
    slope < -EPS  ⇒ declining
    غير ذلك       ⇒ stable
    نقاط < MIN_POINTS ⇒ insufficient

صحّة الغطاء (health_class) من أحدث NDVI مقابل نطاقات عامّة (قرينة لا حقيقة):
    ndvi >= 0.60  ⇒ healthy
    0.40 <= ndvi < 0.60 ⇒ moderate
    ndvi < 0.40   ⇒ stressed
    لا بيانات/نقاط < MIN_POINTS ⇒ unknown
  هذه النطاقات قرينة عامّة لقوّة الغطاء النباتيّ (vegetation vigor) وتتطلّب تحقّقاً
  ميدانيّاً (ground truth)؛ تتأثّر بالمحصول والمرحلة والتربة والاستشعار.
"""

from __future__ import annotations

from statistics import mean

from core.time_series import TimePoint, detect_anomalies

# ─── عتبات موثّقة ──────────────────────────────────────────────────
MIN_POINTS = 3  # الحدّ الأدنى لاتجاه/تصنيف ذي معنى
TREND_EPS = 0.005  # NDVI لكلّ قراءة؛ أصغر منه ⇒ ضوضاء لا اتجاه
HEALTHY_BAND = 0.60  # ndvi >= 0.60 ⇒ صحّيّ
MODERATE_BAND = 0.40  # 0.40 <= ndvi < 0.60 ⇒ متوسّط؛ أقلّ ⇒ مُجهَد
ANOMALY_MIN_SAMPLES = 5  # حدّ detect_anomalies (z-score)


def _clean_series(series: object) -> list[dict]:
    """يستخلص النقاط الصالحة فقط: {"ndvi": float, "date": str}.

    صفر اختراع: نقطة بلا ndvi رقميّ تُتجاهَل بصمت (لا crash، لا تعويض)."""
    if not isinstance(series, list):
        return []
    cleaned: list[dict] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        raw = item.get("ndvi")
        if isinstance(raw, bool):  # bool هو subclass من int — استبعده صراحةً
            continue
        if not isinstance(raw, (int, float)):
            continue
        ndvi = float(raw)
        date_val = item.get("date")
        cleaned.append({"ndvi": ndvi, "date": str(date_val) if date_val is not None else ""})
    return cleaned


def _linreg_slope(values: list[float]) -> float:
    """ميل least-squares لـ(index 0..n-1 → value). NDVI لكلّ قراءة.

    n معروف >= 2 من المُنادي. denominator (Σ(x-x̄)²) > 0 دائماً لـn>=2."""
    n = len(values)
    xs = list(range(n))
    x_bar = (n - 1) / 2.0
    y_bar = mean(values)
    num = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, values, strict=True))
    den = sum((x - x_bar) ** 2 for x in xs)
    return num / den


def _health_class(latest: float) -> str:
    """تصنيف الصحّة من أحدث NDVI مقابل نطاقات قرينة عامّة."""
    if latest >= HEALTHY_BAND:
        return "healthy"
    if latest >= MODERATE_BAND:
        return "moderate"
    return "stressed"


def analyze_ndvi_series(series: list[dict]) -> dict:
    """يحلّل سلسلة NDVI مُمرَّرة من العميل (on-demand). انظر docstring الوحدة.

    لا يرفع استثناءً أبداً: مدخل غير صالح/قصير ⇒ insufficient/unknown + note_ar."""
    points = _clean_series(series)
    n = len(points)

    base = {
        "n_points": n,
        "latest": None,
        "mean": None,
        "trend": "insufficient",
        "trend_slope": None,
        "anomaly": {"has_anomaly": False, "reason_ar": "", "points": []},
        "health_class": "unknown",
        "note_ar": "",
    }

    if n == 0:
        base["note_ar"] = (
            "لا قراءات NDVI صالحة في السلسلة — لا يمكن التحليل (قرار صادق، لا اختراع)."
        )
        return base

    ndvi_values = [p["ndvi"] for p in points]
    latest = ndvi_values[-1]
    base["latest"] = round(latest, 4)
    base["mean"] = round(mean(ndvi_values), 4)

    if n < MIN_POINTS:
        base["note_ar"] = (
            f"عيّنة غير كافية ({n} نقطة، الحدّ الأدنى {MIN_POINTS}) — "
            "الاتجاه والصحّة غير محسومين. وفّر سلسلة أطول من العميل."
        )
        return base

    # ─── الاتجاه (least-squares slope على index → ndvi) ─────────────
    slope = _linreg_slope(ndvi_values)
    base["trend_slope"] = round(slope, 4)
    if slope > TREND_EPS:
        trend = "greening"
    elif slope < -TREND_EPS:
        trend = "declining"
    else:
        trend = "stable"
    base["trend"] = trend

    # ─── الصحّة من أحدث قراءة (قرينة عامّة) ─────────────────────────
    health = _health_class(latest)
    base["health_class"] = health

    # ─── الشذوذ (z-score من core.time_series) ──────────────────────
    tps = [TimePoint(timestamp=p["date"], value=p["ndvi"]) for p in points]
    anom = detect_anomalies(tps, min_samples=ANOMALY_MIN_SAMPLES)
    base["anomaly"] = {
        "has_anomaly": anom.has_anomaly,
        "reason_ar": anom.reason_ar,
        "points": anom.anomaly_points,
    }

    trend_ar = {"greening": "تحسّن (اخضرار)", "declining": "تراجع", "stable": "مستقرّ"}[trend]
    health_ar = {"healthy": "صحّيّ", "moderate": "متوسّط", "stressed": "مُجهَد"}[health]
    base["note_ar"] = (
        f"{n} قراءة: الاتجاه {trend_ar} (ميل {base['trend_slope']:+}/قراءة)، "
        f"أحدث NDVI {base['latest']} ⇒ {health_ar}. "
        "نطاقات NDVI قرينة عامّة لقوّة الغطاء النباتيّ تتطلّب تحقّقاً ميدانيّاً."
    )
    return base
