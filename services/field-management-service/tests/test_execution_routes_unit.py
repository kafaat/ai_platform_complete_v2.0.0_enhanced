"""Actual ASGI owner routing/auth with explicit store doubles.

These are transport/permission contracts, not PostgreSQL or runtime acceptance.
The native owner-store suite supplies the separate database evidence.
"""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
for directory in (SERVICE_DIR, SERVICE_DIR.parents[1]):
    if str(directory) not in sys.path:
        sys.path.append(str(directory))

import fm_execution_routes as routes  # noqa: E402
from fm_execution_tasks import binding_from_source  # noqa: E402
from fm_gateway import Caller  # noqa: E402

pytestmark = pytest.mark.unit
TENANT = "11111111-1111-4111-8111-111111111111"
PEER = "22222222-2222-4222-8222-222222222222"
FIELD = "field-inspection-unit"
REQUEST = "exec_unit"
ADAPTER = "field-management-service-inspection-v1"
ACTOR = Caller(TENANT, "9", "owner")
PREFIX = "/internal/field-inspection-execution-owner/"
PROOF = "/internal/field-tasks/execution-proofs/" + REQUEST
COORDINATOR = {
    "X-Field-Inspection-Coordinator-Token": "unit-coordinator-only-credential",
    "X-Service-Name": "sahool-platform",
    "X-Tenant-Id": TENANT,
    "X-User-Id": "9",
    "X-User-Role": "owner",
}
S2S = {"X-Field-Inspection-Proof-Token": "unit-independent-proof", "X-Tenant-Id": TENANT}
INSPECTION = {
    "pin_id": "pin_unit",
    "assigned_to": 6,
    "due_at": "2026-11-28T12:00:00+00:00",
    "priority": 3,
}
SOURCE = {
    "item": {
        "execution_request_id": REQUEST,
        "decision_id": "dec_unit",
        "execution_plan_id": "plan_unit",
        "dispatch_authorization_id": "auth_unit",
        "target_type": "task",
        "target_id": "pin_unit",
        "operation_type": "field_inspection",
        "command_payload": {"field_id": FIELD, "inspection": dict(INSPECTION)},
    },
    "lineage": {
        "authoritative": True,
        "tenant_id": TENANT,
        "decision_id": "dec_unit",
        "decision": {
            "decision_id": "dec_unit",
            "field_id": FIELD,
            "correlation_id": "44444444-4444-4444-8444-444444444444",
        },
    },
    "plan": {
        "authoritative": True,
        "tenant_id": TENANT,
        "execution_plan_id": "plan_unit",
        "decision_id": "dec_unit",
        "field_id": FIELD,
        "operation_type": "field_inspection",
        "plan_state": "planned",
        "bound": True,
        "review_state": "approved",
        "plan_digest": "b" * 64,
        "decision_value_digest": "c" * 64,
        "current_decision_value_digest": "c" * 64,
        "target_zone_ids": [FIELD],
        "constraints": {"field_id": FIELD, "inspection": dict(INSPECTION)},
    },
}
BINDING = binding_from_source(
    ACTOR, SOURCE["item"], SOURCE["lineage"], SOURCE["plan"], FIELD, ADAPTER
)
LINK = asdict(BINDING) | {"receipt_payload": BINDING.receipt_payload()}
TASK = BINDING.task_id
CONFIRMATION = "fic_" + "a" * 32
RESULT = {
    "accepted": True,
    "tenant_id": TENANT,
    "status": "ok",
    "replay": False,
    "authoritative": True,
    "persisted": True,
    "outcome_id": "out_unit",
    "execution_request_id": REQUEST,
    "execution_plan_id": "plan_unit",
    "dispatch_authorization_id": "auth_unit",
    "decision_id": "dec_unit",
    "receipt_id": BINDING.receipt_id,
    "verification_state": "verified_success",
    "evidence_snapshot_id": "inspection_" + "a" * 64,
    "success": True,
    "verified_by": "9",
    "verified_at": "2026-11-27T18:00:00+00:00",
}
ACK = {
    "tenant_id": TENANT,
    "confirmation_id": CONFIRMATION,
    "execution_request_id": REQUEST,
    "task_id": TASK,
    "field_id": FIELD,
    "outcome_id": "out_unit",
    "upstream_result": RESULT,
}
CLAIM = {
    "authoritative": True,
    "persisted": True,
    "execution_request_id": REQUEST,
    "adapter_id": ADAPTER,
    "adapter_kind": "task",
    "delivery_state": "delivering",
}
OPERATIONS = tuple(routes._COMMAND_MODELS)


def command(operation):
    bodies = {
        "require-field": {"field_id": FIELD},
        "get-link": {"execution_request_id": REQUEST},
        "list-links": {"field_id": FIELD, "limit": 17},
        "validate-binding": {
            "field_id": FIELD,
            "execution_request_id": REQUEST,
            "source": SOURCE,
        },
        "ensure-task": {
            "field_id": FIELD,
            "execution_request_id": REQUEST,
            "source": SOURCE,
            "claim": CLAIM,
        },
        "readback": {"field_id": FIELD, "execution_request_id": REQUEST},
        "preview-confirmation": {"execution_request_id": REQUEST},
        "prepare-confirmation": {"field_id": FIELD, "task_id": TASK},
        "save-outcome": {
            "execution_request_id": REQUEST,
            "confirmation_id": CONFIRMATION,
            "result": RESULT,
        },
    }
    return deepcopy(bodies[operation])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        "FIELD_INSPECTION_COORDINATOR_TOKEN", COORDINATOR["X-Field-Inspection-Coordinator-Token"]
    )
    monkeypatch.setenv("FIELD_INSPECTION_PROOF_TOKEN", S2S["X-Field-Inspection-Proof-Token"])
    monkeypatch.setenv("FIELD_INSPECTION_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("FIELD_INSPECTION_EXECUTION_ADAPTER_ID", ADAPTER)
    monkeypatch.delenv("FIELD_INSPECTION_DELIVERY_TOKEN_KEY", raising=False)
    monkeypatch.delenv("DECISION_SERVICE_URL", raising=False)
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as http:
        yield http


@pytest.fixture
def store(monkeypatch):
    proof = {
        "schema": "sahool.field-inspection-execution-proof/v1",
        "tenant_id": TENANT,
        "execution_request_id": REQUEST,
        "reviewer_id": "9",
        "current": True,
        "observed_at": "2026-11-27T18:00:00Z",
    }
    owner = SimpleNamespace(
        require_field=AsyncMock(return_value=None),
        get_link=AsyncMock(return_value=deepcopy(LINK)),
        list_links=AsyncMock(return_value=[deepcopy(LINK)]),
        validate=AsyncMock(return_value="Synthetic inspector"),
        ensure_task=AsyncMock(return_value=deepcopy(LINK)),
        readback=AsyncMock(return_value=deepcopy(LINK)),
        preview_confirmation=AsyncMock(return_value=deepcopy(proof)),
        prepare_confirmation=AsyncMock(return_value=deepcopy(proof)),
        save_outcome=AsyncMock(return_value=deepcopy(ACK)),
        read_execution_proof=AsyncMock(return_value=deepcopy(proof)),
    )
    owner.builder = Mock(return_value=owner)
    monkeypatch.setattr(routes, "PostgresExecutionStore", owner.builder)
    return owner


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        ({"Authorization": "Bearer user-jwt"}, 401),
        (S2S, 401),
        (COORDINATOR | {"X-Field-Inspection-Coordinator-Token": "wrong"}, 401),
        ({k: v for k, v in COORDINATOR.items() if k != "X-Service-Name"}, 403),
        (COORDINATOR | {"X-Service-Name": "decision-service"}, 403),
        (COORDINATOR | {"X-Field-Tasks-Token": ""}, 403),
        (COORDINATOR | {"X-Field-Tasks-Token": "human-gateway"}, 403),
        (COORDINATOR | {"X-Tenant-Id": "not-a-uuid"}, 403),
        (COORDINATOR | {"X-User-Id": ""}, 403),
        (COORDINATOR | {"X-User-Id": "-1"}, 403),
        (COORDINATOR | {"X-User-Id": "2147483648"}, 403),
        (COORDINATOR | {"X-User-Role": "unrecognized"}, 403),
    ],
)
def test_coordinator_channel_rejects_wrong_audience_and_identity_before_store(
    client, store, headers, status
):
    response = client.post(PREFIX + "require-field", headers=headers, json={})
    assert response.status_code == status
    store.builder.assert_not_called()


@pytest.mark.parametrize("operation", OPERATIONS)
def test_default_off_blocks_every_owner_operation(client, store, monkeypatch, operation):
    monkeypatch.delenv("FIELD_INSPECTION_EXECUTION_ENABLED", raising=False)
    response = client.post(PREFIX + operation, headers=COORDINATOR, json=command(operation))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "field_inspection_execution_disabled"
    store.builder.assert_not_called()


def test_unconfigured_coordinator_is_not_shared_agent_fallback(client, store, monkeypatch):
    monkeypatch.delenv("FIELD_INSPECTION_COORDINATOR_TOKEN")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "unrelated-shared-secret")
    response = client.post(PREFIX + "require-field", headers=COORDINATOR, json={"field_id": FIELD})
    assert response.status_code == 503
    store.builder.assert_not_called()


@pytest.mark.parametrize(
    "operation",
    [
        "validate-binding",
        "ensure-task",
        "preview-confirmation",
        "prepare-confirmation",
        "save-outcome",
    ],
)
@pytest.mark.parametrize("role", ["worker", "viewer", "agronomist", "expert"])
def test_non_operators_cannot_cross_the_decision_execute_boundary(client, store, operation, role):
    response = client.post(
        PREFIX + operation, headers=COORDINATOR | {"X-User-Role": role}, json=command(operation)
    )
    assert response.status_code == 403
    store.builder.assert_not_called()


@pytest.mark.parametrize(
    "role,canonical", [("owner", "owner"), ("admin", "owner"), ("manager", "manager")]
)
def test_owner_actor_is_derived_from_trusted_headers_and_canonical_role(
    client, store, role, canonical
):
    response = client.post(
        PREFIX + "require-field",
        headers=COORDINATOR | {"X-User-Role": role},
        json={"field_id": FIELD},
    )
    assert response.status_code == 200
    store.require_field.assert_awaited_once_with(Caller(TENANT, "9", canonical), FIELD)


def test_store_current_account_refusal_is_preserved(client, store):
    store.require_field.side_effect = HTTPException(
        403, {"code": "current_account_permission_required"}
    )
    response = client.post(PREFIX + "require-field", headers=COORDINATOR, json={"field_id": FIELD})
    assert response.status_code == 403 and "data" not in response.json()


@pytest.mark.parametrize("operation", OPERATIONS)
def test_closed_body_forbids_cross_tenant_or_free_dispatch_fields(client, store, operation):
    body = command(operation) | {"tenant_id": PEER, "method": "delete", "proof": {}}
    response = client.post(PREFIX + operation, headers=COORDINATOR, json=body)
    assert response.status_code == 422
    store.builder.assert_not_called()


@pytest.mark.parametrize("operation", ["delete", "__getattribute__", "save_outcome"])
def test_unknown_operation_never_dispatches_to_store(client, store, operation):
    assert client.post(PREFIX + operation, headers=COORDINATOR, json={}).status_code == 422
    store.builder.assert_not_called()


@pytest.mark.parametrize("limit", [True, "17", 0, 101])
def test_list_limit_is_a_strict_bounded_integer(client, store, limit):
    assert (
        client.post(
            PREFIX + "list-links", headers=COORDINATOR, json={"field_id": FIELD, "limit": limit}
        ).status_code
        == 422
    )
    store.builder.assert_not_called()


@pytest.mark.parametrize("operation", OPERATIONS)
def test_each_declared_owner_operation_returns_bound_envelope_without_outbound_client(
    client, store, operation
):
    response = client.post(PREFIX + operation, headers=COORDINATOR, json=command(operation))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"schema", "authoritative", "tenant_id", "operation", "data"}
    assert body["schema"] == "sahool.field-inspection-owner/v1"
    assert body["authoritative"] is True and body["tenant_id"] == TENANT
    assert body["operation"] == operation
    assert response.headers["cache-control"] == "no-store"
    assert "delivery_token" not in response.text
    if operation == "validate-binding":
        call = store.validate.await_args
        assert call.args[0] == ACTOR
        rebuilt = call.args[1]
        assert rebuilt.received_by == "9" and rebuilt.tenant_id == TENANT
        assert rebuilt.execution_request_id == REQUEST and rebuilt.task_id == TASK
        assert rebuilt.receipt_payload() == BINDING.receipt_payload()
        assert body["data"] == "Synthetic inspector"
    elif operation == "ensure-task":
        store.ensure_task.assert_awaited_once()
        assert store.ensure_task.await_args.args[1].request_digest == BINDING.request_digest
    elif operation == "readback":
        store.get_link.assert_awaited_once_with(ACTOR, REQUEST)
        store.readback.assert_awaited_once_with(ACTOR, BINDING)
    elif operation == "preview-confirmation":
        store.preview_confirmation.assert_awaited_once_with(ACTOR, LINK)
    elif operation == "prepare-confirmation":
        store.prepare_confirmation.assert_awaited_once_with(ACTOR, TASK, FIELD)
    elif operation == "list-links":
        store.require_field.assert_awaited_once_with(ACTOR, FIELD)
        store.list_links.assert_awaited_once_with(ACTOR, FIELD, 17)


@pytest.mark.parametrize("operation", ["validate-binding", "ensure-task"])
def test_preconstructed_binding_is_not_accepted_instead_of_source(client, store, operation):
    body = command(operation)
    body.pop("source")
    body["binding"] = LINK | {"request_digest": "f" * 64}
    assert client.post(PREFIX + operation, headers=COORDINATOR, json=body).status_code == 422
    store.builder.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        "request",
        "tenant",
        "plan-review",
        "plan-digest",
        "plan-field",
        "assignment",
        "pin",
        "envelope-extra",
    ],
)
def test_source_binding_is_recomputed_and_rejects_tampered_lineage(client, store, change):
    body = command("validate-binding")
    if change == "request":
        body["execution_request_id"] = "exec_other"
    elif change == "tenant":
        body["source"]["lineage"]["tenant_id"] = PEER
    elif change == "plan-review":
        body["source"]["plan"]["review_state"] = "pending"
    elif change == "plan-digest":
        body["source"]["plan"]["current_decision_value_digest"] = "f" * 64
    elif change == "plan-field":
        body["source"]["plan"]["field_id"] = "another-field"
    elif change == "assignment":
        body["source"]["item"]["command_payload"]["inspection"]["assigned_to"] = 7
    elif change == "pin":
        body["source"]["item"]["target_id"] = "another-pin"
    else:
        body["source"]["actor"] = {"user_id": "other"}
    response = client.post(PREFIX + "validate-binding", headers=COORDINATOR, json=body)
    assert response.status_code in {409, 422, 503}
    store.validate.assert_not_awaited()


@pytest.mark.parametrize(
    "key,value",
    [
        ("authoritative", False),
        ("persisted", False),
        ("execution_request_id", "exec_other"),
        ("adapter_id", "other-adapter"),
        ("adapter_kind", "equipment"),
        ("delivery_state", "accepted"),
        ("persisted", 1),
        ("delivery_token", "must-not-cross"),
    ],
)
def test_ensure_requires_the_exact_task_claim_before_any_insert(client, store, key, value):
    body = command("ensure-task")
    body["claim"][key] = value
    response = client.post(PREFIX + "ensure-task", headers=COORDINATOR, json=body)
    assert response.status_code in {409, 422}
    store.ensure_task.assert_not_awaited()


def test_get_link_missing_is_explicit_null_not_a_synthetic_link(client, store):
    store.get_link.return_value = None
    response = client.post(
        PREFIX + "get-link", headers=COORDINATOR, json={"execution_request_id": REQUEST}
    )
    assert response.status_code == 200 and response.json()["data"] is None


@pytest.mark.parametrize("operation", ["readback", "preview-confirmation", "save-outcome"])
def test_owner_link_scope_is_checked_before_followup_action(client, store, operation):
    store.get_link.return_value = LINK | {"tenant_id": PEER}
    assert (
        client.post(PREFIX + operation, headers=COORDINATOR, json=command(operation)).status_code
        == 503
    )
    store.readback.assert_not_awaited()
    store.preview_confirmation.assert_not_awaited()
    store.save_outcome.assert_not_awaited()


def test_readback_rejects_different_field_before_owner_readback(client, store):
    body = command("readback") | {"field_id": "peer-field"}
    assert client.post(PREFIX + "readback", headers=COORDINATOR, json=body).status_code == 404
    store.readback.assert_not_awaited()


@pytest.mark.parametrize(
    "key,value",
    [
        ("tenant_id", PEER),
        ("execution_request_id", "exec_other"),
        ("execution_plan_id", "plan_other"),
        ("dispatch_authorization_id", "auth_other"),
        ("decision_id", "dec_other"),
        ("receipt_id", "receipt_other"),
        ("verified_by", "6"),
        ("evidence_snapshot_id", "inspection_" + "b" * 64),
        ("authoritative", False),
        ("persisted", False),
        ("success", False),
        ("accepted", False),
        ("status", "conflict"),
        ("verification_state", "verified_failed"),
        ("actual", {"approved": True}),
        ("delivery_token", "must-not-be-stored"),
        ("verified_at", "2026-11-27T18:00:00"),
        ("persisted", 1),
    ],
)
def test_ack_refuses_unproven_or_mismatched_source_result(client, store, key, value):
    body = command("save-outcome")
    body["result"][key] = value
    response = client.post(PREFIX + "save-outcome", headers=COORDINATOR, json=body)
    assert response.status_code in {409, 422}
    store.save_outcome.assert_not_awaited()


def test_historical_ack_uses_owner_link_ids_and_never_rechecks_current_proof(client, store):
    store.read_execution_proof.side_effect = HTTPException(409, "current photo changed")
    store.prepare_confirmation.side_effect = AssertionError(
        "must not prepare new proof for historical ack"
    )
    response = client.post(
        PREFIX + "save-outcome", headers=COORDINATOR, json=command("save-outcome")
    )
    assert response.status_code == 200
    expected = {
        "confirmation_id": CONFIRMATION,
        "execution_request_id": REQUEST,
        "task_id": TASK,
        "field_id": FIELD,
    }
    store.save_outcome.assert_awaited_once_with(ACTOR, expected, RESULT)
    store.read_execution_proof.assert_not_awaited()
    store.prepare_confirmation.assert_not_awaited()


def test_ack_replay_may_change_only_replay_metadata_and_equivalent_utc_spelling(client, store):
    body = command("save-outcome")
    body["result"].update(replay=True, verified_at="2026-11-27T18:00:00Z")
    assert client.post(PREFIX + "save-outcome", headers=COORDINATOR, json=body).status_code == 200


@pytest.mark.parametrize("kind", ["confirmation", "task", "outcome", "recorded-result"])
def test_ack_never_reports_success_for_mismatched_saved_receipt(client, store, kind):
    saved = deepcopy(ACK)
    if kind == "confirmation":
        saved["confirmation_id"] = "fic_" + "f" * 32
    elif kind == "task":
        saved["task_id"] = "55555555-5555-4555-8555-555555555555"
    elif kind == "outcome":
        saved["outcome_id"] = "out_other"
    else:
        saved["upstream_result"]["evidence_snapshot_id"] = "inspection_" + "f" * 64
    store.save_outcome.return_value = saved
    assert (
        client.post(
            PREFIX + "save-outcome", headers=COORDINATOR, json=command("save-outcome")
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Authorization": "Bearer user-jwt", "X-Tenant-Id": TENANT}, 401),
        (COORDINATOR, 401),
        (S2S | {"X-Field-Tasks-Token": ""}, 403),
        (S2S | {"X-Field-Inspection-Proof-Token": "wrong"}, 401),
        (S2S | {"X-Tenant-Id": "not-a-uuid"}, 400),
    ],
)
def test_proof_keeps_its_separate_read_only_service_audience(client, store, headers, status):
    assert client.get(PROOF, headers=headers).status_code == status
    store.builder.assert_not_called()


def test_proof_still_reads_owner_without_coordinator_or_delivery_key(client, store, monkeypatch):
    monkeypatch.delenv("FIELD_INSPECTION_COORDINATOR_TOKEN")
    response = client.get(PROOF, headers=S2S)
    assert response.status_code == 200 and response.json()["current"] is True
    assert response.headers["cache-control"] == "no-store"
    store.read_execution_proof.assert_awaited_once_with(TENANT, REQUEST)
    store.get_link.assert_not_awaited()


@pytest.mark.parametrize(
    "variable", ["FIELD_INSPECTION_PROOF_TOKEN", "FIELD_INSPECTION_EXECUTION_ENABLED"]
)
def test_proof_still_fails_closed_when_disabled_or_unconfigured(
    client, store, monkeypatch, variable
):
    monkeypatch.delenv(variable)
    assert client.get(PROOF, headers=S2S).status_code == 503
    store.builder.assert_not_called()


def test_proof_owner_conflict_is_never_converted_to_success(client, store):
    store.read_execution_proof.side_effect = HTTPException(
        409, {"code": "current_inspection_confirmation_mismatch"}
    )
    response = client.get(PROOF, headers=S2S)
    assert response.status_code == 409 and "current" not in response.json()


def test_composition_has_only_private_owner_rpc_and_existing_proof_no_old_orchestrator_routes():
    spec = importlib.util.spec_from_file_location(
        "field_execution_routes_composition", SERVICE_DIR / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    published = {
        (method, route.path)
        for route in module.app.routes
        for method in getattr(route, "methods", ())
    }
    assert ("POST", "/internal/field-inspection-execution-owner/{operation}") in published
    assert ("GET", "/internal/field-tasks/execution-proofs/{execution_request_id}") in published
    assert not any(
        "/inspection-executions" in path or path.endswith("/verify-execution")
        for _, path in published
    )
