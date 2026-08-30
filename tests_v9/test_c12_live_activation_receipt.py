from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/staging/c12_live_activation_receipt.py"
CERTIFICATION = ROOT / "scripts/ci/c12_governed_learning_promotion_certification.py"
spec = importlib.util.spec_from_file_location("c12_live_activation_receipt", SCRIPT)
assert spec and spec.loader
c12 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c12
spec.loader.exec_module(c12)

cert_spec = importlib.util.spec_from_file_location(
    "c12_governed_learning_promotion_certification", CERTIFICATION
)
assert cert_spec and cert_spec.loader
certification = importlib.util.module_from_spec(cert_spec)
cert_spec.loader.exec_module(certification)

SHA = "a" * 40
NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def receipt():
    digest = "b" * 64
    return c12.finalize(
        {
            "schema": c12.SCHEMA,
            "subject_sha": SHA,
            "observed_at": "2026-08-30T09:30:00Z",
            "source": {"kind": "postgresql", "read_only": True, "authoritative": True},
            "classification": "PASSED",
            "live_evidence_complete": True,
            "authority_changed": False,
            "chain": {
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "model_id": "yield-v2",
                "target_environment": "staging",
                "promotion_decision_id": "promotion-1",
                "decision_state": "promotion_eligible",
                "candidate_artifact_digest": digest,
                "activation_request_id": "request-1",
                "requested_state": "pending_activation_approval",
                "requested_by": "requester",
                "activation_review_id": "review-1",
                "review_decision": "approved",
                "reviewed_by": "independent-reviewer",
                "activation_command_id": "command-1",
                "command_state": "queued",
                "activation_claim_id": "claim-1",
                "activation_receipt_id": "receipt-1",
                "receipt_state": "activated",
                "active_artifact_digest": digest,
                "verification_id": "verify-1",
                "verification_state": "verified_healthy",
                "verification_artifact_digest": digest,
                "rollout_plan_id": "rollout-1",
                "rollout_mode": "canary",
                "traffic_percent": 10.0,
                "rollout_receipt_id": "rollout-receipt-1",
                "rollout_receipt_state": "applied",
                "observed_traffic_percent": 10.0,
                "rollout_candidate_artifact_digest": digest,
                "monitoring_snapshot_id": "monitor-1",
                "sample_count": 100,
                "drift_state": "stable",
            },
        }
    )


def check(body):
    return c12.problems(body, expected_subject_sha=SHA, now=NOW)


def refinalize(body):
    body["evidence_sha256"] = c12.canonical_digest(body)
    return body


def test_valid_subject_bound_live_chain_passes():
    assert check(receipt()) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda r: r.update(subject_sha="c" * 40), "subject_sha_mismatch"),
        (lambda r: r["chain"].update(reviewed_by="requester"), "activation_self_approval"),
        (
            lambda r: r["chain"].update(active_artifact_digest="c" * 64),
            "artifact_digest_chain_mismatch",
        ),
        (
            lambda r: r["chain"].update(verification_state="verified_degraded"),
            "invalid_chain_state:verification_state",
        ),
        (lambda r: r["chain"].update(sample_count=0), "monitoring_sample_count_not_positive"),
        (lambda r: r["chain"].update(rollout_mode="shadow"), "non_serving_rollout_mode"),
    ],
)
def test_unsafe_chain_mutations_are_rejected(mutate, expected):
    body = receipt()
    mutate(body)
    refinalize(body)
    assert expected in check(body)


def test_tampering_without_resealing_is_rejected():
    body = receipt()
    body["chain"]["sample_count"] = 101
    assert "evidence_digest_mismatch" in check(body)


def test_receipt_may_not_claim_that_it_changed_authority():
    body = receipt()
    body["authority_changed"] = True
    refinalize(body)
    assert "receipt_claims_authority_change" in check(body)


def test_stale_receipt_is_not_live_evidence():
    body = receipt()
    body["observed_at"] = "2026-08-28T09:30:00Z"
    refinalize(body)
    assert "receipt_outside_freshness_window" in check(body)


def test_sql_inputs_are_strictly_validated():
    with pytest.raises(ValueError):
        c12._sql(
            "11111111-1111-1111-1111-111111111111",
            "model'; DROP TABLE x;--",
            None,
            "staging",
        )


def test_receipt_round_trip_is_stable(tmp_path):
    path = tmp_path / "receipt.json"
    body = receipt()
    path.write_text(json.dumps(body), encoding="utf-8")
    assert check(json.loads(path.read_text(encoding="utf-8"))) == []


def test_certification_never_promotes_automatically():
    source = CERTIFICATION.read_text(encoding="utf-8")
    assert '"LIVE_EVIDENCE_VERIFIED"' in source
    assert 'promotion_permitted=False' in source
    assert 'automatic_promotion=False' in source
    assert 'ready_for_authority_adjudication=True' in source
    assert 'independent human adjudication under GATE-01' in source


def test_collector_requires_real_subject_and_authoritative_sor():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'DECISION_SERVICE_SOR_ENABLED' in source
    assert '["git", "rev-parse", "HEAD"]' in source
    assert 'local_subject != args.subject_sha' in source


def test_verified_receipt_only_reaches_independent_adjudication(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(certification, "run", lambda *_args: (0, "{}"))
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("{}", encoding="utf-8")

    assert (
        certification.main(
            ["--receipt", str(receipt_path), "--subject-sha", SHA]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "LIVE_EVIDENCE_VERIFIED"
    assert result["promotion_permitted"] is False
    assert result["automatic_promotion"] is False
    assert result["authority_changed"] is False
    assert result["ready_for_authority_adjudication"] is True
