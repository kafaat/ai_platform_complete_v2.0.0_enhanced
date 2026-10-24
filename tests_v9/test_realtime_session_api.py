"""HTTP session authorization and lifecycle against a real durable SQLite store.

Only the trusted Platform and LiveKit network boundaries are substituted. These
tests do not certify a deployed SFU, browser capture, external-provider consent,
or media transport. No real bearer or LiveKit signing credential is used.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/realtime-session"))

from realtime_session.contracts import Principal, SessionError  # noqa: E402
from realtime_session.engine import SessionService  # noqa: E402
from realtime_session.session_runtime import create_app  # noqa: E402
from realtime_session.store import SessionStore  # noqa: E402

sys.path.remove(str(ROOT / "services/realtime-session"))

pytestmark = [pytest.mark.unit, pytest.mark.security]

FIELD = "00000000-0000-0000-0000-0000000000f1"
TENANT = "00000000-0000-0000-0000-0000000000a1"
OTHER_TENANT = "00000000-0000-0000-0000-0000000000a2"
CREATE = {"field_id": FIELD, "consent": True}


class Authority:
    def __init__(self):
        self.principals = {
            "alice": Principal(TENANT, "alice-user"),
            "bob": Principal(TENANT, "bob-user"),
            "carol": Principal(TENANT, "carol-user"),
            "outsider": Principal(OTHER_TENANT, "outsider-user"),
        }
        self.denied_fields = set()

    async def identity(self, bearer):
        if bearer not in self.principals:
            raise SessionError(401, "identity_rejected")
        return self.principals[bearer]

    async def authorize_field(self, bearer, principal, field_id):
        if field_id != FIELD or bearer in self.denied_fields:
            raise SessionError(403, "field_access_denied")

    async def ready(self):
        return True


class Gateway:
    def __init__(self):
        self.created = []
        self.deleted = []
        self.tokens = []
        self.fail_create = False
        self.fail_delete = False

    async def create_room(self, session):
        # A failed HTTP response does not prove the upstream side effect failed.
        self.created.append(session)
        if self.fail_create:
            raise SessionError(503, "media_backend_unavailable")

    def participant_token(self, session, now, ttl):
        self.tokens.append((session, now, ttl))
        return "synthetic-room-token"

    async def delete_room(self, room_name):
        self.deleted.append(room_name)
        if self.fail_delete:
            raise SessionError(503, "media_backend_unavailable")

    async def ready(self):
        return True

    async def close(self):
        pass


def auth(name="alice"):
    return {"Authorization": f"Bearer {name}"}


@asynccontextmanager
async def harness(tmp_path, *, max_per_tenant=2, max_per_actor=1):
    authority = Authority()
    gateway = Gateway()
    store = SessionStore(
        str(tmp_path / "sessions.sqlite3"),
        max_per_tenant=max_per_tenant,
        max_per_actor=max_per_actor,
    )
    await store.initialize()
    clock = SimpleNamespace(now=1_000)
    service = SessionService(
        authority,
        store,
        gateway,
        "wss://media.example.test",
        clock=lambda: clock.now,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service=service)),
        base_url="http://testserver",
    ) as client:
        yield SimpleNamespace(
            client=client,
            service=service,
            authority=authority,
            gateway=gateway,
            store=store,
            clock=clock,
        )


async def created(h, actor="alice"):
    response = await h.client.post("/api/v1/realtime/sessions", headers=auth(actor), json=CREATE)
    assert response.status_code == 201, response.text
    return response


async def test_default_service_remains_disabled_and_does_not_issue_tokens(monkeypatch):
    monkeypatch.setenv("SAHOOL_REALTIME_ENABLED", "0")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver"
    ) as client:
        health = await client.get("/healthz")
        ready = await client.get("/readyz")
        response = await client.post("/api/v1/realtime/sessions", headers=auth(), json=CREATE)
    assert health.status_code == 200
    assert ready.status_code == 503
    assert response.status_code == 503
    assert "participant_token" not in response.text


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic synthetic"}])
async def test_http_authentication_is_required_before_room_allocation(tmp_path, headers):
    async with harness(tmp_path) as h:
        response = await h.client.post("/api/v1/realtime/sessions", headers=headers, json=CREATE)
        assert response.status_code == 401
        assert "no-store" in response.headers.get("Cache-Control", "")
        assert h.gateway.created == []
        assert h.gateway.tokens == []


async def test_missing_explicit_consent_denies_allocation(tmp_path):
    async with harness(tmp_path) as h:
        response = await h.client.post(
            "/api/v1/realtime/sessions", headers=auth(), json={"field_id": FIELD, "consent": False}
        )
        assert response.status_code == 403
        assert "consent_required" in response.text
        assert h.gateway.created == []


@pytest.mark.parametrize("consent", ["true", 1, None, [], {}])
async def test_non_boolean_consent_cannot_be_coerced_into_permission(tmp_path, consent):
    async with harness(tmp_path) as h:
        response = await h.client.post(
            "/api/v1/realtime/sessions",
            headers=auth(),
            json={"field_id": FIELD, "consent": consent},
        )
        assert response.status_code == 422
        assert h.gateway.created == []


@pytest.mark.parametrize(
    "injected",
    [
        {"tenant_id": OTHER_TENANT},
        {"user_id": "another-user"},
        {"room_name": "existing-privileged-room"},
        {"room_admin": True},
        {"allowed_tools": ["irrigate"]},
    ],
)
async def test_body_cannot_supply_authority_or_room_privileges(tmp_path, injected):
    async with harness(tmp_path) as h:
        response = await h.client.post(
            "/api/v1/realtime/sessions", headers=auth(), json={**CREATE, **injected}
        )
        assert response.status_code == 422
        assert h.gateway.created == []


async def test_field_permission_is_checked_before_allocation(tmp_path):
    async with harness(tmp_path) as h:
        h.authority.denied_fields.add("alice")
        response = await h.client.post("/api/v1/realtime/sessions", headers=auth(), json=CREATE)
        assert response.status_code == 403
        assert h.gateway.created == []
        assert h.gateway.tokens == []


async def test_owner_can_read_and_close_without_disclosing_credentials(tmp_path):
    async with harness(tmp_path) as h:
        response = await created(h)
        payload = response.json()
        session_id = payload["session_id"]
        assert payload["participant_token"] == "synthetic-room-token"
        assert payload["url"] == "wss://media.example.test"
        assert payload["token_expires_at"] <= payload["expires_at"]
        assert FIELD not in h.gateway.created[0].room_name
        assert TENANT not in h.gateway.created[0].room_name
        status = await h.client.get(f"/api/v1/realtime/sessions/{session_id}", headers=auth())
        assert status.status_code == 200
        assert status.json()["status"] == "ACTIVE"
        assert set(status.json()).isdisjoint(
            {"participant_token", "room_name", "tenant_id", "user_id", "api_secret"}
        )
        closing = await h.client.delete(f"/api/v1/realtime/sessions/{session_id}", headers=auth())
        assert closing.status_code == 202
        assert closing.json()["status"] == "CLOSING"
        assert h.gateway.deleted == [h.gateway.created[0].room_name]
        # Room deletion does not revoke a still-valid join token. Keep the
        # admission quota held until the bounded lease and another cleanup pass.
        h.clock.now = payload["expires_at"] + 1
        await h.service.cleanup()
        status_after_cleanup = await h.client.get(
            f"/api/v1/realtime/sessions/{session_id}", headers=auth()
        )
        assert status_after_cleanup.json()["status"] == "CLOSED"
        for item in (response, status, closing, status_after_cleanup):
            assert "no-store" in item.headers.get("Cache-Control", "")


@pytest.mark.parametrize("actor", ["bob", "outsider"])
async def test_other_actor_or_tenant_cannot_read_or_close_session(tmp_path, actor):
    async with harness(tmp_path) as h:
        session_id = (await created(h)).json()["session_id"]
        for method in (h.client.get, h.client.delete):
            response = await method(f"/api/v1/realtime/sessions/{session_id}", headers=auth(actor))
            assert response.status_code == 404
            assert "synthetic-room-token" not in response.text
        assert h.gateway.deleted == []
        owner = await h.client.get(f"/api/v1/realtime/sessions/{session_id}", headers=auth())
        assert owner.json()["status"] == "ACTIVE"


async def test_actor_quota_is_held_through_close_until_lease_cleanup(tmp_path):
    async with harness(tmp_path) as h:
        payload = (await created(h)).json()
        session_id = payload["session_id"]
        limited = await h.client.post("/api/v1/realtime/sessions", headers=auth(), json=CREATE)
        assert limited.status_code == 429
        await h.client.delete(f"/api/v1/realtime/sessions/{session_id}", headers=auth())
        still_limited = await h.client.post(
            "/api/v1/realtime/sessions", headers=auth(), json=CREATE
        )
        assert still_limited.status_code == 429
        h.clock.now = payload["expires_at"] + 1
        await h.service.cleanup()
        assert (await created(h)).status_code == 201
        assert len(h.gateway.created) == 2


async def test_tenant_quota_is_shared_by_distinct_actors(tmp_path):
    async with harness(tmp_path) as h:
        await created(h, "alice")
        await created(h, "bob")
        limited = await h.client.post(
            "/api/v1/realtime/sessions", headers=auth("carol"), json=CREATE
        )
        assert limited.status_code == 429
        assert len(h.gateway.created) == 2


async def test_uncertain_create_and_failed_delete_preserve_cleanup_and_do_not_issue_token(tmp_path):
    async with harness(tmp_path) as h:
        h.gateway.fail_create = True
        h.gateway.fail_delete = True
        response = await h.client.post("/api/v1/realtime/sessions", headers=auth(), json=CREATE)
        assert response.status_code == 503
        assert "participant_token" not in response.text
        assert h.gateway.tokens == []
        allocated = h.gateway.created[0]
        assert (await h.store.get(allocated.session_id)).status == "CLOSING"
        limited = await h.client.post("/api/v1/realtime/sessions", headers=auth(), json=CREATE)
        assert limited.status_code == 429
        h.gateway.fail_delete = False
        h.clock.now = allocated.expires_at + 1
        await h.service.cleanup()
        assert (await h.store.get(allocated.session_id)).status == "CLOSED"


async def test_failed_close_retains_quota_and_retry_closes_the_same_room(tmp_path):
    async with harness(tmp_path) as h:
        payload = (await created(h)).json()
        session_id = payload["session_id"]
        h.gateway.fail_delete = True
        failed = await h.client.delete(f"/api/v1/realtime/sessions/{session_id}", headers=auth())
        assert failed.status_code == 503
        assert (await h.store.get(session_id)).status == "CLOSING"
        limited = await h.client.post("/api/v1/realtime/sessions", headers=auth(), json=CREATE)
        assert limited.status_code == 429
        h.gateway.fail_delete = False
        closing = await h.client.delete(f"/api/v1/realtime/sessions/{session_id}", headers=auth())
        assert closing.status_code == 202
        assert closing.json()["status"] == "CLOSING"
        h.clock.now = payload["expires_at"] + 1
        await h.service.cleanup()
        assert (await h.store.get(session_id)).status == "CLOSED"
        assert h.gateway.deleted == [h.gateway.created[0].room_name] * 3


async def test_expired_session_is_closed_after_engine_restart_from_durable_state(tmp_path):
    async with harness(tmp_path) as h:
        payload = (await created(h)).json()
        h.clock.now = payload["expires_at"] + 1
        restarted_store = SessionStore(str(tmp_path / "sessions.sqlite3"))
        await restarted_store.initialize()
        restarted = SessionService(
            h.authority,
            restarted_store,
            h.gateway,
            "wss://media.example.test",
            clock=lambda: h.clock.now,
        )
        await restarted.cleanup()
        assert (await restarted_store.get(payload["session_id"])).status == "CLOSED"
        assert h.gateway.deleted == [h.gateway.created[0].room_name]


async def test_invalid_bearer_is_not_reflected_in_an_error(tmp_path):
    async with harness(tmp_path) as h:
        response = await h.client.post(
            "/api/v1/realtime/sessions", headers=auth("synthetic-private-bearer"), json=CREATE
        )
        assert response.status_code == 401
        assert "synthetic-private-bearer" not in response.text
        assert h.gateway.created == []
