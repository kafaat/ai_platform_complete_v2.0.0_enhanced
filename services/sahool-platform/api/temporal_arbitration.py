"""
services/sahool-platform/api/temporal_arbitration.py — Temporal Consistency

المرجع: المراجعة (مستند ١٠.٩.C):
   "Sentinel كل 5 أيام، الطقس يومي، ET0 يومي، overlays لحظية.
    لكن لا يوجد temporal arbitration engine.
    قد تقارن NDVI من تاريخ مع ET0 من تاريخ مختلف ثم تنتج توصية خاطئة سببياً."

✅ الادّعاء صحيح. هذا الملف يمنع mixing بين بيانات بـtimestamps متباعدة جدّاً.

ما يفعله:
   ١. يأخذ مجموعة measurements مع timestamps
   ٢. يتحقّق أنّ الفروقات الزمنيّة ضمن النطاق المقبول لكل combination
   ٣. لو لا، يرجع warning مع الفجوة الزمنيّة

ما لا يفعله:
   ✗ time-travel "consciousness"
   ✗ ML temporal reasoning
   ✗ "Causal AI"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ─── Measurement types ──────────────────────────────────────────

class DataSource(str, Enum):
    NDVI_SENTINEL = "ndvi_sentinel"      # ~5 day revisit
    NDWI_SENTINEL = "ndwi_sentinel"
    SOIL_MOISTURE_SAT = "soil_moisture_sat"  # ~10 day
    WEATHER_ETO = "weather_eto"          # daily
    WEATHER_RAIN = "weather_rain"        # daily
    WEATHER_TEMP = "weather_temp"        # hourly
    SOIL_LAB = "soil_lab"                # rare (months)
    SOIL_SENSOR = "soil_sensor"          # hourly/daily
    USER_OBSERVATION = "user_observation"  # whenever
    YIELD_HARVEST = "yield_harvest"      # once per season


# Max acceptable age in days, per source
MAX_FRESHNESS_DAYS: Dict[DataSource, int] = {
    DataSource.NDVI_SENTINEL:     14,   # weekly revisit acceptable
    DataSource.NDWI_SENTINEL:     14,
    DataSource.SOIL_MOISTURE_SAT: 14,
    DataSource.WEATHER_ETO:       3,    # ET0 changes fast
    DataSource.WEATHER_RAIN:      3,
    DataSource.WEATHER_TEMP:      1,
    DataSource.SOIL_LAB:          365,  # rarely changes
    DataSource.SOIL_SENSOR:       7,
    DataSource.USER_OBSERVATION:  30,
    DataSource.YIELD_HARVEST:     365,
}


# Max acceptable gap between two sources when combining (days)
# Default tolerances (crop-agnostic baseline)
PAIRWISE_MAX_GAP: Dict[Tuple[DataSource, DataSource], int] = {
    # NDVI + ET0 used together for water stress → must be within 7 days
    (DataSource.NDVI_SENTINEL, DataSource.WEATHER_ETO): 7,
    (DataSource.NDVI_SENTINEL, DataSource.WEATHER_RAIN): 7,
    (DataSource.NDVI_SENTINEL, DataSource.SOIL_MOISTURE_SAT): 14,
    (DataSource.NDVI_SENTINEL, DataSource.SOIL_SENSOR): 7,
    # Lab + sat indices can be far apart (soil chemistry doesn't change quickly)
    (DataSource.SOIL_LAB, DataSource.NDVI_SENTINEL): 90,
    # Rain + ET0 same time scale
    (DataSource.WEATHER_RAIN, DataSource.WEATHER_ETO): 1,
}


# ─── Crop-aware tolerance multipliers ───────────────────────────
# المراجعة طرحت: "tolerance في القمح ≠ البن ≠ الخضروات"
#
# المنطق الزراعي:
#   - الخضروات (طماطم، فلفل): تتغيّر بسرعة، tolerance أقصر
#   - الحبوب (قمح، شعير): متوسّط
#   - الأشجار (بن، نخيل): تتغيّر ببطء، tolerance أطول
#
# الـmultiplier يُطبَّق على الـbase tolerance:
#   effective_tolerance = base × multiplier

# ⚠ UNVALIDATED DEFAULT — needs agronomist review (جلسة التصحيح الذاتي)
# القيم أدناه تقديريّة ومنطقيّة لكنّها لم تُتحقَّق من مصدر علمي/ميداني موثَّق.
# يجب مراجعتها مع مهندس زراعي يمني قبل الاعتماد عليها في قرارات حقيقيّة.
CROP_TOLERANCE_MULTIPLIER: Dict[str, float] = {
    # خضروات حسّاسة (تتغيّر يومياً)
    "tomato":   0.5,
    "pepper":   0.5,
    "cucumber": 0.5,
    "lettuce":  0.5,
    "onion":    0.7,
    "potato":   0.7,

    # حبوب متوسّطة (تتغيّر أسبوعياً)
    "wheat":    1.0,
    "barley":   1.0,
    "corn":     1.0,
    "sorghum":  1.0,
    "rice":     1.0,

    # محاصيل علفيّة
    "alfalfa":  0.8,    # multi-cut: حسّاس للري

    # أشجار وشُجَيرات (تتغيّر ببطء)
    "coffee":   1.8,
    "qat":      1.5,
    "dates":    2.0,
    "mango":    1.8,
    "citrus":   1.8,
    "olive":    2.0,
}

# Phenological stage modifier (مرحلة النموّ)
# الـstages الحرجة (تزهير، حبيبة) تحتاج tolerance أقصر
# ⚠ UNVALIDATED DEFAULT — needs agronomist review (جلسة التصحيح الذاتي)
# القيم أدناه تقديريّة ومنطقيّة لكنّها لم تُتحقَّق من مصدر علمي/ميداني موثَّق.
# يجب مراجعتها مع مهندس زراعي يمني قبل الاعتماد عليها في قرارات حقيقيّة.
STAGE_TOLERANCE_MODIFIER: Dict[str, float] = {
    "germination":    0.6,   # الإنبات: حسّاس جدّاً
    "flowering":      0.5,   # الأزهار: الأهمّ في الحبوب
    "grain_filling":  0.6,   # امتلاء الحبّة: حسّاس
    "fruit_setting":  0.5,   # عقد الثمار: حسّاس
    # المراحل العاديّة
    "vegetative":     1.0,
    "maturity":       1.2,   # النضج: tolerance أطول
    "post_harvest":   2.0,
}


def _get_pair_limit(
    a: DataSource, b: DataSource,
    crop: Optional[str] = None,
    stage: Optional[str] = None,
) -> int:
    """يجلب الحدّ الأقصى للفارق الزمني بين مصدرين.

    Crop + stage aware (لو متوفّر):
      effective = base_tolerance × crop_mult × stage_mult
    """
    if (a, b) in PAIRWISE_MAX_GAP:
        base = PAIRWISE_MAX_GAP[(a, b)]
    elif (b, a) in PAIRWISE_MAX_GAP:
        base = PAIRWISE_MAX_GAP[(b, a)]
    else:
        base = min(MAX_FRESHNESS_DAYS[a], MAX_FRESHNESS_DAYS[b])

    multiplier = 1.0
    if crop:
        multiplier *= CROP_TOLERANCE_MULTIPLIER.get(crop.lower(), 1.0)
    if stage:
        multiplier *= STAGE_TOLERANCE_MODIFIER.get(stage.lower(), 1.0)

    # نضمن لا يُصبح 0 أو سالب
    return max(1, int(base * multiplier))


# ─── Result types ───────────────────────────────────────────────

@dataclass
class Measurement:
    """قراءة واحدة من مصدر."""
    source: DataSource
    timestamp: datetime
    value: Optional[float] = None
    metadata: Optional[dict] = None


@dataclass
class TemporalIssue:
    severity: str        # "warning" | "error"
    code: str
    message_ar: str


@dataclass
class TemporalArbitrationResult:
    valid: bool
    issues: List[TemporalIssue] = field(default_factory=list)
    oldest_measurement: Optional[DataSource] = None
    newest_measurement: Optional[DataSource] = None
    age_span_days: Optional[int] = None


# ─── Main arbiter ───────────────────────────────────────────────

class TemporalArbiter:
    """يفحص consistency زمنيّة لمجموعة measurements."""

    def __init__(self, now: Optional[datetime] = None):
        self.now = now or datetime.now(timezone.utc)

    def check_freshness(self, m: Measurement) -> Optional[TemporalIssue]:
        """يفحص هل measurement واحدة too stale."""
        age_days = (self.now - m.timestamp).days
        max_age = MAX_FRESHNESS_DAYS.get(m.source, 30)

        if age_days > max_age:
            return TemporalIssue(
                severity="warning",
                code="data_stale",
                message_ar=(
                    f"{m.source.value} قديم ({age_days} يوم، "
                    f"الحدّ المعتاد {max_age})"
                ),
            )
        return None

    def check_combination(
        self,
        measurements: List[Measurement],
        crop: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> TemporalArbitrationResult:
        """
        يفحص هل مجموعة measurements متوافقة زمنياً للاستخدام معاً.

        Args:
            measurements: القراءات
            crop: اختياري — لتطبيق crop-specific tolerance
            stage: اختياري — لتطبيق phenological stage modifier

        Example: لو الـclient يطلب توصية ري بناءً على:
           - NDVI من ٢٠٢٦-٠٢-٠١
           - ET0 من ٢٠٢٦-٠٢-٢٠
           الفجوة ١٩ يوم، الحدّ المسموح ٧ → warning
           لكن لو محصول=tomato + stage=flowering: 7 × 0.5 × 0.5 = 2 يوم → error
        """
        if not measurements:
            return TemporalArbitrationResult(valid=True)

        issues: List[TemporalIssue] = []

        # ١. تحقّق freshness لكل واحدة
        for m in measurements:
            iss = self.check_freshness(m)
            if iss:
                issues.append(iss)

        # ٢. تحقّق pairwise gaps (crop+stage aware)
        for i, m1 in enumerate(measurements):
            for m2 in measurements[i + 1:]:
                gap_days = abs((m1.timestamp - m2.timestamp).days)
                limit = _get_pair_limit(m1.source, m2.source, crop=crop, stage=stage)

                if gap_days > limit:
                    severity = "warning" if gap_days <= limit * 2 else "error"
                    crop_note = f" [crop={crop}]" if crop else ""
                    stage_note = f" [stage={stage}]" if stage else ""
                    issues.append(TemporalIssue(
                        severity=severity,
                        code="pair_gap_exceeded",
                        message_ar=(
                            f"فارق زمني كبير بين {m1.source.value} و {m2.source.value}: "
                            f"{gap_days} يوم (الحدّ {limit}){crop_note}{stage_note}"
                        ),
                    ))

        # ٣. احسب الـspan
        timestamps = [m.timestamp for m in measurements]
        oldest = min(measurements, key=lambda m: m.timestamp)
        newest = max(measurements, key=lambda m: m.timestamp)
        span_days = (newest.timestamp - oldest.timestamp).days

        has_errors = any(i.severity == "error" for i in issues)

        return TemporalArbitrationResult(
            valid=not has_errors,
            issues=issues,
            oldest_measurement=oldest.source,
            newest_measurement=newest.source,
            age_span_days=span_days,
        )

    def can_combine_for_recommendation(
        self,
        measurements: List[Measurement],
        recommendation_type: str,
        crop: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Tuple[bool, List[TemporalIssue]]:
        """
        Higher-level: هل آمن أن نولّد توصية من هذه الـmeasurements؟

        recommendation_type examples:
            - "irrigation":       يحتاج NDVI + ET0 + soil_moisture (~7 day window)
            - "fertilizer":       NDVI + soil_lab (~90 day window OK)
            - "harvest_window":   NDVI + weather forecast (~3 day window)
        """
        result = self.check_combination(measurements, crop=crop, stage=stage)

        # نسمح بـwarnings لكن نرفض errors
        errors = [i for i in result.issues if i.severity == "error"]
        return (not errors, result.issues)
