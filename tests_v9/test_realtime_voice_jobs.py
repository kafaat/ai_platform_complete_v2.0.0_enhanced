"""Voice consent, current authority and ephemeral custody using actual SQLite."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
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
from realtime_session.voice_jobs import VoiceJobBroker  # noqa: E402

sys.path.remove(str(ROOT / "services/realtime-session"))

pytestmark = [pytest.mark.unit, pytest.mark.security]
SECRET = "dedicated-disposable-worker-credential-0001"
BEARER = "disposable-private-user-bearer"


class Authority:
    denied = False
    other_identity = False
    hook = None

    async def identity(self, bearer):
        assert bearer == BEARER
        return Principal("tenant", "farmer")

    async def verified_identity(self, bearer):
        if self.denied:
            raise SessionError(403, "trusted_policy_required")
        if self.hook:
            await self.hook()
        return Principal("other" if self.other_identity else "tenant", "farmer"), {
            "contract": "sahool.ai_policy_envelope",
            "contract_version": 2,
            "version": "v52",
            "tenant_id": "tenant",
            "allowed_tools": [],
            "policy_mode": "local_only",
            "external_llm_allowed": False,
            "external_tts_allowed": False,
        }

    async def authorize_field(self, bearer, principal, field_id):
        assert bearer == BEARER
        assert field_id == "field"
        if self.denied:
            raise SessionError(403, "field_denied")


class Gateway:
    fail_dispatch = False
    block_dispatch = False

    def __init__(self):
        self.dispatches = []
        self.rooms = []

    async def create_room(self, session):
        self.rooms.append(session)

    async def dispatch_agent(self, session, nonce):
        self.dispatches.append((session, nonce))
        if self.block_dispatch:
            await asyncio.Future()
        if self.fail_dispatch:
            raise SessionError(503, "uncertain_dispatch")

    def participant_token(self, session, now, ttl):
        return "disposable-room-token"

    async def delete_room(self, room):
        pass


@pytest.fixture
async def h(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite")
    await store.initialize()
    authority = Authority()
    gateway = Gateway()
    clock = SimpleNamespace(now=1000)
    broker = VoiceJobBroker(authority, store, SECRET, clock=lambda: clock.now)
    service = SessionService(
        authority,
        store,
        gateway,
        "wss://media.example.test",
        clock=lambda: clock.now,
        voice_jobs=broker,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)), base_url="http://session.test"
    ) as client:
        yield SimpleNamespace(
            store=store,
            authority=authority,
            gateway=gateway,
            clock=clock,
            broker=broker,
            service=service,
            client=client,
        )
    broker.close()


async def create_voice(h):
    result = await h.service.create(BEARER, "field", True, voice_consent=True)
    session, nonce = h.gateway.dispatches[-1]
    return result, session, nonce


def headers(nonce, secret=SECRET):
    return {"X-Realtime-Worker-Token": secret, "X-Realtime-Job-Nonce": nonce}


async def test_voice_requires_separate_consent_and_disabled_rejects_before_allocation(h):
    h.service.voice_jobs = None
    with pytest.raises(SessionError, match="voice_disabled"):
        await h.service.create(BEARER, "field", True, voice_consent=True)
    assert h.gateway.rooms == []
    result = await h.service.create(BEARER, "field", True)
    assert result["status"] == "ACTIVE"
    assert h.gateway.dispatches == []


@pytest.mark.parametrize("value", ["true", 1, None, {}, []])
async def test_voice_consent_is_not_coerced(h, value):
    result = await h.client.post(
        "/api/v1/realtime/sessions",
        headers={"Authorization": "Bearer " + BEARER},
        json={"field_id": "field", "consent": True, "voice_consent": value},
    )
    assert result.status_code == 422
    assert h.gateway.rooms == []


async def test_context_contains_only_server_bound_identity_and_current_policy(h):
    result, session, nonce = await create_voice(h)
    response = await h.client.get(
        "/api/v1/realtime/internal/jobs/" + session.session_id, headers=headers(nonce)
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    context = response.json()
    assert context == {
        "session_id": session.session_id,
        "room_name": session.room_name,
        "participant_identity": "participant-" + session.session_id,
        "tenant_id": "tenant",
        "user_id": "farmer",
        "field_id": "field",
        "bearer": BEARER,
        "expires_at": result["expires_at"],
        "policy_envelope": (await h.authority.verified_identity(BEARER))[1],
    }
    assert BEARER not in repr(h.broker._credentials)
    assert nonce not in repr(h.broker._credentials)
    assert SECRET not in repr(h.broker)
    assert "nonce" not in context


@pytest.mark.parametrize("secret", ["", "wrong", "é" * 40, "x" * 1000])
async def test_worker_authentication_cannot_be_replaced_with_user_bearer(h, secret):
    _, session, nonce = await create_voice(h)
    with pytest.raises(SessionError) as error:
        await h.broker.context(session.session_id, secret, nonce)
    assert error.value.status == 401
    assert (await h.broker.context(session.session_id, SECRET, nonce))["bearer"] == BEARER


@pytest.mark.parametrize("nonce", ["", "0" * 32, "é" * 32, "x" * 1000])
async def test_wrong_nonce_cannot_read_or_revoke_the_real_job(h, nonce):
    _, session, actual = await create_voice(h)
    with pytest.raises(SessionError) as error:
        await h.broker.context(session.session_id, SECRET, nonce)
    assert error.value.status == 404
    assert (await h.broker.context(session.session_id, SECRET, actual))["bearer"] == BEARER


@pytest.mark.parametrize("change", ["denied", "other_identity"])
async def test_changed_platform_authority_revokes_credential_permanently(h, change):
    _, session, nonce = await create_voice(h)
    setattr(h.authority, change, True)
    with pytest.raises(SessionError) as error:
        await h.broker.context(session.session_id, SECRET, nonce)
    assert error.value.status == 403
    setattr(h.authority, change, False)
    with pytest.raises(SessionError) as error:
        await h.broker.context(session.session_id, SECRET, nonce)
    assert error.value.status == 404


async def test_close_while_platform_request_is_in_flight_never_returns_bearer(h):
    _, session, nonce = await create_voice(h)

    async def close_during_auth():
        await h.service.close(BEARER, session.session_id)

    h.authority.hook = close_during_auth
    with pytest.raises(SessionError) as error:
        await h.broker.context(session.session_id, SECRET, nonce)
    assert error.value.status == 404
    assert session.session_id not in h.broker._credentials


async def test_expired_lease_revokes_credential_before_platform_or_cleanup(h):
    result, session, nonce = await create_voice(h)
    h.clock.now = result["expires_at"]
    with pytest.raises(SessionError) as error:
        await h.broker.context(session.session_id, SECRET, nonce)
    assert error.value.status == 404
    assert not h.broker._credentials
    await h.service.cleanup()
    assert (await h.store.get(session.session_id)).status == "CLOSED"


async def test_dispatch_failure_holds_quota_cleanup_without_custody(h):
    h.gateway.fail_dispatch = True
    with pytest.raises(SessionError, match="uncertain_dispatch"):
        await create_voice(h)
    session = h.gateway.rooms[-1]
    assert (await h.store.get(session.session_id)).status == "CLOSING"
    assert not h.broker._credentials
    with pytest.raises(SessionError) as error:
        await h.service.create(BEARER, "field", True)
    assert error.value.status == 429


async def test_client_cancellation_retains_cleanup_but_revokes_dispatch_credentials(h):
    h.gateway.block_dispatch = True
    task = asyncio.create_task(h.service.create(BEARER, "field", True, voice_consent=True))
    while not h.gateway.dispatches:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    session = h.gateway.rooms[-1]
    assert (await h.store.get(session.session_id)).status == "CLOSING"
    assert not h.broker._credentials


async def test_restart_marks_only_voice_sessions_for_cleanup_and_never_recovers_secrets(h):
    _, session, nonce = await create_voice(h)
    h.broker.close()
    with sqlite3.connect(h.store.path) as conn:
        encoded_rows = json.dumps(conn.execute("SELECT * FROM realtime_sessions").fetchall())
        encoded_rows += json.dumps(conn.execute("SELECT * FROM realtime_voice_sessions").fetchall())
    assert BEARER not in encoded_rows and nonce not in encoded_rows and SECRET not in encoded_rows
    await h.store.recover_voice()
    assert (await h.store.get(session.session_id)).status == "CLOSING"
    restarted = VoiceJobBroker(h.authority, h.store, SECRET, clock=lambda: h.clock.now)
    with pytest.raises(SessionError) as error:
        await restarted.context(session.session_id, SECRET, nonce)
    assert error.value.status == 404


@pytest.mark.parametrize("secret", ["", "a" * 31, "a" * 257, "é" * 40, "a" * 31 + "\n"])
def test_worker_secret_requires_dedicated_ascii_configuration(secret):
    with pytest.raises(ValueError):
        VoiceJobBroker(None, None, secret)


@pytest.mark.parametrize(
    "key,value",
    [
        ("policy_mode", "hybrid"),
        ("external_llm_allowed", True),
        ("external_llm_allowed", None),
        ("external_tts_allowed", True),
        ("external_tts_allowed", 0),
        ("tenant_id", "other"),
        ("contract_version", 3),
        ("contract_version", True),
        ("version", "future"),
        ("allowed_tools", None),
    ],
)
async def test_current_policy_must_explicitly_limit_both_providers_to_local(h, key, value):
    _, session, nonce = await create_voice(h)
    verified = h.authority.verified_identity

    async def changed_policy(bearer):
        principal, envelope = await verified(bearer)
        envelope[key] = value
        return principal, envelope

    h.authority.verified_identity = changed_policy
    with pytest.raises(SessionError, match="voice_local_policy_required"):
        await h.broker.context(session.session_id, SECRET, nonce)
    assert session.session_id not in h.broker._credentials


async def test_credential_expires_without_another_fetch_or_cleanup_call(h):
    from dataclasses import replace

    _, session, _nonce = await create_voice(h)
    shorter = replace(session, expires_at=h.clock.now + 1)
    h.broker.issue(shorter, BEARER, h.clock.now)
    await asyncio.sleep(1.05)
    assert session.session_id not in h.broker._credentials
    assert session.session_id not in h.broker._expiry
