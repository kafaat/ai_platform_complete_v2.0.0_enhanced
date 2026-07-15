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
