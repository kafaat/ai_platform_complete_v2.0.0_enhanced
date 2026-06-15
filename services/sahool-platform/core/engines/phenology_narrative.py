"""core/engines/phenology_narrative.py — سرد نموّ الحقل الفينولوجي من سلسلة الأقمار.

استلهام صادق من فكرة «Sense of Growth / التصوير المتأخّر» — **بلا عتاد**:
بدل كاميرا IoT لكلّ قطعة (لا تناسب ريف اليمن: كهرباء/شبكة/كلفة)، نستخدم ما
نملكه: **سلسلة مؤشّرات Sentinel-2 الزمنيّة (NDVI)** كـ«تايم‑لابس نموّ من الأقمار».

ما يضيفه (الفجوة المسدودة): الموجود إمّا لحظيّ (spectral_stress_bridge) أو
عمليّاتي (field_workspace timeline) — لا **منحنى نموّ فينولوجي سرديّ**. هذا يعيد
بناء مسار النموّ عبر الموسم، يصنّف الطور (إنبات/خضري/ذروة/شيخوخة)، ويكشف
**شذوذ النموّ** (السيناريو الزراعي الوحيد في المنتج المُلهِم).

⚠ المبدأ (اتّساقاً مع spectral_stress_bridge + confidence_gate + الصدق):
  • مدفوع بالبيانات: دون حدّ أدنى من المشاهد الزمنيّة (multi-temporal) لا سرد.
  • لا قيم أجنبيّة مُقحَمة: «الشذوذ» يُحكَم فقط مقابل **مظروف متوقَّع مُمرَّر**
    (من بطاقات المحاصيل/بيانات محلّيّة) — بدونه: سرد وصفيّ فقط، لا ادّعاء شذوذ.
  • قيم NDVI غير المنتهية (NaN/inf) تُتجاهَل (لا تُفسَد السلسلة).
  • شفّاف حتميّ: يُظهر المسار والطور والثقة (من عدد المشاهد) ونقص التغطية.
  • لا تسويق/«جمال»: مخرَج قرار زراعي (طور/شذوذ)، لا فيديو ترويجي.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# حدود وصفيّة عامّة لمستوى NDVI (لا خاصّة بمحصول — التصنيف من شكل المنحنى).
_BARE_FLOOR = 0.20  # دون هذا: تربة عارية/إنبات مبكّر
# حدّ أدنى من المشاهد الزمنيّة لسرد ذي معنى (يطابق MIN_TEMPORAL_SCENES في الجاهزيّة).
MIN_OBSERVATIONS = 4


class GrowthPhase(str, Enum):
    EMERGENCE = "emergence"  # إنبات (NDVI منخفض، بداية الموسم)
    VEGETATIVE = "vegetative"  # نموّ خضري (NDVI يرتفع نحو الذروة)
    PEAK = "peak"  # الذروة (تويج/طرد سنابل)
    SENESCENCE = "senescence"  # شيخوخة/نضج (NDVI ينحدر بعد الذروة)
    UNKNOWN = "unknown"  # تعذّر التصنيف


class NarrativeConfidence(str, Enum):
    INSUFFICIENT = "insufficient"  # مشاهد أقلّ من الحدّ — لا سرد
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class NDVIObservation:
    """مشاهدة NDVI واحدة لحقل (من سلسلة Sentinel-2 الزمنيّة)."""

    date: str  # ISO date
    ndvi: float
    days_after_planting: int | None = None

    @property
    def is_valid(self) -> bool:
        return isinstance(self.ndvi, (int, float)) and math.isfinite(self.ndvi)


def _confidence_band(n_valid: int) -> NarrativeConfidence:
    """ثقة السرد من عدد المشاهد الصالحة (multi-temporal كلّما زاد قوي)."""
    if n_valid < MIN_OBSERVATIONS:
        return NarrativeConfidence.INSUFFICIENT
    if n_valid < 6:
        return NarrativeConfidence.LOW
    if n_valid < 10:
        return NarrativeConfidence.MEDIUM
    return NarrativeConfidence.HIGH


def build_growth_narrative(
    observations: list[NDVIObservation],
    *,
    crop: str,
    peak_ndvi_floor: float | None = None,
    expected_peak_dap_min: int | None = None,
) -> dict:
    """يبني سرد نموّ فينولوجي من سلسلة NDVI زمنيّة — حتميّ صادق، بلا عتاد.

    peak_ndvi_floor / expected_peak_dap_min: مظروف متوقَّع اختياريّ (من بطاقة
    المحصول/بيانات محلّيّة). بدونه: سرد وصفيّ فقط (لا ادّعاء شذوذ — لا قيم مُقحَمة).
    """
    valid = [o for o in observations if o.is_valid]
    n_valid = len(valid)
    confidence = _confidence_band(n_valid)

    if confidence == NarrativeConfidence.INSUFFICIENT:
        return {
            "crop": crop,
            "confidence": confidence.value,
            "n_observations": len(observations),
            "n_valid": n_valid,
            "trajectory": [],
            "current_phase": GrowthPhase.UNKNOWN.value,
            "anomalies": [],
            "reason_ar": (
                f"مشاهد زمنيّة صالحة {n_valid} < الحدّ الأدنى {MIN_OBSERVATIONS} — "
                "لا سرد نموّ (السرد يحتاج سلسلة متعدّدة الأزمنة، لا لقطة)."
            ),
        }

    # ترتيب زمنيّ: بأيّام-بعد-الزراعة إن توفّرت، وإلّا بالتاريخ. المشاهد بلا DAP
    # تُرتَّب أخيراً (لا تُقحَم في المقدّمة كأنّها يوم 0) لتفادي خلط السلسلة المختلطة.
    ordered = sorted(
        valid,
        key=lambda o: (
            o.days_after_planting is None,
            o.days_after_planting if o.days_after_planting is not None else 0,
            o.date,
        ),
    )
    ndvis = [o.ndvi for o in ordered]
    peak_idx = max(range(len(ndvis)), key=lambda i: ndvis[i])
    peak_ndvi = ndvis[peak_idx]
    peak_dap = ordered[peak_idx].days_after_planting
    # لا نموّ فعليّ: حتّى الذروة دون عتبة التربة العارية ⇒ لا ذروة/شيخوخة وهميّة.
    peak_below_floor = peak_ndvi < _BARE_FLOOR

    def _phase(i: int) -> GrowthPhase:
        if peak_below_floor:
            return GrowthPhase.EMERGENCE  # السلسلة كلّها دون العتبة — إنبات لا أكثر
        if ndvis[i] < _BARE_FLOOR and i <= peak_idx:
            return GrowthPhase.EMERGENCE
        if i < peak_idx:
            return GrowthPhase.VEGETATIVE
        if i == peak_idx:
            return GrowthPhase.PEAK
        return GrowthPhase.SENESCENCE

    trajectory = [
        {
            "date": o.date,
            "ndvi": round(o.ndvi, 3),
            "days_after_planting": o.days_after_planting,
            "phase": _phase(i).value,
        }
        for i, o in enumerate(ordered)
    ]
    current_phase = _phase(len(ordered) - 1)

    # كشف الشذوذ — فقط مقابل مظروف متوقَّع مُمرَّر (لا قيم مُقحَمة).
    anomalies: list[dict] = []
    if peak_ndvi_floor is not None and peak_ndvi < peak_ndvi_floor:
        anomalies.append(
            {
                "type": "low_peak",
                "severity": "warning",
                "note_ar": (
                    f"ذروة NDVI {peak_ndvi:.2f} دون المتوقّع ({peak_ndvi_floor:.2f}) — "
                    "نموّ خضري ضعيف محتمل (إجهاد/إنبات ضعيف؟). يُراجَع ميدانيّاً."
                ),
            }
        )
    if (
        expected_peak_dap_min is not None
        and current_phase == GrowthPhase.SENESCENCE
        and peak_dap is not None
        and peak_dap < expected_peak_dap_min
    ):
        anomalies.append(
            {
                "type": "early_senescence",
                "severity": "warning",
                "note_ar": (
                    f"تدهور مبكّر: الذروة عند {peak_dap} يوم (المتوقّع ≥{expected_peak_dap_min}) "
                    "ثمّ انحدار — شيخوخة مبكّرة محتملة (جفاف/مرض/نقص مغذّيات؟). يُراجَع."
                ),
            }
        )

    return {
        "crop": crop,
        "confidence": confidence.value,
        "n_observations": len(observations),
        "n_valid": n_valid,
        "trajectory": trajectory,
        "current_phase": current_phase.value,
        "peak_ndvi": round(peak_ndvi, 3),
        "peak_days_after_planting": peak_dap,
        "anomalies": anomalies,
        "anomaly_check_available": peak_ndvi_floor is not None or expected_peak_dap_min is not None,
        "honesty_note_ar": (
            "سرد نموّ من سلسلة NDVI القمريّة (بديل صادق للتايم‑لابس بلا عتاد). الطور "
            "من شكل المنحنى. الشذوذ يُحكَم فقط مقابل مظروف متوقَّع مُمرَّر (لا قيم "
            "أجنبيّة مُقحَمة)؛ بدونه سرد وصفيّ. الثقة من عدد المشاهد — تنبيه يُراجَع ميدانيّاً."
        ),
    }
