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
    HALT = "halt"  # خط أحمر — يوقف التوصية تماماً
    WARN = "warn"  # تحذير — لا يوقف لكن يخفض الثقة


@dataclass
class GuardrailBreach:
    name: str
    severity: GuardrailSeverity
    reason_ar: str


@dataclass
class GuardrailResult:
    passed: bool  # هل اجتاز كل الخطوط الحمراء؟
    breaches: list[GuardrailBreach] = field(default_factory=list)
    confidence_cap: str | None = None  # سقف تفرضه التحذيرات
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
        breaches.append(
            GuardrailBreach(
                "pesticide_phi",
                GuardrailSeverity.HALT,
                "فترة أمان المبيد (PHI) لم تنقضِ — يُمنع الحصاد",
            )
        )
    elif pesticide_phi_satisfied is None and has_governing_data is False:
        breaches.append(
            GuardrailBreach(
                "pesticide_unknown",
                GuardrailSeverity.HALT,
                "سجلّ المبيدات غير معروف — لا توصية حصاد حتى يُتحقّق",
            )
        )

    # خط أحمر ٢: البيانات الحاكمة ناقصة
    if not has_governing_data:
        breaches.append(
            GuardrailBreach(
                "missing_governing_data",
                GuardrailSeverity.HALT,
                "بيانات حاكمة ناقصة (تربة/ماء مخبري) — القاعدة الذهبية: لا قرار",
            )
        )

    # خط أحمر ٣: الملوحة تتجاوز عتبة المحصول بشدّة
    if soil_ec_ds_m is not None and crop_salinity_threshold_ds_m is not None:
        if soil_ec_ds_m > crop_salinity_threshold_ds_m * 1.5:
            breaches.append(
                GuardrailBreach(
                    "salinity_exceeds_crop",
                    GuardrailSeverity.HALT,
                    f"ملوحة التربة ({soil_ec_ds_m}) تتجاوز عتبة المحصول "
                    f"({crop_salinity_threshold_ds_m}) بشدّة — المحصول غير مناسب",
                )
            )
        elif soil_ec_ds_m > crop_salinity_threshold_ds_m:
            breaches.append(
                GuardrailBreach(
                    "salinity_above_threshold",
                    GuardrailSeverity.WARN,
                    "ملوحة التربة فوق عتبة المحصول — خفض غلّة متوقّع",
                )
            )

    # خط أحمر ٤: تراكم أملاح من عجز الري بماء مالح
    if deficit_salinity_risk == "high":
        breaches.append(
            GuardrailBreach(
                "deficit_salt_buildup",
                GuardrailSeverity.HALT,
                "عجز ري حادّ بماء مالح — تراكم أملاح خطير (الفيزياء ترفض)",
            )
        )

    # تحذير: غياب المعايرة المحلية يخفض السقف (لا يوقف)
    cap = None
    if not zone_factor_calibrated:
        breaches.append(
            GuardrailBreach(
                "uncalibrated",
                GuardrailSeverity.WARN,
                "لا معايرة محلية (zone_factor) — السقف MEDIUM",
            )
        )
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
        passed=not halted, breaches=breaches, confidence_cap=cap, summary_ar=summary
    )


# ---------------------------------------------------------------------------
# Ponytail policy engine — AI Agronomist pre-generation guardrails
# ---------------------------------------------------------------------------
# This section intentionally lives beside the existing hard safety guardrails.
# Existing check_guardrails() remains unchanged for agronomic red-lines.  The
# Ponytail layer is a pre-generation filter: it decides whether the LLM should
# be used at all and prevents over-recommendation before any text is produced.

from typing import Any  # noqa: E402


class PonytailAction(str, Enum):
    BYPASS_LLM = "bypass_llm"
    SIMPLIFY = "simplify"
    PROCEED = "proceed_to_llm"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class GuardrailPolicy:
    """Configurable policy for AI Agronomist guardrails.

    Keep defaults strict.  The object can later be loaded per-tenant without
    changing code.  RAG/KG are never governing evidence regardless of policy.
    """

    require_lab_for_fertilization: bool = True
    require_weather_for_irrigation: bool = True
    require_human_review_for_pesticides: bool = True
    simplify_threshold: float = 0.70
    one_liner_threshold: float = 0.80


@dataclass(frozen=True)
class GuardrailTrace:
    rule: str
    triggered: bool
    action: PonytailAction
    reason: str


@dataclass(frozen=True)
class PonytailIntent:
    type: str
    complexity: str
    field_id: str


@dataclass(frozen=True)
class FieldStateSnapshot:
    irrigation_state: dict[str, Any] | None = None
    lab_state: dict[str, Any] | None = None
    weather_state: dict[str, Any] | None = None
    satellite_state: dict[str, Any] | None = None
    confidence: float = 0.0

    def has_irrigation_context(self) -> bool:
        irr = self.irrigation_state or {}
        return any(k in irr for k in ("etc_mm", "net_irrigation_mm", "gross_irrigation_mm"))

    def has_lab_context(self) -> bool:
        lab = self.lab_state or {}
        return any(
            k in lab for k in ("ec", "soil_ec", "ph", "npk", "nitrogen", "phosphorus", "potassium")
        )

    def has_weather_context(self) -> bool:
        w = self.weather_state or {}
        return any(
            k in w for k in ("forecast", "hourly", "daily", "et0", "weather_days", "temp_max_c")
        )


@dataclass(frozen=True)
class EvidenceSummary:
    has_lab: bool = False
    has_satellite: bool = False
    has_weather: bool = False
    has_rag: bool = False
    has_kg: bool = False


@dataclass(frozen=True)
class PonytailDecision:
    response: dict[str, Any] | None
    action: PonytailAction
    reason: str
    traces: list[GuardrailTrace]


@dataclass(frozen=True)
class GuardrailEvent:
    event_type: str
    rule: str
    field_id: str
    action: str
    reason: str


class GuardrailEventPublisher:
    """Dependency-free event collector for tests/offline mode.

    Production adapters can replace publish() with a NATS/JetStream publisher.
    """

    def __init__(self) -> None:
        self.events: list[GuardrailEvent] = []

    def publish(self, event: GuardrailEvent) -> None:
        self.events.append(event)


class ConfidenceComposer:
    """Honest confidence composition from evidence availability.

    Lab/IoT/weather are stronger than satellite; RAG/KG only support context and
    receive low weights.  The output is capped to [0, 1] and never upgrades
    annotation-only sources to governing evidence.
    """

    WEIGHTS: dict[str, float] = {
        "lab": 1.0,
        "iot": 0.9,
        "weather": 0.9,
        "satellite": 0.6,
        "kg": 0.35,
        "rag": 0.30,
    }

    def compose(
        self, *, lab=False, weather=False, iot=False, satellite=False, rag=False, kg=False
    ) -> float:
        active = {
            "lab": lab,
            "weather": weather,
            "iot": iot,
            "satellite": satellite,
            "rag": rag,
            "kg": kg,
        }
        weights = [self.WEIGHTS[k] for k, v in active.items() if v]
        if not weights:
            return 0.0
        return round(min(sum(weights) / len(weights), 1.0), 3)


class RecommendationPonytail:
    """Pre-generation filter for SAHOOL AI Agronomist.

    It does not emit recommendations.  It either gives a direct factual answer
    from existing state, simplifies the response, blocks for missing evidence,
    or allows the LLM to synthesize context downstream.
    """

    def __init__(
        self,
        policy: GuardrailPolicy | None = None,
        publisher: GuardrailEventPublisher | None = None,
    ) -> None:
        self.policy = policy or GuardrailPolicy()
        self.publisher = publisher or GuardrailEventPublisher()

    def filter(
        self, intent: PonytailIntent, field_state: FieldStateSnapshot, evidence: EvidenceSummary
    ) -> PonytailDecision:
        traces: list[GuardrailTrace] = []

        def finish(
            response: dict[str, Any] | None, action: PonytailAction, rule: str, reason: str
        ) -> PonytailDecision:
            traces.append(GuardrailTrace(rule=rule, triggered=True, action=action, reason=reason))
            if action in {PonytailAction.INSUFFICIENT_EVIDENCE, PonytailAction.SIMPLIFY}:
                self.publisher.publish(
                    GuardrailEvent("agent.guardrail", rule, intent.field_id, action.value, reason)
                )
            return PonytailDecision(response=response, action=action, reason=reason, traces=traces)

        # Hard evidence and safety gates run before any fast/bypass path.
        # This prevents a stale irrigation_state from bypassing missing weather/ET0.
        if (
            self.policy.require_lab_for_fertilization
            and intent.type == "fertilization"
            and not evidence.has_lab
        ):
            return finish(
                None,
                PonytailAction.INSUFFICIENT_EVIDENCE,
                "fertilization_requires_lab",
                "Precise fertilization requires lab evidence; RAG/KG are supporting only.",
            )
        traces.append(
            GuardrailTrace(
                "fertilization_requires_lab",
                False,
                PonytailAction.PROCEED,
                "passed or not applicable",
            )
        )

        if (
            self.policy.require_weather_for_irrigation
            and intent.type == "irrigation"
            and (not evidence.has_weather or not field_state.has_weather_context())
        ):
            return finish(
                None,
                PonytailAction.INSUFFICIENT_EVIDENCE,
                "irrigation_requires_weather",
                "Irrigation needs weather/ET0 context plus field state.",
            )
        traces.append(
            GuardrailTrace(
                "irrigation_requires_weather",
                False,
                PonytailAction.PROCEED,
                "passed or not applicable",
            )
        )

        if self.policy.require_human_review_for_pesticides and intent.type == "pesticide":
            return finish(
                None,
                PonytailAction.INSUFFICIENT_EVIDENCE,
                "pesticide_requires_phi_review",
                "Pesticide guidance requires PHI check and human review; no automatic recommendation.",
            )
        traces.append(
            GuardrailTrace(
                "pesticide_requires_phi_review",
                False,
                PonytailAction.PROCEED,
                "passed or not applicable",
            )
        )

        if field_state.confidence < self.policy.simplify_threshold:
            return finish(
                self._simplified_advisory(field_state),
                PonytailAction.SIMPLIFY,
                "low_confidence_simplifies",
                "Low confidence: reduce to action items only.",
            )
        traces.append(
            GuardrailTrace(
                "low_confidence_simplifies", False, PonytailAction.PROCEED, "confidence sufficient"
            )
        )

        if (
            intent.type == "irrigation"
            and intent.complexity in {"simple_query", "status_check"}
            and field_state.has_irrigation_context()
        ):
            return finish(
                self._from_fao56(field_state),
                PonytailAction.BYPASS_LLM,
                "simple_irrigation_uses_fao56",
                "FAO56 irrigation state is sufficient; no LLM call needed after evidence gates passed.",
            )
        traces.append(
            GuardrailTrace(
                "simple_irrigation_uses_fao56", False, PonytailAction.PROCEED, "not applicable"
            )
        )

        if self._is_one_liner(intent, field_state):
            return finish(
                self._one_line_answer(intent, field_state),
                PonytailAction.BYPASS_LLM,
                "one_liner_bypasses_llm",
                "High-confidence answer fits in one line.",
            )
        traces.append(
            GuardrailTrace("one_liner_bypasses_llm", False, PonytailAction.PROCEED, "not one-liner")
        )

        return PonytailDecision(
            None,
            PonytailAction.PROCEED,
            "All Ponytail guardrails passed; proceed with context synthesis.",
            traces,
        )

    def _from_fao56(self, field_state: FieldStateSnapshot) -> dict[str, Any]:
        irr = field_state.irrigation_state or {}
        return {
            "response_type": "computed_field_state_hint",
            "amount_mm": irr.get("etc_mm") or irr.get("net_irrigation_mm") or 0,
            "next_date": irr.get("next_date"),
            "source": "FAO56",
            "confidence": field_state.confidence,
            "evidence_level": "governing",
            "note_ar": "معلومة تشغيلية من حالة الحقل وليست توصية نهائية؛ التحويل لتوصية يتم داخل RecommendationEngine فقط.",
        }

    def _simplified_advisory(self, field_state: FieldStateSnapshot) -> dict[str, Any]:
        actions = ["استشر مهندس زراعي"]
        if not field_state.has_lab_context():
            actions.append("أجرِ فحص مختبر للتربة/المياه")
        if not field_state.has_weather_context():
            actions.append("أكمل بيانات الطقس قبل التوصية الدقيقة")
        return {
            "actions": actions,
            "source": "Ponytail-Simplified",
            "confidence": field_state.confidence,
            "evidence_level": "insufficient",
        }

    def _is_one_liner(self, intent: PonytailIntent, field_state: FieldStateSnapshot) -> bool:
        return (
            intent.complexity in {"simple_query", "status_check"}
            and field_state.confidence >= self.policy.one_liner_threshold
            and field_state.has_irrigation_context()
        )

    def _one_line_answer(
        self, intent: PonytailIntent, field_state: FieldStateSnapshot
    ) -> dict[str, Any]:
        irr = field_state.irrigation_state or {}
        amount = irr.get("etc_mm") or irr.get("net_irrigation_mm") or 0
        when = irr.get("next_date") or "عند نافذة الري التالية"
        return {
            "answer": f"الحقل يحتاج {amount} مم ري في {when}.",
            "source": "Ponytail-OneLiner",
            "confidence": field_state.confidence,
            "evidence_level": "governing",
        }
