"""Event-sourced field history utilities.

This module is intentionally dependency-light. It hardens the Canonical Field State
architecture by making every agronomic change replayable as an immutable event.
Events reconstruct observations/signals; they do not emit recommendations.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal

EventName = Literal[
    "FieldCreated",
    "LabResultAdded",
    "SatelliteUpdated",
    "IrrigationExecuted",
    "TaskCompleted",
    "RecommendationIssued",
    "RecommendationAccepted",
    "RecommendationRejected",
    "HarvestRecorded",
]


class FieldEventError(ValueError):
    """Raised when an event violates replay/source-of-truth invariants."""


@dataclass(frozen=True)
class FieldEvent:
    tenant_id: str
    field_id: str
    name: EventName
    payload: dict[str, Any]
    occurred_at: str
    event_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.field_id:
            raise FieldEventError("tenant_id and field_id are required")
        if self.schema_version < 1:
            raise FieldEventError("schema_version must be positive")
        try:
            datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise FieldEventError("occurred_at must be ISO-8601") from exc
        forbidden = {"prescription_map", "direct_task", "raw_decision"}
        if forbidden.intersection(self.payload):
            raise FieldEventError("events must not bypass Recommendation Engine")

    @property
    def stable_id(self) -> str:
        if self.event_id:
            return self.event_id
        raw = f"{self.tenant_id}|{self.field_id}|{self.name}|{self.occurred_at}|{self.payload!r}"
        return sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class ReplayedFieldHistory:
    tenant_id: str
    field_id: str
    at: str | None
    field: dict[str, Any] = dataclass_field(default_factory=dict)
    lab_results: list[dict[str, Any]] = dataclass_field(default_factory=list)
    satellite: list[dict[str, Any]] = dataclass_field(default_factory=list)
    operations: list[dict[str, Any]] = dataclass_field(default_factory=list)
    recommendations: list[dict[str, Any]] = dataclass_field(default_factory=list)
    harvests: list[dict[str, Any]] = dataclass_field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def replay_field_events(
    events: Iterable[FieldEvent], *, tenant_id: str, field_id: str, at: str | None = None
) -> ReplayedFieldHistory:
    """Rebuild field history from immutable events up to an optional timestamp."""
    cutoff = datetime.fromisoformat(at.replace("Z", "+00:00")) if at else None
    relevant: list[FieldEvent] = []
    for event in events:
        if event.tenant_id != tenant_id or event.field_id != field_id:
            continue
        when = datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
        if cutoff and when > cutoff:
            continue
        relevant.append(event)
    relevant.sort(key=lambda e: (e.occurred_at, e.stable_id))

    history = ReplayedFieldHistory(tenant_id=tenant_id, field_id=field_id, at=at)
    for event in relevant:
        payload = {**event.payload, "event_id": event.stable_id, "occurred_at": event.occurred_at}
        if event.name == "FieldCreated":
            history.field.update(payload)
        elif event.name == "LabResultAdded":
            history.lab_results.append(payload)
        elif event.name == "SatelliteUpdated":
            history.satellite.append(payload)
        elif event.name in {"IrrigationExecuted", "TaskCompleted"}:
            history.operations.append({"type": event.name, **payload})
        elif event.name in {
            "RecommendationIssued",
            "RecommendationAccepted",
            "RecommendationRejected",
        }:
            history.recommendations.append({"type": event.name, **payload})
        elif event.name == "HarvestRecorded":
            history.harvests.append(payload)
    return history
