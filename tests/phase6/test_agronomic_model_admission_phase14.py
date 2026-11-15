"""Local admission-preflight tests. No real external licensing or evaluation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from shared.mlops import assess_agronomic_model_candidate as assess

pytestmark = pytest.mark.unit

EVAL = {
    "tenant_id": "tenant-A",
    "model_id": "m-A",
    "evaluation_run_id": "eval-A",
    "candidate_artifact_digest": "a" * 64,
    "agronomic_cohort_fingerprint": "c" * 64,
    "dataset_fingerprint": "d" * 64,
    "evaluation_state": "evaluated",
    "dataset_count": 120,
    "evaluated_by": "evaluator-A",
    "baseline_metrics": {"mae": 2.5},
    "candidate_metrics": {"mae": 2.0},
}
PROMO = {
    "tenant_id": "tenant-A",
    "model_id": "m-A",
    "evaluation_run_id": "eval-A",
    "candidate_artifact_digest": "a" * 64,
    "agronomic_cohort_fingerprint": "c" * 64,
    "decision_state": "promotion_eligible",
    "decided_by": "reviewer-B",
}
EVIDENCE = {
    "model_license_id": "Apache-2.0",
    "dataset_license_id": "CUSTOM-GRANT-99",
    "commercial_use_allowed": True,
    "model_weights_sha256": "f" * 64,
    "weights_receipt_sha256": "1" * 64,
    "dataset_receipt_sha256": "2" * 64,
    "license_receipt_sha256": "3" * 64,
    "evaluation_receipt_sha256": "4" * 64,
    "tested_independent_fields": 8,
    "tested_independent_seasons": 3,
    "dataset_frozen_at": "2026-08-10T00:00:00+00:00",
    "evaluation_completed_at": "2026-09-10T00:00:00+00:00",
    "evaluation_policy_version": "cohort-holdout-v1",
}


def run(e=None, p=None, ev=None, verifier=None, env="production"):
    return assess(
        e or deepcopy(EVAL),
        p or deepcopy(PROMO),
        ev or deepcopy(EVIDENCE),
        target_environment=env,
        trusted_verifier=verifier,
    )


def test_rejects_caller_attested_bools_without_trusted_verifier():
    e = {**EVIDENCE, "verified": True, "human_approved": True}
    result = run(ev=e)
    assert result["eligible_for_independent_review"] is False
    assert "trusted_verifier_not_connected" in result["reason_codes"]
    assert result["activation_performed"] is False
    assert result["authorization_granted"] is False


def test_positive_preflight_requires_explicit_independent_evidence_verifier():
    calls = []

    def trusted(a, b, c, target_environment):
        calls.append(
            (
                a["evaluation_run_id"],
                b["evaluation_run_id"],
                c["model_weights_sha256"],
                target_environment,
            )
        )
        return True

    result = run(verifier=trusted)
    assert result["eligible_for_independent_review"] is True
    assert result["authorization_granted"] is False
    assert calls == [("eval-A", "eval-A", "f" * 64, "production")]


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("commercial_use_allowed", False, "production_commercial_license_not_evidenced"),
        ("model_license_id", "", "license_or_evaluation_policy_missing"),
        ("weights_receipt_sha256", "x", "missing_or_invalid_digest:weights_receipt_sha256"),
        ("tested_independent_fields", 1, "insufficient_field_holdout"),
        ("tested_independent_seasons", 0, "insufficient_season_holdout"),
        (
            "dataset_frozen_at",
            "2026-12-10T00:00:00Z",
            "dataset_freeze_or_evaluation_timestamp_invalid",
        ),
        (
            "dataset_frozen_at",
            "2026-08-10T00:00:00",
            "dataset_freeze_or_evaluation_timestamp_invalid",
        ),
    ],
)
def test_rejects_missing_scientific_or_licensing_proof_even_with_verifier(key, value, reason):
    ev = {**EVIDENCE, key: value}
    result = run(ev=ev, verifier=lambda *_: True)
    assert result["eligible_for_independent_review"] is False
    assert reason in result["reason_codes"]


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("tenant_id", "another-tenant", "evaluation_promotion_scope_mismatch:tenant_id"),
        ("candidate_artifact_digest", "b" * 64, "artifact_digest_mismatch_or_invalid"),
        ("agronomic_cohort_fingerprint", "f" * 64, "agronomic_cohort_lineage_invalid"),
        (
            "decision_state",
            "promotion_rejected",
            "authoritative_evaluation_or_promotion_not_eligible",
        ),
        ("decided_by", "evaluator-A", "independent_evaluator_required"),
    ],
)
def test_rejects_inconsistent_authoritative_lifecycle(key, value, reason):
    p = {**PROMO, key: value}
    result = run(p=p, verifier=lambda *_: True)
    assert reason in result["reason_codes"]
    assert result["eligible_for_independent_review"] is False


@pytest.mark.parametrize("metric", [float("inf"), float("nan"), True, "2.0"])
def test_metrics_must_be_finite_numeric(metric):
    e = {**EVAL, "candidate_metrics": {"mae": metric}}
    assert "metrics_missing_or_nonfinite" in run(e=e, verifier=lambda *_: True)["reason_codes"]


def test_external_verifier_failure_never_grants_review_eligibility():
    assert "external_evidence_verification_failed" in run(verifier=lambda *_: False)["reason_codes"]

    def raises(*_):
        raise ConnectionError("untrusted verifier offline")

    assert "external_evidence_verification_failed" in run(verifier=raises)["reason_codes"]


def test_preflight_is_deterministic_without_mutating_records():
    e = deepcopy(EVAL)
    p = deepcopy(PROMO)
    ev = deepcopy(EVIDENCE)
    a = run(e, p, ev, verifier=lambda *_: True)
    b = run(e, p, ev, verifier=lambda *_: True)
    assert a == b and e == EVAL and p == PROMO and ev == EVIDENCE


def test_trusted_verifier_must_receive_target_environment():
    seen = []

    def verifier(evaluation, promotion, evidence, target_environment):
        seen.append(target_environment)
        return target_environment == "staging"

    assert run(verifier=verifier, env="staging")["eligible_for_independent_review"]
    result = run(verifier=verifier, env="production")
    assert not result["eligible_for_independent_review"]
    assert "external_evidence_verification_failed" in result["reason_codes"]
    assert seen == ["staging", "production"]


def test_legacy_three_arg_verifier_fails_closed():
    result = run(verifier=lambda a, b, c: True)
    assert not result["eligible_for_independent_review"]
    assert "external_evidence_verification_failed" in result["reason_codes"]


def test_trusted_verifier_not_called_if_production_license_missing():
    calls = []
    ev = {**EVIDENCE, "commercial_use_allowed": False}
    result = run(ev=ev, verifier=lambda *args: calls.append(args) or True)
    assert not result["eligible_for_independent_review"]
    assert calls == []
