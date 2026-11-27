"""ASGI boundary tests; the coordinator is doubled, with no DB or service claim."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from api import main as platform
from api.routers import inspection_executions as mod
from core.authorization import Permission, has_permission
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

TENANT = "00000000-0000-0000-0000-000000000001"
PEER = "00000000-0000-0000-0000-000000000002"
TASK = "1a7a45ec-75d1-5d98-9566-c5b676e303b4"
FIELD = "field-inspection-fixture"
REQUEST = "execution-request-fixture"
PREFIX = "/api/v1/inspection-executions/fields/" + FIELD
URLS = {
    "list": PREFIX,
    "receive": PREFIX + "/requests/" + REQUEST + "/receive",
    "verify": PREFIX + "/tasks/" + TASK + "/verify",
}


def _user(role=UserRole.MANAGER, *, tenant_id=TENANT, user_id="7", active=True):
    return UserSchema(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        name_ar="Fixture manager",
        is_active=active,
    )


class RecordingAdapter:
    """Observe the authorized transport call, without pretending to persist it."""

    def __init__(self):
        self.calls = []
        self.error = None

    def _record(self, operation, caller, field_id, reference=None, limit=None):
        self.calls.append((operation, caller, field_id, reference, limit))
        if self.error:
            raise self.error

    async def list_for_field(self, caller, field_id, *, limit=50):
        self._record("list", caller, field_id, limit=limit)
        return {"field_id": field_id, "items": [], "truncated": False, "limit": limit}

    async def receive(self, caller, request_id, *, expected_field_id):
        self._record("receive", caller, expected_field_id, request_id)
        return {
            "state": "accepted",
            "persisted": True,
            "replayed": False,
            "execution_request_id": request_id,
            "task_id": TASK,
            "field_id": expected_field_id,
            "receipt_id": "receipt-fixture",
            "physical_execution_verified": False,
        }

    async def verify(self, caller, task_id, *, expected_field_id):
        self._record("verify", caller, expected_field_id, task_id)
        return {
            "state": "verified_success",
            "persisted": True,
            "replayed": False,
            "task_id": task_id,
            "execution_request_id": REQUEST,
            "outcome_id": "outcome-fixture",
        }


@pytest.fixture
def harness(monkeypatch):
    state = SimpleNamespace(user=_user(), built=0)
    adapter = RecordingAdapter()

    def build():
        state.built += 1
        return adapter

    monkeypatch.setattr(mod, "build_adapter", build)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[platform.get_current_user] = lambda: state.user
    with TestClient(app) as client:
        yield SimpleNamespace(app=app, client=client, state=state, adapter=adapter)


def _call(harness, operation, **kwargs):
    if operation == "list":
        return harness.client.get(URLS[operation], **kwargs)
    return harness.client.post(URLS[operation], json={}, **kwargs)


@pytest.mark.parametrize("operation", URLS)
def test_routes_forward_only_session_identity_and_route_identifiers(harness, operation):
    response = _call(
        harness,
        operation,
        headers={
            "X-Tenant-Id": PEER,
            "X-User-Id": "999",
            "X-User-Role": "owner",
            "X-Field-Tasks-Token": "browser-supplied-not-trusted",
            "X-Field-Inspection-Coordinator-Token": "browser-supplied-not-trusted",
        },
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert harness.state.built == 1
    [(called, caller, field_id, reference, limit)] = harness.adapter.calls
    assert called == operation
    assert (caller.tenant_id, caller.user_id, caller.role) == (TENANT, "7", "manager")
    assert caller.user is harness.state.user
    assert field_id == FIELD
    if operation == "list":
        assert response.json() == {"field_id": FIELD, "items": [], "truncated": False, "limit": 50}
        assert reference is None and limit == 50
    elif operation == "receive":
        assert reference == REQUEST
        assert response.json()["state"] == "accepted"
        assert response.json()["physical_execution_verified"] is False
        assert "outcome_id" not in response.json()
    else:
        assert reference == TASK
        assert response.json()["state"] == "verified_success"
        assert response.json()["outcome_id"] == "outcome-fixture"


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("operation", URLS)
def test_canonical_role_policy_is_enforced_before_adapter_construction(harness, role, operation):
    harness.state.user = _user(role)
    response = _call(harness, operation)
    allowed = (
        has_permission(harness.state.user, Permission.FIELD_VIEW)
        if operation == "list"
        else role in {UserRole.OWNER, UserRole.MANAGER}
    )
    assert response.status_code == (200 if allowed else 403)
    assert harness.state.built == int(allowed)
    assert len(harness.adapter.calls) == int(allowed)
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("operation", URLS)
def test_inactive_session_never_constructs_adapter(harness, operation):
    harness.state.user = _user(active=False)
    response = _call(harness, operation)
    assert response.status_code == 403
    assert harness.state.built == 0


@pytest.mark.parametrize("operation", URLS)
def test_missing_auth_cannot_be_replaced_by_identity_headers(harness, operation):
    harness.app.dependency_overrides.clear()
    response = _call(
        harness,
        operation,
        headers={"X-Tenant-Id": TENANT, "X-User-Id": "7", "X-User-Role": "owner"},
    )
    assert response.status_code == 401
    assert harness.state.built == 0
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("tenant", ["", "not-a-uuid", None, 7])
@pytest.mark.parametrize("operation", URLS)
def test_invalid_authenticated_tenant_fails_closed(harness, tenant, operation):
    harness.state.user = _user(tenant_id=tenant)
    response = _call(harness, operation)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "invalid_trusted_tenant"
    assert harness.state.built == 0


@pytest.mark.parametrize("user_id", ["", " ", None, 7])
def test_missing_authenticated_actor_fails_closed(harness, user_id):
    harness.state.user = _user(user_id=user_id)
    response = _call(harness, "receive")
    assert response.status_code == 403
    assert harness.state.built == 0


@pytest.mark.parametrize("operation", URLS)
def test_peer_tenant_is_forwarded_exactly_and_owner_refusal_is_preserved(harness, operation):
    # This proves routing and refusal propagation, not the remote owner's RLS.
    harness.state.user = _user(tenant_id=PEER)
    harness.adapter.error = HTTPException(404, {"code": "field_not_found"})
    response = _call(harness, operation, headers={"X-Tenant-Id": TENANT})
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "field_not_found"}}
    assert harness.adapter.calls[0][1].tenant_id == PEER
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("operation", ["receive", "verify"])
@pytest.mark.parametrize(
    "body",
    [
        {"tenant_id": PEER},
        {"assigned_to": 99},
        {"verified_by": "7"},
        {"task_id": TASK},
        {"actual": {"task_status": "completed"}},
        {"metrics": {"inspection_approved": True}},
        {"execution_request_id": REQUEST},
        [],
        "",
        1,
        True,
        None,
    ],
)
def test_write_body_accepts_only_empty_object(harness, operation, body):
    response = harness.client.post(URLS[operation], json=body)
    assert response.status_code == 422
    assert harness.state.built == 0
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("operation", ["receive", "verify"])
def test_missing_write_body_is_rejected(harness, operation):
    response = harness.client.post(URLS[operation])
    assert response.status_code == 422
    assert harness.state.built == 0


@pytest.mark.parametrize("limit", [0, 101, "invalid"])
def test_list_rejects_invalid_limit_before_adapter(harness, limit):
    response = harness.client.get(URLS["list"], params={"limit": limit})
    assert response.status_code == 422
    assert harness.state.built == 0


def test_list_limit_is_forwarded(harness):
    response = harness.client.get(URLS["list"], params={"limit": 100})
    assert response.status_code == 200
    assert harness.adapter.calls[0][-1] == 100


@pytest.mark.parametrize(
    "url",
    [
        PREFIX + "/tasks/not-a-uuid/verify",
        PREFIX + "/requests/" + "a" * 201 + "/receive",
        PREFIX + "/requests/request%3Foverride/receive",
        "/api/v1/inspection-executions/fields/" + "f" * 51 + "/requests/r/receive",
    ],
)
def test_invalid_path_identifiers_are_rejected_before_adapter(harness, url):
    response = harness.client.post(url, json={})
    assert response.status_code == 422
    assert harness.state.built == 0


@pytest.mark.parametrize("status", [409, 503])
@pytest.mark.parametrize("operation", ["receive", "verify"])
def test_owner_or_decision_refusal_cannot_become_success(harness, status, operation):
    harness.adapter.error = HTTPException(status, {"code": "owner_or_decision_refused"})
    response = _call(harness, operation)
    assert response.status_code == status
    assert response.json() == {"detail": {"code": "owner_or_decision_refused"}}
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("operation", ["receive", "verify"])
def test_production_unverifiable_revocation_still_blocks_writes(harness, monkeypatch, operation):
    def uncertain_session(request: Request):
        request.state.revocation_unverifiable = True
        return harness.state.user

    harness.app.dependency_overrides[platform.get_current_user] = uncertain_session
    monkeypatch.setattr(platform, "_is_production", lambda: True)
    response = _call(harness, operation)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "token_revocation_unverifiable"
    assert harness.state.built == 0


def test_caller_permission_checks_delegate_to_canonical_authorization():
    for role in UserRole:
        user = _user(role)
        caller = mod._caller(user)
        for permission in Permission:
            assert caller.can(permission.value) == has_permission(user, permission)
        assert caller.can("invented:permission") is False
    user = _user(active=False)
    caller = mod._caller(user)
    assert caller.can(Permission.FIELD_VIEW.value) is False


def test_platform_autoregisters_exactly_three_feature_routes():
    registered = {
        (method, route.path)
        for route in platform.app.routes
        for method in getattr(route, "methods", ())
        if getattr(route, "path", "").startswith("/api/v1/inspection-executions/")
    }
    assert registered == {
        ("GET", "/api/v1/inspection-executions/fields/{field_id}"),
        (
            "POST",
            "/api/v1/inspection-executions/fields/{field_id}/requests/{execution_request_id}/receive",
        ),
        ("POST", "/api/v1/inspection-executions/fields/{field_id}/tasks/{task_id}/verify"),
    }
