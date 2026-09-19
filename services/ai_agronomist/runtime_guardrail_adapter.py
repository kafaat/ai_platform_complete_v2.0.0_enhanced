"""قشرةُ إعادة تصدير — الوحدةُ انتقلت إلى `shared.ai.recommendation_runtime.runtime_guardrail_adapter` (AI-RUNTIME-WIRING-01).

تبقى هنا كي لا يتغيّر مستهلكوها داخل هذه الخدمة واختباراتُها؛ لا منطقَ فيها.
"""

from shared.ai.recommendation_runtime.runtime_guardrail_adapter import (
    ENABLE_LEGACY_RECOMMENDATION_FALLBACK,
    ENABLE_PONYTAIL_GUARDRAILS,
    REQUIRE_CANONICAL_FIELD_STATE,
    REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES,
    MissingCanonicalFieldState,
    guarded_runtime_context,
)

__all__ = [
    "ENABLE_LEGACY_RECOMMENDATION_FALLBACK",
    "ENABLE_PONYTAIL_GUARDRAILS",
    "MissingCanonicalFieldState",
    "REQUIRE_CANONICAL_FIELD_STATE",
    "REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES",
    "guarded_runtime_context",
]
