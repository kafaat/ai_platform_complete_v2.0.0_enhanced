from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{sha256(raw).hexdigest()[:14]}"


@dataclass(frozen=True)
class ModelVersion:
    model_id: str
    model_name: str
    version: str
    task: str
    framework: str
    artifact_uri: str
    artifact_hash: str
    dataset_version_id: str | None
    feature_set_id: str | None
    metrics: dict[str, float]
    status: str
    created_at: str = field(default_factory=_now)


def _artifact_hash(artifacts: dict[str, Any]) -> str:
    return sha256(json.dumps(artifacts, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()


def register_model_version(
    *,
    model_name: str,
    version: str,
    task: str,
    framework: str = "python",
    artifacts: dict[str, Any] | None = None,
    metrics: dict[str, float] | None = None,
    dataset_version_id: str | None = None,
    feature_set_id: str | None = None,
    status: str = "registered",
) -> dict[str, Any]:
    """Create a reproducible model-version manifest.

    Persistence adapters should store this in model_versions/model_artifacts.
    """
    artifacts = artifacts or {}
    ahash = _artifact_hash(artifacts)
    artifact_uri = str(artifacts.get("uri") or artifacts.get("artifact_uri") or f"minio://sahool-models/{model_name}/{version}/{ahash[:12]}")
    version_payload = ModelVersion(
        model_id=_stable_id({"name": model_name, "version": version, "task": task, "artifact_hash": ahash}, "model"),
        model_name=model_name,
        version=version,
        task=task,
        framework=framework,
        artifact_uri=artifact_uri,
        artifact_hash=ahash,
        dataset_version_id=dataset_version_id,
        feature_set_id=feature_set_id,
        metrics={k: float(v) for k, v in (metrics or {}).items()},
        status=status,
    )
    return asdict(version_payload)


def apply_model_promotion(
    *,
    alias: str,
    champion: dict[str, Any] | None,
    challenger: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed promotion workflow with rollback metadata."""
    policy = policy or {"primary_metric": "score", "min_improvement": 0.02, "require_artifact_hash": True}
    reasons: list[str] = []
    allowed = True
    primary = str(policy.get("primary_metric", "score"))
    if policy.get("require_artifact_hash", True) and not challenger.get("artifact_hash"):
        allowed = False
        reasons.append("missing_artifact_hash")
    champion_score = float((champion or {}).get("metrics", {}).get(primary, 0.0))
    challenger_score = float((challenger or {}).get("metrics", {}).get(primary, 0.0))
    delta = challenger_score - champion_score
    if champion and delta < float(policy.get("min_improvement", 0.0)):
        allowed = False
        reasons.append("insufficient_metric_improvement")
    if challenger.get("status") in {"failed", "blocked", "rejected"}:
        allowed = False
        reasons.append("challenger_status_not_promotable")
    target = challenger if allowed else champion
    return {
        "promotion_id": _stable_id({"alias": alias, "champion": (champion or {}).get("model_id"), "challenger": challenger.get("model_id"), "policy": policy}, "prom"),
        "alias": alias,
        "decision": "promote" if allowed else "blocked",
        "target_model_id": (target or {}).get("model_id"),
        "previous_model_id": (champion or {}).get("model_id"),
        "challenger_model_id": challenger.get("model_id"),
        "metric_delta": {primary: round(delta, 6)},
        "reasons": reasons or ["policy_passed"],
        "rollback_target_model_id": (champion or {}).get("model_id"),
        "created_at": _now(),
    }


def rollback_serving_alias(*, alias: str, current_model_id: str, target_model_id: str, reason: str) -> dict[str, Any]:
    return {
        "rollback_id": _stable_id({"alias": alias, "current": current_model_id, "target": target_model_id, "reason": reason}, "rb"),
        "alias": alias,
        "from_model_id": current_model_id,
        "to_model_id": target_model_id,
        "reason": reason,
        "status": "planned",
        "created_at": _now(),
    }


def resolve_serving_alias(*, alias: str, aliases: dict[str, str], default_model_id: str | None = None) -> dict[str, Any]:
    model_id = aliases.get(alias) or default_model_id
    return {"alias": alias, "model_id": model_id, "resolved": model_id is not None, "created_at": _now()}


def build_model_card(*, model: dict[str, Any], feature_lineage: dict[str, Any] | None = None, risk_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "model_card_id": _stable_id({"model": model.get("model_id"), "lineage": (feature_lineage or {}).get("lineage_id")}, "card"),
        "model_id": model.get("model_id"),
        "model_name": model.get("model_name") or model.get("name"),
        "version": model.get("version"),
        "task": model.get("task"),
        "dataset_version_id": model.get("dataset_version_id"),
        "feature_set_id": model.get("feature_set_id"),
        "metrics": model.get("metrics", {}),
        "artifact_hash": model.get("artifact_hash"),
        "lineage_id": (feature_lineage or {}).get("lineage_id"),
        "risk_summary": risk_summary or {"fail_closed": True, "requires_human_approval_for_execution": True},
        "created_at": _now(),
    }
