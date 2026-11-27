"""Phase 10 Continuous Learning AI API contracts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.phase_runtime_store import persist_feature_dataset, persist_phase10_learning_outputs
from api.service_token_auth import _require_service_token
from shared.continuous_learning_phase10 import (
    decide_model_promotion,
    infer_feature_schema,
    materialize_training_dataset,
    run_phase10_learning_cycle,
    run_scientific_scenario,
)
from shared.feature_store import (
    build_point_in_time_snapshot,
    register_feature_definitions,
    write_offline_feature_dataset,
)
from shared.feature_store.runtime import resolve_requested_as_of
from shared.mlops import (
    apply_model_promotion,
    register_model_version,
    resolve_serving_alias,
    rollback_serving_alias,
)

router = APIRouter(
    prefix="/v1/phase10/learning",
    tags=["phase10-continuous-learning-ai"],
    dependencies=[Depends(_require_service_token)],
)


class FeatureRecordsRequest(BaseModel):
    records: list[dict[str, Any]]
    name: str = "canonical_learning_v1"
    version: str = "v1"
    object_uri: str | None = None
    # Decision time for /feature-store/offline-dataset. Omitted: the latest aware
    # prediction_at, capped at now. A future value is capped at now.
    as_of: str | None = None


class ModelPromotionRequest(BaseModel):
    task: str
    champion: dict[str, Any] | None = None
    challenger: dict[str, Any] | None = None
    metric_policy: dict[str, Any] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    field_state: dict[str, Any]
    scenario: dict[str, Any]


class LearningCycleRequest(BaseModel):
    phase9_cycle: dict[str, Any]
    champion_model: dict[str, Any] | None = None
    challenger_model: dict[str, Any] | None = None
    scenario: dict[str, Any] | None = None


class PointInTimeRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    as_of: str
    max_age_hours: int = 48


class ModelRegisterRequest(BaseModel):
    model_name: str
    version: str
    task: str
    framework: str = "python"
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    dataset_version_id: str | None = None
    feature_set_id: str | None = None
    status: str = "registered"


class ModelPromotionRuntimeRequest(BaseModel):
    alias: str
    champion: dict[str, Any] | None = None
    challenger: dict[str, Any]
    policy: dict[str, Any] = Field(default_factory=dict)


class ModelRollbackRequest(BaseModel):
    alias: str
    current_model_id: str
    target_model_id: str
    reason: str


# W4-09 (routes-10): POST /feature-schema · /online-update · /experiments/evaluate
# أُقعِدت — بلا مستدعٍ في أيّ عميل أو خدمة أو SDK أو اختبار أو سجلّ قدرات. الدوالّ
# الصرفة في shared/continuous_learning_phase10 باقية باختباراتها هناك (و/cycle يستدعي
# create_online_learning_update عبر run_phase10_learning_cycle)، و/dataset يُعيد
# feature_set_spec نفسه. يحرسها tests/test_w4_09_retired_dead_routes.py.
# W4-09 (تتمّة، قرار المالك 2026-11-16): POST /drift · /retraining/plan ·
# /champion-challenger أُقعِدت كذلك — بلا مستدعٍ. الدوالّ الصرفة باقية في
# shared/continuous_learning_phase10 باختباراتها (tests_v9/test_phase9_10_event_drift_hardening.py)،
# و/cycle ما زال يُشغّل run_champion_challenger_cycle عبر run_phase10_learning_cycle.
@router.post("/dataset")
async def dataset(req: FeatureRecordsRequest, request: Request) -> dict[str, Any]:
    spec = infer_feature_schema(req.records, name=req.name, version=req.version)
    ds = materialize_training_dataset(req.records, feature_set_spec=spec, object_uri=req.object_uri)
    ds["feature_set_spec"] = spec
    ds["records"] = req.records
    ds["runtime_persistence"] = await persist_feature_dataset(request, spec, ds)
    return ds


@router.post("/models/promote")
def model_promotion(req: ModelPromotionRequest) -> dict[str, Any]:
    return decide_model_promotion(
        task=req.task,
        champion=req.champion,
        challenger=req.challenger,
        metric_policy=req.metric_policy,
    )


@router.post("/scenario")
def scenario(req: ScenarioRequest) -> dict[str, Any]:
    return run_scientific_scenario(field_state=req.field_state, scenario=req.scenario)


@router.post("/cycle")
async def learning_cycle(req: LearningCycleRequest, request: Request) -> dict[str, Any]:
    result = run_phase10_learning_cycle(
        phase9_cycle=req.phase9_cycle,
        champion_model=req.champion_model,
        challenger_model=req.challenger_model,
        scenario=req.scenario,
    )
    result["runtime_persistence"] = await persist_phase10_learning_outputs(request, result)
    return result


# W4-09 inspection-delivery continuation (2026-11-27): /feature-store/register and
# /feature-store/online-materialization are retired HTTP wrappers with no in-repo
# caller or behavioral HTTP test. Their pure functions remain used by /cycle;
# register_feature_definitions also remains used by /offline-dataset below.
# /cycle is not a drop-in replacement for custom name/version/owner/ttl arguments.
# External deployment callers were not measured. The Phase 6 static
# presence contract and W4 live-router regression explicitly record this retirement.
@router.post("/feature-store/offline-dataset")
def feature_store_offline_dataset(req: FeatureRecordsRequest) -> dict[str, Any]:
    registry = register_feature_definitions(req.records, name=req.name, version=req.version)
    return write_offline_feature_dataset(
        req.records,
        feature_set_id=str(registry.get("feature_set", {}).get("feature_set_id")),
        object_uri=req.object_uri,
        as_of=resolve_requested_as_of(req.as_of, req.records),
    )


@router.post("/feature-store/point-in-time")
def feature_store_point_in_time(req: PointInTimeRequest) -> dict[str, Any]:
    try:
        return build_point_in_time_snapshot(
            req.records, as_of=req.as_of, max_age_hours=req.max_age_hours
        )
    except ValueError as exc:
        # The builder rejects a missing, unparseable or naive as_of (and a negative
        # max_age_hours): a client error, not a 500.
        raise HTTPException(
            status_code=422, detail={"code": "invalid_as_of", "message": str(exc)}
        ) from exc


@router.post("/models/register")
def model_register(req: ModelRegisterRequest) -> dict[str, Any]:
    try:
        return register_model_version(
            model_name=req.model_name,
            version=req.version,
            task=req.task,
            framework=req.framework,
            artifacts=req.artifacts,
            metrics=req.metrics,
            dataset_version_id=req.dataset_version_id,
            feature_set_id=req.feature_set_id,
            status=req.status,
        )
    except ValueError as exc:
        # Non-finite or boolean evaluation metrics are invalid input, not server errors.
        raise HTTPException(
            status_code=422, detail={"code": "invalid_model_metrics", "message": str(exc)}
        ) from exc


@router.post("/models/serving/promote")
def model_serving_promote(req: ModelPromotionRuntimeRequest) -> dict[str, Any]:
    return apply_model_promotion(
        alias=req.alias, champion=req.champion, challenger=req.challenger, policy=req.policy or None
    )


@router.post("/models/serving/rollback")
def model_serving_rollback(req: ModelRollbackRequest) -> dict[str, Any]:
    return rollback_serving_alias(
        alias=req.alias,
        current_model_id=req.current_model_id,
        target_model_id=req.target_model_id,
        reason=req.reason,
    )


@router.get("/models/serving/{alias:path}")
def model_serving_resolve(alias: str) -> dict[str, Any]:
    # Runtime DB-backed alias resolution is provided by the persistence adapter.
    # This deterministic response prevents silent fallback in local tests.
    return resolve_serving_alias(alias=alias, aliases={})
