"""Recommendation Ponytail guardrails for SAHOOL.

This module implements a small "do less first" decision filter before any AI
answer builder or recommendation workflow spends tokens, calls RAG, or creates a
prescription. It is deliberately conservative and does **not** produce final
recommendations. It returns a routing decision:

* direct_answer: a simple deterministic answer is enough.
* continue_pipeline: the request may proceed to Context -> FieldState -> RecommendationEngine.
* require_evidence: block precise advice until required evidence exists.
* human_review: high-risk recommendation must go through agronomist review.

The invariant is the same as the Canonical Field State design: RAG/KG/MCP tools
may provide context and annotations only; final decisions still come from
Canonical Field State -> Recommendation Engine -> Human Review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PonytailAction = Literal["direct_answer", "continue_pipeline", "require_evidence", "human_review"]


@dataclass(frozen=True)
class PonytailIntent:
    """Minimal intent descriptor from the query interpreter.

    complexity is intentionally categorical to avoid fake precision. The caller
    may map UI intents or LLM-classified intents into these fields.
    """

    intent_type: str
    complexity: Literal["simple_query", "advisory", "prescription", "diagnosis"] = "advisory"
    asks_for_prescription: bool = False
    risk_domain: str | None = None  # pesticide|fertilization|irrigation|general


@dataclass(frozen=True)
class PonytailEvidence:
    has_lab: bool = False
    has_weather: bool = False
    has_field_state: bool = False
    has_phi: bool = False
    confidence: Literal["none", "low", "medium", "high"] = "none"


@dataclass(frozen=True)
class PonytailDecision:
    action: PonytailAction
    reason_ar: str
    allowed_tools: list[str] = field(default_factory=list)
    max_chunks: int = 0
    requires_human_review: bool = False
    may_create_prescription: bool = False

    @property
    def recommendation(self) -> None:
        """Ponytail must never expose a recommendation-shaped property."""
        raise AttributeError("RecommendationPonytail must not emit recommendations")


class InsufficientEvidenceError(ValueError):
    """Raised when the request tries to cross a hard evidence gate."""


class RecommendationPonytail:
    """Filter excessive agent behavior before expensive or risky processing."""

    def filter(
        self,
        intent: PonytailIntent,
        evidence: PonytailEvidence,
        *,
        field_state: dict[str, Any] | None = None,
    ) -> PonytailDecision:
        """Return the least-powerful safe processing path for the request."""
        field_state = field_state or {}

        # 1) Simple deterministic irrigation/status answer: no RAG, no prescription.
        if intent.complexity == "simple_query" and intent.intent_type in {
            "irrigation",
            "field_status",
        }:
            if evidence.has_field_state and field_state.get("irrigation_state"):
                return PonytailDecision(
                    action="direct_answer",
                    reason_ar="السؤال بسيط وحالة الحقل تحتوي إجابة تشغيلية؛ لا حاجة لاستدعاء RAG أو LLM.",
                    allowed_tools=[],
                    max_chunks=0,
                    may_create_prescription=False,
                )

        # 2) Fertilization precision requires lab evidence.
        if intent.intent_type == "fertilization" and not evidence.has_lab:
            raise InsufficientEvidenceError("تحليل التربة/المختبر مطلوب قبل توصية تسميد دقيقة")

        # 3) Pesticide / PHI-sensitive paths always go to review.
        if intent.risk_domain == "pesticide" or intent.intent_type in {"spraying", "pesticide"}:
            return PonytailDecision(
                action="human_review",
                reason_ar="المبيدات وفترات الأمان قرارات عالية المخاطر؛ يجب مراجعة مهندس زراعي.",
                allowed_tools=["get_field_state", "query_knowledge_graph"],
                max_chunks=3,
                requires_human_review=True,
                may_create_prescription=False,
            )

        # 4) Low confidence: keep it short and action-item oriented.
        if evidence.confidence in {"none", "low"}:
            return PonytailDecision(
                action="require_evidence",
                reason_ar="الثقة غير كافية؛ أعطِ إجراءً محدوداً لجمع بيانات ولا تُصدر توصية دقيقة.",
                allowed_tools=["get_field_state"],
                max_chunks=0,
                may_create_prescription=False,
            )

        # 5) Prescription requests require the normal FieldState -> Recommendation path.
        if intent.asks_for_prescription or intent.complexity == "prescription":
            return PonytailDecision(
                action="continue_pipeline",
                reason_ar="طلب وصفة يتطلب المرور عبر Canonical Field State ثم Recommendation Engine.",
                allowed_tools=[
                    "get_field_state",
                    "get_lab_results",
                    "get_weather",
                    "query_knowledge_graph",
                ],
                max_chunks=5,
                may_create_prescription=False,  # only Prescription Engine after approved recommendation may do it
            )

        return PonytailDecision(
            action="continue_pipeline",
            reason_ar="يمكن متابعة تجميع السياق دون تجاوز مصدر الحقيقة.",
            allowed_tools=["get_field_state", "search_rag", "query_knowledge_graph"],
            max_chunks=5,
            may_create_prescription=False,
        )
