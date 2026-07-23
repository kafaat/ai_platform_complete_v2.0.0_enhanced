"""Phase 11 Federated Multi-Agent Autonomous Operations.

This module sits above Phase 9 closed-loop autonomy and Phase 10 learning.  It
adds a deterministic, auditable federation layer: specialized agents propose
actions, a consensus kernel resolves conflicts, operations are converted into a
safe execution plan, and experiments can run in shadow/canary/champion modes.

The implementation is dependency-light so CI can validate the decision logic;
production adapters can later route proposals through LangGraph/Temporal/MCP,
LLMs, or domain-specific ML services without changing the contracts.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from statistics import mean
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


class AgentRole(str, Enum):
    PLANNER = "planner"
    WATER = "water"
    AGRONOMY = "agronomy"
    DISEASE = "disease"
    SOIL = "soil"
    ECONOMICS = "economics"
    OPERATIONS = "operations"
    SAFETY = "safety"


class ProposalAction(str, Enum):
    IRRIGATE = "irrigate"
    FERTILIZE = "fertilize"
    SCOUT = "scout"
    SPRAY = "spray"
    WAIT = "wait"
    RECOMPUTE = "recompute"
    BLOCK = "block"


class ConsensusStatus(str, Enum):
    APPROVED = "approved"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"


class ExecutionMode(str, Enum):
    SHADOW = "shadow"
    ADVISORY = "advisory"
    HUMAN_IN_LOOP = "human_in_loop"
    AUTONOMOUS = "autonomous"


@dataclass(frozen=True)
class AgentProposal:
    proposal_id: str
    agent_role: str
    action: str
    confidence: float
    priority: int
    rationale: list[str]
    expected_effect: dict[str, float]
    required_inputs: list[str]
    safety_flags: list[str]
    evidence: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ConsensusDecision:
    decision_id: str
    objective: str
    status: str
    selected_action: str | None
    confidence: float
    approval_required: bool
    conflict_reasons: list[str]
    vetoes: list[str]
    proposal_count: int
    ranked_actions: list[dict[str, Any]]
    created_at: str


@dataclass(frozen=True)
class AutonomousOperationPlan:
    plan_id: str
    decision_id: str
    execution_mode: str
    field_id: str | None
    action: str | None
    steps: list[dict[str, Any]]
    safety_gates: list[dict[str, Any]]
    rollback_plan: list[dict[str, Any]]
    dispatch_ready: bool
    blocked_reasons: list[str]
    created_at: str


@dataclass(frozen=True)
class ShadowExperimentPlan:
    experiment_id: str
    name: str
    mode: str
    objective: str
    champion_policy: str
    challenger_policy: str
    traffic_split: dict[str, float]
    guardrails: dict[str, Any]
    promotion_metrics: list[str]
    created_at: str


@dataclass(frozen=True)
class FederationCycle:
    cycle_id: str
    objective: str
    context_id: str
    proposals: list[dict[str, Any]]
    consensus: dict[str, Any]
    operation_plan: dict[str, Any]
    experiment_plan: dict[str, Any] | None
    created_at: str


def build_agent_context(
    *,
    canonical_field_state: dict[str, Any],
    phase9_cycle: dict[str, Any] | None = None,
    phase10_learning: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize state into a single read model for specialist agents."""
    truths = (
        canonical_field_state.get("operational_truths") or canonical_field_state.get("truths") or {}
    )
    signals = canonical_field_state.get("signals") or canonical_field_state.get("indices") or {}
    field_id = canonical_field_state.get("field_id") or canonical_field_state.get("id")
    context = {
        "context_id": _stable_id({"field": field_id, "truths": truths, "signals": signals}, "ctx"),
        "field_id": field_id,
        "crop": canonical_field_state.get("crop") or canonical_field_state.get("crop_type"),
        "growth_stage": canonical_field_state.get("growth_stage") or truths.get("growth_stage"),
        "truths": truths,
        "signals": signals,
        "risks": canonical_field_state.get("risks") or truths.get("risks") or [],
        "confidence": _num(
            canonical_field_state.get("confidence", truths.get("confidence", 0.5)), 0.5
        ),
        "execution": (phase9_cycle or {}).get("execution")
        or (phase9_cycle or {}).get("operation_plan")
        or {},
        "learning": phase10_learning or {},
        "market": market_context or {},
        "created_at": _now(),
    }
    return context


def _proposal(
    role: AgentRole,
    action: ProposalAction,
    confidence: float,
    priority: int,
    rationale: list[str],
    *,
    evidence: dict[str, Any] | None = None,
    expected: dict[str, float] | None = None,
    required: list[str] | None = None,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    data = {
        "role": role.value,
        "action": action.value,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "priority": int(priority),
        "rationale": rationale,
        "evidence": evidence or {},
        "expected": expected or {},
        "required": required or [],
        "flags": flags or [],
    }
    return asdict(
        AgentProposal(
            proposal_id=_stable_id(data, "prop"),
            agent_role=role.value,
            action=action.value,
            confidence=data["confidence"],
            priority=data["priority"],
            rationale=rationale,
            expected_effect=expected or {},
            required_inputs=required or [],
            safety_flags=flags or [],
            evidence=evidence or {},
            created_at=_now(),
        )
    )


def run_specialist_agents(
    context: dict[str, Any],
    *,
    objective: str = "optimize_field_outcome",
    enabled_roles: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run deterministic specialist policies and return auditable proposals."""
    enabled = {r for r in (enabled_roles or [r.value for r in AgentRole])}
    truths = context.get("truths") or {}
    signals = context.get("signals") or {}
    risks = set(context.get("risks") or [])
    proposals: list[dict[str, Any]] = []

    water_stress = _num(truths.get("water_stress", signals.get("water_stress", 0.0)))
    soil_moisture = _num(truths.get("soil_moisture", signals.get("soil_moisture", 0.5)), 0.5)
    heat_risk = _num(truths.get("heat_risk", signals.get("heat_risk", 0.0)))
    vigor = _num(truths.get("vigor", signals.get("ndvi", 0.55)), 0.55)
    disease_risk = _num(truths.get("disease_risk", signals.get("disease_risk", 0.0)))
    salinity = _num(truths.get("salinity_risk", truths.get("soil_ec_risk", 0.0)))
    profit_margin = _num(
        (context.get("market") or {}).get("expected_margin", truths.get("expected_margin", 0.0))
    )
    confidence = _num(context.get("confidence"), 0.5)

    if AgentRole.WATER.value in enabled:
        if water_stress >= 0.65 or soil_moisture <= 0.28 or heat_risk >= 0.75:
            proposals.append(
                _proposal(
                    AgentRole.WATER,
                    ProposalAction.IRRIGATE,
                    max(0.62, confidence),
                    90,
                    ["water_or_heat_stress_detected"],
                    expected={"water_stress_delta": -0.25, "yield_risk_delta": -0.08},
                    evidence={
                        "water_stress": water_stress,
                        "soil_moisture": soil_moisture,
                        "heat_risk": heat_risk,
                    },
                    required=["pump_status", "water_allocation"],
                )
            )
        else:
            proposals.append(
                _proposal(
                    AgentRole.WATER,
                    ProposalAction.WAIT,
                    0.58,
                    30,
                    ["water_status_within_operational_band"],
                    evidence={"soil_moisture": soil_moisture},
                )
            )

    if AgentRole.AGRONOMY.value in enabled:
        if vigor < 0.42 and salinity < 0.6:
            proposals.append(
                _proposal(
                    AgentRole.AGRONOMY,
                    ProposalAction.FERTILIZE,
                    0.66,
                    70,
                    ["low_vigor_without_salinity_blocker"],
                    expected={"vigor_delta": 0.07},
                    evidence={"vigor": vigor, "salinity": salinity},
                    required=["recent_fertilizer_log", "crop_stage"],
                )
            )
        elif vigor < 0.42:
            proposals.append(
                _proposal(
                    AgentRole.AGRONOMY,
                    ProposalAction.SCOUT,
                    0.7,
                    65,
                    ["low_vigor_with_possible_non_nutrient_constraint"],
                    evidence={"vigor": vigor, "salinity": salinity},
                )
            )

    if AgentRole.DISEASE.value in enabled:
        if disease_risk >= 0.7 or "disease_high" in risks:
            proposals.append(
                _proposal(
                    AgentRole.DISEASE,
                    ProposalAction.SPRAY,
                    0.68,
                    80,
                    ["disease_risk_exceeds_action_threshold"],
                    expected={"disease_risk_delta": -0.2},
                    evidence={"disease_risk": disease_risk},
                    required=["spray_window", "chemical_label", "operator_available"],
                )
            )
        elif disease_risk >= 0.45:
            proposals.append(
                _proposal(
                    AgentRole.DISEASE,
                    ProposalAction.SCOUT,
                    0.64,
                    55,
                    ["disease_risk_requires_field_confirmation"],
                    evidence={"disease_risk": disease_risk},
                )
            )

    if AgentRole.SOIL.value in enabled:
        if salinity >= 0.75:
            proposals.append(
                _proposal(
                    AgentRole.SOIL,
                    ProposalAction.BLOCK,
                    0.82,
                    100,
                    ["salinity_critical_blocks_fertilizer_or_heavy_irrigation"],
                    evidence={"salinity": salinity},
                    flags=["soil_safety_veto"],
                )
            )
        elif salinity >= 0.5:
            proposals.append(
                _proposal(
                    AgentRole.SOIL,
                    ProposalAction.SCOUT,
                    0.62,
                    60,
                    ["soil_constraint_requires_sampling"],
                    evidence={"salinity": salinity},
                )
            )

    if AgentRole.ECONOMICS.value in enabled:
        if profit_margin < -0.05:
            proposals.append(
                _proposal(
                    AgentRole.ECONOMICS,
                    ProposalAction.WAIT,
                    0.72,
                    75,
                    ["negative_expected_margin_blocks_non_urgent_operation"],
                    evidence={"expected_margin": profit_margin},
                    flags=["economic_guardrail"],
                )
            )
        elif profit_margin > 0.12:
            proposals.append(
                _proposal(
                    AgentRole.ECONOMICS,
                    ProposalAction.RECOMPUTE,
                    0.57,
                    40,
                    ["positive_margin_allows_optimization"],
                    evidence={"expected_margin": profit_margin},
                )
            )

    if AgentRole.SAFETY.value in enabled:
        if confidence < 0.45:
            proposals.append(
                _proposal(
                    AgentRole.SAFETY,
                    ProposalAction.BLOCK,
                    0.9,
                    100,
                    ["field_state_confidence_below_safe_threshold"],
                    evidence={"confidence": confidence},
                    flags=["low_confidence_veto"],
                )
            )
        if truths.get("human_approval_required") is True:
            proposals.append(
                _proposal(
                    AgentRole.SAFETY,
                    ProposalAction.SCOUT,
                    0.75,
                    95,
                    ["human_approval_required_by_policy"],
                    flags=["approval_gate"],
                )
            )

    if AgentRole.OPERATIONS.value in enabled:
        if (context.get("execution") or {}).get("dispatch_ready") is False:
            proposals.append(
                _proposal(
                    AgentRole.OPERATIONS,
                    ProposalAction.RECOMPUTE,
                    0.63,
                    50,
                    ["previous_dispatch_not_ready"],
                    evidence=context.get("execution") or {},
                )
            )

    if AgentRole.PLANNER.value in enabled and not proposals:
        proposals.append(
            _proposal(
                AgentRole.PLANNER,
                ProposalAction.WAIT,
                0.55,
                10,
                ["no_specialist_threshold_crossed"],
                evidence={"objective": objective},
            )
        )

    return proposals


def reach_consensus(
    proposals: list[dict[str, Any]],
    *,
    objective: str = "optimize_field_outcome",
    execution_mode: str = ExecutionMode.HUMAN_IN_LOOP.value,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    """Resolve specialist proposals into one consensus decision with veto support."""
    if not proposals:
        return asdict(
            ConsensusDecision(
                _stable_id({"objective": objective, "empty": True}, "cons"),
                objective,
                ConsensusStatus.BLOCKED.value,
                None,
                0.0,
                True,
                ["no_proposals"],
                [],
                0,
                [],
                _now(),
            )
        )

    vetoes = [
        p["agent_role"] + ":" + flag
        for p in proposals
        for flag in p.get("safety_flags", [])
        if "veto" in flag or p.get("action") == ProposalAction.BLOCK.value
    ]
    action_scores: dict[str, list[float]] = {}
    action_reasons: dict[str, list[str]] = {}
    for p in proposals:
        action = str(p.get("action"))
        score = _num(p.get("confidence")) * (1.0 + _num(p.get("priority")) / 100.0)
        action_scores.setdefault(action, []).append(score)
        action_reasons.setdefault(action, []).extend(p.get("rationale") or [])

    ranked = []
    for action, scores in action_scores.items():
        ranked.append(
            {
                "action": action,
                "score": round(sum(scores), 4),
                "support": len(scores),
                "reasons": sorted(set(action_reasons.get(action, []))),
            }
        )
    ranked.sort(key=lambda item: (item["score"], item["support"]), reverse=True)

    conflict_reasons: list[str] = []
    selected = ranked[0]["action"] if ranked else None
    selected_conf = min(1.0, (ranked[0]["score"] / max(1.0, len(proposals))) if ranked else 0.0)
    action_set = {p.get("action") for p in proposals}
    if ProposalAction.IRRIGATE.value in action_set and ProposalAction.BLOCK.value in action_set:
        conflict_reasons.append("irrigation_conflicts_with_safety_or_soil_veto")
    if ProposalAction.SPRAY.value in action_set and ProposalAction.WAIT.value in action_set:
        conflict_reasons.append("spray_conflicts_with_wait_guardrail")
    if ProposalAction.FERTILIZE.value in action_set and ProposalAction.BLOCK.value in action_set:
        conflict_reasons.append("fertilizer_conflicts_with_safety_or_soil_veto")

    if vetoes:
        status = ConsensusStatus.BLOCKED.value
        selected = None
        approval_required = True
    elif conflict_reasons:
        status = ConsensusStatus.CONFLICTED.value
        approval_required = True
    elif selected_conf < min_confidence:
        status = ConsensusStatus.NEEDS_HUMAN_APPROVAL.value
        approval_required = True
    elif execution_mode in {
        ExecutionMode.SHADOW.value,
        ExecutionMode.ADVISORY.value,
        ExecutionMode.HUMAN_IN_LOOP.value,
    }:
        status = (
            ConsensusStatus.NEEDS_HUMAN_APPROVAL.value
            if selected
            not in {
                ProposalAction.WAIT.value,
                ProposalAction.SCOUT.value,
                ProposalAction.RECOMPUTE.value,
            }
            else ConsensusStatus.APPROVED.value
        )
        approval_required = status != ConsensusStatus.APPROVED.value
    else:
        status = ConsensusStatus.APPROVED.value
        approval_required = False

    decision = ConsensusDecision(
        decision_id=_stable_id(
            {"objective": objective, "ranked": ranked, "vetoes": vetoes}, "cons"
        ),
        objective=objective,
        status=status,
        selected_action=selected,
        confidence=round(selected_conf, 4),
        approval_required=approval_required,
        conflict_reasons=conflict_reasons,
        vetoes=vetoes,
        proposal_count=len(proposals),
        ranked_actions=ranked,
        created_at=_now(),
    )
    return asdict(decision)


def create_autonomous_operation_plan(
    consensus: dict[str, Any],
    context: dict[str, Any],
    *,
    execution_mode: str = ExecutionMode.HUMAN_IN_LOOP.value,
    max_autonomous_risk: float = 0.35,
) -> dict[str, Any]:
    """Convert consensus into an auditable operation plan."""
    action = consensus.get("selected_action")
    field_id = context.get("field_id")
    risk = 1.0 - _num(consensus.get("confidence"), 0.0)
    blocked: list[str] = []
    steps: list[dict[str, Any]] = []

    if consensus.get("status") in {ConsensusStatus.BLOCKED.value, ConsensusStatus.CONFLICTED.value}:
        blocked.append(f"consensus_{consensus.get('status')}")
    if consensus.get("approval_required") and execution_mode == ExecutionMode.AUTONOMOUS.value:
        blocked.append("human_approval_required")
    if execution_mode == ExecutionMode.AUTONOMOUS.value and risk > max_autonomous_risk:
        blocked.append("autonomous_risk_above_threshold")

    if action == ProposalAction.IRRIGATE.value:
        steps = [
            {"step": "check_water_allocation", "required": True},
            {"step": "verify_pump_and_pivot_status", "required": True},
            {"step": "dispatch_irrigation_command", "required": True},
            {"step": "verify_flow_and_pressure", "required": True},
            {"step": "measure_post_operation_response", "required": False},
        ]
    elif action == ProposalAction.SPRAY.value:
        steps = [
            {"step": "verify_spray_window", "required": True},
            {"step": "verify_chemical_label_and_ppe", "required": True},
            {"step": "create_work_order", "required": True},
            {"step": "verify_application_log", "required": True},
        ]
    elif action == ProposalAction.FERTILIZE.value:
        steps = [
            {"step": "verify_nutrient_budget", "required": True},
            {"step": "check_soil_guardrails", "required": True},
            {"step": "create_variable_rate_work_order", "required": True},
        ]
    elif action in {
        ProposalAction.SCOUT.value,
        ProposalAction.RECOMPUTE.value,
        ProposalAction.WAIT.value,
    }:
        steps = [{"step": action, "required": True}]
    elif action is None:
        steps = []

    safety_gates = [
        {"gate": "canonical_field_state_fresh", "pass_required": True},
        {"gate": "tenant_scope_verified", "pass_required": True},
        {
            "gate": "weather_window_safe",
            "pass_required": action in {ProposalAction.SPRAY.value, ProposalAction.IRRIGATE.value},
        },
        {
            "gate": "rollback_available",
            "pass_required": execution_mode == ExecutionMode.AUTONOMOUS.value,
        },
    ]
    rollback = [
        {"step": "cancel_pending_command", "when": "before_dispatch"},
        {"step": "stop_actuator", "when": "telemetry_anomaly"},
        {"step": "escalate_to_human", "when": "verification_failed"},
    ]
    plan = AutonomousOperationPlan(
        plan_id=_stable_id(
            {"decision": consensus.get("decision_id"), "mode": execution_mode, "field": field_id},
            "opplan",
        ),
        decision_id=str(consensus.get("decision_id")),
        execution_mode=execution_mode,
        field_id=field_id,
        action=action,
        steps=steps,
        safety_gates=safety_gates,
        rollback_plan=rollback,
        dispatch_ready=(
            not blocked
            and action not in {None, ProposalAction.WAIT.value}
            and execution_mode != ExecutionMode.SHADOW.value
        ),
        blocked_reasons=blocked,
        created_at=_now(),
    )
    return asdict(plan)


def design_shadow_experiment(
    *,
    name: str,
    objective: str,
    champion_policy: str,
    challenger_policy: str,
    mode: str = "shadow",
    traffic_pct: float = 0.1,
    guardrails: dict[str, Any] | None = None,
    promotion_metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Create a safe experiment plan for agent policies or operation policies."""
    traffic_pct = max(0.0, min(0.5, traffic_pct))
    if mode not in {"shadow", "canary", "champion_challenger"}:
        mode = "shadow"
    plan = ShadowExperimentPlan(
        experiment_id=_stable_id(
            {
                "name": name,
                "champion": champion_policy,
                "challenger": challenger_policy,
                "mode": mode,
            },
            "exp11",
        ),
        name=name,
        mode=mode,
        objective=objective,
        champion_policy=champion_policy,
        challenger_policy=challenger_policy,
        traffic_split={
            "champion": round(1.0 - traffic_pct, 4),
            "challenger": round(traffic_pct, 4),
        },
        guardrails=guardrails
        or {
            "max_negative_outcome_rate": 0.02,
            "min_confidence": 0.6,
            "human_approval_for_actuation": True,
        },
        promotion_metrics=promotion_metrics
        or ["net_benefit", "safety_incidents", "operator_acceptance"],
        created_at=_now(),
    )
    return asdict(plan)


def evaluate_agent_consensus_quality(cycles: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize the health of a federated-agent rollout."""
    if not cycles:
        return {
            "status": "insufficient_data",
            "cycle_count": 0,
            "approval_rate": 0.0,
            "blocked_rate": 0.0,
            "mean_confidence": 0.0,
            "recommendation": "collect_more_cycles",
        }
    statuses = [(c.get("consensus") or {}).get("status") for c in cycles]
    confidences = [_num((c.get("consensus") or {}).get("confidence"), 0.0) for c in cycles]
    blocked = sum(
        1
        for s in statuses
        if s in {ConsensusStatus.BLOCKED.value, ConsensusStatus.CONFLICTED.value}
    )
    approved = sum(1 for s in statuses if s == ConsensusStatus.APPROVED.value)
    blocked_rate = blocked / len(cycles)
    approval_rate = approved / len(cycles)
    mean_conf = mean(confidences) if confidences else 0.0
    if blocked_rate > 0.25:
        rec = "tighten_context_quality_and_agent_conflict_rules"
        status = "needs_attention"
    elif mean_conf < 0.55:
        rec = "keep_in_shadow_mode"
        status = "shadow_only"
    else:
        rec = "eligible_for_human_in_loop_canary"
        status = "healthy"
    return {
        "status": status,
        "cycle_count": len(cycles),
        "approval_rate": round(approval_rate, 4),
        "blocked_rate": round(blocked_rate, 4),
        "mean_confidence": round(mean_conf, 4),
        "recommendation": rec,
    }


def run_phase11_federation_cycle(
    *,
    canonical_field_state: dict[str, Any],
    objective: str = "optimize_field_outcome",
    phase9_cycle: dict[str, Any] | None = None,
    phase10_learning: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    execution_mode: str = ExecutionMode.HUMAN_IN_LOOP.value,
    experiment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the complete Phase 11 federation workflow."""
    context = build_agent_context(
        canonical_field_state=canonical_field_state,
        phase9_cycle=phase9_cycle,
        phase10_learning=phase10_learning,
        market_context=market_context,
    )
    proposals = run_specialist_agents(context, objective=objective)
    consensus = reach_consensus(proposals, objective=objective, execution_mode=execution_mode)
    op_plan = create_autonomous_operation_plan(consensus, context, execution_mode=execution_mode)
    experiment_plan = None
    if experiment:
        experiment_plan = design_shadow_experiment(
            name=experiment.get("name", "phase11_policy_experiment"),
            objective=objective,
            champion_policy=experiment.get("champion_policy", "current_policy"),
            challenger_policy=experiment.get("challenger_policy", "challenger_policy"),
            mode=experiment.get("mode", "shadow"),
            traffic_pct=_num(experiment.get("traffic_pct"), 0.1),
            guardrails=experiment.get("guardrails"),
            promotion_metrics=experiment.get("promotion_metrics"),
        )
    cycle = FederationCycle(
        cycle_id=_stable_id(
            {
                "ctx": context.get("context_id"),
                "objective": objective,
                "consensus": consensus.get("decision_id"),
            },
            "fedcycle",
        ),
        objective=objective,
        context_id=str(context.get("context_id")),
        proposals=proposals,
        consensus=consensus,
        operation_plan=op_plan,
        experiment_plan=experiment_plan,
        created_at=_now(),
    )
    return asdict(cycle)
