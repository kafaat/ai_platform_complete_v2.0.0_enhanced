"""Exercise OAuth signing and FCM receipts through mocked HTTP, not live devices."""

import json
from urllib.parse import parse_qs

import httpx
import pytest
from jose import jwt

from shared import fcm
from tests_v9.fcm_fixture import service_account_json

pytestmark = pytest.mark.unit
SEND_URI = "https://fcm.googleapis.com/v1/projects/unit-project/messages:send"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in (
        "FCM_CREDENTIALS_JSON",
        "FCM_SERVER_KEY",
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(fcm, "_token_cache", None)


def test_only_valid_explicit_credentials_activate(monkeypatch):
    monkeypatch.setenv("FCM_SERVER_KEY", "legacy-is-retired")
    assert not fcm.fcm_push_active()
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", service_account_json())
    assert fcm.fcm_push_active()


@pytest.mark.parametrize(
    "mutation",
    [
        {"token_uri": "http://169.254.169.254/metadata"},
        {"project_id": "../wrong"},
        {"private_key": "broken"},
        {"type": "authorized_user"},
        {"client_email": "invalid"},
    ],
)
@pytest.mark.asyncio
async def test_invalid_credentials_never_make_network_requests(monkeypatch, respx_mock, mutation):
    data = json.loads(service_account_json()) | mutation
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", json.dumps(data))
    assert not fcm.fcm_push_active()
    assert not await fcm.send_push("device-token", "title", "body")
    assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_signed_oauth_and_named_message_receipt(monkeypatch, respx_mock):
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", service_account_json())
    oauth = respx_mock.post(fcm.TOKEN_URI).respond(
        200, json={"access_token": "synthetic-oauth", "expires_in": 3600, "token_type": "Bearer"}
    )
    message = respx_mock.post(SEND_URI).respond(
        200, json={"name": "projects/unit-project/messages/accepted-1"}
    )
    assert await fcm.send_push("device-token", "title", "body")
    assert await fcm.send_push("device-token", "title", "body")
    assert oauth.call_count == 1
    assertion = parse_qs(oauth.calls[0].request.content.decode())["assertion"][0]
    account = fcm.credentials()
    claims = jwt.decode(
        assertion, account.private_key, algorithms=["RS256"], audience=fcm.TOKEN_URI
    )
    assert claims["iss"] == account.client_email and claims["scope"] == fcm.SCOPE
    assert message.calls[0].request.headers["authorization"] == "Bearer synthetic-oauth"
    assert json.loads(message.calls[0].request.content)["message"]["token"] == "device-token"


@pytest.mark.parametrize(
    "status,payload",
    [(200, {}), (200, {"name": "wrong-project"}), (401, {"error": "denied"}), (503, {})],
)
@pytest.mark.asyncio
async def test_provider_failure_or_empty_receipt_is_not_success(
    monkeypatch, respx_mock, status, payload
):
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", service_account_json())
    respx_mock.post(fcm.TOKEN_URI).respond(
        200, json={"access_token": "synthetic", "expires_in": 3600, "token_type": "Bearer"}
    )
    respx_mock.post(SEND_URI).respond(status, json=payload)
    assert not await fcm.send_push("device-token", "title", "body")
    if status == 401:
        assert fcm._token_cache is None


@pytest.mark.asyncio
async def test_oauth_rejection_does_not_send(monkeypatch, respx_mock):
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", service_account_json())
    respx_mock.post(fcm.TOKEN_URI).respond(403, json={"error": "invalid_grant"})
    assert not await fcm.send_push("device-token", "title", "body")
    assert len(respx_mock.calls) == 1
