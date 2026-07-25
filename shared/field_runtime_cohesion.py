"""Runtime cohesion contracts for SAHOOL field intelligence.

This module closes the gap found in the audit: multiple field-state/twin/decision
views existed, but there was no single runtime adapter making CanonicalFieldState
THE source of truth.  The functions here are dependency-light and testable; live
adapters can persist the returned dictionaries to PostGIS/outbox/NATS without
changing the contracts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:  # runtime when services/sahool-platform is on PYTHONPATH
    from core.agronomic_state_engine import CanonicalFieldState  # type: ignore
except Exception:  # fallback for pure import in tooling
    CanonicalFieldState = Any  # type: ignore


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


def _state_to_dict(state: Any) -> dict[str, Any]:
    if hasattr(state, "to_dict"):
        return state.to_dict()
    if isinstance(state, dict):
        return dict(state)
    raise TypeError("canonical state must be CanonicalFieldState-like or dict")


@dataclass(frozen=True)
class CanonicalStateEnvelope:
    """Immutable runtime envelope for one legal field-state snapshot."""

    state_id: str
    tenant_id: str | None
    farm_id: str | None
    field_id: str
    generated_at: str
    schema_version: str
    fusion_strategy_version: str
    state: dict[str, Any]
    derived_view_policy: str = "canonical_field_state_is_source_of_truth"


def create_canonical_state_envelope(state: Any) -> dict[str, Any]:
    """Create a stable envelope from CanonicalFieldState.

    Every downstream view/twin/recommendation should reference `state_id` rather
    than recomputing its own interpretation from raw signals.
    """
    d = _state_to_dict(state)
    material = {
        "tenant_id": d.get("tenant_id"),
        "farm_id": d.get("farm_id"),
        "field_id": d.get("field_id"),
        "generated_at": d.get("generated_at"),
        "schema_version": d.get("schema_version"),
        "fusion_strategy_version": d.get("fusion_strategy_version"),
        "operational_truths": d.get("operational_truths", {}),
        "confidence": d.get("confidence"),
    }
    envelope = CanonicalStateEnvelope(
        state_id=_stable_id(material, "cfs"),
        tenant_id=d.get("tenant_id"),
        farm_id=d.get("farm_id"),
        field_id=str(d.get("field_id")),
        generated_at=str(d.get("generated_at")),
        schema_version=str(d.get("schema_version", "unknown")),
        fusion_strategy_version=str(d.get("fusion_strategy_version", "unknown")),
        state=d,
    )
    return asdict(envelope)


@dataclass(frozen=True)
class DerivedTwinView:
    twin_id: str
    source_state_id: str
    field_id: str
    tenant_id: str | None
    generated_at: str
    health: dict[str, Any]
    water: dict[str, Any]
    crop: dict[str, Any]
    economics: dict[str, Any]
    limitations: list[str]


def build_unified_digital_twin_view(
    envelope: dict[str, Any],
    *,
    economics: dict[str, Any] | None = None,
    equipment: dict[str, Any] | None = None,
    irrigation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a digital-twin view derived from the canonical state only."""
    state = envelope.get("state", {})
    truths = state.get("operational_truths", {}) or {}
    limitations = list(state.get("missing_signals", []) or [])
    if equipment is None:
        limitations.append("equipment_state_not_bound")
    if irrigation is None:
        limitations.append("irrigation_runtime_not_bound")
    view = DerivedTwinView(
        twin_id=_stable_id(
            {"source": envelope.get("state_id"), "kind": "digital_twin_view"}, "dtv"
        ),
        source_state_id=str(envelope.get("state_id")),
        field_id=str(envelope.get("field_id")),
        tenant_id=envelope.get("tenant_id"),
        generated_at=_now(),
        health={
            "effective_status": truths.get("effective_status"),
            "crop_vigor": truths.get("crop_vigor"),
            "ndvi_trend": truths.get("ndvi_trend"),
            "salinity_class": truths.get("salinity_class"),
            "confidence": state.get("confidence"),
        },
        water={
            "kc": truths.get("kc"),
            "et0_mm": truths.get("et0_mm"),
            "etc_mm": truths.get("etc_mm"),
            "water_context": irrigation or {},
        },
        crop={
            "growth_stage": truths.get("growth_stage") or truths.get("fao56_stage"),
            "crop_id": truths.get("crop_id"),
            "variety_id": truths.get("variety_id"),
            "farmer_objective": truths.get("farmer_objective"),
        },
        economics=economics or {},
        limitations=sorted(set(limitations)),
    )
    return asdict(view)


class RecommendationStatus(str, Enum):
    PROPOSED = "proposed"
    GUARDRAILS_BLOCKED = "guardrails_blocked"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    EXECUTED = "executed"
    VERIFIED = "verified"
    LEARNED = "learned"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[RecommendationStatus, set[RecommendationStatus]] = {
    RecommendationStatus.PROPOSED: {
        RecommendationStatus.GUARDRAILS_BLOCKED,
        RecommendationStatus.APPROVED,
        RecommendationStatus.CANCELLED,
    },
    RecommendationStatus.GUARDRAILS_BLOCKED: {
        RecommendationStatus.PROPOSED,
        RecommendationStatus.CANCELLED,
    },
    RecommendationStatus.APPROVED: {
        RecommendationStatus.DISPATCHED,
        RecommendationStatus.CANCELLED,
    },
    RecommendationStatus.DISPATCHED: {
        RecommendationStatus.EXECUTED,
        RecommendationStatus.CANCELLED,
    },
    RecommendationStatus.EXECUTED: {RecommendationStatus.VERIFIED},
    RecommendationStatus.VERIFIED: {RecommendationStatus.LEARNED},
    RecommendationStatus.LEARNED: set(),
    RecommendationStatus.CANCELLED: set(),
}


@dataclass
class RecommendationLifecycle:
    recommendation_id: str
    source_state_id: str
    field_id: str
    tenant_id: str | None
    status: RecommendationStatus
    action_type: str | None
    decision: dict[str, Any]
    evidence: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)

    def transition(
        self,
        to_status: RecommendationStatus | str,
        *,
        actor: str,
        note: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> None:
        target = RecommendationStatus(to_status)
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(
                f"invalid recommendation transition: {self.status.value} -> {target.value}"
            )
        self.status = target
        self.events.append(
            {
                "event_id": _stable_id(
                    {"rec": self.recommendation_id, "to": target.value, "n": len(self.events)},
                    "revt",
                ),
                "status": target.value,
                "actor": actor,
                "note": note,
                "evidence": evidence or {},
                "occurred_at": _now(),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def open_recommendation_lifecycle(
    envelope: dict[str, Any],
    decision: dict[str, Any],
    *,
    actor: str = "field_intelligence_coordinator",
) -> dict[str, Any]:
    """Open the recommendation lifecycle from one canonical state snapshot."""
    status = RecommendationStatus.PROPOSED
    if decision.get("actionable") and not decision.get("executable", False):
        status = RecommendationStatus.GUARDRAILS_BLOCKED
    elif decision.get("executable", False):
        status = RecommendationStatus.APPROVED
    rec = RecommendationLifecycle(
        recommendation_id=_stable_id(
            {"state": envelope.get("state_id"), "decision": decision}, "rec"
        ),
        source_state_id=str(envelope.get("state_id")),
        field_id=str(envelope.get("field_id")),
        tenant_id=envelope.get("tenant_id"),
        status=status,
        action_type=decision.get("action_type"),
        decision=dict(decision),
        evidence={
            "canonical_state_id": envelope.get("state_id"),
            "confidence": envelope.get("state", {}).get("confidence"),
            "effective_status": envelope.get("state", {})
            .get("operational_truths", {})
            .get("effective_status"),
            "dispatch_block_reason": decision.get("dispatch_block_reason"),
        },
    )
    rec.events.append(
        {
            "event_id": _stable_id(
                {"rec": rec.recommendation_id, "status": rec.status.value}, "revt"
            ),
            "status": rec.status.value,
            "actor": actor,
            "note": "recommendation lifecycle opened from canonical state",
            "evidence": rec.evidence,
            "occurred_at": _now(),
        }
    )
    return rec.to_dict()


def apply_lifecycle_transition(
    record: dict[str, Any],
    to_status: str,
    *,
    actor: str,
    note: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec = RecommendationLifecycle(
        recommendation_id=record["recommendation_id"],
        source_state_id=record["source_state_id"],
        field_id=record["field_id"],
        tenant_id=record.get("tenant_id"),
        status=RecommendationStatus(record["status"]),
        action_type=record.get("action_type"),
        decision=record.get("decision", {}),
        evidence=record.get("evidence", {}),
        events=list(record.get("events", [])),
    )
    rec.transition(to_status, actor=actor, note=note, evidence=evidence)
    return rec.to_dict()


def build_outcome_feedback(
    recommendation: dict[str, Any],
    *,
    verification: dict[str, Any],
    outcome_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build a learning-loop event after verification."""
    if recommendation.get("status") != RecommendationStatus.VERIFIED.value:
        raise ValueError("outcome feedback requires a verified recommendation")
    return {
        "feedback_id": _stable_id(
            {"rec": recommendation.get("recommendation_id"), "metrics": outcome_metrics}, "fbk"
        ),
        "recommendation_id": recommendation.get("recommendation_id"),
        "source_state_id": recommendation.get("source_state_id"),
        "field_id": recommendation.get("field_id"),
        "tenant_id": recommendation.get("tenant_id"),
        "verification": verification,
        "outcome_metrics": outcome_metrics,
        "feature_store_candidate": True,
        "model_training_candidate": bool(outcome_metrics),
        "created_at": _now(),
    }


def adapt_phase6_inputs_from_twin(twin_view: dict[str, Any]) -> dict[str, Any]:
    """Normalize canonical twin view into Phase 6 intelligence inputs."""
    health = twin_view.get("health", {})
    water = twin_view.get("water", {})
    crop = twin_view.get("crop", {})
    return {
        "field_id": twin_view.get("field_id"),
        "source_state_id": twin_view.get("source_state_id"),
        "features": {
            "crop_vigor": health.get("crop_vigor"),
            "ndvi_trend": health.get("ndvi_trend"),
            "salinity_class": health.get("salinity_class"),
            "kc": water.get("kc"),
            "etc_mm": water.get("etc_mm"),
            "growth_stage": crop.get("growth_stage"),
        },
        "limitations": twin_view.get("limitations", []),
        "runtime_binding": "phase6_uses_canonical_twin_view",
    }


def run_cohesive_field_runtime(
    *,
    field_intelligence_result: Any,
    economics: dict[str, Any] | None = None,
    equipment: dict[str, Any] | None = None,
    irrigation: dict[str, Any] | None = None,
    persist_fn: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Compose the unified runtime payload from the existing coordinator result."""
    state = getattr(
        field_intelligence_result, "canonical_state", None
    ) or field_intelligence_result.get("canonical_state")
    decision = getattr(
        field_intelligence_result, "policy_decision", None
    ) or field_intelligence_result.get("policy_decision", {})
    envelope = create_canonical_state_envelope(state)
    twin = build_unified_digital_twin_view(
        envelope, economics=economics, equipment=equipment, irrigation=irrigation
    )
    recommendation = open_recommendation_lifecycle(envelope, decision)
    phase6_inputs = adapt_phase6_inputs_from_twin(twin)
    payload = {
        "runtime_id": _stable_id(
            {"state": envelope["state_id"], "recommendation": recommendation["recommendation_id"]},
            "frt",
        ),
        "canonical_state": envelope,
        "digital_twin_view": twin,
        "recommendation_lifecycle": recommendation,
        "phase6_runtime_inputs": phase6_inputs,
        "created_at": _now(),
        "contract": "canonical_state_to_twin_to_recommendation_to_feedback",
    }
    if persist_fn is not None:
        persist_fn(payload)
    return payload
