"""Real BFF HTTP routes retain the owning service's opaque correlation identity.

The service facade and authenticated-user dependency are explicit test doubles;
this suite proves response projection and identity forwarding, not DB persistence
or JWT validation. No execution command or downstream network request is issued.
"""

import api.decision_service_client as facade
import api.main  # noqa: F401
import api.routers.decision_review as routes
import pytest
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit
USER = UserSchema(
    user_id="correlation-reviewer",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.MANAGER,
    name_ar="مراجع",
)
CORRELATION = "21ff8426-f30e-4ff2-b8f9-9d69655fd4b4"
_MISSING = object()


def _case(kind):
    payload = {
        "decision_id": "dec_1",
        "review_id": "review_1",
        "candidate_lineage_id": "lineage_1",
        "idempotency_key": "request_1",
    }
    result = {
        **payload,
        "authoritative": True,
        "persisted": True,
        "execution_plan_id": "plan_1",
        "dispatch_authorization_id": "auth_1",
        "execution_request_id": "exec_1",
    }
    if kind == "review":
        payload.update(
            action="approve", expected_state="pending_approval", decision_value_digest="a" * 64
        )
        result.update(
            previous_state="pending_approval",
            state="approved",
            reviewed_by=USER.user_id,
            reviewed_at="2026-10-16T00:00:00Z",
            decision_value_digest="a" * 64,
        )
        return (
            "/api/v1/decisions/dec_1/review",
            routes,
            "ds_review_decision",
            "reviewed_by",
            payload,
            result,
        )
    if kind == "plan":
        payload.update(operation_type="inspection")
        result.update(
            plan_state="planned",
            plan_digest="b" * 64,
            created_by=USER.user_id,
            created_at="2026-10-16T00:00:00Z",
        )
        return (
            "/api/v1/decisions/dec_1/execution-plan",
            facade,
            "create_execution_plan",
            "created_by",
            payload,
            result,
        )
    if kind == "authorize":
        payload.update(
            expected_plan_state="planned",
            policy_version="p1",
            weather_snapshot_id="w1",
            resource_snapshot_id="r1",
        )
        result.update(
            payload,
            authorization_state="authorized",
            authorized_by=USER.user_id,
            authorized_at="2026-10-16T00:00:00Z",
        )
        return (
            "/api/v1/execution-plans/plan_1/authorize-dispatch",
            facade,
            "authorize_dispatch",
            "authorized_by",
            payload,
            result,
        )
    payload.update(
        dispatch_authorization_id="auth_1",
        execution_plan_id="plan_1",
        target_type="task",
        target_id="synthetic-only",
        operation_type="inspection",
    )
    result.update(
        payload,
        execution_state="queued",
        requested_by=USER.user_id,
        requested_at="2026-10-16T00:00:00Z",
    )
    return (
        "/api/v1/dispatch-authorizations/auth_1/execute",
        facade,
        "create_execution_request",
        "requested_by",
        payload,
        result,
    )


@pytest.mark.parametrize("kind", ["review", "plan", "authorize", "execute"])
@pytest.mark.parametrize("correlation", [CORRELATION, None, _MISSING])
@pytest.mark.parametrize("replay", [False, True])
def test_bff_http_retains_service_correlation(monkeypatch, kind, correlation, replay):
    url, module, method, actor_key, payload, result = _case(kind)
    if correlation is not _MISSING:
        result["correlation_id"] = correlation
    result["replay"] = replay
    payload["correlation_id"] = "caller-must-not-own-the-trace"
    observed = {}

    async def remote(identity, body, **kwargs):
        observed.update(kwargs)
        assert "correlation_id" not in body
        return result

    monkeypatch.setattr(module, method, remote)
    app = FastAPI()
    app.include_router(routes.router)
    # Override only the original user permission dependencies on this test app.
    # The actual endpoint, Pydantic body and HTTP serialization still execute.
    for route in routes.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "user":
                app.dependency_overrides[dependency.call] = lambda: USER
    response = TestClient(app).post(url, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["correlation_id"] == (None if correlation is _MISSING else correlation)
    assert response.json()["replay"] is replay
    assert observed["tenant_id"] == str(USER.tenant_id)
    assert observed[actor_key] == USER.user_id
