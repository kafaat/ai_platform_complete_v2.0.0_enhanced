"""Human review repository boundary.

This module intentionally separates workflow logic from persistence. The in-memory
implementation is safe for unit tests; PostgreSQLRepository is a dependency-injected
boundary for production without forcing DB availability in sandbox tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    recommendation_id: str
    tenant_id: str
    field_id: str
    risk_level: str
    state: str = "pending_review"
    created_at: str = field(default_factory=utc_now)
    published_at: str | None = None


@dataclass(frozen=True)
class ReviewDecisionRecord:
    decision_id: str
    review_id: str
    reviewer_id: str
    action: str
    reason: str = ""
    modifications: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


class ReviewRepository(Protocol):
    def create_review(self, record: ReviewRecord) -> ReviewRecord: ...
    def add_decision(self, decision: ReviewDecisionRecord) -> ReviewDecisionRecord: ...
    def get_review(self, review_id: str) -> ReviewRecord | None: ...
    def list_pending(self, tenant_id: str | None = None) -> list[ReviewRecord]: ...


class InMemoryReviewRepository:
    """Test-safe repository. Replace with SQL repository in live runtime."""

    def __init__(self) -> None:
        self._reviews: dict[str, ReviewRecord] = {}
        self._decisions: list[ReviewDecisionRecord] = []

    def create_review(self, record: ReviewRecord) -> ReviewRecord:
        self._reviews[record.review_id] = record
        return record

    def add_decision(self, decision: ReviewDecisionRecord) -> ReviewDecisionRecord:
        if decision.review_id not in self._reviews:
            raise KeyError(f"review not found: {decision.review_id}")
        self._decisions.append(decision)
        review = self._reviews[decision.review_id]
        new_state = {
            "approve": "approved",
            "revise": "revised",
            "reject": "rejected",
            "publish": "published",
        }.get(decision.action, review.state)
        self._reviews[decision.review_id] = ReviewRecord(
            review_id=review.review_id,
            recommendation_id=review.recommendation_id,
            tenant_id=review.tenant_id,
            field_id=review.field_id,
            risk_level=review.risk_level,
            state=new_state,
            created_at=review.created_at,
            published_at=utc_now() if new_state == "published" else review.published_at,
        )
        return decision

    def get_review(self, review_id: str) -> ReviewRecord | None:
        return self._reviews.get(review_id)

    def list_pending(self, tenant_id: str | None = None) -> list[ReviewRecord]:
        rows = [r for r in self._reviews.values() if r.state == "pending_review"]
        if tenant_id is not None:
            rows = [r for r in rows if r.tenant_id == tenant_id]
        return rows

    def export_learning_dataset(self) -> list[dict[str, Any]]:
        return [
            {"review": asdict(self._reviews[d.review_id]), "decision": asdict(d)}
            for d in self._decisions
        ]


def new_review_id() -> str:
    return f"review-{uuid4()}"
