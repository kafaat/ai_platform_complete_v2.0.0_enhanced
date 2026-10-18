from datetime import UTC, datetime
from uuid import UUID

import pytest
from diagnosis_engine import build_diagnosis


def confirmed_record():
    return {
        "anomaly_ref": "urn:sahool:anomaly:anm_abc",
        "tenant_id": "88ddb9f8-cf89-4398-a404-fe88ec4d4bb6",
        "field_id": "fld_abc",
        "season_id": "season_2026",
        "status": "confirmed",
        "payload": {
            "signal_type": "ndmi_decline",
            "confidence": "0.78",
            "verification_evidence_refs": ["urn:sahool:evidence:evd_1"],
            "verification_evidence": [
                {
                    "evidence_ref": "urn:sahool:evidence:evd_1",
                    "tenant_id": "88ddb9f8-cf89-4398-a404-fe88ec4d4bb6",
                    "source_system": "task-service",
                    "evidence_type": "ground_verification",
                    "relation_type": "corroborating",
                    "captured_at": "2026-07-15T00:00:00Z",
                    "content_hash": "a" * 64,
                    "verification_state": "verified",
                }
            ],
            "disposition_reason_codes": ["soil_dry"],
        },
    }


def test_builds_hypothesis_not_prescription():
    diagnosis = build_diagnosis(
        anomaly_record=confirmed_record(),
        tenant_id=UUID("88ddb9f8-cf89-4398-a404-fe88ec4d4bb6"),
    )
    assert diagnosis.suspected_condition == "water_stress"
    assert "prescription" not in type(diagnosis).model_fields
    assert diagnosis.evidence_bundle.evidence[0].verification_state == "verified"


def test_requires_confirmed_anomaly():
    record = confirmed_record()
    record["status"] = "triaged"
    with pytest.raises(ValueError, match="confirmed"):
        build_diagnosis(
            anomaly_record=record, tenant_id=UUID("88ddb9f8-cf89-4398-a404-fe88ec4d4bb6")
        )


def test_preserves_source_evidence_hash_capture_time_and_input_quality():
    record = confirmed_record()
    diagnosis = build_diagnosis(anomaly_record=record, tenant_id=UUID(record["tenant_id"]))
    evidence = diagnosis.evidence_bundle.evidence[0]
    assert evidence.content_hash == "a" * 64
    assert evidence.captured_at == datetime(2026, 7, 15, tzinfo=UTC)
    assert str(diagnosis.confidence) == "0.78"


@pytest.mark.parametrize("mutation", ["metadata_missing", "cross_tenant", "not_verified"])
def test_unverifiable_metadata_cannot_become_a_diagnosis(mutation):
    record = confirmed_record()
    if mutation == "metadata_missing":
        record["payload"].pop("verification_evidence")
    elif mutation == "cross_tenant":
        record["payload"]["verification_evidence"][0]["tenant_id"] = str(UUID(int=2))
    else:
        record["payload"]["verification_evidence"][0]["verification_state"] = "pending"
    with pytest.raises(ValueError):
        build_diagnosis(anomaly_record=record, tenant_id=UUID(record["tenant_id"]))
