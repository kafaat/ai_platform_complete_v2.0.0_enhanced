"""Replay-to-Canonical Field State bridge.

This module closes the loop between event sourcing and the Canonical Field State.
It rebuilds a field state from immutable field events, while preserving the
Source-of-Truth rule: events become signals/annotations only; they never become
recommendations or prescriptions directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .canonical_field_state_lock import (
    CanonicalFieldState,
    FieldAnnotation,
    FieldSignal,
    compose_locked_field_state,
)
from .field_event_sourcing import FieldEvent, replay_field_events


@dataclass(frozen=True)
class ReplayToStateResult:
    """Replay result with the locked state and audit facts for deterministic checks."""

    state: CanonicalFieldState
    replayed_event_count: int
    lab_count: int
    satellite_count: int
    operation_count: int
    recommendation_event_count: int
    harvest_count: int


def _lab_signal(result: dict) -> FieldSignal:
    value = {
        key: result[key]
        for key in ("ph", "ec", "sar", "npk", "organic_matter_pct", "sample_id")
        if key in result
    }
    return FieldSignal(
        name="lab_state",
        kind="lab",
        value=value,
        verified=True,
        evidence_class="governing",
        source=result.get("source", "lab_event"),
    )


def _satellite_signal(result: dict) -> FieldSignal:
    value = {
        key: result[key]
        for key in ("ndvi", "ndmi", "msavi", "capture_date", "cloud_cover_pct")
        if key in result
    }
    return FieldSignal(
        name="satellite_state",
        kind="satellite",
        value=value,
        verified=bool(result.get("quality") == "clear" or result.get("verified")),
        evidence_class="indication",
        source=result.get("source", "satellite_event"),
    )


def _operation_signal(result: dict) -> FieldSignal:
    value = {
        key: result[key]
        for key in ("type", "operation", "status", "water_mm", "task_id", "completed_pct")
        if key in result
    }
    return FieldSignal(
        name="operation_state",
        kind="operations",
        value=value,
        verified=True,
        evidence_class="modifying",
        source=result.get("source", "operation_event"),
    )


def _recommendation_annotation(result: dict) -> FieldAnnotation:
    return FieldAnnotation(
        name="recommendation_history",
        kind="kg",
        value={
            key: result[key]
            for key in ("type", "recommendation_id", "status", "reason", "engine_version")
            if key in result
        },
        source="event_history",
    )


def build_canonical_state_from_events(
    events: Iterable[FieldEvent], *, tenant_id: str, field_id: str, at: str | None = None
) -> ReplayToStateResult:
    """Build a locked Canonical Field State from replayed immutable events.

    Lab events become verified governing evidence. Satellite events remain
    indications. Recommendation events are explanatory annotations only and are
    deliberately excluded from recommendation_inputs to avoid decision feedback
    loops.
    """

    history = replay_field_events(events, tenant_id=tenant_id, field_id=field_id, at=at)
    signals: list[FieldSignal] = []
    annotations: list[FieldAnnotation] = []

    for lab in history.lab_results:
        signals.append(_lab_signal(lab))
    for satellite in history.satellite:
        signals.append(_satellite_signal(satellite))
    for operation in history.operations:
        signals.append(_operation_signal(operation))
    for rec in history.recommendations:
        annotations.append(_recommendation_annotation(rec))

    lifecycle = "ready" if history.lab_results else "limited"
    state = compose_locked_field_state(
        field_id=field_id,
        tenant_id=tenant_id,
        signals=signals,
        annotations=annotations,
        lifecycle=lifecycle,
    )

    return ReplayToStateResult(
        state=state,
        replayed_event_count=len(history.lab_results)
        + len(history.satellite)
        + len(history.operations)
        + len(history.recommendations)
        + len(history.harvests)
        + (1 if history.field else 0),
        lab_count=len(history.lab_results),
        satellite_count=len(history.satellite),
        operation_count=len(history.operations),
        recommendation_event_count=len(history.recommendations),
        harvest_count=len(history.harvests),
    )
