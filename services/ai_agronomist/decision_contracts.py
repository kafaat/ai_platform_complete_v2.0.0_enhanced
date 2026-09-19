"""قشرةُ إعادة تصدير — الوحدةُ انتقلت إلى `shared.ai.recommendation_runtime.decision_contracts` (AI-RUNTIME-WIRING-01).

تبقى هنا كي لا يتغيّر مستهلكوها داخل هذه الخدمة واختباراتُها؛ لا منطقَ فيها.
"""

from shared.ai.recommendation_runtime.decision_contracts import (
    EVIDENCE_WEIGHTS,
    FORBIDDEN_DECISION_KEYS,
    DecisionContractViolation,
    EvidenceItem,
    EvidenceStrength,
    assert_no_decision_keys,
    compose_confidence,
    has_decision_keys,
    iter_structured_keys,
    recommendation_inputs_from_context,
)

__all__ = [
    "DecisionContractViolation",
    "EVIDENCE_WEIGHTS",
    "EvidenceItem",
    "EvidenceStrength",
    "FORBIDDEN_DECISION_KEYS",
    "assert_no_decision_keys",
    "compose_confidence",
    "has_decision_keys",
    "iter_structured_keys",
    "recommendation_inputs_from_context",
]
