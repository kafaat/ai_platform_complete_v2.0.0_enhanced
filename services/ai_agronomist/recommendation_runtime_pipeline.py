"""Recommendation runtime pipeline.

This is the final bridge for the remaining phases. It does not replace the
existing internal_orchestrator; it offers a single safe callable that can be
wired behind a feature flag.

Authority:
- Tools/RAG/KG provide context only.
- canonical_field_state is mandatory.
- RecommendationEngine remains the only producer of final recommendations.
- Pesticide/high-risk paths are routed to human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .human_review_repository import InMemoryReviewRepository, ReviewRecord, new_review_id
from .multi_tenant_runtime_validator import MultiTenantRuntimeValidator
from .recommendation_events import RecommendationEvent, RecommendationEventPublisher
from .runtime_metrics import runtime_metrics

try:
    from .runtime_guardrail_adapter import guarded_runtime_context
except Exception:  # pragma: no cover
    guarded_runtime_context = None  # type: ignore


@dataclass(frozen=True)
class RuntimePipelineResult:
    status: str
    recommendation: dict[str, Any] | None
    review_id: str | None
    events_published: int


class RecommendationRuntimePipeline:
    def __init__(
        self,
        *,
        review_repo: InMemoryReviewRepository | None = None,
        event_publisher: RecommendationEventPublisher | None = None,
        tenant_validator: MultiTenantRuntimeValidator | None = None,
    ) -> None:
        self.review_repo = review_repo or InMemoryReviewRepository()
        self.event_publisher = event_publisher or RecommendationEventPublisher()
        self.tenant_validator = tenant_validator or MultiTenantRuntimeValidator()

    async def execute(
        self,
        *,
        tenant_id: str,
        field_id: str,
        context: dict[str, Any],
        recommendation_engine: Any,
        intent: str = "general",
    ) -> RuntimePipelineResult:
        self.tenant_validator.validate(tenant_id, context)
        runtime_metrics.inc("recommendation_runtime_requests_total")

        if guarded_runtime_context is not None:
            prepared = guarded_runtime_context(context)
        else:
            if not context.get("canonical_field_state"):
                runtime_metrics.inc("recommendation_blocked_total")
                return RuntimePipelineResult("blocked_missing_field_state", None, None, 0)
            prepared = context

        if not prepared.get("canonical_field_state"):
            runtime_metrics.inc("recommendation_blocked_total")
            return RuntimePipelineResult("blocked_missing_field_state", None, None, 0)

        recommendation = recommendation_engine(prepared)
        self.tenant_validator.validate(tenant_id, recommendation)

        rec_id = str(recommendation.get("id", "runtime-rec"))
        await self.event_publisher.publish(
            RecommendationEvent(
                tenant_id=tenant_id,
                field_id=field_id,
                recommendation_id=rec_id,
                event_type="created",
                payload={"intent": intent},
            )
        )

        risk = str(recommendation.get("risk_level", "")).lower()
        rec_type = str(recommendation.get("type", intent)).lower()
        needs_review = (
            intent == "pesticide"
            or "pesticide" in rec_type
            or "spray" in rec_type
            or risk == "high"
            or bool(recommendation.get("requires_human_review"))
        )

        if needs_review:
            review = self.review_repo.create_review(
                ReviewRecord(
                    review_id=new_review_id(),
                    recommendation_id=rec_id,
                    tenant_id=tenant_id,
                    field_id=field_id,
                    risk_level=risk or "high",
                    state="pending_review",
                )
            )
            runtime_metrics.inc("human_review_required_total")
            await self.event_publisher.publish(
                RecommendationEvent(
                    tenant_id=tenant_id,
                    field_id=field_id,
                    recommendation_id=rec_id,
                    event_type="review_required",
                    payload={"review_id": review.review_id},
                )
            )
            return RuntimePipelineResult(
                "pending_review",
                recommendation,
                review.review_id,
                len(self.event_publisher.published),
            )

        return RuntimePipelineResult(
            "ready", recommendation, None, len(self.event_publisher.published)
        )
