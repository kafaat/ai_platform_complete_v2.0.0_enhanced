"""Real Opus/WebSocket exchange and lease rejection; no cloud, models or hardware."""

import asyncio
import struct
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from realtime_agent.xiaozhi_codec import OpusCodec, pack_audio, unpack_audio
from starlette.websockets import WebSocketDisconnect
from test_speech import wav

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "realtime-session"))
from realtime_session.contracts import Principal, SessionError
from realtime_session.xiaozhi_gateway import DeviceConversation, create_gateway
from realtime_session.xiaozhi_leases import DeviceLeases

DEVICE = "aa:bb:cc:dd:ee:ff"
CLIENT = "00000000-0000-4000-8000-000000000001"


class Authority:
    revoked = False
    local = True
    blocked_field = False
    calls = 0

    async def verified_identity(self, bearer):
        self.calls += 1
        if self.revoked:
            raise SessionError(401, "authentication_required")
        principal = Principal("tenant-a", "user-a" if bearer == "user-token" else "other-user")
        return principal, {
            "contract": "sahool.ai_policy_envelope",
            "contract_version": 2,
            "version": "v52",
            "tenant_id": "tenant-a",
            "policy_mode": "local_only" if self.local else "cloud",
            "external_llm_allowed": False,
            "external_tts_allowed": False,
            "allowed_tools": ["actuator.execute"],
        }

    async def identity(self, bearer):
        return (await self.verified_identity(bearer))[0]

    async def authorize_field(self, bearer, principal, field_id):
        if self.blocked_field or field_id != "field-a":
            raise SessionError(403, "access_denied")


class Recognizer:
    calls = 0

    async def transcribe(self, pcm, sample_rate):
        assert sample_rate == 16000 and pcm and len(pcm) % 2 == 0
        self.calls += 1
        return "ما حالة الحقل؟"


class Providers:
    calls = 0

    async def answer(self, context, question):
        assert context["field_id"] == "field-a" and context["tenant_id"] == "tenant-a"
        self.calls += 1
        return "اقرأ القياسات من لوحة سهول."

    async def synthesize(self, context, answer):
        return wav()


def enrollment(**extra):
    return {
        "field_id": "field-a",
        "device_id": DEVICE,
        "client_id": CLIENT,
        "consent": True,
        "voice_consent": True,
        **extra,
    }


def headers(token, version=1):
    return {
        "Authorization": "Bearer " + token,
        "Device-Id": DEVICE,
        "Client-Id": CLIENT,
        "Protocol-Version": str(version),
    }


def hello(version=1):
    return {
        "type": "hello",
        "version": version,
        "transport": "websocket",
        "audio_params": {
            "format": "opus",
            "sample_rate": 16000,
            "channels": 1,
            "frame_duration": 60,
        },
    }


@pytest.fixture
def gateway():
    authority, recognizer, providers = Authority(), Recognizer(), Providers()
    registry = DeviceLeases(authority)
    app = create_gateway(
        leases=registry,
        recognizer=recognizer,
        providers=providers,
        public_url="wss://testserver/xiaozhi/v1/",
    )
    with TestClient(app, base_url="https://testserver") as client:
        yield client, registry, authority, recognizer, providers


@pytest.mark.parametrize("version", [1, 2, 3])
def test_real_opus_voice_exchange_and_one_connection_lease(gateway, version):
    client, registry, authority, recognizer, providers = gateway
    response = client.post(
        "/api/v1/realtime/xiaozhi/leases",
        json=enrollment(),
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    with client.websocket_connect(
        "wss://testserver/xiaozhi/v1/", headers=headers(data["token"], version)
    ) as ws:
        ws.send_json(hello(version))
        greeting = ws.receive_json()
        assert greeting["audio_params"]["sample_rate"] == 48000
        sid = greeting["session_id"]
        ws.send_json({"type": "listen", "state": "start", "mode": "manual", "session_id": sid})
        packet = OpusCodec.encode(b"\0\0" * 2880)[0]
        ws.send_bytes(pack_audio(packet, version))
        ws.send_json({"type": "listen", "state": "stop", "session_id": sid})
        assert ws.receive_json()["state"] == "start"
        output = []
        while True:
            message = ws.receive()
            if "bytes" in message:
                output.append(unpack_audio(message["bytes"], version))
            else:
                import json

                assert json.loads(message["text"])["state"] == "stop"
                break
        assert output and OpusCodec().decode(output[0])
        assert recognizer.calls == providers.calls == 1
        assert authority.calls >= 5
    assert not registry._leases
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("wss://testserver/xiaozhi/v1/", headers=headers(data["token"])),
    ):
        pass


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"consent": False}, 403),
        ({"voice_consent": False}, 403),
        ({"voice_consent": "true"}, 422),
        ({"field_id": "field-b"}, 403),
        ({"device_id": "x" * 17}, 422),
        ({"tenant_id": "other"}, 422),
    ],
)
def test_enrollment_requires_explicit_consent_and_canonical_field(gateway, change, expected):
    client, *_ = gateway
    response = client.post(
        "/api/v1/realtime/xiaozhi/leases",
        json=enrollment(**change),
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == expected


def test_enrollment_requires_user_bearer_and_local_policy(gateway):
    client, _, authority, *_ = gateway
    assert client.post("/api/v1/realtime/xiaozhi/leases", json=enrollment()).status_code == 401
    authority.local = False
    assert (
        client.post(
            "/api/v1/realtime/xiaozhi/leases",
            json=enrollment(),
            headers={"Authorization": "Bearer user-token"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "override",
    [
        {"Device-Id": "00:00:00:00:00:00"},
        {"Client-Id": "bad"},
        {"Origin": "https://untrusted.invalid"},
        {"Authorization": "Bearer user-token"},
    ],
)
def test_socket_requires_bound_ephemeral_token(gateway, override):
    client, *_ = gateway
    data = client.post(
        "/api/v1/realtime/xiaozhi/leases",
        json=enrollment(),
        headers={"Authorization": "Bearer user-token"},
    ).json()
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "wss://testserver/xiaozhi/v1/", headers={**headers(data["token"]), **override}
        ),
    ):
        pass


@pytest.mark.parametrize(
    "bad_hello",
    [
        {**hello(), "version": 4},
        {**hello(), "version": True},
        {**hello(), "audio_params": {"format": "pcm", "sample_rate": 16000}},
    ],
)
def test_unsupported_hello_cannot_reach_stt(gateway, bad_hello):
    client, _, _, recognizer, _ = gateway
    data = client.post(
        "/api/v1/realtime/xiaozhi/leases",
        json=enrollment(),
        headers={"Authorization": "Bearer user-token"},
    ).json()
    with client.websocket_connect(
        "wss://testserver/xiaozhi/v1/", headers=headers(data["token"])
    ) as ws:
        ws.send_json(bad_hello)
        assert ws.receive()["type"] == "websocket.close"
    assert recognizer.calls == 0


@pytest.mark.asyncio
async def test_revocation_field_change_expiry_and_no_foreign_close():
    authority = Authority()
    now = [1000.0]
    registry = DeviceLeases(authority, clock=lambda: now[0])
    data = await registry.create("user-token", **enrollment())
    lease = await registry.claim(data["token"], DEVICE, CLIENT)
    with pytest.raises(SessionError, match="device_binding_rejected"):
        await registry.claim(data["token"], DEVICE, CLIENT)
    with pytest.raises(SessionError):
        await registry.close_owned("other-token", data["session_id"])
    authority.blocked_field = True
    with pytest.raises(SessionError):
        await registry.fetch(lease)
    assert lease.stop.is_set() and lease.bearer == "" and not registry._leases
    authority.blocked_field = False
    data = await registry.create("user-token", **enrollment())
    now[0] += 301
    with pytest.raises(SessionError):
        await registry.claim(data["token"], DEVICE, CLIENT)
    registry.close()


@pytest.mark.asyncio
async def test_no_mcp_action_wake_text_or_clips_reach_models():
    authority, recognizer, providers = Authority(), Recognizer(), Providers()
    registry = DeviceLeases(authority)
    data = await registry.create("user-token", **enrollment())
    lease = await registry.claim(data["token"], DEVICE, CLIENT)
    conversation = DeviceConversation(None, registry, lease, recognizer, providers)
    conversation.codec = OpusCodec()
    await conversation.control(
        {
            "type": "mcp",
            "session_id": lease.session_id,
            "payload": {"method": "tools/call", "params": {"name": "pump.open"}},
        }
    )
    await conversation.control(
        {"type": "listen", "state": "detect", "session_id": lease.session_id, "text": "شغل المضخة"}
    )
    await conversation.audio(OpusCodec.encode(b"\0\0" * 2880)[0])
    assert recognizer.calls == providers.calls == 0
    await conversation.runner.close()
    registry.close()


@pytest.mark.parametrize("version", [1, 2, 3])
def test_binary_headers_and_declared_lengths_are_validated(version):
    packet = pack_audio(b"opus", version, 123)
    assert unpack_audio(packet, version) == b"opus"
    if version > 1:
        with pytest.raises(ValueError):
            unpack_audio(packet + b"x", version)
        with pytest.raises(ValueError):
            unpack_audio(packet[:2], version)
    with pytest.raises(ValueError):
        unpack_audio(b"x" * 5000, version)
    with pytest.raises(ValueError):
        unpack_audio(b"", version)


def test_disabled_gateway_and_plaintext_enrollment_are_refused(gateway):
    with TestClient(create_gateway(), base_url="https://testserver") as client:
        assert client.get("/readyz").status_code == 503
    client, *_ = gateway
    assert (
        client.post(
            "http://testserver/api/v1/realtime/xiaozhi/leases",
            json=enrollment(),
            headers={"Authorization": "Bearer user-token"},
        ).status_code
        == 403
    )
