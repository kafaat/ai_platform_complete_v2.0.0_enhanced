"""Actual SDK signing and request types; RPC boundaries do not use the network."""

from __future__ import annotations

import base64
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/realtime-session"))

from livekit import api  # noqa: E402
from livekit.api.twirp_client import TwirpErrorCode  # noqa: E402
from realtime_session.contracts import Session, SessionError  # noqa: E402
from realtime_session.livekit_adapter import LiveKitGateway  # noqa: E402

sys.path.remove(str(ROOT / "services/realtime-session"))

pytestmark = [pytest.mark.unit, pytest.mark.security]
KEY = "synthetic-api-key"
SECRET = "s" * 48


def _session():
    now = int(time.time())
    return Session(
        "b4fd610ab1be4d61bfaa001122334455",
        "rt_c5fd610ab1be4d61bfaa001122334455",
        "private-tenant-id",
        "private-user-id",
        "private-field-id",
        now,
        now + 300,
        "ACTIVE",
    )


def _payload(token):
    value = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


@pytest.fixture
async def gateway():
    value = LiveKitGateway("http://livekit:7880", KEY, SECRET)
    yield value
    await value.close()


async def test_actual_sdk_token_is_opaque_room_scoped_and_microphone_only(gateway):
    session = _session()
    now = int(time.time())
    token = gateway.participant_token(session, now, 60)
    verified = api.TokenVerifier(KEY, SECRET).verify(token)
    claims = _payload(token)
    assert verified.identity == f"participant-{session.session_id}"
    assert claims["iss"] == KEY
    assert now < claims["exp"] <= now + 60
    assert claims["nbf"] <= int(time.time()) < claims["exp"]
    assert "iat" not in claims, "SDK 1.2.2 emits nbf and exp, not iat"
    assert claims["video"]["room"] == session.room_name
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublishSources"] == ["microphone"]
    assert claims["video"]["canSubscribe"] is True
    assert claims["video"]["canPublishData"] is False
    for name in (
        "roomCreate",
        "roomList",
        "roomAdmin",
        "roomRecord",
        "ingressAdmin",
        "agent",
        "recorder",
        "canManageAgentSession",
        "canUpdateOwnMetadata",
    ):
        assert claims["video"][name] is False, f"Participant must not receive {name}"
    raw = json.dumps(claims)
    assert (
        session.tenant_id not in raw and session.user_id not in raw and session.field_id not in raw
    )
    assert "roomConfig" not in claims and "sip" not in claims and "metadata" not in claims


async def test_token_does_not_outlive_the_durable_session_lease(gateway):
    now = int(time.time())
    session = replace(_session(), expires_at=now + 8)
    token = gateway.participant_token(session, now, 60)
    assert _payload(token)["exp"] <= session.expires_at


@pytest.mark.parametrize("ttl", [0, -1, True, 61, "60"])
async def test_invalid_or_excessive_ttl_never_issues_token(gateway, ttl):
    with pytest.raises(SessionError, match="session_not_joinable"):
        gateway.participant_token(_session(), int(time.time()), ttl)


@pytest.mark.parametrize("status", ["CLOSING", "CLOSED"])
async def test_closed_or_closing_session_never_issues_token(gateway, status):
    with pytest.raises(SessionError, match="session_not_joinable"):
        gateway.participant_token(replace(_session(), status=status), int(time.time()), 60)


async def test_clock_delay_past_the_lease_fails_closed(gateway):
    now = int(time.time())
    with pytest.raises(SessionError, match="session_expired"):
        gateway.participant_token(replace(_session(), expires_at=now), now, 60)


async def test_sdk_expiration_overshoot_is_rejected(gateway, monkeypatch):
    original = api.AccessToken.to_jwt

    def delayed(self):
        self.with_ttl(self.ttl + __import__("datetime").timedelta(seconds=100))
        return original(self)

    monkeypatch.setattr(api.AccessToken, "to_jwt", delayed)
    with pytest.raises(SessionError, match="livekit_token_unavailable"):
        gateway.participant_token(_session(), int(time.time()), 60)


async def test_create_room_uses_sdk_request_without_metadata_egress_or_agents(gateway):
    create = AsyncMock(return_value=api.Room())
    gateway._client._room = SimpleNamespace(create_room=create)
    session = _session()
    await gateway.create_room(session)
    request = create.call_args.args[0]
    assert isinstance(request, api.CreateRoomRequest)
    assert request.name == session.room_name and request.max_participants == 2
    assert request.empty_timeout == 30 and request.departure_timeout == 5
    assert not request.metadata and not request.agents and not request.HasField("egress")


async def test_only_typed_not_found_with_404_is_idempotent(gateway):
    delete = AsyncMock(
        side_effect=api.TwirpError(TwirpErrorCode.NOT_FOUND, "sensitive", status=404)
    )
    gateway._client._room = SimpleNamespace(delete_room=delete)
    await gateway.delete_room(_session().room_name)
    assert isinstance(delete.call_args.args[0], api.DeleteRoomRequest)


@pytest.mark.parametrize(
    "error",
    [
        api.TwirpError(TwirpErrorCode.PERMISSION_DENIED, "sensitive", status=403),
        api.TwirpError(TwirpErrorCode.NOT_FOUND, "sensitive", status=500),
        RuntimeError("sensitive-secret"),
    ],
)
async def test_delete_failures_do_not_acknowledge_cleanup_or_expose_errors(gateway, error):
    gateway._client._room = SimpleNamespace(delete_room=AsyncMock(side_effect=error))
    with pytest.raises(SessionError) as raised:
        await gateway.delete_room(_session().room_name)
    assert raised.value.code == "livekit_unavailable"
    assert "sensitive" not in str(raised.value)


async def test_readiness_query_is_narrow_and_returns_no_room_data(gateway):
    listing = AsyncMock(return_value=api.ListRoomsResponse())
    gateway._client._room = SimpleNamespace(list_rooms=listing)
    assert await gateway.ready() is True
    request = listing.call_args.args[0]
    assert isinstance(request, api.ListRoomsRequest)
    assert list(request.names) == ["sahool-realtime-readiness-probe"]
    listing.side_effect = RuntimeError("sensitive")
    assert await gateway.ready() is False


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?key=secret",
        "wss://example.com",
    ],
)
async def test_invalid_admin_url_is_rejected_before_creating_client(url):
    with pytest.raises(ValueError, match="Invalid LiveKit backend configuration"):
        LiveKitGateway(url, KEY, SECRET)


async def test_dispatch_uses_actual_sdk_request_and_opaque_scoped_metadata(gateway):
    session = _session()
    request_call = AsyncMock()
    gateway._client.agent_dispatch.create_dispatch = request_call
    nonce = "1" * 32
    await gateway.dispatch_agent(session, nonce)
    request = request_call.call_args.args[0]
    assert isinstance(request, api.CreateAgentDispatchRequest)
    assert request.agent_name == "sahool-agronomist"
    assert request.room == session.room_name
    assert json.loads(request.metadata) == {"session_id": session.session_id, "nonce": nonce}
    for private in (session.tenant_id, session.user_id, session.field_id, SECRET):
        assert private not in request.metadata
