"""
core.recommendation_engine
===========================
المايسترو — خط التوصية المتكامل. يربط كل المكوّنات في توصية واحدة.

التدفّق (يطبّق دستور بناء المعلومة من البداية للنهاية):

  ١. validate_observations   → بوابة الجودة (BLOCKED?)
  ٢. المحرّكات (fao56, suitability) → مؤشرات backend خام
  ٣. المعرفة المحلية (وزن ≤0.15) → ترجّح وتوجّه، لا تحكم
  ٤. المعايرة المديريةية       → zone_factor (إن وُجد)
  ٥. التوليف                  → توصية + سبب + ثقة
  ٦. الفصل                    → backend (كل شيء) | farmer (مبسّط)

القاعدة الذهبية مطبّقة: الثقة = أضعف حلقة. لا توصية إن BLOCKED.
الفصل الصارم: المزارع يرى القرار+السبب+الثقة. الـ backend يحمل التفاصيل.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class RecommendationStatus(str, Enum):
    ISSUED = "issued"            # توصية دقيقة صادرة (READY)
    LIMITED = "limited"          # توصيات عامة (تخطّى الفحوصات)
    PENDING_LAB = "pending_lab"  # ينتظر نتائج المعمل — توصيات عامة مؤقتاً
    BLOCKED = "blocked"          # حاكم صارم غائب — لا توصية
    PENDING_DATA = "pending_data"  # بيانات ناقصة (غير حاكمة)


class FarmerSignal(str, Enum):
    """إشارة بصرية بسيطة للمزارع — لا أرقام معقّدة."""
    GOOD = "🟢 جيد"
    CAUTION = "🟡 انتبه"
    DANGER = "🔴 خطر"
    UNKNOWN = "⚪ بيانات ناقصة"


# ── مخرجات backend (التفاصيل الكاملة — لا تُعرض للمزارع) ──────
@dataclass
class BackendDetail:
    """كل المؤشرات الخام والوسيطة. للمهندس/المطوّر/التدقيق فقط."""
    et0_mm: float | None = None
    etc_mm: float | None = None
    kc: float | None = None
    salinity_ks: float | None = None
    irrigation_m3_ha: float | None = None
    irrigation_error_pct: float | None = None
    suitability_class: str | None = None
    governing_failures: list[str] = field(default_factory=list)
    quality_grade: str = "UNKNOWN"
    missing_observables: list[str] = field(default_factory=list)
    zone_factor: float | None = None
    zone_factor_status: str = "pending"
    local_knowledge_applied: list[dict] = field(default_factory=list)
    provenance_chain: list[dict] = field(default_factory=list)


# ── مخرجات المزارع (مبسّطة — القرار + السبب + الثقة) ──────────
@dataclass
class FarmerView:
    """ما يراه المزارع. لا معادلات، لا نسب خطأ — قرار قابل للتنفيذ."""
    signal: FarmerSignal
    headline_ar: str             # "اروِ المحوري ١ بـ ٣٥ مم غداً"
    reason_ar: str               # "الطقس حار والتربة جفّت"
    confidence_ar: str           # "ثقة متوسطة (لا حساس رطوبة)"
    alerts_ar: list[str] = field(default_factory=list)   # تنبيهات الحاكمات
    next_action_ar: str = ""     # ما يفتح توصية أدق


@dataclass
class Recommendation:
    status: RecommendationStatus
    farmer_view: FarmerView
    backend: BackendDetail
    # for the recommendation_log:
    predicted_yield_t_ha: float | None = None
    confidence: str = "unknown"

    def to_log_dict(self) -> dict:
        return {
            "status": self.status.value,
            "headline": self.farmer_view.headline_ar,
            "quality_grade": self.backend.quality_grade,
            "predicted_yield_t_ha": self.predicted_yield_t_ha,
            "confidence": self.confidence,
        }


# ── المايسترو ────────────────────────────────────────────────
def generate_recommendation(
    validation: dict,            # من validate_observations.validate()
    irrigation=None,             # IrrigationResult من fao56 (أو None)
    suitability=None,            # SuitabilityResult من suitability (أو None)
    zone_factor: float | None = None,
    zone_factor_status: str = "pending",
    local_knowledge: list | None = None,   # FarmerKnowledge مُتحقَّقة
    field_state: str | None = None,  # حالة الحقل: limited/pending_lab/ready (من field_lifecycle)
) -> Recommendation:
    """يولّف كل المخرجات في توصية واحدة، مع فصل backend عن المزارع."""
    backend = BackendDetail(
        quality_grade=validation.get("quality_grade", "UNKNOWN"),
        missing_observables=validation.get("missing_A", []),
        governing_failures=validation.get("blocking_observables", []),
        zone_factor=zone_factor,
        zone_factor_status=zone_factor_status,
    )

    # ── الحالة ١: BLOCKED — حاكم صارم غائب، لا توصية ──────────
    if validation.get("quality_grade") == "BLOCKED":
        # ربط field_lifecycle: إن اختار المزارع التخطّي أو طلب التحليل،
        # نُصدر توصيات عامة بدل الحجب القاطع (الفلسفة التحفيزية).
        # لكن الحاكمات الصارمة للسلامة (المبيدات) تبقى محجوبة دائماً.
        if field_state in ("limited", "pending_lab"):
            is_pending = field_state == "pending_lab"
            return Recommendation(
                status=(RecommendationStatus.PENDING_LAB if is_pending
                        else RecommendationStatus.LIMITED),
                backend=backend,
                farmer_view=FarmerView(
                    signal=FarmerSignal.CAUTION,
                    headline_ar=("توصيات عامة — بانتظار نتائج المعمل" if is_pending
                                 else "توصيات عامة (محدودة)"),
                    reason_ar=("طلبت تحليلاً مخبرياً؛ توصيات الري والطقس متاحة الآن، "
                               "وتُفعّل الدقيقة عند وصول النتائج." if is_pending
                               else "تخطّيت الفحوصات؛ توصيات الري والطقس متاحة، "
                               "لا توصيات دقيقة للملوحة أو المبيدات."),
                    confidence_ar="عامة 🟡",
                    alerts_ar=["🛑 توصيات المبيدات محجوبة حتى تكتمل التحاليل (سلامة المستهلك)"],
                    next_action_ar="أكمل تحاليل التربة (S3·S4·I3) لتوصيات دقيقة قيّمة",
                ),
                confidence="limited",
            )
        blocking = validation.get("blocking_observables", [])
        names = _observable_names_ar(blocking)
        return Recommendation(
            status=RecommendationStatus.BLOCKED,
            backend=backend,
            farmer_view=FarmerView(
                signal=FarmerSignal.UNKNOWN,
                headline_ar="لا يمكن إصدار توصية بعد",
                reason_ar=f"بيانات ضرورية ناقصة: {names}",
                confidence_ar="—",
                alerts_ar=[f"⚠️ مطلوب: {names}"] if names else [],
                next_action_ar=f"أدخل {names} لتفعيل التوصية",
            ),
            confidence="blocked",
        )

    # ── الحالة ٢: توصية صادرة ────────────────────────────────
    alerts = []
    signal = FarmerSignal.GOOD

    # الري (من fao56)
    headline = "النظام جاهز — لا توصية ري محدّدة"
    reason = "البيانات المتاحة كافية للحساب الأساسي"
    if irrigation is not None:
        backend.et0_mm = getattr(irrigation, "et0_mm", None)
        backend.etc_mm = getattr(irrigation, "etc_mm", None)
        backend.irrigation_m3_ha = getattr(irrigation, "m3_per_ha", None)
        if backend.irrigation_m3_ha:
            mm = round(backend.irrigation_m3_ha / 10, 1)  # m3/ha → mm
            headline = f"اروِ بما يعادل {mm} مم"
            reason = "حساب الاحتياج المائي حسب الطقس ومرحلة المحصول (FAO-56)"

    # الملاءمة والحاكمات (من suitability)
    if suitability is not None:
        backend.suitability_class = getattr(suitability, "suitability_class", None)
        sc = backend.suitability_class
        if sc in ("N", "unsuitable"):
            signal = FarmerSignal.DANGER
            alerts.append("🔴 هذا المحصول غير ملائم لظروف التربة الحالية")
        elif sc in ("S3", "marginal"):
            signal = FarmerSignal.CAUTION
            alerts.append("🟡 ملاءمة حدّية — يحتاج تحسين تربة")

    # المعرفة المحلية (وزن ≤0.15 — ترجّح، توجّه، لا تحكم)
    if local_knowledge:
        for fk in local_knowledge:
            w = getattr(fk, "prior_weight", 0)
            if w > 0:
                backend.local_knowledge_applied.append({
                    "content": getattr(fk, "content_ar", ""),
                    "weight": w,
                    "scope": getattr(fk, "spatial_scope", ""),
                })

    # الثقة (محكومة بأضعف حلقة + حالة المعايرة)
    conf, conf_ar = _compute_confidence(validation, zone_factor_status)

    # الإشارة النهائية تنخفض إن ثقة منخفضة
    if conf == "low" and signal == FarmerSignal.GOOD:
        signal = FarmerSignal.CAUTION

    next_action = ""
    if validation.get("missing_A"):
        next_action = f"لرفع الدقة: أدخل {_observable_names_ar(validation['missing_A'])}"
    elif zone_factor_status == "pending":
        next_action = "المعايرة المديريةية قيد الاكتمال (تحتاج ٥ مزارع)"

    return Recommendation(
        status=RecommendationStatus.ISSUED,
        backend=backend,
        farmer_view=FarmerView(
            signal=signal,
            headline_ar=headline,
            reason_ar=reason,
            confidence_ar=conf_ar,
            alerts_ar=alerts,
            next_action_ar=next_action,
        ),
        predicted_yield_t_ha=None,   # null حتى المعايرة — لا رقم وهمي
        confidence=conf,
    )


# ── مساعدات ──────────────────────────────────────────────────
_OBS_AR = {
    "S3": "ملوحة التربة", "S4": "حموضة التربة pH", "I3": "ملوحة مياه الري",
    "L3": "فترة أمان المبيد", "O1": "صنف المحصول", "O2": "تاريخ الزراعة",
    "C1": "حرارة الهواء", "C5": "هطول الأمطار", "I1": "كمية المياه", "G1": "الإنتاج",
}


def _observable_names_ar(ids: list[str]) -> str:
    return "، ".join(_OBS_AR.get(i, i) for i in ids)


def _compute_confidence(validation: dict, zone_factor_status: str) -> tuple[str, str]:
    """الثقة = أضعف حلقة. تنخفض مع نقص المراصد أو غياب المعايرة."""
    grade = validation.get("quality_grade", "UNKNOWN")
    missing_b = validation.get("missing_B_count", 0)
    if grade == "HIGH" and zone_factor_status == "calibrated":
        return "high", "ثقة عالية (بيانات كاملة ومعايرة)"
    if grade in ("HIGH", "MEDIUM"):
        if zone_factor_status != "calibrated":
            return "medium", "ثقة متوسطة (النموذج عام، لم يُعاير محلياً بعد)"
        return "medium", "ثقة متوسطة (بعض البيانات ناقصة)"
    return "low", "ثقة منخفضة (بيانات محدودة — استرشادي)"
