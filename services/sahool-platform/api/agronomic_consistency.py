"""
api/agronomic_consistency.py — فحص التناقض الزراعي (Agronomic Consistency)

الفجوة التي يسدّها (من المراجعة المعماريّة، مستندات ٢ و٣):
  المنصّة تحسب الميزان المائي والمؤشّرات، لكن لا توجد طبقة تتحقّق صراحةً:
  "هل هذا القرار يتناقض منطقيّاً مع الظروف الحاليّة؟"
  مثال خطير: توصية بزيادة الريّ مع توقّع مطر غزير + تربة مشبعة.

ما يفعله (وما لا يفعله — صدق):
  ✓ فحص قاعدي شفّاف لتناقضات زراعيّة معروفة (قواعد محدّدة، لا AI)
  ✓ يُرجع التناقضات مع شدّتها وتفسيرها — لا يحجب القرار، بل يُعلِم
  ✗ ليس "حلّال قيود" كامل ولا محاكاة فيزيائيّة — تلك تحتاج نمذجة أعمق
  ✗ لا يستبدل حكم المهندس الزراعي — يكمّله بإنذار مبكر

يعمل **بعد** توليد التوصية و**قبل** عرضها — طبقة أمان منطقيّة.
متّسق مع مبدأ الصدق: القواعد صريحة ومذكورة، والحدود واضحة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ConflictSeverity(str, Enum):  # noqa: UP042 — keep (str, Enum); StrEnum changes str() output (serialization)
    BLOCK = "block"  # تناقض صريح — يجب مراجعة بشريّة قبل التنفيذ
    WARN = "warn"  # تناقض محتمل — يُعرض للمستخدم مع التوصية
    INFO = "info"  # ملاحظة — لا يمنع لكن يستحقّ الانتباه


@dataclass
class Conflict:
    rule_id: str
    severity: ConflictSeverity
    message_ar: str
    evidence_ar: str  # البيانات التي أطلقت القاعدة (شفافيّة)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message_ar": self.message_ar,
            "evidence_ar": self.evidence_ar,
        }


@dataclass
class ConsistencyResult:
    consistent: bool
    conflicts: list[Conflict] = field(default_factory=list)
    checked_rules: int = 0

    @property
    def requires_review(self) -> bool:
        return any(c.severity == ConflictSeverity.BLOCK for c in self.conflicts)

    def to_dict(self) -> dict:
        return {
            "consistent": self.consistent,
            "requires_human_review": self.requires_review,
            "conflict_count": len(self.conflicts),
            "checked_rules": self.checked_rules,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "note_ar": (
                "فحص قاعدي شفّاف — يُعلِم بالتناقضات لا يحجب القرار. "
                "حكم المهندس الزراعي يبقى المرجع النهائي."
            ),
        }


def check_irrigation_consistency(
    irrigation_delta_pct: float | None = None,  # +زيادة / −خفض مقترح %
    rain_forecast_mm: float | None = None,  # مطر متوقّع قريب
    soil_moisture_ratio: float | None = None,  # θ/θFC الحالي (0-1)
    et0_mm: float | None = None,  # تبخّر-نتح مرجعي
    recommendation_confidence: float | None = None,
) -> ConsistencyResult:
    """يفحص توصية ريّ ضدّ الظروف الحاليّة لكشف التناقضات المنطقيّة.

    كلّ المدخلات اختياريّة — يفحص فقط ما توفّر (صدق: لا يخترع بيانات).
    """
    conflicts: list[Conflict] = []
    checked = 0

    # قاعدة ١: زيادة ريّ مع توقّع مطر غزير
    if irrigation_delta_pct is not None and rain_forecast_mm is not None:
        checked += 1
        if irrigation_delta_pct > 10 and rain_forecast_mm >= 15:
            conflicts.append(
                Conflict(
                    "irrig_vs_rain",
                    ConflictSeverity.BLOCK,
                    "توصية بزيادة الريّ رغم توقّع مطر غزير — تناقض. راجع قبل التنفيذ.",
                    f"زيادة مقترحة {irrigation_delta_pct:.0f}% + مطر متوقّع {rain_forecast_mm:.0f} مم.",
                )
            )

    # قاعدة ٢: زيادة ريّ مع تربة قريبة من التشبّع
    if irrigation_delta_pct is not None and soil_moisture_ratio is not None:
        checked += 1
        if irrigation_delta_pct > 10 and soil_moisture_ratio >= 0.85:
            conflicts.append(
                Conflict(
                    "irrig_vs_saturation",
                    ConflictSeverity.BLOCK,
                    "توصية بزيادة الريّ والتربة شبه مشبعة — خطر غدق وغسل مغذّيات.",
                    f"زيادة {irrigation_delta_pct:.0f}% + رطوبة {soil_moisture_ratio * 100:.0f}% من السعة.",
                )
            )

    # قاعدة ٣: خفض ريّ مع تربة جافّة + تبخّر عالٍ
    if irrigation_delta_pct is not None and soil_moisture_ratio is not None and et0_mm is not None:
        checked += 1
        if irrigation_delta_pct < -10 and soil_moisture_ratio < 0.40 and et0_mm > 6:
            conflicts.append(
                Conflict(
                    "cut_vs_drought",
                    ConflictSeverity.WARN,
                    "توصية بخفض الريّ رغم تربة جافّة وتبخّر عالٍ — خطر إجهاد مائي.",
                    f"خفض {abs(irrigation_delta_pct):.0f}% + رطوبة {soil_moisture_ratio * 100:.0f}% + ET0 {et0_mm:.1f} مم.",
                )
            )

    # قاعدة ٤: ثقة منخفضة على قرار ريّ كبير
    if recommendation_confidence is not None and irrigation_delta_pct is not None:
        checked += 1
        if recommendation_confidence < 0.6 and abs(irrigation_delta_pct) > 20:
            conflicts.append(
                Conflict(
                    "low_confidence_big_change",
                    ConflictSeverity.WARN,
                    "تغيير ريّ كبير بثقة منخفضة — يُفضّل تأكيد ميداني أوّلاً.",
                    f"تغيير {irrigation_delta_pct:+.0f}% بثقة {recommendation_confidence * 100:.0f}%.",
                )
            )

    consistent = len(conflicts) == 0
    return ConsistencyResult(consistent, conflicts, checked)


def check_decision_freshness(
    ndvi_age_days: float | None = None,
    soil_age_days: float | None = None,
    weather_age_hours: float | None = None,
) -> ConsistencyResult:
    """يفحص أعمار البيانات الداخلة في القرار (طبقة freshness صريحة).

    عتبات من المراجعة المعماريّة (المستند ١): NDVI ≤5 أيّام، تربة ≤2 يوم،
    طقس ≤6 ساعات. تجاوزها لا يحجب — يخفض الثقة ويُعلِم.
    """
    conflicts: list[Conflict] = []
    checked = 0
    MAX_NDVI, MAX_SOIL, MAX_WX = 5.0, 2.0, 6.0

    if ndvi_age_days is not None:
        checked += 1
        if ndvi_age_days > MAX_NDVI:
            conflicts.append(
                Conflict(
                    "stale_ndvi",
                    ConflictSeverity.WARN,
                    f"قراءة NDVI قديمة ({ndvi_age_days:.0f} يوم > {MAX_NDVI:.0f}) — خفّض الثقة.",
                    f"عمر NDVI {ndvi_age_days:.0f} يوم.",
                )
            )
    if soil_age_days is not None:
        checked += 1
        if soil_age_days > MAX_SOIL:
            conflicts.append(
                Conflict(
                    "stale_soil",
                    ConflictSeverity.WARN,
                    f"بيانات تربة قديمة ({soil_age_days:.0f} يوم > {MAX_SOIL:.0f}) — خفّض الثقة.",
                    f"عمر بيانات التربة {soil_age_days:.0f} يوم.",
                )
            )
    if weather_age_hours is not None:
        checked += 1
        if weather_age_hours > MAX_WX:
            conflicts.append(
                Conflict(
                    "stale_weather",
                    ConflictSeverity.WARN,
                    f"بيانات طقس قديمة ({weather_age_hours:.0f} ساعة > {MAX_WX:.0f}) — خفّض الثقة.",
                    f"عمر الطقس {weather_age_hours:.0f} ساعة.",
                )
            )

    return ConsistencyResult(len(conflicts) == 0, conflicts, checked)
