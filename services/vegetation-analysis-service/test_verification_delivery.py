"""HTTP and durable receipt checks on the real local anomaly store (no DB stand-in)."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from anomaly_requests import VerificationCompletion
from anomaly_runtime import AnomalyStoreFacade
from anomaly_store import AnomalyStore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import verification

from shared.contracts.remote_sensing.verification_delivery import (
    canonical_completion_digest,
    canonical_completion_payload,
    verification_request_binding,
)
from shared.security.service_tenant_assertion import create_tenant_assertion

pytestmark = pytest.mark.unit
TENANT = "11111111-1111-4111-8111-111111111111"
OTHER_TENANT = "22222222-2222-4222-8222-222222222222"
ANOMALY = "urn:sahool:anomaly:delivery_test"
TASK = "urn:sahool:task:33333333-3333-4333-8333-333333333333"
TOKEN = "local-verification-callback-token"
ASSERTION_KEY = "local-verification-assertion-key-32-characters"
KEY = "verification-delivery-key-0001"
COMPLETED = "2026-03-31T12:00:00+00:00"


def path(action="verification-results", ref=ANOMALY):
    return f"/internal/anomalies/{quote(ref, safe='')}/{action}"


def body(**changes):
    return {
        "expected_version": 3,
        "task_ref": TASK,
        "verification_result": "inconclusive",
        "evidence_refs": [],
        "evidence": [],
        "reason_codes": ["VISIT_DID_NOT_RESOLVE_TARGET"],
        "completed_at": COMPLETED,
        **changes,
    }


def headers(payload=None, *, tenant=TENANT, method="POST", target=None, key=KEY):
    target = target or path("verification-context" if method == "GET" else "verification-results")
    request_id = uuid.uuid4().hex
    if payload is not None:
        wire = VerificationCompletion.model_validate(payload).model_dump(mode="json")
        request_id += "." + verification_request_binding(key, canonical_completion_digest(wire))
    return {
        "X-Task-Service-Token": TOKEN,
        "X-Tenant-Id": tenant,
        "X-Service-Name": "field-management-service",
        "X-Request-Id": request_id,
        "X-Tenant-Assertion": create_tenant_assertion(
            ASSERTION_KEY,
            "field-management-service",
            tenant,
            method=method,
            path=target,
            request_id=request_id,
        ),
        "Idempotency-Key": key,
    }


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("VEGETATION_VERIFICATION_SERVICE_TOKEN", TOKEN)
    monkeypatch.delenv("TASK_SERVICE_CALLBACK_TOKEN", raising=False)
    monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY", ASSERTION_KEY)
    monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "current")
    db = AnomalyStore(str(tmp_path / "anomalies.sqlite3"))
    db.upsert_detected(
        {
            "anomaly_ref": ANOMALY,
            "tenant_id": TENANT,
            "field_id": "fld_verification",
            "season_id": "season_verification",
            "geometry_ref": "urn:sahool:geometry:verification_target",
            "primary_observation_ref": "urn:sahool:observation:real_store_fixture",
            "signal_type": "ndvi_decline",
            "status": "detected",
        }
    )
    db.reserve_verification(
        ANOMALY, expected_version=1, idempotency_key="dispatch-key", tenant_id=TENANT
    )
    db.attach_verification_task(
        ANOMALY, expected_version=2, idempotency_key="dispatch-key", task_ref=TASK, tenant_id=TENANT
    )
    monkeypatch.setattr(verification, "_store", AnomalyStoreFacade(db))
    app = FastAPI()
    app.include_router(verification.router)
    with TestClient(app) as client:
        yield client, db


def test_context_is_the_exact_persisted_owner_snapshot(harness):
    client, db = harness
    response = client.get(path("verification-context"), headers=headers(method="GET"))
    assert response.status_code == 200, response.text
    result = response.json()
    stored = db.get(ANOMALY, tenant_id=TENANT)
    assert result["anomaly"] == stored
    assert result["persisted"] is True
    assert (
        result["snapshot_digest"]
        == hashlib.sha256(
            json.dumps(
                stored, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest()
    )
    assert stored["aggregate_version"] == 3


def test_one_callback_records_one_receipt_and_exact_replay_does_not_transition(harness):
    client, db = harness
    data = body()
    first = client.post(path(), json=data, headers=headers(data))
    assert first.status_code == 200, first.text
    before_replay = db.get(ANOMALY, tenant_id=TENANT)
    second = client.post(path(), json=data, headers=headers(data))
    assert second.status_code == 200, second.text
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert first.json()["verification_delivery"] == second.json()["verification_delivery"]
    assert first.json()["verification_delivery"][
        "original_completion"
    ] == canonical_completion_payload(data)
    assert db.get(ANOMALY, tenant_id=TENANT) == before_replay
    assert before_replay["aggregate_version"] == 4
    assert before_replay["status"] == "inconclusive"
    assert before_replay["payload"]["verification_completed_at"] == COMPLETED


def test_receipt_replays_after_store_and_http_client_restart(harness, monkeypatch):
    client, db = harness
    data = body()
    accepted = client.post(path(), json=data, headers=headers(data))
    assert accepted.status_code == 200
    restarted = AnomalyStore(db.path)
    monkeypatch.setattr(verification, "_store", AnomalyStoreFacade(restarted))
    app = FastAPI()
    app.include_router(verification.router)
    with TestClient(app) as other:
        replay = other.post(path(), json=data, headers=headers(data))
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert restarted.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 4


@pytest.mark.parametrize(
    "change",
    [{"reason_codes": ["CHANGED"]}, {"expected_version": 4}, {"verification_result": "rejected"}],
)
def test_same_key_different_body_is_conflict_without_overwrite(harness, change):
    client, db = harness
    data = body()
    assert client.post(path(), json=data, headers=headers(data)).status_code == 200
    original = db.get(ANOMALY, tenant_id=TENANT)
    changed = body(**change)
    refused = client.post(path(), json=changed, headers=headers(changed))
    assert refused.status_code == 409
    assert "different_request" in refused.json()["detail"]
    assert db.get(ANOMALY, tenant_id=TENANT) == original


def test_different_key_does_not_claim_an_existing_receipt(harness):
    client, db = harness
    data = body()
    assert client.post(path(), json=data, headers=headers(data)).status_code == 200
    response = client.post(
        path(), json=data, headers=headers(data, key="different-operation-key-002")
    )
    assert response.status_code == 409
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 4


def test_stale_expected_version_is_not_raised_automatically(harness):
    client, db = harness
    data = body(expected_version=2)
    response = client.post(path(), json=data, headers=headers(data))
    assert response.status_code == 409
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_callback_for_another_tenant_returns_no_record(harness):
    client, db = harness
    data = body()
    response = client.post(path(), json=data, headers=headers(data, tenant=OTHER_TENANT))
    assert response.status_code == 404
    assert (
        client.get(
            path("verification-context"), headers=headers(method="GET", tenant=OTHER_TENANT)
        ).status_code
        == 404
    )
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_unbound_task_and_another_task_are_refused(harness):
    client, db = harness
    changed = body(task_ref="urn:sahool:task:another")
    assert client.post(path(), json=changed, headers=headers(changed)).status_code == 409
    other = "urn:sahool:anomaly:unbound"
    db.upsert_detected(
        {
            "anomaly_ref": other,
            "tenant_id": TENANT,
            "field_id": "fld_verification",
            "season_id": "season_verification",
        }
    )
    db.transition(other, "verification_requested", expected_version=1, tenant_id=TENANT)
    data = body(expected_version=2)
    assert (
        client.post(
            path(ref=other), json=data, headers=headers(data, target=path(ref=other))
        ).status_code
        == 409
    )
    assert db.get(other, tenant_id=TENANT)["aggregate_version"] == 2


@pytest.mark.parametrize(
    "variable",
    ["VEGETATION_VERIFICATION_SERVICE_TOKEN", "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY"],
)
def test_credentials_missing_fail_closed(harness, monkeypatch, variable):
    client, db = harness
    monkeypatch.delenv(variable)
    data = body()
    assert client.post(path(), json=data, headers=headers(data)).status_code == 503
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_the_legacy_callback_token_does_not_open_the_bridge(harness, monkeypatch):
    # Holding only the legacy route's TASK_SERVICE_CALLBACK_TOKEN is not enough, and the bridge
    # refuses to run at all when its token is configured to the same value.
    client, db = harness
    monkeypatch.setenv("TASK_SERVICE_CALLBACK_TOKEN", "legacy-only-token-value")
    data = body()
    hdrs = dict(headers(data))
    hdrs["X-Task-Service-Token"] = "legacy-only-token-value"
    assert client.post(path(), json=data, headers=hdrs).status_code == 403
    monkeypatch.setenv("TASK_SERVICE_CALLBACK_TOKEN", TOKEN)
    assert client.post(path(), json=data, headers=headers(data)).status_code == 503
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_flag_is_off_by_default(harness, monkeypatch):
    client, db = harness
    monkeypatch.delenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED")
    assert client.get(path("verification-context")).status_code == 404
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


@pytest.mark.parametrize(
    "name,value",
    [
        ("X-Task-Service-Token", "wrong"),
        ("X-Service-Name", "another-service"),
        ("X-Tenant-Id", "not-a-uuid"),
        ("X-Tenant-Assertion", "bad"),
        ("X-Request-Id", "another-id"),
    ],
)
def test_authentication_is_fail_closed_and_caller_bound(harness, name, value):
    client, db = harness
    data = body()
    signed = headers(data)
    signed[name] = value
    assert client.post(path(), json=data, headers=signed).status_code == 403
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_assertion_is_bound_to_encoded_path_and_method(harness):
    client, db = harness
    data = body()
    for signed in (
        headers(data, method="GET", target=path()),
        headers(data, target=path("verification-context")),
    ):
        assert client.post(path(), json=data, headers=signed).status_code == 403
    assert (
        client.post(path().replace("%3A", ":"), json=data, headers=headers(data)).status_code == 403
    )
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_changed_body_or_key_cannot_reuse_a_signed_request(harness):
    client, db = harness
    data = body()
    signed = headers(data)
    assert (
        client.post(path(), json=body(reason_codes=["tampered"]), headers=signed).status_code == 403
    )
    signed["Idempotency-Key"] = "changed-operation-key-002"
    assert client.post(path(), json=data, headers=signed).status_code == 403
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_expired_assertion_does_not_reach_the_store(harness):
    client, db = harness
    data = body()
    signed = headers(data)
    signed["X-Tenant-Assertion"] = create_tenant_assertion(
        ASSERTION_KEY,
        "field-management-service",
        TENANT,
        method="POST",
        path=path(),
        request_id=signed["X-Request-Id"],
        issued_at=int(datetime.now(UTC).timestamp()) - 90,
    )
    assert client.post(path(), json=data, headers=signed).status_code == 403
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def evidence(**changes):
    return {
        "evidence_ref": "urn:sahool:evidence:inspection_1",
        "tenant_id": TENANT,
        "source_system": "field-management-service",
        "evidence_type": "reviewed_inspection",
        "relation_type": "primary",
        "captured_at": "2026-03-31T11:00:00Z",
        "content_hash": "a" * 64,
        "verification_state": "verified",
        **changes,
    }


def test_confirmed_requires_qualified_original_metadata(harness):
    client, db = harness
    data = body(
        verification_result="confirmed",
        evidence=[evidence()],
        evidence_refs=[evidence()["evidence_ref"]],
    )
    response = client.post(path(), json=data, headers=headers(data))
    assert response.status_code == 200, response.text
    assert response.json()["anomaly"]["status"] == "confirmed"
    assert (
        response.json()["anomaly"]["payload"]["verification_evidence"][0]["content_hash"]
        == "a" * 64
    )
    assert "diagnosis" not in response.json()


def test_evidence_from_another_tenant_is_refused(harness):
    client, db = harness
    data = body(
        verification_result="confirmed",
        evidence=[evidence(tenant_id=OTHER_TENANT)],
        evidence_refs=[evidence()["evidence_ref"]],
    )
    response = client.post(path(), json=data, headers=headers(data))
    assert response.status_code == 403
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"verification_result": "confirmed"},
        {"completed_at": "2026-03-31T12:00:00"},
        {"completed_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        {"snapshot_digest": "b" * 64},
    ],
)
def test_original_dto_rejects_unsupported_or_invalid_completions(harness, changes):
    client, db = harness
    valid = body()
    signed = headers(valid)
    response = client.post(path(), json=body(**changes), headers=signed)
    assert response.status_code == 422, response.text
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_a_nonconfirmed_result_cannot_hide_mismatched_evidence_refs(harness):
    client, db = harness
    data = body(evidence_refs=["urn:sahool:evidence:missing"])
    assert client.post(path(), json=data, headers=headers(data)).status_code == 422
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_repeated_evidence_ref_is_rejected_even_when_metadata_matches(harness):
    client, db = harness
    data = body(evidence=[evidence()], evidence_refs=[evidence()["evidence_ref"]] * 2)
    assert client.post(path(), json=data, headers=headers(data)).status_code == 422
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 3


def test_context_refuses_stored_identity_inconsistency(harness):
    client, db = harness
    db.transition(
        ANOMALY,
        "inconclusive",
        expected_version=3,
        patch={"field_id": "another_field"},
        tenant_id=TENANT,
    )
    response = client.get(path("verification-context"), headers=headers(method="GET"))
    assert response.status_code == 503
    assert response.json()["detail"] == "verification_anomaly_scope_inconsistent"


def test_pending_reservation_does_not_accept_a_completion(harness):
    client, db = harness
    other = "urn:sahool:anomaly:pending"
    db.upsert_detected(
        {
            "anomaly_ref": other,
            "tenant_id": TENANT,
            "field_id": "fld_verification",
            "season_id": "season_verification",
        }
    )
    db.reserve_verification(
        other, expected_version=1, idempotency_key="pending-key", tenant_id=TENANT
    )
    data = body(expected_version=2)
    response = client.post(
        path(ref=other), json=data, headers=headers(data, target=path(ref=other))
    )
    assert response.status_code == 409
    assert db.get(other, tenant_id=TENANT)["aggregate_version"] == 2


@pytest.mark.parametrize("resolution_codes", [[], ["RESOLVED_WITHOUT_INTERVENTION"]])
def test_exact_replay_remains_a_receipt_after_a_later_owner_transition(harness, resolution_codes):
    client, db = harness
    data = body()
    accepted = client.post(path(), json=data, headers=headers(data)).json()
    db.transition(
        ANOMALY,
        "resolved",
        expected_version=4,
        tenant_id=TENANT,
        patch={"disposition_reason_codes": resolution_codes},
    )
    replay = client.post(path(), json=data, headers=headers(data))
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["verification_delivery"] == accepted["verification_delivery"]
    assert replay.json()["anomaly"]["status"] == "resolved"
    assert replay.json()["anomaly"]["payload"]["disposition_reason_codes"] == resolution_codes
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 5


def test_two_simultaneous_http_deliveries_commit_only_once(harness):
    client, db = harness
    data = body()
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(lambda _: client.post(path(), json=data, headers=headers(data)), range(2))
        )
    assert [r.status_code for r in replies] == [200, 200]
    assert sorted(r.json()["replayed"] for r in replies) == [False, True]
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 4


@pytest.mark.parametrize(
    "changes",
    [
        {"original_completion": None},
        {"request_digest": "0" * 64},
        {"idempotency_key": "bad"},
        {"expected_version": True},
        {"accepted_version": "4"},
        {"request_snapshot_digest": "invalid"},
    ],
)
def test_context_refuses_a_corrupted_historical_delivery_receipt(harness, changes):
    client, db = harness
    data = body()
    accepted = client.post(path(), json=data, headers=headers(data))
    receipt = {**accepted.json()["verification_delivery"], **changes}
    db.transition(
        ANOMALY,
        "resolved",
        expected_version=4,
        tenant_id=TENANT,
        patch={"verification_delivery": receipt, "disposition_reason_codes": ["RESOLVED"]},
    )
    response = client.get(path("verification-context"), headers=headers(method="GET"))
    assert response.status_code == 503
    assert "verification_delivery_receipt" in response.json()["detail"]
    assert client.post(path(), json=data, headers=headers(data)).status_code == 503
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 5


def test_context_refuses_metadata_corruption_at_the_accepted_version(harness):
    client, db = harness
    data = body()
    assert client.post(path(), json=data, headers=headers(data)).status_code == 200
    corrupted = db.get(ANOMALY, tenant_id=TENANT)["payload"]
    corrupted["disposition_reason_codes"] = ["CHANGED_WITHOUT_A_VERSION"]
    # Inject a local storage fault without a legitimate owner transition/version.
    with sqlite3.connect(db.path) as conn:
        conn.execute(
            "UPDATE signal_anomalies SET payload_json=? WHERE anomaly_ref=?",
            (json.dumps(corrupted), ANOMALY),
        )
    response = client.get(path("verification-context"), headers=headers(method="GET"))
    assert response.status_code == 503
    assert response.json()["detail"] == "verification_delivery_receipt_inconsistent"


def test_canonical_bytes_preserve_arrays_and_expected_version_but_normalize_offsets():
    data = body(evidence=[evidence()], evidence_refs=[evidence()["evidence_ref"]])
    original = copy.deepcopy(data)
    equivalent = copy.deepcopy(data)
    equivalent["completed_at"] = "2026-03-31T15:00:00+03:00"
    equivalent["evidence"][0]["captured_at"] = "2026-03-31T14:00:00+03:00"
    assert canonical_completion_digest(equivalent) == canonical_completion_digest(data)
    assert data == original
    assert canonical_completion_digest(body(expected_version=2)) != canonical_completion_digest(
        body()
    )
    assert canonical_completion_digest(
        body(reason_codes=["a", "b"])
    ) != canonical_completion_digest(body(reason_codes=["b", "a"]))
    minimal = {
        k: v for k, v in body().items() if k not in {"evidence", "evidence_refs", "reason_codes"}
    }
    assert canonical_completion_payload(minimal)["reason_codes"] == []
    wire = VerificationCompletion.model_validate(data).model_dump(mode="json")
    assert canonical_completion_digest(wire) == canonical_completion_digest(data)
    assert canonical_completion_payload(data)["evidence"][0]["quality_grade"] is None
    graded = copy.deepcopy(data)
    graded["evidence"][0]["quality_grade"] = "reviewed"
    assert canonical_completion_digest(graded) != canonical_completion_digest(data)
    with pytest.raises(ValueError):
        canonical_completion_digest({**body(), "extra": 1})


def test_equivalent_timezone_replay_uses_the_same_durable_receipt(harness):
    client, db = harness
    data = body()
    first = client.post(path(), json=data, headers=headers(data))
    data["completed_at"] = "2026-03-31T15:00:00+03:00"
    second = client.post(path(), json=data, headers=headers(data))
    assert first.status_code == second.status_code == 200
    assert first.json()["verification_delivery"] == second.json()["verification_delivery"]
    assert second.json()["replayed"] is True
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 4


@pytest.mark.asyncio
async def test_actual_field_owner_sender_and_receiver_share_the_wire_contract(harness, monkeypatch):
    client, db = harness
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[1] / "field-management-service")
    )
    sender = importlib.import_module("fm_verification_client")
    monkeypatch.setenv("VEGETATION_VERIFICATION_URL", "http://vegetation.test")
    data = body(
        verification_result="confirmed",
        evidence=[evidence()],
        evidence_refs=[evidence()["evidence_ref"]],
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app)) as transport:
        owner_client = sender.VegetationVerificationClient(transport)
        context = await owner_client.context(TENANT, ANOMALY)
        assert context["anomaly"]["aggregate_version"] == 3
        first = await owner_client.complete(TENANT, ANOMALY, data, KEY)
        replay = await owner_client.complete(TENANT, ANOMALY, data, KEY)
    assert first["replayed"] is False and replay["replayed"] is True
    assert first["verification_delivery"]["request_snapshot_digest"] == context["snapshot_digest"]
    assert first["verification_delivery"] == replay["verification_delivery"]
    assert db.get(ANOMALY, tenant_id=TENANT)["aggregate_version"] == 4
