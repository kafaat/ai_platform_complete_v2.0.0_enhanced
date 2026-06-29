"""Phase 10 Continuous Learning AI and simulation foundation.

This module turns Phase 9's execution/outcome stream into a deterministic
learning runtime: feature materialization, training dataset assembly, model
lifecycle decisions, online feedback updates, experiment evaluation, and a
scientific scenario simulator scaffold.  It is dependency-light by design so it
can run in CI and later be backed by PostGIS, object storage, MLflow/Feast, and
APSIM/WOFOST/DSSAT adapters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from statistics import mean
from typing import Any
import hashlib
import json
import math

from shared.feature_store import (
    build_feature_lineage_manifest as build_production_feature_lineage,
    build_point_in_time_snapshot,
    materialize_online_feature_values,
    register_feature_definitions,
    write_offline_feature_dataset,
)
from shared.mlops import (
    apply_model_promotion,
    build_model_card,
    register_model_version,
    rollback_serving_alias,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


class DatasetStatus(str, Enum):
    DRAFT = "draft"
    TRAINABLE = "trainable"
    BLOCKED = "blocked"


class PromotionDecision(str, Enum):
    KEEP_CHAMPION = "keep_champion"
    PROMOTE_CHALLENGER = "promote_challenger"
    SHADOW_ONLY = "shadow_only"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class FeatureSetSpec:
    feature_set_id: str
    name: str
    version: str
    entity_type: str
    feature_names: list[str]
    label_names: list[str]
    freshness_hours: int
    quality_gates: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class TrainingDataset:
    dataset_id: str
    feature_set_id: str
    entity_type: str
    entity_count: int
    row_count: int
    feature_names: list[str]
    label_names: list[str]
    status: str
    quality: dict[str, Any]
    object_uri: str | None
    created_at: str


@dataclass(frozen=True)
class ModelLifecycleDecision:
    decision_id: str
    task: str
    champion_model_id: str | None
    challenger_model_id: str | None
    decision: str
    reasons: list[str]
    metric_deltas: dict[str, float]
    rollout: dict[str, Any]
    decided_at: str


@dataclass(frozen=True)
class OnlineLearningUpdate:
    update_id: str
    model_id: str
    feature_set_id: str
    learning_rate: float
    sample_count: int
    label_summary: dict[str, Any]
    drift_score: float
    action: str
    created_at: str


@dataclass(frozen=True)
class ExperimentEvaluation:
    evaluation_id: str
    experiment_key: str
    variants: dict[str, dict[str, Any]]
    winner: str | None
    decision: str
    confidence: float
    evaluated_at: str


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    field_id: str
    crop: str | None
    assumptions: dict[str, Any]
    baseline: dict[str, float]
    projected: dict[str, float]
    deltas: dict[str, float]
    risk_flags: list[str]
    created_at: str


def infer_feature_schema(records: list[dict[str, Any]], *, name: str = "canonical_learning_v1", version: str = "v1") -> dict[str, Any]:
    """Infer a stable feature-set contract from Phase 9 feature records."""
    feature_names: set[str] = set()
    label_names: set[str] = set()
    entity_type = "field"
    for rec in records:
        entity_type = rec.get("entity_type") or entity_type
        feature_names.update((rec.get("features") or {}).keys())
        label_names.update((rec.get("labels") or {}).keys())
    spec = FeatureSetSpec(
        feature_set_id=_stable_id({"name": name, "version": version, "features": sorted(feature_names), "labels": sorted(label_names)}, "fs"),
        name=name,
        version=version,
        entity_type=entity_type,
        feature_names=sorted(feature_names),
        label_names=sorted(label_names),
        freshness_hours=24,
        quality_gates={"min_rows": 10, "max_missing_ratio": 0.35, "min_label_coverage": 0.2},
        created_at=_now(),
    )
    return asdict(spec)


def materialize_training_dataset(
    records: list[dict[str, Any]],
    *,
    feature_set_spec: dict[str, Any] | None = None,
    object_uri: str | None = None,
) -> dict[str, Any]:
    """Build a trainable dataset manifest from feature records."""
    spec = feature_set_spec or infer_feature_schema(records)
    feature_names = list(spec.get("feature_names", []))
    label_names = list(spec.get("label_names", []))
    row_count = len(records)
    entity_count = len({r.get("entity_id") for r in records if r.get("entity_id")})

    missing_values = 0
    total_values = max(1, row_count * max(1, len(feature_names)))
    labelled_rows = 0
    numeric_values: list[float] = []
    for rec in records:
        features = rec.get("features") or {}
        labels = rec.get("labels") or {}
        if any(labels.get(k) is not None for k in label_names):
            labelled_rows += 1
        for name in feature_names:
            value = features.get(name)
            if value is None:
                missing_values += 1
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                numeric_values.append(float(value))

    missing_ratio = missing_values / total_values
    label_coverage = labelled_rows / max(1, row_count)
    gates = spec.get("quality_gates") or {}
    reasons: list[str] = []
    if row_count < int(gates.get("min_rows", 1)):
        reasons.append("insufficient_rows")
    if missing_ratio > float(gates.get("max_missing_ratio", 1.0)):
        reasons.append("too_many_missing_features")
    if label_names and label_coverage < float(gates.get("min_label_coverage", 0.0)):
        reasons.append("insufficient_label_coverage")

    status = DatasetStatus.TRAINABLE.value if not reasons else DatasetStatus.BLOCKED.value
    dataset = TrainingDataset(
        dataset_id=_stable_id({"spec": spec.get("feature_set_id"), "records": [r.get("feature_id") for r in records]}, "ds"),
        feature_set_id=str(spec.get("feature_set_id")),
        entity_type=str(spec.get("entity_type", "field")),
        entity_count=entity_count,
        row_count=row_count,
        feature_names=feature_names,
        label_names=label_names,
        status=status,
        quality={
            "missing_ratio": round(missing_ratio, 4),
            "label_coverage": round(label_coverage, 4),
            "numeric_mean": mean(numeric_values) if numeric_values else None,
            "blocked_reasons": reasons,
        },
        object_uri=object_uri,
        created_at=_now(),
    )
    return asdict(dataset)


def decide_model_promotion(
    *,
    task: str,
    champion: dict[str, Any] | None,
    challenger: dict[str, Any] | None,
    metric_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate champion/challenger metrics and return a rollout decision."""
    metric_policy = metric_policy or {"primary_metric": "score", "min_improvement": 0.02, "max_regression": 0.0}
    primary = metric_policy.get("primary_metric", "score")
    min_improvement = _num(metric_policy.get("min_improvement"), 0.0)
    max_regression = _num(metric_policy.get("max_regression"), 0.0)
    reasons: list[str] = []

    if not challenger:
        reasons.append("missing_challenger")
        decision = PromotionDecision.BLOCKED.value
    else:
        c_score = _num((champion or {}).get("metrics", {}).get(primary), 0.0)
        n_score = _num(challenger.get("metrics", {}).get(primary), 0.0)
        delta = n_score - c_score
        if challenger.get("status") in {"failed", "blocked"}:
            reasons.append("challenger_not_eligible")
            decision = PromotionDecision.BLOCKED.value
        elif not champion or delta >= min_improvement:
            reasons.append("challenger_meets_improvement_threshold")
            decision = PromotionDecision.PROMOTE_CHALLENGER.value
        elif delta >= -max_regression:
            reasons.append("challenger_safe_for_shadow")
            decision = PromotionDecision.SHADOW_ONLY.value
        else:
            reasons.append("challenger_regressed")
            decision = PromotionDecision.KEEP_CHAMPION.value

    metric_deltas: dict[str, float] = {}
    if challenger:
        metric_keys = set((champion or {}).get("metrics", {}).keys()) | set(challenger.get("metrics", {}).keys())
        metric_deltas = {k: _num(challenger.get("metrics", {}).get(k)) - _num((champion or {}).get("metrics", {}).get(k)) for k in sorted(metric_keys)}

    return asdict(ModelLifecycleDecision(
        decision_id=_stable_id({"task": task, "champion": champion, "challenger": challenger, "policy": metric_policy}, "mld"),
        task=task,
        champion_model_id=(champion or {}).get("model_id"),
        challenger_model_id=(challenger or {}).get("model_id") if challenger else None,
        decision=decision,
        reasons=reasons,
        metric_deltas=metric_deltas,
        rollout={
            "initial_percentage": 0 if decision in {PromotionDecision.BLOCKED.value, PromotionDecision.KEEP_CHAMPION.value} else 5,
            "max_percentage": 100 if decision == PromotionDecision.PROMOTE_CHALLENGER.value else 20,
            "requires_shadow_period_hours": decision != PromotionDecision.PROMOTE_CHALLENGER.value,
            "fail_closed": True,
        },
        decided_at=_now(),
    ))


def create_online_learning_update(
    *,
    model: dict[str, Any],
    dataset: dict[str, Any],
    records: list[dict[str, Any]],
    drift_threshold: float = 0.35,
) -> dict[str, Any]:
    """Create a safe online-learning update candidate from fresh labelled records."""
    label_values: dict[str, list[float]] = {}
    feature_means: list[float] = []
    for rec in records:
        for k, v in (rec.get("labels") or {}).items():
            if isinstance(v, (int, float, bool)):
                label_values.setdefault(k, []).append(float(v))
        numeric = [_num(v) for v in (rec.get("features") or {}).values() if isinstance(v, (int, float))]
        if numeric:
            feature_means.append(mean(numeric))

    baseline_mean = _num((model.get("training_stats") or {}).get("feature_mean"), mean(feature_means) if feature_means else 0.0)
    current_mean = mean(feature_means) if feature_means else baseline_mean
    drift_score = abs(current_mean - baseline_mean) / max(1.0, abs(baseline_mean))
    action = "queue_retraining" if drift_score >= drift_threshold else "online_update_candidate"
    if dataset.get("status") != DatasetStatus.TRAINABLE.value:
        action = "blocked_dataset_not_trainable"

    label_summary = {k: {"count": len(vs), "mean": mean(vs) if vs else None} for k, vs in label_values.items()}
    return asdict(OnlineLearningUpdate(
        update_id=_stable_id({"model": model.get("model_id"), "dataset": dataset.get("dataset_id"), "records": [r.get("feature_id") for r in records]}, "olu"),
        model_id=str(model.get("model_id")),
        feature_set_id=str(dataset.get("feature_set_id")),
        learning_rate=_num(model.get("online_learning_rate"), 0.01),
        sample_count=len(records),
        label_summary=label_summary,
        drift_score=round(drift_score, 4),
        action=action,
        created_at=_now(),
    ))


def evaluate_experiment_outcomes(*, experiment_key: str, assignments: list[dict[str, Any]], outcomes: list[dict[str, Any]], metric: str = "net_benefit") -> dict[str, Any]:
    """Aggregate A/B outcomes and pick a conservative winner."""
    entity_to_variant = {a.get("entity_id"): a.get("variant") for a in assignments if a.get("experiment_key") == experiment_key}
    grouped: dict[str, list[float]] = {}
    for outcome in outcomes:
        variant = entity_to_variant.get(outcome.get("entity_id"))
        if variant:
            grouped.setdefault(variant, []).append(_num(outcome.get(metric), 0.0))
    variants = {k: {"count": len(v), "mean": mean(v) if v else 0.0} for k, v in grouped.items()}
    winner = None
    confidence = 0.0
    decision = "insufficient_data"
    if len(variants) >= 2 and all(v["count"] >= 2 for v in variants.values()):
        ordered = sorted(variants.items(), key=lambda item: item[1]["mean"], reverse=True)
        winner = ordered[0][0]
        spread = ordered[0][1]["mean"] - ordered[1][1]["mean"]
        confidence = max(0.0, min(0.99, spread / max(1.0, abs(ordered[1][1]["mean"]))))
        decision = "promote_variant" if confidence >= 0.05 else "continue_experiment"
    return asdict(ExperimentEvaluation(
        evaluation_id=_stable_id({"experiment": experiment_key, "assignments": assignments, "outcomes": outcomes, "metric": metric}, "eval"),
        experiment_key=experiment_key,
        variants=variants,
        winner=winner,
        decision=decision,
        confidence=round(confidence, 4),
        evaluated_at=_now(),
    ))


def run_scientific_scenario(
    *,
    field_state: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Run a deterministic APSIM/WOFOST/DSSAT-ready scenario approximation.

    Production adapters can replace this formula-based estimator with scientific
    crop models while preserving the output contract.
    """
    state = field_state.get("state", field_state)
    truths = state.get("operational_truths", {}) if isinstance(state, dict) else {}
    field_id = str(field_state.get("field_id") or state.get("field_id") or "unknown")
    crop = scenario.get("crop") or state.get("crop")

    baseline_yield = _num(scenario.get("baseline_yield_t_ha"), _num(truths.get("yield_t_ha"), 4.0))
    baseline_water = _num(scenario.get("baseline_water_mm"), _num(truths.get("seasonal_water_mm"), 450.0))
    baseline_profit = _num(scenario.get("baseline_profit_per_ha"), _num(truths.get("profit_per_ha"), 900.0))

    rainfall_delta = _num(scenario.get("rainfall_delta_pct"), 0.0) / 100.0
    fertilizer_delta = _num(scenario.get("fertilizer_delta_pct"), 0.0) / 100.0
    sowing_delay_days = _num(scenario.get("sowing_delay_days"), 0.0)
    heat_stress_delta = _num(scenario.get("heat_stress_delta"), 0.0)

    water_factor = 1.0 + 0.35 * rainfall_delta
    nutrient_factor = 1.0 + min(0.12, 0.22 * fertilizer_delta)
    delay_factor = max(0.75, 1.0 - 0.01 * max(0.0, sowing_delay_days))
    heat_factor = max(0.65, 1.0 - 0.08 * max(0.0, heat_stress_delta))
    projected_yield = baseline_yield * water_factor * nutrient_factor * delay_factor * heat_factor
    projected_water = max(0.0, baseline_water * (1.0 - rainfall_delta * 0.25))
    projected_profit = baseline_profit + (projected_yield - baseline_yield) * _num(scenario.get("price_per_ton"), 250.0) - max(0.0, fertilizer_delta) * 80.0

    baseline = {"yield_t_ha": round(baseline_yield, 3), "water_mm": round(baseline_water, 2), "profit_per_ha": round(baseline_profit, 2)}
    projected = {"yield_t_ha": round(projected_yield, 3), "water_mm": round(projected_water, 2), "profit_per_ha": round(projected_profit, 2)}
    deltas = {k: round(projected[k] - baseline[k], 3) for k in baseline}
    flags: list[str] = []
    if deltas["yield_t_ha"] < -0.25:
        flags.append("yield_decline_risk")
    if projected_water > baseline_water * 1.1:
        flags.append("water_demand_increase")
    if deltas["profit_per_ha"] < 0:
        flags.append("profitability_risk")

    return asdict(ScenarioResult(
        scenario_id=_stable_id({"field": field_id, "scenario": scenario, "state": state.get("state_id")}, "scn"),
        field_id=field_id,
        crop=crop,
        assumptions=dict(scenario),
        baseline=baseline,
        projected=projected,
        deltas=deltas,
        risk_flags=flags,
        created_at=_now(),
    ))



# --- Phase 10 production hardening: drift, lineage, retraining and champion/challenger runtime ---

class DriftDecision(str, Enum):
    STABLE = "stable"
    WATCH = "watch"
    RETRAIN = "retrain"
    BLOCK_PROMOTION = "block_promotion"


def detect_feature_drift(
    *,
    baseline_stats: dict[str, Any],
    current_records: list[dict[str, Any]],
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute lightweight population/feature drift scores without external deps."""
    thresholds = thresholds or {"watch": 0.15, "retrain": 0.3, "block": 0.5}
    feature_values: dict[str, list[float]] = {}
    for rec in current_records:
        for key, value in (rec.get("features") or {}).items():
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                feature_values.setdefault(key, []).append(float(value))
    feature_scores: dict[str, float] = {}
    for key, values in feature_values.items():
        current_mean = mean(values) if values else 0.0
        base = baseline_stats.get(key, {}) if isinstance(baseline_stats.get(key), dict) else {"mean": baseline_stats.get(key)}
        baseline_mean = _num(base.get("mean"), current_mean)
        baseline_std = max(abs(_num(base.get("std"), 1.0)), 1.0)
        feature_scores[key] = round(abs(current_mean - baseline_mean) / baseline_std, 4)
    overall = max(feature_scores.values()) if feature_scores else 0.0
    if overall >= thresholds.get("block", 0.5):
        decision = DriftDecision.BLOCK_PROMOTION.value
    elif overall >= thresholds.get("retrain", 0.3):
        decision = DriftDecision.RETRAIN.value
    elif overall >= thresholds.get("watch", 0.15):
        decision = DriftDecision.WATCH.value
    else:
        decision = DriftDecision.STABLE.value
    return {
        "drift_id": _stable_id({"baseline": baseline_stats, "records": [r.get("feature_id") for r in current_records], "scores": feature_scores}, "drift"),
        "overall_score": round(overall, 4),
        "feature_scores": feature_scores,
        "decision": decision,
        "thresholds": thresholds,
        "created_at": _now(),
    }


def build_feature_lineage(*, feature_set: dict[str, Any], sources: list[dict[str, Any]], models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Describe reproducible feature lineage from source→transform→consumer models."""
    payload = {
        "feature_set_id": feature_set.get("feature_set_id"),
        "feature_names": feature_set.get("feature_names", []),
        "sources": sources,
        "models": [{"model_id": m.get("model_id"), "name": m.get("name"), "version": m.get("version")} for m in (models or [])],
    }
    payload["lineage_id"] = _stable_id(payload, "lin")
    payload["created_at"] = _now()
    return payload


def plan_retraining_job(*, drift: dict[str, Any], dataset: dict[str, Any], model: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a fail-closed retraining decision and reproducible job manifest."""
    policy = policy or {"allow_online_update": True, "min_rows": 10}
    reasons: list[str] = []
    action = "no_action"
    if dataset.get("status") != DatasetStatus.TRAINABLE.value:
        reasons.append("dataset_not_trainable")
        action = "blocked"
    elif int(dataset.get("row_count", 0)) < int(policy.get("min_rows", 10)):
        reasons.append("insufficient_rows")
        action = "wait_for_more_data"
    elif drift.get("decision") in {DriftDecision.RETRAIN.value, DriftDecision.BLOCK_PROMOTION.value}:
        reasons.append("drift_threshold_exceeded")
        action = "queue_retraining"
    elif drift.get("decision") == DriftDecision.WATCH.value and policy.get("allow_online_update", True):
        reasons.append("minor_drift_online_update")
        action = "online_update"
    return {
        "job_id": _stable_id({"drift": drift.get("drift_id"), "dataset": dataset.get("dataset_id"), "model": model.get("model_id"), "policy": policy}, "rtj"),
        "model_id": model.get("model_id"),
        "dataset_id": dataset.get("dataset_id"),
        "action": action,
        "reasons": reasons,
        "drift_score": drift.get("overall_score"),
        "reproducibility": {"feature_set_id": dataset.get("feature_set_id"), "object_uri": dataset.get("object_uri"), "model_version": model.get("version")},
        "created_at": _now(),
    }


def run_champion_challenger_cycle(
    *,
    task: str,
    champion: dict[str, Any] | None,
    challenger: dict[str, Any] | None,
    dataset: dict[str, Any],
    drift: dict[str, Any],
    metric_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promotion cycle that blocks rollout under material drift or bad data."""
    promotion = decide_model_promotion(task=task, champion=champion, challenger=challenger, metric_policy=metric_policy)
    blocked_by_drift = drift.get("decision") == DriftDecision.BLOCK_PROMOTION.value
    blocked_by_dataset = dataset.get("status") != DatasetStatus.TRAINABLE.value
    if blocked_by_drift or blocked_by_dataset:
        promotion = dict(promotion)
        promotion["decision"] = PromotionDecision.BLOCKED.value
        promotion["reasons"] = list(promotion.get("reasons", [])) + (["drift_blocks_promotion"] if blocked_by_drift else []) + (["dataset_blocks_promotion"] if blocked_by_dataset else [])
        promotion["rollout"] = {"initial_percentage": 0, "max_percentage": 0, "requires_shadow_period_hours": True, "fail_closed": True}
    return {
        "cycle_id": _stable_id({"promotion": promotion.get("decision_id"), "drift": drift.get("drift_id"), "dataset": dataset.get("dataset_id")}, "cc"),
        "promotion": promotion,
        "drift": drift,
        "dataset_id": dataset.get("dataset_id"),
        "created_at": _now(),
    }


def run_phase10_learning_cycle(
    *,
    phase9_cycle: dict[str, Any],
    champion_model: dict[str, Any] | None = None,
    challenger_model: dict[str, Any] | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """End-to-end learning cycle from Phase 9 feature batch to simulation output."""
    records = list(phase9_cycle.get("feature_store_batch") or [])
    spec = infer_feature_schema(records) if records else infer_feature_schema([])
    dataset = materialize_training_dataset(records, feature_set_spec=spec)

    feature_registry = register_feature_definitions(
        records,
        name=str(spec.get("name", "canonical_field_features")),
        version=str(spec.get("version", "v1")),
        entity_type=str(spec.get("entity_type", "field")),
    )
    production_feature_set = feature_registry.get("feature_set", {})
    offline_dataset_version = write_offline_feature_dataset(
        records,
        feature_set_id=str(production_feature_set.get("feature_set_id") or spec.get("feature_set_id")),
        object_uri=dataset.get("object_uri"),
    )
    online_materialization = materialize_online_feature_values(
        records,
        feature_set_id=str(production_feature_set.get("feature_set_id") or spec.get("feature_set_id")),
    )
    as_of = max((r.get("event_time") for r in records if r.get("event_time")), default=_now())
    try:
        point_in_time_snapshot = build_point_in_time_snapshot(records, as_of=str(as_of))
    except ValueError:
        point_in_time_snapshot = {"snapshot_id": None, "row_count": 0, "excluded_count": len(records), "point_in_time_safe": False}

    promotion = decide_model_promotion(task=(challenger_model or champion_model or {}).get("task", "agronomic_recommendation"), champion=champion_model, challenger=challenger_model)
    drift = detect_feature_drift(baseline_stats=(champion_model or {}).get("training_stats", {}), current_records=records)
    lineage = build_feature_lineage(feature_set=spec, sources=[{"source": "phase9.feature_store_batch", "record_count": len(records)}], models=[m for m in [champion_model, challenger_model] if m])
    production_lineage = build_production_feature_lineage(
        feature_set=production_feature_set,
        definitions=feature_registry.get("definitions", []),
        dataset_version=offline_dataset_version,
        consumers=[{"consumer": "phase10.model_registry", "task": (challenger_model or champion_model or {}).get("task", "agronomic_recommendation")}],
    )
    retraining_job = plan_retraining_job(drift=drift, dataset=dataset, model=champion_model or challenger_model or {"model_id": "unregistered"})
    champion_challenger = run_champion_challenger_cycle(task=(challenger_model or champion_model or {}).get("task", "agronomic_recommendation"), champion=champion_model, challenger=challenger_model, dataset=dataset, drift=drift)

    registered_champion = None
    if champion_model:
        registered_champion = register_model_version(
            model_name=str(champion_model.get("name") or champion_model.get("model_id") or "champion"),
            version=str(champion_model.get("version") or "champion"),
            task=str(champion_model.get("task") or "agronomic_recommendation"),
            artifacts=champion_model.get("artifacts") or {"uri": champion_model.get("artifact_uri", "")},
            metrics=champion_model.get("metrics") or {},
            dataset_version_id=offline_dataset_version.get("dataset_version_id"),
            feature_set_id=production_feature_set.get("feature_set_id"),
            status="champion",
        )
    registered_challenger = None
    if challenger_model:
        registered_challenger = register_model_version(
            model_name=str(challenger_model.get("name") or challenger_model.get("model_id") or "challenger"),
            version=str(challenger_model.get("version") or "candidate"),
            task=str(challenger_model.get("task") or "agronomic_recommendation"),
            artifacts=challenger_model.get("artifacts") or {"uri": challenger_model.get("artifact_uri", "")},
            metrics=challenger_model.get("metrics") or {},
            dataset_version_id=offline_dataset_version.get("dataset_version_id"),
            feature_set_id=production_feature_set.get("feature_set_id"),
            status=str(challenger_model.get("status") or "candidate"),
        )
    serving_promotion = None
    rollback_plan = None
    if registered_challenger:
        serving_promotion = apply_model_promotion(
            alias="agronomic_recommendation:production",
            champion=registered_champion,
            challenger=registered_challenger,
            policy={"primary_metric": "score", "min_improvement": 0.02, "require_artifact_hash": True},
        )
        if serving_promotion.get("rollback_target_model_id") and serving_promotion.get("target_model_id"):
            rollback_plan = rollback_serving_alias(
                alias=str(serving_promotion.get("alias")),
                current_model_id=str(serving_promotion.get("target_model_id")),
                target_model_id=str(serving_promotion.get("rollback_target_model_id")),
                reason="phase10_safe_rollback_plan",
            )
    online_update = None
    if champion_model:
        online_update = create_online_learning_update(model=champion_model, dataset=dataset, records=records)
    scenario_result = None
    if scenario:
        canonical_runtime = phase9_cycle.get("canonical_runtime") or {}
        state = canonical_runtime.get("canonical_state") or phase9_cycle.get("canonical_state") or {}
        scenario_result = run_scientific_scenario(field_state=state, scenario=scenario)
    return {
        "phase": "phase10_continuous_learning_ai",
        "cycle_id": _stable_id({"phase9": phase9_cycle.get("cycle_id"), "dataset": dataset.get("dataset_id"), "promotion": promotion.get("decision_id")}, "learn"),
        "feature_set": spec,
        "training_dataset": dataset,
        "model_promotion": champion_challenger.get("promotion", promotion),
        "drift_report": drift,
        "feature_lineage": lineage,
        "feature_store_runtime": {
            "registry": feature_registry,
            "offline_dataset_version": offline_dataset_version,
            "online_materialization": online_materialization,
            "point_in_time_snapshot": point_in_time_snapshot,
            "lineage": production_lineage,
        },
        "model_registry_runtime": {
            "champion": registered_champion,
            "challenger": registered_challenger,
            "serving_promotion": serving_promotion,
            "rollback_plan": rollback_plan,
            "model_cards": [
                build_model_card(model=m, feature_lineage=production_lineage)
                for m in [registered_champion, registered_challenger]
                if m
            ],
        },
        "retraining_job": retraining_job,
        "champion_challenger": champion_challenger,
        "online_learning_update": online_update,
        "scenario_result": scenario_result,
        "created_at": _now(),
    }
