"""Recommendation lifecycle events.

The publisher is intentionally a boundary: tests use the in-memory mode, while
production can pass a NATS JetStream client implementing publish(subject, bytes).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

RECOMMENDATION_STREAM = "SAHOOL_RECOMMENDATIONS"

SUBJECTS = {
    "created": "recommendation.created",
    "review_required": "recommendation.review_required",
    "approved": "recommendation.approved",
    "rejected": "recommendation.rejected",
    "published": "recommendation.published",
    "executed": "recommendation.executed",
    "feedback_received": "recommendation.feedback_received",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RecommendationEvent:
    tenant_id: str
    field_id: str
    recommendation_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=utc_now)

    def subject(self) -> str:
        return SUBJECTS.get(self.event_type, f"recommendation.{self.event_type}")

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True).encode("utf-8")


class RecommendationEventPublisher:
    """Safe event publisher. If no client is supplied, events are stored locally."""

    def __init__(self, client: Any | None = None, enabled: bool = False) -> None:
        self.client = client
        self.enabled = enabled
        self.published: list[tuple[str, RecommendationEvent]] = []

    async def publish(self, event: RecommendationEvent) -> bool:
        self.published.append((event.subject(), event))
        if not self.enabled or self.client is None:
            return True
        await self.client.publish(event.subject(), event.to_bytes())
        return True
