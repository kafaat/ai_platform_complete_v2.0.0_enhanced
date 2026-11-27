"""Owner HTTP port contracts through httpx.MockTransport; no real HTTP or DB.

The coordinator module is loaded independently so these transport tests do not
import api.main or share another service's api namespace during collection.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

_MODULE_PATH = Path(__file__).resolve().parents[1] / "api/inspection_execution_adapter.py"
_SPEC = importlib.util.spec_from_file_location(
    "inspection_owner_client_contract_tests", _MODULE_PATH
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)

pytestmark = pytest.mark.unit
TENANT = "11111111-1111-4111-8111-111111111111"
PEER = "22222222-2222-4222-8222-222222222222"
FIELD = "field-owner-client-fixture"
REQUEST = "request-owner-client-fixture"
COORDINATOR_TOKEN = "synthetic-coordinator-token"
PROOF_TOKEN = "synthetic-independent-proof-token"
RAW_DELIVERY_TOKEN = "synthetic-raw-delivery-token-must-not-reach-owner"
UPSTREAM_PRIVATE = "synthetic-upstream-private-body"


@dataclass(frozen=True)
class Identity:
    tenant_id: str = TENANT
    user_id: str = "9"
    role: str = "owner"

    def can(self, permission):
        return permission in {"field:view", "field:edit", "inspection:review"}


CALLER = Identity()


def _source():
    inspection = {
        "pin_id": "pin-owner-client-fixture",
        "assigned_to": 7,
        "due_at": "2026-11-27T18:00:00+00:00",
        "priority": 3,
    }
    item = {
        "execution_request_id": REQUEST,
        "decision_id": "decision-fixture",
        "execution_plan_id": "plan-fixture",
        "dispatch_authorization_id": "authorization-fixture",
        "target_type": "task",
        "target_id": inspection["pin_id"],
        "operation_type": "field_inspection",
        "command_payload": {"field_id": FIELD, "inspection": copy.deepcopy(inspection)},
    }
    lineage = {
        "authoritative": True,
        "tenant_id": TENANT,
        "decision_id": item["decision_id"],
        "decision": {
            "decision_id": item["decision_id"],
            "field_id": FIELD,
            "correlation_id": "33333333-3333-4333-8333-333333333333",
        },
    }
    plan = {
        "authoritative": True,
        "tenant_id": TENANT,
        "execution_plan_id": item["execution_plan_id"],
        "decision_id": item["decision_id"],
        "field_id": FIELD,
        "operation_type": "field_inspection",
        "plan_state": "planned",
        "bound": True,
        "review_state": "approved",
        "plan_digest": "a" * 64,
        "decision_value_digest": "b" * 64,
        "current_decision_value_digest": "b" * 64,
        "target_zone_ids": [FIELD],
        "constraints": {"field_id": FIELD, "inspection": copy.deepcopy(inspection)},
    }
    return item, lineage, plan


def _binding():
    return mod.binding_from_source(
        CALLER, *_source(), FIELD, "field-management-service-inspection-v1"
    )


def _claim(binding):
    return {
        "authoritative": True,
        "persisted": True,
        "execution_request_id": binding.execution_request_id,
        "adapter_id": binding.adapter_id,
        "adapter_kind": "task",
        "delivery_state": "delivering",
    }


def _proof(binding):
    # Scope projection only. Proof authenticity/freshness is a separate DS/owner contract.
    return {
        "tenant_id": TENANT,
        "execution_request_id": REQUEST,
        "task_id": binding.task_id,
        "field_id": FIELD,
        "confirmation_id": "fic_" + "c" * 32,
        "actual": {"owner_only_finding": "must not be sent in acknowledgement"},
        "metrics": {"inspection_approved": True},
    }


def _result(binding):
    return {
        "status": "ok",
        "authoritative": True,
        "persisted": True,
        "outcome_id": "outcome-fixture",
        "execution_request_id": REQUEST,
        "execution_plan_id": binding.execution_plan_id,
        "dispatch_authorization_id": binding.dispatch_authorization_id,
        "decision_id": binding.decision_id,
        "receipt_id": binding.receipt_id,
        "verification_state": "verified_success",
        "success": True,
        "evidence_snapshot_id": "inspection_" + "c" * 64,
        "verified_by": CALLER.user_id,
        "verified_at": "2026-11-27T18:01:00+00:00",
    }


def _envelope(operation, data, **changes):
    return {
        "schema": mod.HttpOwnerStore.SCHEMA,
        "authoritative": True,
        "tenant_id": TENANT,
        "operation": operation,
        "data": data,
    } | changes


@pytest.fixture
def transport(monkeypatch):
    binding = _binding()
    proof, result = _proof(binding), _result(binding)
    ack = {
        key: proof[key]
        for key in ("tenant_id", "execution_request_id", "task_id", "field_id", "confirmation_id")
    } | {"outcome_id": result["outcome_id"], "upstream_result": copy.deepcopy(result)}
    state = SimpleNamespace(
        requests=[],
        client_options=[],
        binding=binding,
        proof=proof,
        result=result,
        ack=ack,
        data={
            "require-field": None,
            "get-link": None,
            "list-links": [],
            "validate-binding": "Fixture inspector",
            "ensure-task": asdict(binding),
            "readback": asdict(binding),
            "preview-confirmation": proof,
            "prepare-confirmation": proof,
            "save-outcome": ack,
        },
    )

    def owner_reply(request):
        operation = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_envelope(operation, state.data[operation]))

    state.responder = owner_reply

    def handle(request):
        state.requests.append(request)
        return state.responder(request)

    real_client = httpx.AsyncClient
    mock_transport = httpx.MockTransport(handle)

    def client(**kwargs):
        state.client_options.append(dict(kwargs))
        return real_client(transport=mock_transport, **kwargs)

    monkeypatch.setattr(mod.httpx, "AsyncClient", client)
    state.store = mod.HttpOwnerStore("http://owner.test", COORDINATOR_TOKEN)
    return state


def _run(awaitable):
    return asyncio.run(awaitable)


def _assert_refused(awaitable, code, status=503):
    with pytest.raises(HTTPException) as caught:
        _run(awaitable)
    assert caught.value.status_code == status
    assert caught.value.detail == {"code": code}
    assert UPSTREAM_PRIVATE not in str(caught.value)
    assert COORDINATOR_TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "owner.test",
        "ftp://owner.test",
        "http:///missing-host",
        "http://user:password@owner.test",
        "http://owner.test?token=private",
        "http://owner.test#private",
        "http://owner.test:invalid",
        "http://[broken",
    ],
)
def test_invalid_owner_url_is_rejected_without_echoing_configuration(url):
    with pytest.raises(HTTPException) as caught:
        mod.HttpOwnerStore(url, COORDINATOR_TOKEN)
    assert caught.value.status_code == 503
    assert caught.value.detail == {"code": "inspection_owner_url_unconfigured"}


@pytest.mark.parametrize("token", ["", " ", "\t"])
def test_blank_coordinator_credential_is_rejected(token):
    with pytest.raises(HTTPException) as caught:
        mod.HttpOwnerStore("https://owner.test", token)
    assert caught.value.detail == {"code": "inspection_coordinator_token_unconfigured"}


def test_proof_token_cannot_replace_missing_coordinator_credential(monkeypatch):
    monkeypatch.delenv("FIELD_INSPECTION_COORDINATOR_TOKEN", raising=False)
    monkeypatch.setenv("FIELD_INSPECTION_PROOF_TOKEN", PROOF_TOKEN)
    with pytest.raises(HTTPException) as caught:
        mod.HttpOwnerStore.from_env()
    assert caught.value.detail == {"code": "inspection_coordinator_token_unconfigured"}


def test_http_channel_uses_only_configured_coordinator_and_caller_identity(transport, monkeypatch):
    monkeypatch.setenv("FIELD_MANAGEMENT_SERVICE_URL", "https://owner.test/")
    monkeypatch.setenv("FIELD_INSPECTION_COORDINATOR_TOKEN", COORDINATOR_TOKEN)
    monkeypatch.setenv("FIELD_INSPECTION_PROOF_TOKEN", PROOF_TOKEN)
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "synthetic-decision-token")
    monkeypatch.setenv("FIELD_TASKS_SERVICE_TOKEN", "synthetic-gateway-token")
    store = mod.HttpOwnerStore.from_env()
    assert _run(store.require_field(CALLER, FIELD)) is None
    [request] = transport.requests
    assert request.method == "POST"
    assert str(request.url) == "https://owner.test" + store.PREFIX + "require-field"
    assert json.loads(request.content) == {"field_id": FIELD}
    assert request.headers["X-Field-Inspection-Coordinator-Token"] == COORDINATOR_TOKEN
    assert request.headers["X-Service-Name"] == "sahool-platform"
    assert request.headers["X-Tenant-Id"] == CALLER.tenant_id
    assert request.headers["X-User-Id"] == CALLER.user_id
    assert request.headers["X-User-Role"] == CALLER.role
    for forbidden in ("Authorization", "X-Field-Inspection-Proof-Token", "X-Field-Tasks-Token"):
        assert forbidden not in request.headers
    assert transport.client_options == [
        {"timeout": 8.0, "trust_env": False, "follow_redirects": False}
    ]


@pytest.mark.parametrize(
    "caller",
    [
        Identity(tenant_id=""),
        Identity(tenant_id=PEER.replace("-", "")),
        Identity(user_id=""),
        Identity(user_id="-1"),
        Identity(user_id="human-name"),
    ],
)
def test_invalid_trusted_identity_is_rejected_before_transport(transport, caller):
    _assert_refused(
        transport.store.require_field(caller, FIELD), "inspection_owner_identity_invalid"
    )
    assert transport.requests == []


def test_unsupported_operation_cannot_create_an_arbitrary_owner_path(transport):
    _assert_refused(
        transport.store._request(CALLER, "../execution-proofs", {}),
        "inspection_owner_operation_unsupported",
        422,
    )
    assert transport.requests == []


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "wrong-schema"},
        {"schema": None},
        {"authoritative": False},
        {"authoritative": 1},
        {"authoritative": "true"},
        {"tenant_id": PEER},
        {"tenant_id": None},
        {"operation": "ensure-task"},
    ],
)
def test_owner_envelope_must_be_exactly_scoped(transport, change):
    transport.responder = lambda request: httpx.Response(
        200, json=_envelope("require-field", None) | change
    )
    _assert_refused(
        transport.store.require_field(CALLER, FIELD), "inspection_owner_invalid_response"
    )


@pytest.mark.parametrize(
    "payload", [None, [], "untrusted", {"schema": "sahool.field-inspection-owner/v1"}]
)
def test_non_envelope_owner_json_is_rejected(transport, payload):
    transport.responder = lambda request: httpx.Response(200, json=payload)
    _assert_refused(
        transport.store.require_field(CALLER, FIELD), "inspection_owner_invalid_response"
    )


def test_missing_data_is_not_treated_as_null_success(transport):
    payload = _envelope("require-field", None)
    del payload["data"]
    transport.responder = lambda request: httpx.Response(200, json=payload)
    _assert_refused(
        transport.store.require_field(CALLER, FIELD), "inspection_owner_invalid_response"
    )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 500, 503])
def test_owner_errors_expose_only_status_code_not_upstream_body(transport, status):
    transport.responder = lambda request: httpx.Response(status, text=UPSTREAM_PRIVATE)
    exposed = status if status in {400, 403, 404, 409, 422} else 503
    _assert_refused(
        transport.store.require_field(CALLER, FIELD),
        "inspection_owner_refused_" + str(status),
        exposed,
    )


def test_redirect_never_sends_coordinator_secret_to_second_host(transport):
    transport.responder = lambda request: httpx.Response(
        302, headers={"Location": "https://untrusted.test/collect"}, text=UPSTREAM_PRIVATE
    )
    _assert_refused(transport.store.require_field(CALLER, FIELD), "inspection_owner_refused_302")
    assert [r.url.host for r in transport.requests] == ["owner.test"]


def test_transport_timeout_is_redacted_and_fails_closed(transport):
    def timeout(request):
        raise httpx.ReadTimeout(UPSTREAM_PRIVATE, request=request)

    transport.responder = timeout
    _assert_refused(transport.store.require_field(CALLER, FIELD), "inspection_owner_unavailable")


@pytest.mark.parametrize(
    "content,reason",
    [
        (UPSTREAM_PRIVATE.encode(), "inspection_owner_invalid_response"),
        (b"x" * (2 * 1024 * 1024 + 1), "inspection_owner_response_too_large"),
    ],
)
def test_invalid_or_oversized_response_is_not_parsed_as_success(transport, content, reason):
    transport.responder = lambda request: httpx.Response(200, content=content)
    _assert_refused(transport.store.require_field(CALLER, FIELD), reason)


@pytest.mark.parametrize("method", ["validate", "ensure_task"])
def test_source_envelope_is_required_before_source_bound_operations(transport, method):
    _assert_refused(
        getattr(transport.store, method)(CALLER, transport.binding),
        "inspection_source_context_missing",
    )
    assert transport.requests == []


def test_claim_is_required_after_source_before_create(transport):
    transport.store.source_context(transport.binding, *_source())
    _assert_refused(
        transport.store.ensure_task(CALLER, transport.binding), "execution_claim_unproven"
    )
    assert transport.requests == []


@pytest.mark.parametrize(
    "change",
    [
        {"authoritative": 1},
        {"persisted": False},
        {"execution_request_id": "other-request"},
        {"adapter_id": "other-adapter"},
        {"adapter_kind": "equipment"},
        {"delivery_state": "queued"},
    ],
)
def test_claim_context_cannot_be_forged_by_truthy_flags_or_other_request(transport, change):
    with pytest.raises(HTTPException) as caught:
        transport.store.claim_context(transport.binding, _claim(transport.binding) | change)
    assert caught.value.detail == {"code": "execution_claim_unproven"}
    assert transport.requests == []


@pytest.mark.parametrize(
    "caller,binding_change",
    [
        (Identity(tenant_id=PEER), {}),
        (Identity(user_id="8"), {}),
        (CALLER, {"field_id": "other-field"}),
        (CALLER, {"task_id": PEER}),
    ],
)
def test_source_context_is_not_reused_for_another_actor_or_binding(
    transport, caller, binding_change
):
    transport.store.source_context(transport.binding, *_source())
    changed = replace(transport.binding, **binding_change)
    _assert_refused(transport.store.validate(caller, changed), "inspection_source_context_missing")
    assert transport.requests == []


def test_create_sends_frozen_source_and_projected_claim_without_delivery_token(transport):
    source = _source()
    original = copy.deepcopy(source)
    claim = _claim(transport.binding) | {"delivery_token": RAW_DELIVERY_TOKEN}
    transport.store.source_context(transport.binding, *source)
    transport.store.claim_context(transport.binding, claim)
    source[0]["command_payload"]["inspection"]["assigned_to"] = 99
    claim["delivery_state"] = "queued"
    assert _run(transport.store.ensure_task(CALLER, transport.binding)) == asdict(transport.binding)
    [request] = transport.requests
    body = json.loads(request.content)
    assert body == {
        "field_id": FIELD,
        "execution_request_id": REQUEST,
        "source": dict(zip(("item", "lineage", "plan"), original, strict=True)),
        "claim": _claim(transport.binding),
    }
    assert RAW_DELIVERY_TOKEN.encode() not in request.content
    assert "binding" not in body and "task_id" not in body and "received_by" not in body


@pytest.mark.parametrize("operation", ["ensure_task", "readback"])
@pytest.mark.parametrize(
    "key,value",
    [
        ("tenant_id", PEER),
        ("task_id", PEER),
        ("field_id", "other-field"),
        ("execution_request_id", "other-request"),
        ("operation_type", "irrigation"),
        ("receipt_id", "other-receipt"),
        ("request_digest", "f" * 64),
    ],
)
def test_create_and_readback_reject_a_different_persisted_binding(transport, operation, key, value):
    transport.store.source_context(transport.binding, *_source())
    transport.store.claim_context(transport.binding, _claim(transport.binding))
    wire_operation = "ensure-task" if operation == "ensure_task" else "readback"
    transport.data[wire_operation] = asdict(transport.binding) | {key: value}
    _assert_refused(
        getattr(transport.store, operation)(CALLER, transport.binding),
        "inspection_owner_link_unproven",
    )


@pytest.mark.parametrize("data", [[], {}, {"tenant_id": TENANT}])
def test_get_link_rejects_non_records(transport, data):
    transport.data["get-link"] = data
    _assert_refused(transport.store.get_link(CALLER, REQUEST), "inspection_owner_link_unproven")


def test_link_absence_is_explicit_and_does_not_invent_a_task(transport):
    assert _run(transport.store.get_link(CALLER, REQUEST)) is None
    assert json.loads(transport.requests[0].content) == {"execution_request_id": REQUEST}


@pytest.mark.parametrize(
    "key,value", [("tenant_id", PEER), ("execution_request_id", "other-request")]
)
def test_get_link_rejects_cross_request_or_tenant_row(transport, key, value):
    transport.data["get-link"] = asdict(transport.binding) | {key: value}
    _assert_refused(transport.store.get_link(CALLER, REQUEST), "inspection_owner_link_unproven")


@pytest.mark.parametrize("case", ["not-list", "over-limit", "peer-tenant", "other-field"])
def test_list_links_is_bounded_and_scoped(transport, case):
    row = asdict(transport.binding)
    transport.data["list-links"] = {
        "not-list": {},
        "over-limit": [row, row],
        "peer-tenant": [row | {"tenant_id": PEER}],
        "other-field": [row | {"field_id": "other-field"}],
    }[case]
    reason = (
        "inspection_owner_links_unproven"
        if case in {"not-list", "over-limit"}
        else "inspection_owner_link_unproven"
    )
    _assert_refused(transport.store.list_links(CALLER, FIELD, 1), reason)


@pytest.mark.parametrize(
    "key,value", [("tenant_id", PEER), ("execution_request_id", "other-request")]
)
def test_preview_rejects_wrong_tenant_or_request(transport, key, value):
    transport.data["preview-confirmation"] = transport.proof | {key: value}
    _assert_refused(
        transport.store.preview_confirmation(CALLER, asdict(transport.binding)),
        "inspection_owner_confirmation_unproven",
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("tenant_id", PEER),
        ("task_id", PEER),
        ("field_id", "other-field"),
    ],
)
def test_prepare_rejects_proof_outside_requested_scope(transport, key, value):
    transport.data["prepare-confirmation"] = transport.proof | {key: value}
    _assert_refused(
        transport.store.prepare_confirmation(CALLER, transport.binding.task_id, FIELD),
        "inspection_owner_confirmation_unproven",
    )


def test_prepare_sends_only_task_and_field_and_preserves_owner_proof(transport):
    result = _run(transport.store.prepare_confirmation(CALLER, transport.binding.task_id, FIELD))
    assert result == transport.proof
    assert json.loads(transport.requests[0].content) == {
        "task_id": transport.binding.task_id,
        "field_id": FIELD,
    }


def test_acknowledgement_sends_confirmation_reference_and_result_without_browser_proof(transport):
    ack = _run(transport.store.save_outcome(CALLER, transport.proof, transport.result))
    assert ack == transport.ack
    body = json.loads(transport.requests[0].content)
    assert body == {
        "execution_request_id": REQUEST,
        "confirmation_id": transport.proof["confirmation_id"],
        "result": transport.result,
    }
    assert "actual" not in body and "metrics" not in body and "proof" not in body


@pytest.mark.parametrize(
    "key,value",
    [
        ("tenant_id", PEER),
        ("execution_request_id", "other-request"),
        ("confirmation_id", "fic_" + "d" * 32),
        ("task_id", PEER),
        ("field_id", "other-field"),
        ("outcome_id", "other-outcome"),
    ],
)
def test_mismatched_owner_acknowledgement_is_rejected(transport, key, value):
    transport.data["save-outcome"] = transport.ack | {key: value}
    _assert_refused(
        transport.store.save_outcome(CALLER, transport.proof, transport.result),
        "inspection_owner_outcome_ack_unproven",
    )


@pytest.mark.parametrize("readback_fails", [False, True])
def test_real_coordinator_http_calls_read_committed_owner_before_acceptance(
    transport, readback_fails
):
    # Both service clients serialize real httpx requests; MockTransport supplies their replies.
    # This proves sequencing/credential separation, not an actual DB commit or live network.
    item, lineage, plan = _source()
    owner_reply = transport.responder

    def reply(request):
        path = request.url.path
        if request.url.host == "owner.test":
            assert "Authorization" not in request.headers
            assert "X-Field-Inspection-Proof-Token" not in request.headers
            assert RAW_DELIVERY_TOKEN.encode() not in request.content
            if path.endswith("/readback") and readback_fails:
                return httpx.Response(409, text=UPSTREAM_PRIVATE)
            return owner_reply(request)
        assert request.url.host == "decision.test"
        assert request.headers["Authorization"] == "Bearer synthetic-decision-token"
        assert "X-Field-Inspection-Coordinator-Token" not in request.headers
        assert "X-Field-Inspection-Proof-Token" not in request.headers
        if path in {"/v1/execution-requests", "/v1/execution-requests/recovery"}:
            return httpx.Response(
                200,
                json={
                    "authoritative": True,
                    "persisted": True,
                    "tenant_id": TENANT,
                    "items": [] if path.endswith("/recovery") else [item],
                },
            )
        if path.endswith("/lineage"):
            return httpx.Response(200, json=lineage)
        if path == "/v1/execution-plans/plan-fixture":
            return httpx.Response(200, json=plan)
        if path.endswith("/claim"):
            return httpx.Response(
                200, json=_claim(transport.binding) | {"delivery_token": RAW_DELIVERY_TOKEN}
            )
        if path.endswith("/receipt"):
            assert transport.requests[-2].url.path.endswith("/readback")
            return httpx.Response(
                200,
                json={
                    "authoritative": True,
                    "persisted": True,
                    "execution_request_id": REQUEST,
                    "receipt_id": transport.binding.receipt_id,
                    "execution_state": "accepted",
                },
            )
        raise AssertionError("unexpected decision request: " + path)

    transport.responder = reply
    settings = mod.ExecutionSettings(True, transport.binding.adapter_id, "synthetic-key-" * 4)
    adapter = mod.ExecutionAdapter(
        transport.store,
        mod.HttpDecisionClient("http://decision.test", "synthetic-decision-token"),
        settings,
    )
    if readback_fails:
        _assert_refused(
            adapter.receive(CALLER, REQUEST, expected_field_id=FIELD),
            "inspection_owner_refused_409",
            409,
        )
    else:
        result = _run(adapter.receive(CALLER, REQUEST, expected_field_id=FIELD))
        assert result["state"] == "accepted" and result["physical_execution_verified"] is False
    operations = [r.url.path.rsplit("/", 1)[-1] for r in transport.requests]
    assert operations.count("ensure-task") == operations.count("readback") == 1
    assert operations.index("ensure-task") < operations.index("readback")
    assert operations.count("receipt") == int(not readback_fails)
    owner_requests = [r for r in transport.requests if r.url.host == "owner.test"]
    readback = next(r for r in owner_requests if r.url.path.endswith("/readback"))
    assert json.loads(readback.content) == {"field_id": FIELD, "execution_request_id": REQUEST}
    raw_hmac = settings.token(TENANT, REQUEST).encode()
    assert all(raw_hmac not in r.content for r in owner_requests)
