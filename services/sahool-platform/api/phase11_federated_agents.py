"""Phase 11 Federated Multi-Agent Autonomous Operations API contracts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api.phase_runtime_store import persist_phase11_cycle
from shared.federated_agent_runtime import (
    build_federation_event_envelope,
    create_authority_envelope,
    reputation_weighted_consensus,
    update_agent_reputation,
)
from shared.federated_agents_phase11 import (
    build_agent_context,
    create_autonomous_operation_plan,
    design_shadow_experiment,
    evaluate_agent_consensus_quality,
    reach_consensus,
    run_phase11_federation_cycle,
    run_specialist_agents,
)

router = APIRouter(prefix="/v1/phase11/federation", tags=["phase11-federated-agents"])


class AgentContextRequest(BaseModel):
    canonical_field_state: dict[str, Any]
    phase9_cycle: dict[str, Any] | None = None
    phase10_learning: dict[str, Any] | None = None
    market_context: dict[str, Any] = Field(default_factory=dict)


class SpecialistAgentsRequest(BaseModel):
    context: dict[str, Any]
    objective: str = "optimize_field_outcome"
    enabled_roles: list[str] | None = None


class ConsensusRequest(BaseModel):
    proposals: list[dict[str, Any]]
    objective: str = "optimize_field_outcome"
    execution_mode: str = "human_in_loop"
    min_confidence: float = 0.6


class OperationPlanRequest(BaseModel):
    consensus: dict[str, Any]
    context: dict[str, Any]
    execution_mode: str = "human_in_loop"
    max_autonomous_risk: float = 0.35


class ShadowExperimentRequest(BaseModel):
    name: str
    objective: str = "optimize_field_outcome"
    champion_policy: str = "current_policy"
    challenger_policy: str = "challenger_policy"
    mode: str = "shadow"
    traffic_pct: float = 0.1
    guardrails: dict[str, Any] = Field(default_factory=dict)
    promotion_metrics: list[str] = Field(default_factory=list)


class FederationCycleRequest(BaseModel):
    canonical_field_state: dict[str, Any]
    objective: str = "optimize_field_outcome"
    phase9_cycle: dict[str, Any] | None = None
    phase10_learning: dict[str, Any] | None = None
    market_context: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = "human_in_loop"
    experiment: dict[str, Any] | None = None


class ConsensusQualityRequest(BaseModel):
    cycles: list[dict[str, Any]]


class RuntimeConsensusRequest(BaseModel):
    proposals: list[dict[str, Any]]
    objective: str = "optimize_field_outcome"
    execution_mode: str = "human_in_loop"
    min_confidence: float = 0.62
    reputations: dict[str, Any] = Field(default_factory=dict)


class AuthorityEnvelopeRequest(BaseModel):
    cycle: dict[str, Any]
    resolution: dict[str, Any] | None = None
    requested_authority: str = "advisory"


class ReputationUpdateRequest(BaseModel):
    prior: dict[str, Any] = Field(default_factory=dict)
    agent_role: str
    outcome: str
    confidence_error: float = 0.0
    safety_incident: bool = False


class FederationEventEnvelopeRequest(BaseModel):
    cycle: dict[str, Any]
    authority: dict[str, Any]


@router.post("/context")
def context(req: AgentContextRequest) -> dict[str, Any]:
    return build_agent_context(
        canonical_field_state=req.canonical_field_state,
        phase9_cycle=req.phase9_cycle,
        phase10_learning=req.phase10_learning,
        market_context=req.market_context,
    )


@router.post("/agents/propose")
def agents_propose(req: SpecialistAgentsRequest) -> list[dict[str, Any]]:
    return run_specialist_agents(
        req.context, objective=req.objective, enabled_roles=req.enabled_roles
    )


@router.post("/consensus")
def consensus(req: ConsensusRequest) -> dict[str, Any]:
    return reach_consensus(
        req.proposals,
        objective=req.objective,
        execution_mode=req.execution_mode,
        min_confidence=req.min_confidence,
    )


@router.post("/operation-plan")
def operation_plan(req: OperationPlanRequest) -> dict[str, Any]:
    return create_autonomous_operation_plan(
        req.consensus,
        req.context,
        execution_mode=req.execution_mode,
        max_autonomous_risk=req.max_autonomous_risk,
    )


@router.post("/experiments/shadow")
def shadow_experiment(req: ShadowExperimentRequest) -> dict[str, Any]:
    return design_shadow_experiment(
        name=req.name,
        objective=req.objective,
        champion_policy=req.champion_policy,
        challenger_policy=req.challenger_policy,
        mode=req.mode,
        traffic_pct=req.traffic_pct,
        guardrails=req.guardrails or None,
        promotion_metrics=req.promotion_metrics or None,
    )


@router.post("/quality")
def quality(req: ConsensusQualityRequest) -> dict[str, Any]:
    return evaluate_agent_consensus_quality(req.cycles)


@router.post("/cycle")
async def cycle(req: FederationCycleRequest, request: Request) -> dict[str, Any]:
    result = run_phase11_federation_cycle(
        canonical_field_state=req.canonical_field_state,
        objective=req.objective,
        phase9_cycle=req.phase9_cycle,
        phase10_learning=req.phase10_learning,
        market_context=req.market_context,
        execution_mode=req.execution_mode,
        experiment=req.experiment,
    )
    result["runtime_resolution"] = reputation_weighted_consensus(
        result.get("proposals") or [],
        objective=req.objective,
        execution_mode=req.execution_mode,
    )
    result["authority_envelope"] = create_authority_envelope(
        result, resolution=result["runtime_resolution"], requested_authority="proposal"
    )
    result["event_envelope"] = build_federation_event_envelope(result, result["authority_envelope"])
    result["runtime_persistence"] = await persist_phase11_cycle(request, result)
    return result


@router.post("/runtime/resolve")
def runtime_resolve(req: RuntimeConsensusRequest) -> dict[str, Any]:
    return reputation_weighted_consensus(
        req.proposals,
        objective=req.objective,
        execution_mode=req.execution_mode,
        reputations=req.reputations,
        min_confidence=req.min_confidence,
    )


@router.post("/runtime/authority-envelope")
def runtime_authority_envelope(req: AuthorityEnvelopeRequest) -> dict[str, Any]:
    return create_authority_envelope(
        req.cycle, resolution=req.resolution, requested_authority=req.requested_authority
    )


@router.post("/runtime/reputation/update")
def runtime_reputation_update(req: ReputationUpdateRequest) -> dict[str, Any]:
    return update_agent_reputation(
        req.prior,
        agent_role=req.agent_role,
        outcome=req.outcome,
        confidence_error=req.confidence_error,
        safety_incident=req.safety_incident,
    )


@router.post("/runtime/event-envelope")
def runtime_event_envelope(req: FederationEventEnvelopeRequest) -> dict[str, Any]:
    return build_federation_event_envelope(req.cycle, req.authority)
