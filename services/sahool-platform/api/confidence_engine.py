"""
services/sahool-platform/api/confidence_engine.py — Spatial/Temporal Confidence

المرجع: المراجعة (مستند ١٠.٩.D):
   "النظام يعطي مؤشرات. لكن لا يظهر:
      - confidence intervals
      - cloud contamination scores
      - interpolation uncertainty
      - sensor quality metrics"

✅ الادّعاء صحيح جزئياً. لدينا confidence في yield_heuristics لكنه ليس
   موحّداً للـraster indices. هذا الملف يسدّ الفجوة.

ما يحسبه:
   ١. Cloud Coverage Confidence (Sentinel-2 SCL band)
   ٢. Temporal Freshness (كم يوم منذ آخر observation)
   ٣. Pixel Density (كم بكسل صالح/مغطّى بسحب)
   ٤. Sensor Quality (لو لدينا multiple sources)
   ٥. Composite confidence score (0-1) للـrecommendation النهائيّة

كيف تختلف عن "AI Causal Reasoning" المُدّعى في المستندات السابقة:
   هذه قواعد رياضيّة من remote sensing literature (Justice et al. 1998,
   Vermote et al. 2016). لا "AI"، لا ML — معادلات معيّنة.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
import math


# ─── Confidence levels ──────────────────────────────────────────

class ConfidenceLevel(str, Enum):
    HIGH = "high"           # 0.80-1.0  → trust + act
    MEDIUM = "medium"       # 0.55-0.79 → suggest, verify
    LOW = "low"             # 0.35-0.54 → warn user
    VERY_LOW = "very_low"   # 0.00-0.34 → don't show / require ground-truth


def level_from_score(score: float) -> ConfidenceLevel:
    if score >= 0.80: return ConfidenceLevel.HIGH
    if score >= 0.55: return ConfidenceLevel.MEDIUM
    if score >= 0.35: return ConfidenceLevel.LOW
    return ConfidenceLevel.VERY_LOW


# ─── Component scores ───────────────────────────────────────────

@dataclass
class CloudConfidence:
    """Sentinel-2 cloud assessment.

    مرجع: ESA Sentinel-2 SCL (Scene Classification Layer)
    SCL values:
        0=NO_DATA, 1=SATURATED, 2=DARK_AREA, 3=CLOUD_SHADOW,
        4=VEGETATION, 5=BARE_SOIL, 6=WATER, 7=UNCLASSIFIED,
        8=CLOUD_MEDIUM_PROB, 9=CLOUD_HIGH_PROB, 10=THIN_CIRRUS, 11=SNOW
    """
    cloud_pct: float            # 0-100, % of pixels classified as cloud
    cloud_shadow_pct: float = 0
    cirrus_pct: float = 0
    valid_pixel_pct: float = 100  # what's left for analysis

    @property
    def score(self) -> float:
        """0=fully clouded, 1=clear."""
        contamination = (
            self.cloud_pct * 1.0 +
            self.cloud_shadow_pct * 0.8 +
            self.cirrus_pct * 0.4
        ) / 100
        return max(0.0, 1.0 - contamination)


@dataclass
class TemporalConfidence:
    """كم يوم منذ آخر observation. الأحدث = أعلى ثقة."""
    days_since_observation: int
    typical_revisit_days: int = 5      # Sentinel-2 revisit time

    @property
    def score(self) -> float:
        """يبدأ من 1.0 (نفس اليوم) وينخفض exponentially."""
        if self.days_since_observation <= 0:
            return 1.0
        # Decay: 0.95^days for first revisit_days, then steeper
        if self.days_since_observation <= self.typical_revisit_days:
            return 0.95 ** self.days_since_observation
        # Beyond revisit: serious aging
        beyond = self.days_since_observation - self.typical_revisit_days
        return max(0.1, (0.95 ** self.typical_revisit_days) * (0.85 ** beyond))


@dataclass
class CoverageConfidence:
    """نسبة الـpixels الفعليّة المتوفّرة من الـregion المطلوبة."""
    pixels_observed: int
    pixels_expected: int

    @property
    def score(self) -> float:
        if self.pixels_expected <= 0:
            return 0.0
        ratio = self.pixels_observed / self.pixels_expected
        # M3 FIX: خريطة متّصلة ورتيبة بدل قفزة عند 0.5 (السابق: 0.49→0.245 مقابل
        # 0.50→0.50). تحت 50% نعاقب بانحناء تربيعي يلتقي القيمة 0.5 عند ratio=0.5
        # (متّصل)، وفوقها خطّي حتّى 1.0.
        if ratio < 0.5:
            return 2.0 * ratio * ratio
        return min(1.0, ratio)


@dataclass
class SourceConfidence:
    """عدد المصادر المُؤكِّدة. multiple sources = أعلى."""
    source_count: int               # كم sensor/satellite يؤكّد القراءة
    has_ground_truth: bool = False  # عيّنة مختبر أو in-situ sensor

    @property
    def score(self) -> float:
        base = min(1.0, 0.5 + (self.source_count - 1) * 0.15)
        if self.has_ground_truth:
            base = min(1.0, base + 0.2)
        return base


# ─── Composite confidence ──────────────────────────────────────

@dataclass
class IndicatorConfidence:
    """confidence معاملة شاملة لقراءة معيّنة (مثلاً NDVI mean لحقل)."""
    indicator_name: str             # "ndvi", "moisture", "ndwi"...
    measurement_value: Optional[float]

    cloud: CloudConfidence
    temporal: TemporalConfidence
    coverage: CoverageConfidence
    source: SourceConfidence

    # Computed
    composite_score: float = 0.0
    level: ConfidenceLevel = ConfidenceLevel.VERY_LOW
    reasons_ar: List[str] = field(default_factory=list)
    recommendation_ar: str = ""

    def __post_init__(self):
        # Weighted geometric mean (أيّ ضعف خطير يُخفّض الكل)
        scores = [
            (self.cloud.score, 0.30),
            (self.temporal.score, 0.30),
            (self.coverage.score, 0.25),
            (self.source.score, 0.15),
        ]
        # Geometric mean weighted
        log_sum = sum(w * math.log(max(0.01, s)) for s, w in scores)
        self.composite_score = round(math.exp(log_sum), 3)
        self.level = level_from_score(self.composite_score)

        # Reasons
        if self.cloud.score < 0.6:
            self.reasons_ar.append(f"تغطية سحب عالية ({self.cloud.cloud_pct:.0f}%)")
        if self.temporal.score < 0.5:
            self.reasons_ar.append(f"البيانات قديمة ({self.temporal.days_since_observation} يوم)")
        if self.coverage.score < 0.6:
            self.reasons_ar.append(f"تغطية البكسلات ضعيفة ({self.coverage.pixels_observed}/{self.coverage.pixels_expected})")
        if self.source.score < 0.5:
            self.reasons_ar.append("مصدر واحد فقط بدون تأكيد ميداني")

        # Recommendation
        if self.level == ConfidenceLevel.HIGH:
            self.recommendation_ar = "البيانات موثوقة — يمكن الاعتماد عليها."
        elif self.level == ConfidenceLevel.MEDIUM:
            self.recommendation_ar = "البيانات معقولة — تحقّق ميدانياً قبل قرار حسّاس."
        elif self.level == ConfidenceLevel.LOW:
            self.recommendation_ar = "ثقة منخفضة — لا تتّخذ قرارات صرف ري/سماد بناءً عليها وحدها."
        else:
            self.recommendation_ar = "ثقة شبه معدومة — انتظر صورة جديدة أو اطلب عيّنة ميدانيّة."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator": self.indicator_name,
            "value": self.measurement_value,
            "confidence": {
                "score": self.composite_score,
                "level": self.level.value,
                "components": {
                    "cloud": round(self.cloud.score, 3),
                    "temporal": round(self.temporal.score, 3),
                    "coverage": round(self.coverage.score, 3),
                    "source": round(self.source.score, 3),
                },
            },
            "reasons_ar": self.reasons_ar,
            "recommendation_ar": self.recommendation_ar,
        }


# ─── Helpers ────────────────────────────────────────────────────

def compute_ndvi_confidence(
    ndvi_value: float,
    observation_date: datetime,
    field_area_ha: float,
    cloud_pct: float = 0,
    cloud_shadow_pct: float = 0,
    cirrus_pct: float = 0,
    pixels_observed: Optional[int] = None,
    has_ground_truth: bool = False,
    now: Optional[datetime] = None,
) -> IndicatorConfidence:
    """واجهة مُبسَّطة لحساب confidence لقراءة NDVI."""
    if now is None:
        now = datetime.now(timezone.utc)

    days = max(0, (now - observation_date).days)

    # Sentinel-2 native resolution: 10m × 10m = 100 m² per pixel
    expected_pixels = max(1, int(field_area_ha * 10000 / 100))
    obs_pixels = pixels_observed if pixels_observed is not None else expected_pixels

    return IndicatorConfidence(
        indicator_name="NDVI",
        measurement_value=ndvi_value,
        cloud=CloudConfidence(
            cloud_pct=cloud_pct,
            cloud_shadow_pct=cloud_shadow_pct,
            cirrus_pct=cirrus_pct,
            valid_pixel_pct=max(0, 100 - cloud_pct - cloud_shadow_pct - cirrus_pct),
        ),
        temporal=TemporalConfidence(days_since_observation=days),
        coverage=CoverageConfidence(
            pixels_observed=obs_pixels,
            pixels_expected=expected_pixels,
        ),
        source=SourceConfidence(
            source_count=1,  # Sentinel-2 by default
            has_ground_truth=has_ground_truth,
        ),
    )
