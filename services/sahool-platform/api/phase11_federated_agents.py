"""Phase 11 Federated Multi-Agent Autonomous Operations API contracts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.phase_runtime_store import persist_phase11_cycle
from api.service_token_auth import _require_service_token
from shared.federated_agent_runtime import (
    build_federation_event_envelope,
    create_authority_envelope,
    reputation_weighted_consensus,
)
from shared.federated_agents_phase11 import (
    build_agent_context,
    create_autonomous_operation_plan,
    evaluate_agent_consensus_quality,
    reach_consensus,
    run_phase11_federation_cycle,
)

router = APIRouter(
    prefix="/v1/phase11/federation",
    tags=["phase11-federated-agents"],
    dependencies=[Depends(_require_service_token)],
)

# W4-09 (routes-10، تتمّة بقرار المالك 2026-11-16): POST /agents/propose ·
# /experiments/shadow · /runtime/reputation/update أُقعِدت — بلا مستدعٍ في أيّ عميل أو
# خدمة أو SDK أو اختبار أو سجلّ قدرات. الدوالّ الصرفة باقية في shared/ باختباراتها، و/cycle
# ما زال يُشغّل run_specialist_agents وdesign_shadow_experiment عبر run_phase11_federation_cycle.
# يحرسها tests/test_w4_09_retired_dead_routes.py.
# W4-09 (2026-11-27): /runtime/event-envelope has no repository HTTP caller or
# product-level route test. The shared builder and its tests remain; /cycle still
# builds the envelope before persistence. Retirement is guarded with its siblings.


class AgentContextRequest(BaseModel):
    canonical_field_state: dict[str, Any]
    phase9_cycle: dict[str, Any] | None = None
    phase10_learning: dict[str, Any] | None = None
    market_context: dict[str, Any] = Field(default_factory=dict)


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


@router.post("/context")
def context(req: AgentContextRequest) -> dict[str, Any]:
    return build_agent_context(
        canonical_field_state=req.canonical_field_state,
        phase9_cycle=req.phase9_cycle,
        phase10_learning=req.phase10_learning,
        market_context=req.market_context,
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
