"""Platform alert push goes through FCM HTTP v1 (shared.fcm), never the legacy endpoint.

Copilot on #997: ``shared/fcm.py`` landed with credential and receipt validation, but the
platform alert path (``api.alert_senders.real_channel_sender``) still posted to
``fcm.googleapis.com/fcm/send`` with ``FCM_SERVER_KEY`` — every platform-generated push
alert bypassed the new validation. These cases pin the wiring with mocked HTTP.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from shared import fcm
from tests_v9.fcm_fixture import service_account_json

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
SEND_URI = "https://fcm.googleapis.com/v1/projects/unit-project/messages:send"
LEGACY_URI = "https://fcm.googleapis.com/fcm/send"


@pytest.fixture
def senders(monkeypatch):
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
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    from api import alert_delivery, alert_senders

    return alert_delivery, alert_senders


def _push(alert_delivery):
    return alert_delivery.ChannelMessage(
        channel=alert_delivery.CHANNEL_PUSH,
        severity="warning",
        recipient="device-token",
        title_ar="تنبيه",
        body_ar="نصّ",
    )


def test_legacy_server_key_alone_does_not_configure_push(senders, monkeypatch, respx_mock):
    alert_delivery, alert_senders = senders
    monkeypatch.setenv("FCM_SERVER_KEY", "legacy-is-retired")
    channel, ok, detail = alert_senders.real_channel_sender(_push(alert_delivery))
    assert (channel, ok) == (alert_delivery.CHANNEL_PUSH, False)
    assert "logged_not_sent" in detail
    assert len(respx_mock.calls) == 0
    assert not hasattr(alert_senders, "FCM_SERVER_KEY")


def test_push_is_delivered_through_fcm_v1_with_a_named_receipt(senders, monkeypatch, respx_mock):
    alert_delivery, alert_senders = senders
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", service_account_json())
    respx_mock.post(fcm.TOKEN_URI).respond(
        200, json={"access_token": "synthetic-oauth", "expires_in": 3600, "token_type": "Bearer"}
    )
    legacy = respx_mock.post(LEGACY_URI).respond(200, json={"success": 1})
    message = respx_mock.post(SEND_URI).respond(
        200, json={"name": "projects/unit-project/messages/accepted-1"}
    )
    channel, ok, detail = alert_senders.real_channel_sender(_push(alert_delivery))
    assert (channel, ok) == (alert_delivery.CHANNEL_PUSH, True)
    assert "fcm_v1" in detail
    assert legacy.call_count == 0
    assert message.call_count == 1
    assert message.calls[0].request.headers["authorization"] == "Bearer synthetic-oauth"
    body = json.loads(message.calls[0].request.content)["message"]
    assert body["token"] == "device-token"
    assert body["notification"] == {"title": "تنبيه", "body": "نصّ"}


def test_unnamed_receipt_is_not_reported_as_delivered(senders, monkeypatch, respx_mock):
    alert_delivery, alert_senders = senders
    monkeypatch.setenv("FCM_CREDENTIALS_JSON", service_account_json())
    respx_mock.post(fcm.TOKEN_URI).respond(
        200, json={"access_token": "synthetic", "expires_in": 3600, "token_type": "Bearer"}
    )
    respx_mock.post(SEND_URI).respond(200, json={})
    channel, ok, detail = alert_senders.real_channel_sender(_push(alert_delivery))
    assert (channel, ok) == (alert_delivery.CHANNEL_PUSH, False)
    assert "not_accepted" in detail
