"""Startup cannot turn an unconfigured SFU into an admitted media endpoint."""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/realtime-session"))

from realtime_session.session_runtime import create_app  # noqa: E402

# Keep other services' legacy main imports independent of this test module.
sys.path.remove(str(Path(__file__).resolve().parents[1] / "services/realtime-session"))

pytestmark = [pytest.mark.unit, pytest.mark.security]


def test_startup_requires_explicit_media_hosting_trust(monkeypatch):
    monkeypatch.setenv("SAHOOL_REALTIME_ENABLED", "1")
    monkeypatch.delenv("SAHOOL_REALTIME_MEDIA_TRUST", raising=False)
    with pytest.raises(RuntimeError, match="self-hosted"):
        with TestClient(create_app()):
            pytest.fail("misconfigured service started")


def test_startup_requires_separate_sfu_admission_configuration(monkeypatch):
    monkeypatch.setenv("SAHOOL_REALTIME_ENABLED", "1")
    monkeypatch.setenv("SAHOOL_REALTIME_MEDIA_TRUST", "self_hosted")
    monkeypatch.delenv("LIVEKIT_AUTO_CREATE_DISABLED", raising=False)
    with pytest.raises(RuntimeError, match="auto_create"):
        with TestClient(create_app()):
            pytest.fail("service started without SFU admission configuration")


async def test_invalid_input_does_not_echo_an_input_credential():
    secret = "synthetic-bearer-do-not-echo"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/realtime/sessions",
            headers={"Authorization": "Bearer test"},
            json={"field_id": "field-a", "consent": True, "api_secret": secret},
        )
    assert response.status_code == 422, "untrusted fields must be rejected"
    assert secret not in response.text, "validation errors must not echo credentials"
