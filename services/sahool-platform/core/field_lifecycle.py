"""
core.field_lifecycle
====================
دورة حياة الحقل — حالات الجودة الأربع.

يطوّر النموذج الثنائي (BLOCKED/READY) إلى أربع حالات واقعية،
بناءً على فكرتي المستخدم: تخطّي الفحوصات + طلب تحليل مخبري.

  BLOCKED      → لم تُدخَل التحاليل الحاكمة ولم يُتّخذ قرار
  LIMITED      → تخطّى الفحوصات عمداً → توصيات عامة فقط
  PENDING_LAB  → طلب تحليلاً، ينتظر نتائج المعمل
  READY        → التحاليل الحاكمة كاملة → توصيات دقيقة

القاعدة الذهبية المحفوظة (سلامة):
  LIMITED يفتح التوصيات العامة (ري، طقس، NDVI)
  لكن حاكم السلامة L3 (PHI — أمان المبيد) يبقى BLOCKED دائماً
  حتى في LIMITED. لا توصية كيميائية بلا بيانات. السلامة لا تُتخطّى.

ملاحظة معمارية: مطبّق على SQLite (lite_store)، لا PostgreSQL.
الجداول مصمّمة بنفس شكل المقترح → ترحيل سهل عند تجاوز ~100 مزرعة.
"""
from __future__ import annotations

from enum import Enum


class FieldQualityState(str, Enum):
    BLOCKED = "blocked"          # لا قرار بعد
    LIMITED = "limited"          # تخطّى الفحوصات — توصيات عامة
    PENDING_LAB = "pending_lab"  # ينتظر نتائج المعمل
    READY = "ready"              # تحاليل كاملة — توصيات دقيقة


class SoilTestChoice(str, Enum):
    """قرار المزارع بشأن فحوصات التربة."""
    PROVIDED = "provided"    # أدخل التحاليل
    SKIP = "skip"            # تخطّى (يقبل توصيات عامة)
    REQUEST_LAB = "request_lab"  # طلب تحليلاً مخبرياً


# الحاكمات الصارمة التي لا تُتخطّى أبداً (سلامة المستهلك/الفيزياء)
# L3 = فترة أمان المبيد (PHI) — صارم حتى في LIMITED
_SAFETY_GOVERNORS = {"L3"}

# الحاكمات التي تفتح READY عند توفّرها
_QUALITY_GOVERNORS = {"S3", "S4", "I3"}


def resolve_state(
    soil_choice: SoilTestChoice,
    provided_governors: set[str],
    lab_request_pending: bool = False,
) -> tuple[FieldQualityState, list[str]]:
    """يحدّد حالة الحقل + التوصيات المتاحة.

    Returns: (الحالة، قائمة أنواع التوصيات المتاحة)
    """
    missing = _QUALITY_GOVERNORS - provided_governors

    # كل الحاكمات متوفّرة → READY
    if not missing:
        return FieldQualityState.READY, ["irrigation", "crop_suitability",
                                         "salinity_mgmt", "pesticide_phi", "fertility"]

    # طلب تحليل مخبري → PENDING_LAB
    if soil_choice == SoilTestChoice.REQUEST_LAB or lab_request_pending:
        return FieldQualityState.PENDING_LAB, ["irrigation_basic", "weather", "ndvi_monitoring"]

    # تخطّى الفحوصات → LIMITED (توصيات عامة، لا حاكمات سلامة)
    if soil_choice == SoilTestChoice.SKIP:
        return FieldQualityState.LIMITED, ["irrigation_basic", "weather",
                                           "ndvi_monitoring", "general_advisory"]

    # لم يُتّخذ قرار → BLOCKED
    return FieldQualityState.BLOCKED, []


def can_recommend(state: FieldQualityState, recommendation_type: str) -> tuple[bool, str]:
    """هل يُسمح بنوع توصية معيّن في هذه الحالة؟

    القاعدة الحاسمة: توصيات السلامة (المبيدات/PHI) تتطلب READY دائماً،
    مهما كانت الحالة. لا تُتخطّى أبداً.
    """
    # توصيات السلامة — تتطلب READY حصراً
    if recommendation_type in ("pesticide_phi", "pesticide", "phi"):
        if state != FieldQualityState.READY:
            return False, ("توصيات المبيدات تتطلب تحاليل كاملة (سلامة المستهلك) — "
                           "لا تُتخطّى حتى في الوضع المحدود")
        return True, ""

    # READY → كل شيء مسموح
    if state == FieldQualityState.READY:
        return True, ""

    # BLOCKED → لا توصية
    if state == FieldQualityState.BLOCKED:
        return False, "أدخل التحاليل أو اختر تخطّيها للحصول على توصيات عامة"

    # LIMITED / PENDING_LAB → التوصيات العامة فقط
    general = {"irrigation_basic", "weather", "ndvi_monitoring", "general_advisory"}
    if recommendation_type in general:
        return True, ""
    return False, "توصية دقيقة — تحتاج تحاليل التربة الكاملة"


def state_explanation_ar(state: FieldQualityState) -> dict:
    """شرح الحالة للمزارع (شفافية)."""
    return {
        FieldQualityState.BLOCKED: {
            "signal": "⚪", "label_ar": "بانتظار البيانات",
            "detail_ar": "أدخل تحاليل التربة، أو اختر تخطّيها لتوصيات عامة، أو اطلب تحليلاً مخبرياً.",
        },
        FieldQualityState.LIMITED: {
            "signal": "🟡", "label_ar": "توصيات عامة (محدود)",
            "detail_ar": "تخطّيت الفحوصات — توصيات الري والطقس متاحة، لكن لا توصيات دقيقة "
                         "للملوحة أو المبيدات حتى تتوفّر التحاليل.",
        },
        FieldQualityState.PENDING_LAB: {
            "signal": "🔵", "label_ar": "بانتظار المعمل",
            "detail_ar": "طلبت تحليلاً مخبرياً. توصيات عامة متاحة الآن، وتُفعّل الدقيقة عند وصول النتائج.",
        },
        FieldQualityState.READY: {
            "signal": "🟢", "label_ar": "جاهز",
            "detail_ar": "التحاليل كاملة — كل التوصيات مُفعّلة بدقة كاملة.",
        },
    }[state]
