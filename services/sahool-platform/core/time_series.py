"""
sahool_core.time_series
=========================
Time-series aggregation للـobservations — moving averages, rolling windows,
temporal patterns.

الفجوة المسدودة من تحليل AI Ag Template:
  "Time-series treatment للـobservations" غير مكتمل.
  multi_season للمواسم، cross_reference للحالات،
  لكنّ "30-day moving average" غير موجود.

الاستخدامات الزراعية الفعلية:
  • متوسّط NDVI آخر 30 يوم → تحذير حقيقي من تراجع
  • Trend detection داخل الموسم (لا فقط بين المواسم)
  • Anomaly في القراءات (هل القفزة جوهرية أم noise؟)
  • Smoothing للـsensor noise

المبادئ المحفوظة:
  • صفر اختراع: نافذة فارغة → None صريح، لا "أفضل تخمين"
  • شفّافية: كل aggregation يحمل sample_count + period_ar
  • Pure functions: لا I/O، لا state، لا dependencies
  • Multi-tenant safe: لا "global state" يتقاطع
  • Offline-first: in-memory pure logic

التمييز عن وحدات أخرى:
  • multi_season_analytics: عبر مواسم متعدّدة (months/years)
  • cross_reference_finder: حالات تاريخية مشابهة
  • time_series: نوافذ زمنية داخل الموسم (days/weeks)

التكامل:
  ← يأخذ observations كـlist of (timestamp, value, source)
  → يُغذّي recommendation_bridge عند الحاجة لـsmoothed indicators
  → يُغذّي farm_memory للـtemporal views
  → يُغذّي evidence_class (anomaly detection)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from statistics import mean, median, stdev


class TrendDirection(str, Enum):
    INSUFFICIENT = "insufficient"  # < min_samples
    STABLE = "stable"
    INCREASING = "increasing"
    DECREASING = "decreasing"
    VOLATILE = "volatile"  # noise مرتفع، اتجاه غير واضح


@dataclass
class TimePoint:
    """نقطة زمنية واحدة (lightweight)."""

    timestamp: str  # ISO datetime
    value: float


@dataclass
class WindowResult:
    """نتيجة aggregation لنافذة واحدة."""

    window_label: str  # "آخر 30 يوم"، "آخر أسبوع"
    period_from: str
    period_to: str
    sample_count: int
    mean_value: float | None
    median_value: float | None
    min_value: float | None
    max_value: float | None
    std_dev: float | None  # noise indicator
    reason_ar: str  # تفسير صريح


@dataclass
class TrendResult:
    """تحليل اتجاه ضمن نافذة."""

    direction: TrendDirection
    slope_per_day: float | None  # معدّل التغيّر اليومي
    confidence: str  # low/medium/high (إحصائية، لا "AI")
    samples_analyzed: int
    noise_level: float | None  # std_dev / mean (coefficient of variation)
    reason_ar: str


# ─── Pure helper functions ───────────────────────────────────────


def _parse_ts(s: str) -> datetime | None:
    """يحاول parse عدّة صيغ. لا اختراع: فشل → None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "").replace("+00:00", ""))
    except (ValueError, AttributeError):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(s[: len(fmt) + 6], fmt)
            except ValueError:
                continue
    return None


def _filter_window(
    points: list[TimePoint],
    days_back: int,
    anchor: datetime | None = None,
) -> list[TimePoint]:
    """يفلتر النقاط ضمن نافذة days_back من anchor (افتراضياً الآن).

    صفر اختراع: تاريخ غير صالح → يُستبعَد بصمت (مُسجَّل في reason)."""
    if anchor is None:
        anchor = datetime.now()
    cutoff = anchor - timedelta(days=days_back)

    result = []
    for p in points:
        ts = _parse_ts(p.timestamp)
        if ts is None:
            continue
        if cutoff <= ts <= anchor:
            result.append(p)
    return result


# ─── Window aggregation ──────────────────────────────────────────


def aggregate_window(
    points: list[TimePoint],
    days_back: int,
    *,
    anchor: datetime | None = None,
    min_samples: int = 3,
    label: str | None = None,
) -> WindowResult:
    """يحسب إحصائيات نافذة زمنية.

    min_samples: الحدّ الأدنى لاعتبار النتائج (لا اختراع لـ"متوسّط من نقطة").
    """
    if anchor is None:
        anchor = datetime.now()

    window = _filter_window(points, days_back, anchor)
    label = label or f"آخر {days_back} يوم"
    period_to = anchor.isoformat()
    period_from = (anchor - timedelta(days=days_back)).isoformat()

    if len(window) < min_samples:
        return WindowResult(
            window_label=label,
            period_from=period_from,
            period_to=period_to,
            sample_count=len(window),
            mean_value=None,
            median_value=None,
            min_value=None,
            max_value=None,
            std_dev=None,
            reason_ar=(f"عيّنة غير كافية ({len(window)} نقطة، الحدّ الأدنى {min_samples})"),
        )

    values = [p.value for p in window]
    return WindowResult(
        window_label=label,
        period_from=period_from,
        period_to=period_to,
        sample_count=len(window),
        mean_value=round(mean(values), 4),
        median_value=round(median(values), 4),
        min_value=round(min(values), 4),
        max_value=round(max(values), 4),
        std_dev=round(stdev(values), 4) if len(values) >= 2 else None,
        reason_ar=(f"{len(window)} قراءة في {label} (من {period_from[:10]} إلى {period_to[:10]})"),
    )


# ─── Moving average ──────────────────────────────────────────────


def moving_average(
    points: list[TimePoint],
    window_days: int = 7,
    *,
    anchor: datetime | None = None,
) -> float | None:
    """متوسّط متحرّك بسيط لنافذة. None إن لا بيانات."""
    result = aggregate_window(points, window_days, anchor=anchor, min_samples=1)
    return result.mean_value


# ─── Trend detection ─────────────────────────────────────────────


def detect_trend(
    points: list[TimePoint],
    days_back: int = 30,
    *,
    anchor: datetime | None = None,
    min_samples: int = 4,
    stable_threshold_pct: float = 5.0,
    volatility_threshold: float = 0.25,
) -> TrendResult:
    """يكشف اتجاهاً ضمن نافذة باستخدام linear approximation بسيط.

    صفر اختراع:
      • <min_samples → INSUFFICIENT
      • noise > threshold → VOLATILE (لا "trend مزيّف")
      • تغيّر <stable_threshold → STABLE
    """
    if anchor is None:
        anchor = datetime.now()

    window = _filter_window(points, days_back, anchor)

    if len(window) < min_samples:
        return TrendResult(
            direction=TrendDirection.INSUFFICIENT,
            slope_per_day=None,
            confidence="low",
            samples_analyzed=len(window),
            noise_level=None,
            reason_ar=(f"عيّنة غير كافية ({len(window)} نقطة، الحدّ الأدنى {min_samples})"),
        )

    # رتّب زمنياً
    sorted_pts = sorted(
        [(p, _parse_ts(p.timestamp)) for p in window if _parse_ts(p.timestamp) is not None],
        key=lambda x: x[1],
    )
    if len(sorted_pts) < min_samples:
        return TrendResult(
            direction=TrendDirection.INSUFFICIENT,
            slope_per_day=None,
            confidence="low",
            samples_analyzed=len(sorted_pts),
            noise_level=None,
            reason_ar="نقاط زمنية غير صالحة",
        )

    values = [p.value for p, _ in sorted_pts]

    # noise level (coefficient of variation)
    m = mean(values)
    sd = stdev(values) if len(values) >= 2 else 0.0
    cv = abs(sd / m) if m != 0 else 0.0

    if cv > volatility_threshold:
        return TrendResult(
            direction=TrendDirection.VOLATILE,
            slope_per_day=None,
            confidence="low",
            samples_analyzed=len(values),
            noise_level=round(cv, 3),
            reason_ar=(f"تذبذب مرتفع (CV={cv:.2f} > {volatility_threshold}). اتجاه غير موثوق."),
        )

    # linear approximation: slope between first and last
    first_p, first_ts = sorted_pts[0]
    last_p, last_ts = sorted_pts[-1]
    days_span = max((last_ts - first_ts).days, 1)
    slope = (last_p.value - first_p.value) / days_span
    pct_change = (
        ((last_p.value - first_p.value) / abs(first_p.value) * 100) if first_p.value != 0 else 0.0
    )

    # تصنيف
    if abs(pct_change) < stable_threshold_pct:
        direction = TrendDirection.STABLE
        reason = (
            f"مستقرّ (تغيّر {pct_change:+.1f}% خلال {days_span} يوم، "
            f"ضمن العتبة {stable_threshold_pct}%)"
        )
    elif pct_change > 0:
        direction = TrendDirection.INCREASING
        reason = f"متزايد: {pct_change:+.1f}% خلال {days_span} يوم ({slope:+.4f}/يوم)"
    else:
        direction = TrendDirection.DECREASING
        reason = f"متناقص: {pct_change:+.1f}% خلال {days_span} يوم ({slope:+.4f}/يوم)"

    # confidence إحصائي
    confidence = "high" if len(values) >= 10 else ("medium" if len(values) >= 6 else "low")

    return TrendResult(
        direction=direction,
        slope_per_day=round(slope, 4),
        confidence=confidence,
        samples_analyzed=len(values),
        noise_level=round(cv, 3),
        reason_ar=reason,
    )


# ─── Anomaly detection (بسيط، شفّاف) ───────────────────────────────


@dataclass
class AnomalyResult:
    has_anomaly: bool
    anomaly_points: list[dict] = field(default_factory=list)
    threshold_used: float = 0.0
    reason_ar: str = ""


def detect_anomalies(
    points: list[TimePoint],
    *,
    z_score_threshold: float = 2.5,
    min_samples: int = 5,
) -> AnomalyResult:
    """يكشف نقاط شاذّة بـz-score بسيط.

    لا "ML سحرية" — chosen تفسيراً لشفّافية:
      • z-score = (value - mean) / std_dev
      • |z| > threshold → anomaly
      • تفسير صريح في reason_ar
    """
    if len(points) < min_samples:
        return AnomalyResult(
            has_anomaly=False,
            reason_ar=f"عيّنة غير كافية ({len(points)} < {min_samples})",
        )

    values = [p.value for p in points]
    m = mean(values)
    sd = stdev(values)

    if sd == 0:
        return AnomalyResult(
            has_anomaly=False,
            threshold_used=z_score_threshold,
            reason_ar="كل القيم متطابقة، لا شذوذ ممكن",
        )

    anomalies = []
    for p in points:
        z = abs((p.value - m) / sd)
        if z > z_score_threshold:
            anomalies.append(
                {
                    "timestamp": p.timestamp,
                    "value": p.value,
                    "z_score": round(z, 2),
                    "expected_mean": round(m, 4),
                }
            )

    return AnomalyResult(
        has_anomaly=len(anomalies) > 0,
        anomaly_points=anomalies,
        threshold_used=z_score_threshold,
        reason_ar=(
            f"{len(anomalies)} نقطة شاذّة من {len(points)} "
            f"(عتبة |z| > {z_score_threshold}، μ={m:.3f}، σ={sd:.3f})"
        ),
    )


# ─── Summary ─────────────────────────────────────────────────────


def temporal_summary(
    points: list[TimePoint],
    *,
    indicator_name_ar: str = "المؤشّر",
) -> dict:
    """ملخّص شامل قابل للقراءة: نافذتان (7 و 30 يوم) + trend + anomalies."""
    last_7 = aggregate_window(points, 7, label="آخر أسبوع")
    last_30 = aggregate_window(points, 30, label="آخر 30 يوم")
    trend = detect_trend(points, 30)
    anomalies = detect_anomalies(points)

    return {
        "indicator_ar": indicator_name_ar,
        "last_7_days": {
            "samples": last_7.sample_count,
            "mean": last_7.mean_value,
            "reason_ar": last_7.reason_ar,
        },
        "last_30_days": {
            "samples": last_30.sample_count,
            "mean": last_30.mean_value,
            "reason_ar": last_30.reason_ar,
        },
        "trend": {
            "direction": trend.direction.value,
            "slope_per_day": trend.slope_per_day,
            "confidence": trend.confidence,
            "reason_ar": trend.reason_ar,
        },
        "anomalies": {
            "count": len(anomalies.anomaly_points),
            "has_anomaly": anomalies.has_anomaly,
            "reason_ar": anomalies.reason_ar,
        },
    }
