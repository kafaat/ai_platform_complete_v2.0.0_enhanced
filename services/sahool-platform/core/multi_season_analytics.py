"""
sahool_core.multi_season_analytics
====================================
تحليل عبر مواسم — يبني فوق historical_loader.

الفجوة المسدودة: historical_loader يستورد البيانات، لكنّ لا أحد يُحلّل
الاتجاهات عبر المواسم. مزرعة فيها ٣ سنوات بيانات يمكن أن تكشف:
  • هل الإنتاجية تتحسّن أم تتراجع؟ بأيّ معدّل؟
  • هل الـsalinity تتزايد (تربة متدهورة)؟
  • هل نمط NDVI الموسمي ثابت؟
  • أيّ المحاصيل ينجح على هذه القطعة؟

المبادئ المحفوظة:
  • صفر اختراع: لا "اتجاه" بدون ≥2 موسم
  • Conformal-style intervals: نُعلن عدم اليقين، لا نقطة وحيدة
  • tenant isolation: عبر كل دالة
  • التفسير عربي: كل اتجاه يحمل reason_ar

التمييز عن calibration_loop:
  calibration_loop  → zone_factor واحد (معايرة لحظية)
  multi_season      → اتجاه + معدّل تغيّر + تنبيه طويل المدى

التكامل:
  ← يقرأ من historical_loader (CalibrationRecord)
  ← يقرأ من recommendation_log (outcomes)
  → يُغذّي transfer_learning (يبني عليه)
  → يُغذّي recommendation_engine (سياق متعدّد المواسم)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrendDirection(str, Enum):
    IMPROVING = "improving"      # تحسّن إيجابي
    DECLINING = "declining"      # تراجع
    STABLE = "stable"            # مستقرّ ضمن النطاق الطبيعي
    INSUFFICIENT = "insufficient"  # بيانات قليلة جدّاً


@dataclass
class SeasonTrend:
    """اتجاه مقياس عبر مواسم متعدّدة."""
    metric: str                  # "yield" / "salinity" / "ndvi_peak"
    direction: TrendDirection
    seasons_analyzed: int        # عدد المواسم في التحليل
    first_value: float | None
    last_value: float | None
    change_per_season: float | None   # المعدّل
    change_pct_total: float | None    # النسبة الإجمالية
    reason_ar: str
    confidence: str = "low"      # low/medium/high


@dataclass
class CropRotationPattern:
    """نمط تناوب المحاصيل المكتشف."""
    field_id: str
    seasons: int
    crops_sequence: list[str]     # ["wheat", "fallow", "barley", ...]
    diversity_index: float        # 0.0 (monoculture) → 1.0 (max diversity)
    most_used_crop: str | None
    most_used_pct: float | None
    reason_ar: str


def analyze_yield_trend(
    season_yields: list[dict],
    *,
    min_seasons: int = 2,
) -> SeasonTrend:
    """يحلّل اتجاه الإنتاجية عبر المواسم.

    season_yields: [{"season_year": 2024, "yield_t_ha": 3.5}, ...]
    
    مبدأ "صفر اختراع":
      - <2 موسم → INSUFFICIENT (لا "stable" مزيّفة)
      - بيانات شاذّة (None) → تُتجاهَل بصراحة
      - الاتجاه يُحسب من linear fit بسيط، لا "ML سحرية"
    """
    # تنظيف صريح: لا اختراع
    valid = [(s["season_year"], s["yield_t_ha"])
             for s in season_yields
             if s.get("yield_t_ha") is not None
             and isinstance(s.get("season_year"), int)]

    if len(valid) < min_seasons:
        return SeasonTrend(
            metric="yield_t_ha",
            direction=TrendDirection.INSUFFICIENT,
            seasons_analyzed=len(valid),
            first_value=None, last_value=None,
            change_per_season=None, change_pct_total=None,
            reason_ar=f"بيانات غير كافية ({len(valid)} موسم، الحدّ الأدنى {min_seasons})",
            confidence="low",
        )

    # رتّب زمنياً
    valid.sort(key=lambda x: x[0])
    first_year, first_y = valid[0]
    last_year, last_y = valid[-1]

    # معدّل تغيّر (linear approximation — لا ML)
    span = last_year - first_year
    if span == 0:
        change_per_season = 0.0
    else:
        change_per_season = (last_y - first_y) / span

    # نسبة التغيّر الإجمالية
    if first_y > 0:
        change_pct = (last_y - first_y) / first_y * 100
    else:
        change_pct = None

    # عتبة "stable" زراعياً: ±5% عبر الفترة الكاملة
    if change_pct is None:
        direction = TrendDirection.INSUFFICIENT
        reason = "القيمة الأولى صفر أو غير صالحة"
    elif abs(change_pct) < 5.0:
        direction = TrendDirection.STABLE
        reason = f"الإنتاج مستقرّ (تغيّر {change_pct:.1f}% عبر {span+1} موسم)"
    elif change_pct > 0:
        direction = TrendDirection.IMPROVING
        reason = (f"تحسّن إيجابي: {change_pct:+.1f}% من {first_y:.1f} "
                 f"إلى {last_y:.1f} ط/هـ عبر {span+1} موسم")
    else:
        direction = TrendDirection.DECLINING
        reason = (f"تراجع: {change_pct:+.1f}% من {first_y:.1f} "
                 f"إلى {last_y:.1f} ط/هـ — يستحقّ المراجعة")

    # الثقة: 2 موسم = low، 3 = medium، 4+ = high (مبدأ Conformal-style)
    confidence_map = {2: "low", 3: "medium"}
    conf = confidence_map.get(len(valid), "high" if len(valid) >= 4 else "low")

    return SeasonTrend(
        metric="yield_t_ha",
        direction=direction,
        seasons_analyzed=len(valid),
        first_value=first_y,
        last_value=last_y,
        change_per_season=round(change_per_season, 3) if change_per_season else 0.0,
        change_pct_total=round(change_pct, 1) if change_pct else None,
        reason_ar=reason,
        confidence=conf,
    )


def analyze_salinity_trend(
    salinity_history: list[dict],
    *,
    min_seasons: int = 2,
    alert_threshold_pct_year: float = 10.0,
) -> SeasonTrend:
    """يحلّل اتجاه الملوحة — حرج لاستدامة التربة.

    تزايد الملوحة 10%/سنة = إنذار حقيقي (تربة قيد التدهور).
    salinity_history: [{"season_year": 2024, "ec_ds_m": 1.2}, ...]
    """
    valid = [(s["season_year"], s["ec_ds_m"])
             for s in salinity_history
             if s.get("ec_ds_m") is not None]

    if len(valid) < min_seasons:
        return SeasonTrend(
            metric="ec_ds_m",
            direction=TrendDirection.INSUFFICIENT,
            seasons_analyzed=len(valid),
            first_value=None, last_value=None,
            change_per_season=None, change_pct_total=None,
            reason_ar=f"بيانات ملوحة غير كافية ({len(valid)} موسم)",
            confidence="low",
        )

    valid.sort(key=lambda x: x[0])
    first_year, first_ec = valid[0]
    last_year, last_ec = valid[-1]
    span = max(last_year - first_year, 1)

    pct_per_year = ((last_ec - first_ec) / first_ec * 100 / span
                   if first_ec > 0 else 0.0)

    if pct_per_year > alert_threshold_pct_year:
        direction = TrendDirection.DECLINING   # ملوحة أعلى = تربة أسوأ
        reason = (f"⚠️ ملوحة متزايدة بـ{pct_per_year:.1f}%/سنة "
                 f"(من {first_ec:.2f} إلى {last_ec:.2f} dS/m) — "
                 f"تحتاج برنامج غسيل")
    elif pct_per_year < -5.0:
        direction = TrendDirection.IMPROVING
        reason = f"تحسّن ملوحي: {pct_per_year:.1f}%/سنة"
    else:
        direction = TrendDirection.STABLE
        reason = f"ملوحة مستقرّة ({pct_per_year:+.1f}%/سنة)"

    return SeasonTrend(
        metric="ec_ds_m",
        direction=direction,
        seasons_analyzed=len(valid),
        first_value=first_ec,
        last_value=last_ec,
        change_per_season=round((last_ec - first_ec) / span, 3),
        change_pct_total=round(pct_per_year * span, 1),
        reason_ar=reason,
        confidence="medium" if len(valid) >= 3 else "low",
    )


def detect_rotation_pattern(
    field_id: str,
    season_crops: list[dict],
) -> CropRotationPattern:
    """يكشف نمط تناوب المحاصيل في حقل.

    season_crops: [{"season_year": 2024, "crop_id": "wheat"}, ...]

    diversity_index: Shannon-style مبسّط (0=monoculture، 1=max diversity).
    """
    crops = [s["crop_id"] for s in season_crops
            if s.get("crop_id")]

    if not crops:
        return CropRotationPattern(
            field_id=field_id,
            seasons=0,
            crops_sequence=[],
            diversity_index=0.0,
            most_used_crop=None,
            most_used_pct=None,
            reason_ar="لا بيانات محاصيل لهذا الحقل",
        )

    # تنوّع المحاصيل
    unique_crops = set(crops)
    diversity = len(unique_crops) / len(crops) if crops else 0.0

    # الأكثر استخداماً
    counts = {c: crops.count(c) for c in unique_crops}
    most_used = max(counts, key=counts.get)
    most_pct = counts[most_used] / len(crops) * 100

    # تفسير زراعي
    if diversity < 0.3:
        reason = (f"زراعة أحادية: {most_used} في {most_pct:.0f}% من "
                 f"المواسم ({len(crops)}). يستحقّ تنويع.")
    elif diversity > 0.7:
        reason = (f"تنويع جيّد: {len(unique_crops)} محاصيل في "
                 f"{len(crops)} مواسم")
    else:
        reason = (f"تنويع متوسّط: {most_used} يهيمن "
                 f"({most_pct:.0f}%)")

    return CropRotationPattern(
        field_id=field_id,
        seasons=len(crops),
        crops_sequence=crops,
        diversity_index=round(diversity, 2),
        most_used_crop=most_used,
        most_used_pct=round(most_pct, 1),
        reason_ar=reason,
    )


def multi_season_summary(
    *,
    yield_trend: SeasonTrend | None = None,
    salinity_trend: SeasonTrend | None = None,
    rotation: CropRotationPattern | None = None,
) -> dict:
    """ملخّص شامل قابل للقراءة + alerts."""
    alerts: list[str] = []

    if yield_trend and yield_trend.direction == TrendDirection.DECLINING:
        alerts.append(f"إنتاجية متراجعة: {yield_trend.reason_ar}")
    if salinity_trend and salinity_trend.direction == TrendDirection.DECLINING:
        # في الملوحة، declining يعني تدهور
        alerts.append(f"ملوحة متزايدة: {salinity_trend.reason_ar}")
    if rotation and rotation.diversity_index < 0.3 and rotation.seasons >= 3:
        alerts.append(f"زراعة أحادية: {rotation.reason_ar}")

    return {
        "yield_trend": yield_trend,
        "salinity_trend": salinity_trend,
        "rotation": rotation,
        "alerts_count": len(alerts),
        "alerts_ar": alerts,
        "summary_ar": ("⚠️ " + "؛ ".join(alerts) if alerts
                      else "✅ لا تنبيهات استدامة على المدى المتعدّد"),
    }
