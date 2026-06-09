"""
sahool_core.source_of_truth
=============================
Arbitration المصادر المتضاربة — نقطة الحقيقة الواحدة.

الفجوة المسدودة: الوثيقة كشفت مشكلة جوهرية في الأنظمة الزراعية:
  "هل مصدر الحقيقة للإنتاج هو:
    • combine harvester؟
    • ERP؟
    • user edits؟"

في سهول، نفس السؤال يظهر بصور أبسط لكن أعمق:
  • NDVI من قمر صناعي = 0.55
  • NDVI من حسّاس ميداني = 0.48
  • أيّهما يدخل recommendation_engine؟

بدون حاكم صريح، النظام يصبح غير قابل للتفسير. وقد كان غير قابل
للتفسير حتى الآن — لأنّ observations EAV يقبل من 5+ مصادر بلا
arbitration.

المبدأ الحاكم:
  • LAB measurement > MANUAL entry > SENSOR > SATELLITE > HISTORICAL
  • الأحدث أوزن من الأقدم (decay زمني)
  • التضارب الكبير = إعلان صريح، لا "خوارزمية تختار"
  • الشفّافية: كل قرار arbitration يحمل reason_ar

التمييز عن evidence_class:
  evidence_class: يحدّد سقف الثقة (low/medium/high) للمشاهدة الواحدة
  source_of_truth: يفصل بين عدّة مشاهدات لنفس المتغيّر

التمييز عن validation:
  validation: هل القيمة في النطاق الفيزيائي؟
  source_of_truth: أيّ قيمة من بين متعدّدة؟

التكامل:
  ← يأخذ observations من مصادر مختلفة
  → يُرجع canonical value + reasoning
  → يُستخدم في field_bundle قبل تغذية recommendation_engine
  → يُستخدم في farm_memory للذاكرة الموحّدة
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from core.canonical_schemas import ObservationSource


# ─── سلّم الموثوقية ──────────────────────────────────────────────
# مبدأ زراعي صريح: المختبر يحكم على الاستشعار.
# هذا تطبيق آخر للمبدأ السهولي #٢ ("الاستشعار يوجّه، المختبر يحكم").

_SOURCE_PRIORITY = {
    ObservationSource.LAB: 100,         # دليل قطعي
    ObservationSource.MANUAL: 80,       # إدخال بشري مُتحقَّق
    ObservationSource.SENSOR: 60,       # حسّاس ميداني معاير
    ObservationSource.DRONE: 50,        # رصد جوّي قريب
    ObservationSource.SATELLITE: 40,    # قمر صناعي (resolution منخفض)
    ObservationSource.HISTORICAL: 30,   # بيانات تاريخية (قد تكون stale)
}


class ConflictSeverity(str, Enum):
    """شدّة التضارب بين مصادر متعدّدة."""
    NONE = "none"            # مصدر واحد فقط
    AGREEMENT = "agreement"  # كلّ المصادر ضمن tolerance
    MINOR = "minor"          # فرق <15%
    MAJOR = "major"          # فرق 15-30%
    CRITICAL = "critical"    # فرق >30% — يحتاج مراجعة بشرية


@dataclass
class Observation:
    """تمثيل خفيف لمشاهدة (نسخة مبسّطة من ObservationSchema)."""
    value: float
    source: ObservationSource
    confidence: str               # "low"/"medium"/"high"
    measured_at: str              # ISO datetime
    observable_id: str
    method: str | None = None


@dataclass
class ArbitrationResult:
    """نتيجة arbitration — مع reasoning كامل."""
    canonical_value: float | None        # القيمة المُختارة (None إن critical)
    canonical_source: ObservationSource | None
    canonical_confidence: str            # سقف الثقة بعد arbitration
    severity: ConflictSeverity
    competing_sources: int               # عدد المصادر التي شاركت
    spread_pct: float                    # نطاق التباين
    reasoning_ar: str
    rejected_sources: list[dict] = field(default_factory=list)
    requires_human_review: bool = False


# ─── الـcore arbitration ─────────────────────────────────────────

def _age_decay_factor(measured_at: str,
                     current: datetime | None = None,
                     half_life_days: int = 30) -> float:
    """عامل تخفيف بسبب العمر. 30 يوم half-life افتراضياً.

    حسّاس قرأ منذ ساعة > قمر صناعي قرأ منذ شهر.
    مبدأ صفر اختراع: تنسيق time غير صالح → 1.0 (لا penalty حتى نعرف)."""
    if current is None:
        current = datetime.now()
    try:
        m = datetime.fromisoformat(measured_at.replace("Z", ""))
    except (ValueError, AttributeError):
        try:
            m = datetime.strptime(measured_at[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return 1.0
    age_days = max((current - m).days, 0)
    # exponential decay: نصف الوزن كل half_life_days
    return 0.5 ** (age_days / half_life_days)


def _classify_spread(values: list[float]) -> tuple[ConflictSeverity, float]:
    """يقيس شدّة التباين بين قيم. يُرجع (severity، spread_pct)."""
    if len(values) <= 1:
        return ConflictSeverity.NONE, 0.0
    mn, mx = min(values), max(values)
    if mn == mx:
        return ConflictSeverity.AGREEMENT, 0.0
    denom = max(abs(mn), abs(mx), 1e-9)
    spread = (mx - mn) / denom * 100

    if spread < 15:
        return ConflictSeverity.AGREEMENT, spread
    elif spread < 30:
        return ConflictSeverity.MINOR, spread
    elif spread < 50:
        return ConflictSeverity.MAJOR, spread
    else:
        return ConflictSeverity.CRITICAL, spread


def arbitrate(
    observations: list[Observation],
    *,
    current_time: datetime | None = None,
    critical_threshold_pct: float = 50.0,
) -> ArbitrationResult:
    """يحلّ التضارب بين مصادر متعدّدة لنفس المتغيّر.

    خوارزمية شفّافة (لا "ML سحرية"):
      1. كل مشاهدة تحصل على score = priority × age_decay × confidence_multiplier
      2. الأعلى score → canonical
      3. لو الفرق >50%: critical → require human review
      4. القيم المرفوضة تُسجَّل (للـaudit)

    مبدأ "صفر اختراع":
      • قائمة فارغة → None صريح
      • critical spread → لا canonical_value (لا تخمين)
      • معايرة لا تكفي → confidence مخفّضة"""

    if not observations:
        return ArbitrationResult(
            canonical_value=None, canonical_source=None,
            canonical_confidence="none",
            severity=ConflictSeverity.NONE,
            competing_sources=0, spread_pct=0.0,
            reasoning_ar="لا مشاهدات للـarbitration",
        )

    # فلترة: لا نشتغل على قيم None
    valid = [o for o in observations if o.value is not None]
    if not valid:
        return ArbitrationResult(
            canonical_value=None, canonical_source=None,
            canonical_confidence="none",
            severity=ConflictSeverity.NONE,
            competing_sources=0, spread_pct=0.0,
            reasoning_ar="كل المشاهدات بقيمة None",
        )

    # حالة مصدر واحد: لا arbitration، فقط شفّافية
    if len(valid) == 1:
        obs = valid[0]
        return ArbitrationResult(
            canonical_value=obs.value,
            canonical_source=obs.source,
            canonical_confidence=obs.confidence,
            severity=ConflictSeverity.NONE,
            competing_sources=1,
            spread_pct=0.0,
            reasoning_ar=(f"مصدر واحد: {obs.source.value} "
                         f"({obs.confidence}) → القيمة كما هي"),
        )

    # حالة متعدّدة: قِس التباين أوّلاً
    values = [o.value for o in valid]
    severity, spread = _classify_spread(values)

    # CRITICAL: تباين كبير = لا canonical
    if spread > critical_threshold_pct:
        return ArbitrationResult(
            canonical_value=None,
            canonical_source=None,
            canonical_confidence="none",
            severity=ConflictSeverity.CRITICAL,
            competing_sources=len(valid),
            spread_pct=spread,
            reasoning_ar=(f"تضارب حرج: {len(valid)} مصدر، "
                         f"تباين {spread:.1f}% > {critical_threshold_pct}%. "
                         "يتطلّب مراجعة بشرية — لا اختيار آلي."),
            rejected_sources=[{"source": o.source.value, "value": o.value}
                             for o in valid],
            requires_human_review=True,
        )

    # احسب score لكل مشاهدة
    conf_multiplier = {"low": 0.5, "medium": 1.0, "high": 1.5, "none": 0.1}
    scored = []
    for o in valid:
        priority = _SOURCE_PRIORITY.get(o.source, 30)
        decay = _age_decay_factor(o.measured_at, current_time)
        conf = conf_multiplier.get(o.confidence, 1.0)
        score = priority * decay * conf
        scored.append((score, o))

    # رتّب وأخذ الأعلى
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]

    rejected = [
        {"source": o.source.value, "value": o.value,
         "score": round(s, 2),
         "rejected_because": f"score {s:.1f} < winner {best_score:.1f}"}
        for s, o in scored[1:]
    ]

    # سقف الثقة لا يتجاوز الفائز، يُخفَّض إن كان severity != AGREEMENT
    final_conf = best.confidence
    if severity == ConflictSeverity.MINOR:
        # خفّض medium → low (لا high مع تباين)
        final_conf = {"high": "medium", "medium": "low",
                     "low": "low"}.get(best.confidence, "low")
    elif severity == ConflictSeverity.MAJOR:
        final_conf = "low"   # دائماً low مع تباين major

    return ArbitrationResult(
        canonical_value=best.value,
        canonical_source=best.source,
        canonical_confidence=final_conf,
        severity=severity,
        competing_sources=len(valid),
        spread_pct=round(spread, 1),
        reasoning_ar=(f"{best.source.value} يفوز "
                     f"({len(valid)} مصدر، تباين {spread:.1f}%، "
                     f"شدّة {severity.value}). "
                     f"الثقة النهائية: {final_conf}."),
        rejected_sources=rejected,
        requires_human_review=False,
    )


def arbitrate_summary(result: ArbitrationResult) -> str:
    """ملخّص قابل للقراءة للسجلّ والواجهة."""
    if result.canonical_value is None:
        return f"⛔ {result.reasoning_ar}"
    if result.severity == ConflictSeverity.NONE:
        return f"✅ {result.reasoning_ar}"
    elif result.severity == ConflictSeverity.AGREEMENT:
        return f"✅ توافق ({result.competing_sources} مصادر): {result.reasoning_ar}"
    elif result.severity in (ConflictSeverity.MINOR, ConflictSeverity.MAJOR):
        return f"⚠️ {result.reasoning_ar}"
    else:
        return f"⛔ {result.reasoning_ar}"


# ─── سياسات قابلة للتخصيص ────────────────────────────────────────

def set_source_priority(source: ObservationSource, priority: int) -> None:
    """تخصيص priority لمصدر معيّن (للتجربة/المعايرة).

    استخدام: لو في منطقة معيّنة الـsatellite أدقّ من sensor"""
    _SOURCE_PRIORITY[source] = priority


def get_source_priority(source: ObservationSource) -> int:
    """يُرجع priority الحالي."""
    return _SOURCE_PRIORITY.get(source, 30)


def reset_priorities_to_default() -> None:
    """يُعيد التعيينات الافتراضية. للاختبارات + reset."""
    global _SOURCE_PRIORITY
    _SOURCE_PRIORITY.clear()
    _SOURCE_PRIORITY.update({
        ObservationSource.LAB: 100,
        ObservationSource.MANUAL: 80,
        ObservationSource.SENSOR: 60,
        ObservationSource.DRONE: 50,
        ObservationSource.SATELLITE: 40,
        ObservationSource.HISTORICAL: 30,
    })
