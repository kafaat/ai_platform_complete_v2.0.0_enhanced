"""
Runtime guardrail adapter.

Safe integration point: wraps existing runtime without replacing internal_orchestrator.
Default flags keep legacy path available. This adapter never emits final recommendations.
"""

from __future__ import annotations

from typing import Any

try:
    from config.guardrail_feature_flags import (
        ENABLE_LEGACY_RECOMMENDATION_FALLBACK,
        ENABLE_PONYTAIL_GUARDRAILS,
        REQUIRE_CANONICAL_FIELD_STATE,
        REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES,
    )
except Exception:
    ENABLE_PONYTAIL_GUARDRAILS = False
    ENABLE_LEGACY_RECOMMENDATION_FALLBACK = True
    REQUIRE_CANONICAL_FIELD_STATE = True
    REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES = True

from .decision_contracts import assert_no_decision_keys, recommendation_inputs_from_context


class MissingCanonicalFieldState(RuntimeError):
    """Raised when guarded runtime is asked to proceed without canonical field state."""


def guarded_runtime_context(context: dict[str, Any]) -> dict[str, Any]:
    """
    Prepare context for RecommendationEngine.

    - Does not generate recommendations.
    - Strips RAG/KG from governing decision inputs.
    - Requires Canonical Field State when strict mode is enabled.
    """
    if REQUIRE_CANONICAL_FIELD_STATE and not context.get("canonical_field_state"):
        raise MissingCanonicalFieldState(
            "canonical_field_state is required before guarded recommendations"
        )

    assert_no_decision_keys(context.get("tool_outputs", {}), layer="MCP tools")
    return {
        "canonical_field_state": context.get("canonical_field_state"),
        "recommendation_inputs": recommendation_inputs_from_context(context),
        "annotations": {
            "rag": context.get("signals", {}).get("rag")
            if isinstance(context.get("signals"), dict)
            else None,
            "kg": context.get("signals", {}).get("kg")
            if isinstance(context.get("signals"), dict)
            else None,
        },
        "guardrails_enabled": ENABLE_PONYTAIL_GUARDRAILS,
        "legacy_fallback_enabled": ENABLE_LEGACY_RECOMMENDATION_FALLBACK,
        "require_human_review_for_pesticides": REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES,
    }
