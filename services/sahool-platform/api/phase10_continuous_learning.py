"""Phase 10 Continuous Learning AI API contracts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.phase_runtime_store import persist_feature_dataset, persist_phase10_learning_outputs
from api.service_token_auth import _require_service_token
from shared.continuous_learning_phase10 import (
    create_online_learning_update,
    decide_model_promotion,
    detect_feature_drift,
    evaluate_experiment_outcomes,
    infer_feature_schema,
    materialize_training_dataset,
    plan_retraining_job,
    run_champion_challenger_cycle,
    run_phase10_learning_cycle,
    run_scientific_scenario,
)
from shared.feature_store import (
    build_point_in_time_snapshot,
    materialize_online_feature_values,
    register_feature_definitions,
    write_offline_feature_dataset,
)
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


class ModelPromotionRequest(BaseModel):
    task: str
    champion: dict[str, Any] | None = None
    challenger: dict[str, Any] | None = None
    metric_policy: dict[str, Any] = Field(default_factory=dict)


class OnlineLearningRequest(BaseModel):
    model: dict[str, Any]
    dataset: dict[str, Any]
    records: list[dict[str, Any]]
    drift_threshold: float = 0.35


class ExperimentEvaluationRequest(BaseModel):
    experiment_key: str
    assignments: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    metric: str = "net_benefit"


class ScenarioRequest(BaseModel):
    field_state: dict[str, Any]
    scenario: dict[str, Any]


class LearningCycleRequest(BaseModel):
    phase9_cycle: dict[str, Any]
    champion_model: dict[str, Any] | None = None
    challenger_model: dict[str, Any] | None = None
    scenario: dict[str, Any] | None = None


class DriftRequest(BaseModel):
    baseline_stats: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)


class RetrainingRequest(BaseModel):
    drift: dict[str, Any]
    dataset: dict[str, Any]
    model: dict[str, Any]
    policy: dict[str, Any] = Field(default_factory=dict)


class ChampionChallengerRequest(BaseModel):
    task: str
    champion: dict[str, Any] | None = None
    challenger: dict[str, Any] | None = None
    dataset: dict[str, Any]
    drift: dict[str, Any]
    metric_policy: dict[str, Any] = Field(default_factory=dict)


class FeatureStoreRegisterRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)
    name: str = "canonical_field_features"
    version: str = "v1"
    owner: str = "phase10"
    ttl_hours: int = 24


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


@router.post("/feature-schema")
def feature_schema(req: FeatureRecordsRequest) -> dict[str, Any]:
    return infer_feature_schema(req.records, name=req.name, version=req.version)


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


@router.post("/online-update")
def online_update(req: OnlineLearningRequest) -> dict[str, Any]:
    return create_online_learning_update(
        model=req.model,
        dataset=req.dataset,
        records=req.records,
        drift_threshold=req.drift_threshold,
    )


@router.post("/experiments/evaluate")
def experiment_evaluation(req: ExperimentEvaluationRequest) -> dict[str, Any]:
    return evaluate_experiment_outcomes(
        experiment_key=req.experiment_key,
        assignments=req.assignments,
        outcomes=req.outcomes,
        metric=req.metric,
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


@router.post("/drift")
def drift(req: DriftRequest) -> dict[str, Any]:
    return detect_feature_drift(
        baseline_stats=req.baseline_stats,
        current_records=req.records,
        thresholds=req.thresholds or None,
    )


@router.post("/retraining/plan")
def retraining_plan(req: RetrainingRequest) -> dict[str, Any]:
    return plan_retraining_job(
        drift=req.drift, dataset=req.dataset, model=req.model, policy=req.policy or None
    )


@router.post("/champion-challenger")
def champion_challenger(req: ChampionChallengerRequest) -> dict[str, Any]:
    return run_champion_challenger_cycle(
        task=req.task,
        champion=req.champion,
        challenger=req.challenger,
        dataset=req.dataset,
        drift=req.drift,
        metric_policy=req.metric_policy or None,
    )


@router.post("/feature-store/register")
def feature_store_register(req: FeatureStoreRegisterRequest) -> dict[str, Any]:
    return register_feature_definitions(
        req.records, name=req.name, version=req.version, owner=req.owner, ttl_hours=req.ttl_hours
    )


@router.post("/feature-store/offline-dataset")
def feature_store_offline_dataset(req: FeatureRecordsRequest) -> dict[str, Any]:
    registry = register_feature_definitions(req.records, name=req.name, version=req.version)
    return write_offline_feature_dataset(
        req.records,
        feature_set_id=str(registry.get("feature_set", {}).get("feature_set_id")),
        object_uri=req.object_uri,
    )


@router.post("/feature-store/online-materialization")
def feature_store_online_materialization(req: FeatureRecordsRequest) -> dict[str, Any]:
    registry = register_feature_definitions(req.records, name=req.name, version=req.version)
    return materialize_online_feature_values(
        req.records, feature_set_id=str(registry.get("feature_set", {}).get("feature_set_id"))
    )


@router.post("/feature-store/point-in-time")
def feature_store_point_in_time(req: PointInTimeRequest) -> dict[str, Any]:
    return build_point_in_time_snapshot(
        req.records, as_of=req.as_of, max_age_hours=req.max_age_hours
    )


@router.post("/models/register")
def model_register(req: ModelRegisterRequest) -> dict[str, Any]:
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
