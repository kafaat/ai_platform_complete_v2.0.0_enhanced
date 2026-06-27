"""Recommendation feedback persistence boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    recommendation_id: str
    tenant_id: str
    field_id: str
    accepted: bool | None = None
    actual_yield: float | None = None
    predicted_yield: float | None = None
    actual_cost: float | None = None
    standard_cost: float | None = None
    actual_water: float | None = None
    standard_water: float | None = None
    created_at: str = field(default_factory=utc_now)


class InMemoryFeedbackRepository:
    def __init__(self) -> None:
        self._rows: list[FeedbackRecord] = []

    def add(self, record: FeedbackRecord) -> FeedbackRecord:
        self._rows.append(record)
        return record

    def list(
        self, tenant_id: str | None = None, field_id: str | None = None
    ) -> list[FeedbackRecord]:
        rows = self._rows
        if tenant_id is not None:
            rows = [r for r in rows if r.tenant_id == tenant_id]
        if field_id is not None:
            rows = [r for r in rows if r.field_id == field_id]
        return rows

    def metrics(self, tenant_id: str | None = None) -> dict[str, Any]:
        rows = self.list(tenant_id=tenant_id)
        accepted_known = [r for r in rows if r.accepted is not None]
        acceptance_rate = (
            None
            if not accepted_known
            else sum(1 for r in accepted_known if r.accepted) / len(accepted_known)
        )
        yield_pairs = [
            (r.predicted_yield, r.actual_yield)
            for r in rows
            if r.predicted_yield is not None and r.actual_yield is not None
        ]
        rmse = None
        if yield_pairs:
            rmse = math.sqrt(sum((a - p) ** 2 for p, a in yield_pairs) / len(yield_pairs))
        return {
            "count": len(rows),
            "acceptance_rate": acceptance_rate,
            "yield_rmse": rmse,
        }


def new_feedback_id() -> str:
    return f"feedback-{uuid4()}"
