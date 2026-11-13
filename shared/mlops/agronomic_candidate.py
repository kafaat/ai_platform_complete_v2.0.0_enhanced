"""Read-only admission preflight for an existing Decision Service model lifecycle.

This is not a registry, promotion, evaluation, approval, or activation service.
It cross-checks an *authoritative* evaluation and promotion record against
externally verifiable license/model-byte/dataset receipts. Without an independent
trusted verifier, a caller's booleans or metadata can never confer readiness.

The caller MUST fetch evaluation/promotion rows from the tenant-scoped Decision
Service, never accept them from an untrusted client as authorization evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ADMISSION_SCHEMA = "sahool.agronomic-model-candidate/v1"
REQUIRED_EVIDENCE = (
    "model_license_id",
    "dataset_license_id",
    "commercial_use_allowed",
    "model_weights_sha256",
    "weights_receipt_sha256",
    "dataset_receipt_sha256",
    "license_receipt_sha256",
    "evaluation_receipt_sha256",
    "tested_independent_fields",
    "tested_independent_seasons",
    "dataset_frozen_at",
    "evaluation_completed_at",
    "evaluation_policy_version",
)
# Verifier is supplied from the trusted operator/Decision Service boundary.
# It must authenticate actual source bytes, license grants and independent
# evaluation receipts, not only check the shape of the supplied identifiers.
ProofVerifier = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], bool]


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _stamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            return None
        return result.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _finite_metrics(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    for metric in value.values():
        if isinstance(metric, bool) or not isinstance(metric, (int, float)):
            return False
        try:
            if not math.isfinite(float(metric)):
                return False
        except (ValueError, OverflowError):
            return False
    return True


def assess_agronomic_model_candidate(
    evaluation: Mapping[str, Any],
    promotion: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    target_environment: str,
    trusted_verifier: ProofVerifier | None = None,
) -> dict[str, Any]:
    """Assess provenance only; a positive result is *still not activation*.

    No filesystem, network, database writes, registry mutation or crop decisions.
    `trusted_verifier` must be owned by the authoritative infrastructure.
    """
    reasons: list[str] = []
    if target_environment not in {"staging", "production"}:
        reasons.append("environment_unsupported")
    if not all(isinstance(x, Mapping) for x in (evaluation, promotion, evidence)):
        raise ValueError("admission inputs must be mappings")
    for key in REQUIRED_EVIDENCE:
        if key not in evidence:
            reasons.append(f"missing_evidence:{key}")
    for field in ("tenant_id", "model_id", "evaluation_run_id"):
        if (
            not evaluation.get(field)
            or not promotion.get(field)
            or evaluation[field] != promotion[field]
        ):
            reasons.append(f"evaluation_promotion_scope_mismatch:{field}")
    if evaluation.get("candidate_artifact_digest") != promotion.get(
        "candidate_artifact_digest"
    ) or not _sha(evaluation.get("candidate_artifact_digest")):
        reasons.append("artifact_digest_mismatch_or_invalid")
    if evaluation.get("agronomic_cohort_fingerprint") != promotion.get(
        "agronomic_cohort_fingerprint"
    ) or not _sha(evaluation.get("agronomic_cohort_fingerprint")):
        reasons.append("agronomic_cohort_lineage_invalid")
    if (
        evaluation.get("evaluation_state") != "evaluated"
        or promotion.get("decision_state") != "promotion_eligible"
    ):
        reasons.append("authoritative_evaluation_or_promotion_not_eligible")
    if (
        not isinstance(evaluation.get("dataset_count"), int)
        or isinstance(evaluation.get("dataset_count"), bool)
        or evaluation["dataset_count"] < 1
    ):
        reasons.append("dataset_count_invalid")
    if not _sha(evaluation.get("dataset_fingerprint")):
        reasons.append("dataset_fingerprint_invalid")
    if not _finite_metrics(evaluation.get("candidate_metrics")) or not _finite_metrics(
        evaluation.get("baseline_metrics")
    ):
        reasons.append("metrics_missing_or_nonfinite")
    if (
        not evaluation.get("evaluated_by")
        or not promotion.get("decided_by")
        or evaluation.get("evaluated_by") == promotion.get("decided_by")
    ):
        reasons.append("independent_evaluator_required")
    if not all(
        isinstance(evidence.get(k), str) and evidence[k].strip()
        for k in ("model_license_id", "dataset_license_id", "evaluation_policy_version")
    ):
        reasons.append("license_or_evaluation_policy_missing")
    if evidence.get("commercial_use_allowed") is not True and target_environment == "production":
        reasons.append("production_commercial_license_not_evidenced")
    for key in (
        "model_weights_sha256",
        "weights_receipt_sha256",
        "dataset_receipt_sha256",
        "license_receipt_sha256",
        "evaluation_receipt_sha256",
    ):
        if not _sha(evidence.get(key)):
            reasons.append(f"missing_or_invalid_digest:{key}")
    fields = evidence.get("tested_independent_fields")
    seasons = evidence.get("tested_independent_seasons")
    if not isinstance(fields, int) or isinstance(fields, bool) or fields < 2:
        reasons.append("insufficient_field_holdout")
    if not isinstance(seasons, int) or isinstance(seasons, bool) or seasons < 2:
        reasons.append("insufficient_season_holdout")
    freeze = _stamp(evidence.get("dataset_frozen_at"))
    completed = _stamp(evidence.get("evaluation_completed_at"))
    if freeze is None or completed is None or completed <= freeze:
        reasons.append("dataset_freeze_or_evaluation_timestamp_invalid")
    # A caller-provided `verified: true` is not trusted evidence.
    if not reasons:
        if trusted_verifier is None:
            reasons.append("trusted_verifier_not_connected")
        else:
            try:
                if trusted_verifier(evaluation, promotion, evidence) is not True:
                    reasons.append("external_evidence_verification_failed")
            except Exception:
                reasons.append("external_evidence_verification_failed")
    payload = {
        "contract_version": ADMISSION_SCHEMA,
        "tenant_id": evaluation.get("tenant_id"),
        "model_id": evaluation.get("model_id"),
        "evaluation_run_id": evaluation.get("evaluation_run_id"),
        "artifact_digest": evaluation.get("candidate_artifact_digest"),
        "target_environment": target_environment,
        "eligible_for_independent_review": not reasons,
        "activation_performed": False,
        "authorization_granted": False,
        "reason_codes": sorted(set(reasons)),
    }
    payload["assessment_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    return payload
