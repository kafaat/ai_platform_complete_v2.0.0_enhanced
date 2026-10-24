import asyncio
import json
import time

import httpx
import pytest
from realtime_agent.context import BrokerLease, LeaseRejected, parse_job, validate_context

SID = "a" * 32
NONCE = "b" * 32


def context(**updates):
    value = {
        "session_id": SID,
        "room_name": "room-opaque",
        "participant_identity": "participant-" + SID,
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "field_id": "field-a",
        "expires_at": int(time.time()) + 600,
        "bearer": "private-user-credential",
        "policy_envelope": {
            "contract": "sahool.ai_policy_envelope",
            "contract_version": 2,
            "version": "v52",
            "tenant_id": "tenant-a",
            "policy_mode": "local_only",
            "external_llm_allowed": False,
            "external_tts_allowed": False,
            "allowed_tools": [],
        },
    }
    value.update(updates)
    return value


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"session_id": SID},
        {"session_id": SID, "nonce": NONCE, "bearer": "bad"},
        {"session_id": "../../bad", "nonce": NONCE},
        {"session_id": SID, "nonce": "x" * 32},
        [],
    ],
)
def test_dispatch_metadata_rejects_credentials_and_untrusted_identifiers(value):
    with pytest.raises(LeaseRejected):
        parse_job(json.dumps(value))


def test_exact_dispatch_assignment_and_unprintable_bearer():
    assert parse_job(json.dumps({"session_id": SID, "nonce": NONCE})) == (SID, NONCE)
    parsed = validate_context(context(), SID)
    assert "private-user-credential" not in repr(parsed)
    assert parsed.provider_context()["bearer"] == "private-user-credential"


@pytest.mark.parametrize(
    "updates",
    [
        {"session_id": "different"},
        {"participant_identity": "agent"},
        {"expires_at": True},
        {"expires_at": 0},
        {"expires_at": float("inf")},
        {"expires_at": time.time() + 3605},
        {"bearer": "a\nb"},
        {"tenant_id": "tenant-b"},
        {"policy_envelope": {}},
        {"user_id": ""},
    ],
)
def test_context_rejects_cross_identity_expired_and_missing_policy(updates):
    with pytest.raises(LeaseRejected):
        validate_context(context(**updates), SID)


@pytest.mark.parametrize(
    "change",
    [
        {"policy_mode": "full_external"},
        {"contract_version": True},
        {"external_llm_allowed": True},
        {"external_tts_allowed": True},
        {"version": "future"},
        {"allowed_tools": None},
    ],
)
def test_only_current_local_policy_is_admitted(change):
    value = context()
    value["policy_envelope"].update(change)
    with pytest.raises(LeaseRejected):
        validate_context(value, SID)


@pytest.mark.asyncio
async def test_broker_uses_fixed_origin_headers_and_detects_assignment_swap():
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json=context(field_id="other") if len(requests) > 1 else context()
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        lease = BrokerLease("http://sessions", "secret" * 8, SID, NONCE, client=client)
        await lease.fetch()
        with pytest.raises(LeaseRejected, match="assignment_changed"):
            await lease.fetch()
    assert requests[0].url.path == "/api/v1/realtime/internal/jobs/" + SID
    assert requests[0].headers["X-Realtime-Job-Nonce"] == NONCE
    assert requests[0].headers["X-Realtime-Worker-Token"] == "secret" * 8
    assert "Authorization" not in requests[0].headers


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 503])
async def test_any_non_success_context_stops_the_job(status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as client:
        lease = BrokerLease("http://sessions", "s" * 32, SID, NONCE, client=client)
        with pytest.raises(LeaseRejected):
            await lease.fetch()


@pytest.mark.asyncio
async def test_broker_caps_oversized_body_and_total_elapsed_time(monkeypatch):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 40000))
    ) as client:
        with pytest.raises(LeaseRejected, match="context_too_large"):
            await BrokerLease("http://sessions", "s" * 32, SID, NONCE, client=client).fetch()
    original_timeout = asyncio.timeout
    monkeypatch.setattr(
        "realtime_agent.context.asyncio.timeout", lambda seconds: original_timeout(0.02)
    )

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=context())

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
        with pytest.raises(LeaseRejected, match="context_unavailable"):
            await BrokerLease("http://sessions", "s" * 32, SID, NONCE, client=client).fetch()
