"""Phase 11 federated-agent production runtime guards.

This module hardens the existing deterministic Phase 11 federation layer with
production-style controls that stay dependency-light for CI:

* reputation-weighted consensus so unreliable agents cannot dominate;
* explicit conflict-resolution policy before Phase 9 execution;
* authority envelopes that keep agents in a propose-only lane;
* audit/event envelopes for downstream outbox/NATS publishing.

The runtime is intentionally fail-closed: any unknown high-impact action,
missing field context, safety veto, or conflicting proposal set requires human
approval and cannot be dispatched directly.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


class RuntimeDecisionStatus(str, Enum):
    APPROVED_ADVISORY = "approved_advisory"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AgentReputation:
    agent_role: str
    score: float
    sample_count: int
    safety_incident_count: int
    stale: bool
    updated_at: str


@dataclass(frozen=True)
class ConflictResolution:
    resolution_id: str
    status: str
    selected_action: str | None
    conflict_reasons: list[str]
    vetoes: list[str]
    approval_required: bool
    ranked_actions: list[dict[str, Any]]
    created_at: str


@dataclass(frozen=True)
class AuthorityEnvelope:
    envelope_id: str
    cycle_id: str | None
    field_id: str | None
    allowed_authority: str
    may_execute: bool
    may_publish_event: bool
    required_next_gate: str
    blocked_reasons: list[str]
    evidence: dict[str, Any]
    created_at: str


DEFAULT_REPUTATION: dict[str, float] = {
    "planner": 0.78,
    "water": 0.86,
    "agronomy": 0.84,
    "disease": 0.82,
    "soil": 0.83,
    "economics": 0.76,
    "operations": 0.80,
    "safety": 0.92,
}

HIGH_IMPACT_ACTIONS = {"irrigate", "fertilize", "spray", "actuate", "execute"}
SAFE_ACTIONS = {"wait", "scout", "recompute", "explain", "advise"}
CONFLICT_PAIRS = {
    frozenset({"irrigate", "block"}): "irrigation_conflicts_with_safety_veto",
    frozenset({"fertilize", "block"}): "fertilization_conflicts_with_safety_veto",
    frozenset({"spray", "wait"}): "spray_window_conflicts_with_wait_recommendation",
    frozenset({"spray", "block"}): "spray_conflicts_with_safety_veto",
    frozenset({"irrigate", "wait"}): "irrigation_conflicts_with_wait_recommendation",
}


def normalize_reputations(raw: dict[str, Any] | None = None) -> dict[str, AgentReputation]:
    """Return bounded, auditable reputation records keyed by agent role."""
    raw = raw or {}
    roles = set(DEFAULT_REPUTATION) | {str(k) for k in raw.keys()}
    out: dict[str, AgentReputation] = {}
    for role in sorted(roles):
        item = raw.get(role, {}) if isinstance(raw.get(role), dict) else {"score": raw.get(role)}
        score = _num(
            item.get("score", DEFAULT_REPUTATION.get(role, 0.75)),
            DEFAULT_REPUTATION.get(role, 0.75),
        )
        score = max(0.05, min(1.0, score))
        sample_count = max(0, int(_num(item.get("sample_count", item.get("samples", 0)), 0)))
        incident_count = max(
            0, int(_num(item.get("safety_incident_count", item.get("incidents", 0)), 0))
        )
        stale = bool(item.get("stale", sample_count < 3))
        if incident_count:
            score = max(0.05, score - min(0.4, incident_count * 0.08))
        out[role] = AgentReputation(
            role,
            round(score, 4),
            sample_count,
            incident_count,
            stale,
            str(item.get("updated_at") or _now()),
        )
    return out


def reputation_weighted_consensus(
    proposals: list[dict[str, Any]],
    *,
    objective: str = "optimize_field_outcome",
    execution_mode: str = "human_in_loop",
    reputations: dict[str, Any] | None = None,
    min_confidence: float = 0.62,
) -> dict[str, Any]:
    """Resolve proposals with reputation and fail-closed conflict controls."""
    reputation_records = normalize_reputations(reputations)
    if not proposals:
        return asdict(
            ConflictResolution(
                resolution_id=_stable_id({"objective": objective, "empty": True}, "res11"),
                status=RuntimeDecisionStatus.BLOCKED.value,
                selected_action=None,
                conflict_reasons=["no_agent_proposals"],
                vetoes=[],
                approval_required=True,
                ranked_actions=[],
                created_at=_now(),
            )
        ) | {"reputations": {k: asdict(v) for k, v in reputation_records.items()}}

    action_scores: dict[str, float] = {}
    action_support: dict[str, int] = {}
    action_roles: dict[str, list[str]] = {}
    vetoes: list[str] = []
    action_set = {str(p.get("action")) for p in proposals}

    for proposal in proposals:
        role = str(proposal.get("agent_role") or proposal.get("role") or "unknown")
        action = str(proposal.get("action") or "unknown")
        rep = reputation_records.get(role) or AgentReputation(role, 0.65, 0, 0, True, _now())
        confidence = _num(proposal.get("confidence"), 0.0)
        priority = max(0.0, min(100.0, _num(proposal.get("priority"), 0.0)))
        safety_flags = [
            str(f) for f in (proposal.get("safety_flags") or proposal.get("flags") or [])
        ]
        if action == "block" or any(
            "veto" in f.lower() or "unsafe" in f.lower() for f in safety_flags
        ):
            vetoes.append(f"{role}:{action}:{','.join(safety_flags) or 'safety_veto'}")
        # Safety agents get their reputation weight, but high confidence alone is not enough to execute.
        score = confidence * rep.score * (1.0 + priority / 100.0)
        action_scores[action] = action_scores.get(action, 0.0) + score
        action_support[action] = action_support.get(action, 0) + 1
        action_roles.setdefault(action, []).append(role)

    ranked = [
        {
            "action": action,
            "score": round(score, 4),
            "support": action_support[action],
            "roles": sorted(set(action_roles[action])),
        }
        for action, score in action_scores.items()
    ]
    ranked.sort(key=lambda r: (r["score"], r["support"]), reverse=True)

    conflict_reasons: list[str] = []
    for pair, reason in CONFLICT_PAIRS.items():
        if pair.issubset(action_set):
            conflict_reasons.append(reason)

    selected = ranked[0]["action"] if ranked else None
    denominator = max(1.0, sum(action_scores.values()))
    selected_conf = (ranked[0]["score"] / denominator) if ranked else 0.0

    if vetoes:
        status = RuntimeDecisionStatus.BLOCKED.value
        selected = None
        approval_required = True
    elif conflict_reasons:
        status = RuntimeDecisionStatus.CONFLICTED.value
        approval_required = True
    elif selected_conf < min_confidence:
        status = RuntimeDecisionStatus.NEEDS_HUMAN_APPROVAL.value
        approval_required = True
    elif selected in HIGH_IMPACT_ACTIONS or execution_mode in {"autonomous", "human_in_loop"}:
        status = RuntimeDecisionStatus.NEEDS_HUMAN_APPROVAL.value
        approval_required = True
    else:
        status = RuntimeDecisionStatus.APPROVED_ADVISORY.value
        approval_required = False

    return asdict(
        ConflictResolution(
            resolution_id=_stable_id(
                {"objective": objective, "ranked": ranked, "vetoes": vetoes}, "res11"
            ),
            status=status,
            selected_action=selected,
            conflict_reasons=sorted(set(conflict_reasons)),
            vetoes=sorted(set(vetoes)),
            approval_required=approval_required,
            ranked_actions=ranked,
            created_at=_now(),
        )
    ) | {
        "objective": objective,
        "execution_mode": execution_mode,
        "confidence": round(selected_conf, 4),
        "reputations": {k: asdict(v) for k, v in reputation_records.items()},
        "proposal_count": len(proposals),
    }


def create_authority_envelope(
    cycle: dict[str, Any],
    *,
    resolution: dict[str, Any] | None = None,
    requested_authority: str = "advisory",
) -> dict[str, Any]:
    """Build a least-privilege envelope that keeps Phase 11 propose-only."""
    resolution = resolution or cycle.get("runtime_resolution") or cycle.get("consensus") or {}
    context = cycle.get("context") or {}
    op_plan = cycle.get("operation_plan") or {}
    selected_action = resolution.get("selected_action") or (cycle.get("consensus") or {}).get(
        "selected_action"
    )
    field_id = context.get("field_id") or op_plan.get("field_id") or cycle.get("field_id")
    status = str(resolution.get("status") or "unknown")
    blocked: list[str] = []

    if not field_id:
        blocked.append("field_context_missing")
    if status in {
        RuntimeDecisionStatus.BLOCKED.value,
        RuntimeDecisionStatus.CONFLICTED.value,
        "blocked",
        "conflicted",
    }:
        blocked.append(f"resolution_{status}")
    if resolution.get("approval_required"):
        blocked.append("human_approval_required")
    if selected_action in HIGH_IMPACT_ACTIONS:
        blocked.append("high_impact_action_requires_phase9_guardrails")
    if requested_authority not in {"advisory", "proposal", "shadow"}:
        blocked.append("phase11_cannot_request_execution_authority")

    may_publish_event = bool(field_id) and not any(
        b.startswith("resolution_blocked") for b in blocked
    )
    envelope = AuthorityEnvelope(
        envelope_id=_stable_id(
            {
                "cycle": cycle.get("cycle_id"),
                "field": field_id,
                "status": status,
                "blocked": blocked,
            },
            "auth11",
        ),
        cycle_id=cycle.get("cycle_id"),
        field_id=field_id,
        allowed_authority="proposal" if not blocked else "advisory_blocked",
        may_execute=False,
        may_publish_event=may_publish_event,
        required_next_gate="phase9_guardrails"
        if selected_action in HIGH_IMPACT_ACTIONS
        else "human_review_or_advisory_response",
        blocked_reasons=blocked,
        evidence={
            "resolution_id": resolution.get("resolution_id") or resolution.get("decision_id"),
            "selected_action": selected_action,
            "confidence": resolution.get("confidence"),
            "ranked_actions": resolution.get("ranked_actions", [])[:5],
        },
        created_at=_now(),
    )
    return asdict(envelope)


def update_agent_reputation(
    prior: dict[str, Any] | None,
    *,
    agent_role: str,
    outcome: str,
    confidence_error: float = 0.0,
    safety_incident: bool = False,
) -> dict[str, Any]:
    """Deterministically update one agent reputation from observed outcome."""
    reps = normalize_reputations(prior)
    current = reps.get(agent_role) or AgentReputation(agent_role, 0.65, 0, 0, True, _now())
    score = current.score
    if outcome in {"accepted", "verified", "beneficial"}:
        score += 0.035
    elif outcome in {"rejected", "unhelpful"}:
        score -= 0.035
    elif outcome in {"harmful", "unsafe", "failed"}:
        score -= 0.12
    score -= min(0.08, abs(_num(confidence_error, 0.0)) * 0.04)
    incidents = current.safety_incident_count + (1 if safety_incident else 0)
    if safety_incident:
        score -= 0.18
    updated = AgentReputation(
        agent_role=agent_role,
        score=round(max(0.05, min(1.0, score)), 4),
        sample_count=current.sample_count + 1,
        safety_incident_count=incidents,
        stale=False,
        updated_at=_now(),
    )
    reps[agent_role] = updated
    return {k: asdict(v) for k, v in reps.items()}


def build_federation_event_envelope(
    cycle: dict[str, Any], authority: dict[str, Any]
) -> dict[str, Any]:
    """Create an event envelope suitable for an outbox/NATS publisher."""
    event_type = (
        "agent.federation.proposed"
        if authority.get("may_publish_event")
        else "agent.federation.blocked"
    )
    payload = {
        "cycle_id": cycle.get("cycle_id"),
        "field_id": authority.get("field_id"),
        "authority": authority,
        "consensus": cycle.get("consensus"),
        "runtime_resolution": cycle.get("runtime_resolution"),
    }
    return {
        "event_id": _stable_id(payload, "evt11"),
        "event_type": event_type,
        "aggregate_type": "agent_federation_cycle",
        "aggregate_id": str(cycle.get("cycle_id") or authority.get("envelope_id")),
        "payload": payload,
        "idempotency_key": _stable_id(
            {"type": event_type, "cycle": cycle.get("cycle_id")}, "idem11"
        ),
        "created_at": _now(),
    }
