"""Plaintext origins are only trusted on internal networks.

The broker origin receives the worker secret and the AI/TTS origins receive users' bearer
JWTs, so http:// (and ws:// for LiveKit) is accepted only for loopback, single-label internal
service names (compose/k8s style, e.g. ``sahool-platform``) and ``*.railway.internal``.
Everything else must use TLS.
"""

from __future__ import annotations

import pytest
from realtime_agent.config import origin
from realtime_agent.providers import HttpVoiceProviders, VoiceProviderError, _origin

pytestmark = pytest.mark.unit

PLAINTEXT_EXTERNAL = [
    "http://example.com",
    "http://frontend.example.com",
    "http://203.0.113.7",
    "http://10.0.0.5:8080",
    "http://[2001:db8::1]",
    "http://2130706433",
    "http://0x7f000001",
    "http://sahool-platform.evil.test",
    "http://railway.internal.evil.test",
]

PLAINTEXT_INTERNAL = [
    "http://localhost:3000",
    "http://127.0.0.1:8080",
    "http://[::1]:8080",
    "http://sahool-platform:8000",
    "http://frontend",
    "http://realtime-session.railway.internal:8080",
    "http://LOCALHOST.",
]


@pytest.mark.parametrize("value", PLAINTEXT_EXTERNAL)
def test_config_origin_rejects_plaintext_external_host(value):
    with pytest.raises(ValueError, match="invalid_trusted_origin"):
        origin(value)


@pytest.mark.parametrize("value", PLAINTEXT_EXTERNAL)
def test_config_websocket_origin_rejects_plaintext_external_host(value):
    with pytest.raises(ValueError, match="invalid_trusted_origin"):
        origin(value.replace("http://", "ws://", 1), websocket=True)


@pytest.mark.parametrize("value", PLAINTEXT_EXTERNAL)
def test_provider_origin_rejects_plaintext_external_host(value):
    with pytest.raises(VoiceProviderError, match="voice_provider_origin_invalid"):
        _origin(value)
    with pytest.raises(VoiceProviderError, match="voice_provider_origin_invalid"):
        HttpVoiceProviders("https://frontend.example.com", value)


@pytest.mark.parametrize("value", PLAINTEXT_INTERNAL)
def test_plaintext_internal_hosts_are_still_accepted(value):
    assert origin(value) == value.rstrip("/")
    assert origin(value.replace("http://", "ws://", 1), websocket=True)
    assert _origin(value) == value.rstrip("/")


@pytest.mark.parametrize("value", ["https://example.com", "https://203.0.113.7:8443"])
def test_tls_external_hosts_are_accepted(value):
    assert origin(value) == value
    assert origin(value.replace("https://", "wss://", 1), websocket=True)
    assert _origin(value) == value
