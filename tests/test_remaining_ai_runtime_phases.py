
import pytest

from services.ai_agronomist.feedback_repository import FeedbackRecord, InMemoryFeedbackRepository, new_feedback_id
from services.ai_agronomist.human_review_repository import InMemoryReviewRepository, ReviewDecisionRecord, ReviewRecord, new_review_id
from services.ai_agronomist.multi_tenant_runtime_validator import MultiTenantRuntimeValidator, TenantIsolationViolation
from services.ai_agronomist.recommendation_events import RecommendationEvent, RecommendationEventPublisher
from services.ai_agronomist.recommendation_runtime_pipeline import RecommendationRuntimePipeline


def test_human_review_repository_lifecycle():
    repo = InMemoryReviewRepository()
    review = repo.create_review(ReviewRecord(
        review_id=new_review_id(),
        recommendation_id="rec-1",
        tenant_id="tenant-1",
        field_id="field-1",
        risk_level="high",
    ))
    assert repo.list_pending("tenant-1")
    repo.add_decision(ReviewDecisionRecord(
        decision_id="decision-1",
        review_id=review.review_id,
        reviewer_id="u-1",
        action="approve",
    ))
    assert repo.get_review(review.review_id).state == "approved"


def test_feedback_metrics():
    repo = InMemoryFeedbackRepository()
    repo.add(FeedbackRecord(
        feedback_id=new_feedback_id(),
        recommendation_id="rec-1",
        tenant_id="tenant-1",
        field_id="field-1",
        accepted=True,
        predicted_yield=4.0,
        actual_yield=5.0,
    ))
    metrics = repo.metrics("tenant-1")
    assert metrics["count"] == 1
    assert metrics["acceptance_rate"] == 1.0
    assert metrics["yield_rmse"] == 1.0


def test_tenant_validator_blocks_nested_leak():
    validator = MultiTenantRuntimeValidator()
    with pytest.raises(TenantIsolationViolation):
        validator.validate("tenant-1", {"items": [{"tenant_id": "tenant-2"}]})


@pytest.mark.asyncio
async def test_event_publisher_stores_events_without_nats():
    publisher = RecommendationEventPublisher()
    event = RecommendationEvent(
        tenant_id="tenant-1",
        field_id="field-1",
        recommendation_id="rec-1",
        event_type="created",
    )
    assert await publisher.publish(event)
    assert publisher.published[0][0] == "recommendation.created"


@pytest.mark.asyncio
async def test_runtime_pipeline_pesticide_requires_review():
    def fake_engine(prepared):
        return {
            "id": "rec-1",
            "tenant_id": "tenant-1",
            "field_id": "field-1",
            "type": "pesticide",
            "risk_level": "high",
        }

    pipeline = RecommendationRuntimePipeline()
    result = await pipeline.execute(
        tenant_id="tenant-1",
        field_id="field-1",
        intent="pesticide",
        context={
            "canonical_field_state": {"tenant_id": "tenant-1", "field_id": "field-1"},
            "signals": {"weather": {"tenant_id": "tenant-1", "et0": 4.2}},
            "tool_outputs": {},
        },
        recommendation_engine=fake_engine,
    )
    assert result.status == "pending_review"
    assert result.review_id is not None
    assert result.events_published >= 2


@pytest.mark.asyncio
async def test_runtime_pipeline_blocks_cross_tenant_recommendation():
    def bad_engine(prepared):
        return {"id": "rec-1", "tenant_id": "tenant-2", "field_id": "field-1"}

    pipeline = RecommendationRuntimePipeline()
    with pytest.raises(TenantIsolationViolation):
        await pipeline.execute(
            tenant_id="tenant-1",
            field_id="field-1",
            intent="general",
            context={
                "canonical_field_state": {"tenant_id": "tenant-1", "field_id": "field-1"},
                "signals": {},
                "tool_outputs": {},
            },
            recommendation_engine=bad_engine,
        )
