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


# --- stored-diagnosis reload (referral path) -------------------------------------------------
# The diagnosis is persisted with ``model_dump(mode="json")``. The strict ContractModel used to be
# reloaded with ``model_validate`` on that dict, which rejects the JSON-mode datetime/UUID/Decimal/
# enum strings, so the decision referral failed before ever reaching the bridge.


def _stored_payload():
    record = confirmed_record()
    diagnosis = build_diagnosis(anomaly_record=record, tenant_id=UUID(record["tenant_id"]))
    return diagnosis, diagnosis.model_dump(mode="json")


def test_stored_json_mode_diagnosis_reloads_and_equals_original():
    from diagnosis_engine import load_stored_diagnosis

    from shared.contracts.remote_sensing import DiagnosisHypothesisV1

    original, stored = _stored_payload()
    # Pin the regression: the old reload really is rejected by the strict contract.
    with pytest.raises(ValueError):
        DiagnosisHypothesisV1.model_validate(stored)
    assert load_stored_diagnosis(stored) == original


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda p: p.pop("tenant_id"),
        lambda p: p.update(confidence="not-a-number"),
        lambda p: p.update(proposed_at="yesterday"),
        lambda p: p.update(unexpected_field=1),
    ],
)
def test_corrupt_stored_diagnosis_is_refused_as_invalid_transition(corrupt):
    from anomaly_store import InvalidTransition
    from diagnosis_engine import load_stored_diagnosis

    _, stored = _stored_payload()
    corrupt(stored)
    with pytest.raises(InvalidTransition, match="stored_diagnosis_invalid"):
        load_stored_diagnosis(stored)


@pytest.mark.parametrize("payload", [None, {}])
def test_missing_stored_diagnosis_is_refused(payload):
    from anomaly_store import InvalidTransition
    from diagnosis_engine import load_stored_diagnosis

    with pytest.raises(InvalidTransition, match="diagnosis_not_proposed"):
        load_stored_diagnosis(payload)


def test_non_mapping_stored_diagnosis_is_refused():
    from anomaly_store import InvalidTransition
    from diagnosis_engine import load_stored_diagnosis

    with pytest.raises(InvalidTransition, match="stored_diagnosis_invalid"):
        load_stored_diagnosis(["not", "a", "mapping"])


def _referral_harness(monkeypatch, stored):
    import asyncio

    import main
    from routers import diagnoses

    tenant = confirmed_record()["tenant_id"]
    referred: list = []

    class _Store:
        async def get(self, ref, tenant_id):
            return {"tenant_id": tenant, "payload": {"diagnosis": stored}}

        async def transition(self, ref, status, *, expected_version, patch, tenant_id):
            return {"status": status, "patch": patch}

    class _Bridge:
        async def refer(self, *, diagnosis, **kwargs):
            referred.append(diagnosis)
            return {"referral": {"id": "r1"}, "decision_service": {"decision_id": "d1"}}

    monkeypatch.setattr(main, "_verify_claims", lambda token: {"tenant_id": tenant})
    monkeypatch.setattr(main, "_tenant_from_claims", lambda claims: tenant)
    monkeypatch.setattr(diagnoses, "_store", _Store())
    monkeypatch.setattr(diagnoses, "_bridge", _Bridge())
    request = diagnoses.ReferralRequest(expected_version=3, field_state_ref="urn:sahool:fs:1")

    def call():
        return asyncio.run(
            diagnoses.refer_to_decision(
                "urn:sahool:anomaly:anm_abc", request, authorization="Bearer t", token="t"
            )
        )

    return call, referred


def test_referral_endpoint_reaches_bridge_with_reloaded_diagnosis(monkeypatch):
    original, stored = _stored_payload()
    call, referred = _referral_harness(monkeypatch, stored)
    out = call()
    assert referred == [original]
    assert out["anomaly"]["status"] == "decision_referred"


def test_referral_endpoint_refuses_corrupt_stored_diagnosis_with_409(monkeypatch):
    from fastapi import HTTPException

    _, stored = _stored_payload()
    stored["confidence"] = "garbage"
    call, referred = _referral_harness(monkeypatch, stored)
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == 409
    assert referred == []
