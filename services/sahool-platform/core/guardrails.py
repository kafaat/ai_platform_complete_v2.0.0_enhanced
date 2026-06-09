"""
sahool_core.guardrails
======================
طبقة الحراسة الموحّدة — خطوط حمراء توقف أي توصية مهما كانت "ناجحة".

مستلهَمة من قانون مؤشّرات الحراسة (ByteDance، ق24): لكل قرار مؤشّرات
نجاح ومؤشّرات حراسة؛ الحراسة خطوط حمراء — إن خُرقت، تُوقَف التوصية
فوراً حتى لو كانت مؤشّرات النجاح ممتازة.

الفجوة المسدودة: خطوط سهول الحمراء كانت **متفرّقة** (PHI في pesticide،
الملوحة في deficit_irrigation، البيانات الناقصة في field_lifecycle).
هذه الطبقة **توحّدها** في فحص واحد قبل أي توصية — لا قرار يمرّ إن خُرق
خط أحمر، بغضّ النظر عن جودة بقية المؤشّرات.

التمييز الجوهري عن A/B الرقمي: لا نأخذ هندسة التدفّق (طبقات، hash) —
8 حقول لا تحتاجها. نأخذ **المبدأ** فقط: الحراسة تَغلِب النجاح.

هذا تجسيد لمبدأ "السلامة لا تُتخطّى" و"الحاكم يُلغي الكل" — موحّداً.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GuardrailSeverity(str, Enum):
    HALT = "halt"          # خط أحمر — يوقف التوصية تماماً
    WARN = "warn"          # تحذير — لا يوقف لكن يخفض الثقة


@dataclass
class GuardrailBreach:
    name: str
    severity: GuardrailSeverity
    reason_ar: str


@dataclass
class GuardrailResult:
    passed: bool                          # هل اجتاز كل الخطوط الحمراء؟
    breaches: list[GuardrailBreach] = field(default_factory=list)
    confidence_cap: str | None = None     # سقف تفرضه التحذيرات
    summary_ar: str = ""

    @property
    def halted(self) -> bool:
        return any(b.severity == GuardrailSeverity.HALT for b in self.breaches)


def check_guardrails(
    *,
    # السلامة (PHI) — حاكم صارم
    pesticide_phi_satisfied: bool | None = None,
    # اكتمال البيانات الحاكمة
    has_governing_data: bool = True,
    # الملوحة مقابل عتبة المحصول
    soil_ec_ds_m: float | None = None,
    crop_salinity_threshold_ds_m: float | None = None,
    # تراكم أملاح من عجز الري بماء مالح
    deficit_salinity_risk: str | None = None,
    # المعايرة المحلية
    zone_factor_calibrated: bool = False,
) -> GuardrailResult:
    """الفحص الموحّد للخطوط الحمراء قبل أي توصية.

    أي خط أحمر (HALT) → لا توصية. التحذيرات (WARN) تخفض السقف لا توقف.
    يجمع ما كان متفرّقاً: PHI، البيانات الحاكمة، الملوحة، تراكم الأملاح."""
    breaches: list[GuardrailBreach] = []

    # خط أحمر ١: السلامة (PHI) — لا حصاد ضمن فترة الأمان
    if pesticide_phi_satisfied is False:
        breaches.append(GuardrailBreach(
            "pesticide_phi", GuardrailSeverity.HALT,
            "فترة أمان المبيد (PHI) لم تنقضِ — يُمنع الحصاد"))
    elif pesticide_phi_satisfied is None and has_governing_data is False:
        breaches.append(GuardrailBreach(
            "pesticide_unknown", GuardrailSeverity.HALT,
            "سجلّ المبيدات غير معروف — لا توصية حصاد حتى يُتحقّق"))

    # خط أحمر ٢: البيانات الحاكمة ناقصة
    if not has_governing_data:
        breaches.append(GuardrailBreach(
            "missing_governing_data", GuardrailSeverity.HALT,
            "بيانات حاكمة ناقصة (تربة/ماء مخبري) — القاعدة الذهبية: لا قرار"))

    # خط أحمر ٣: الملوحة تتجاوز عتبة المحصول بشدّة
    if soil_ec_ds_m is not None and crop_salinity_threshold_ds_m is not None:
        if soil_ec_ds_m > crop_salinity_threshold_ds_m * 1.5:
            breaches.append(GuardrailBreach(
                "salinity_exceeds_crop", GuardrailSeverity.HALT,
                f"ملوحة التربة ({soil_ec_ds_m}) تتجاوز عتبة المحصول "
                f"({crop_salinity_threshold_ds_m}) بشدّة — المحصول غير مناسب"))
        elif soil_ec_ds_m > crop_salinity_threshold_ds_m:
            breaches.append(GuardrailBreach(
                "salinity_above_threshold", GuardrailSeverity.WARN,
                "ملوحة التربة فوق عتبة المحصول — خفض غلّة متوقّع"))

    # خط أحمر ٤: تراكم أملاح من عجز الري بماء مالح
    if deficit_salinity_risk == "high":
        breaches.append(GuardrailBreach(
            "deficit_salt_buildup", GuardrailSeverity.HALT,
            "عجز ري حادّ بماء مالح — تراكم أملاح خطير (الفيزياء ترفض)"))

    # تحذير: غياب المعايرة المحلية يخفض السقف (لا يوقف)
    cap = None
    if not zone_factor_calibrated:
        breaches.append(GuardrailBreach(
            "uncalibrated", GuardrailSeverity.WARN,
            "لا معايرة محلية (zone_factor) — السقف MEDIUM"))
        cap = "medium"

    halted = any(b.severity == GuardrailSeverity.HALT for b in breaches)
    if halted:
        summary = "توقّفت التوصية — خط أحمر مخروق (الحراسة تَغلِب النجاح)"
        cap = "none"
    elif breaches:
        summary = f"مرّت بتحذيرات ({len(breaches)}) — السقف {cap or 'محدود'}"
    else:
        summary = "اجتازت كل الخطوط الحمراء"

    return GuardrailResult(
        passed=not halted, breaches=breaches,
        confidence_cap=cap, summary_ar=summary)
