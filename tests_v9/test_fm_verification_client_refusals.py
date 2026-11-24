"""field-management's verification client: which owner replies are unknown, refused or rejected.

The dispatcher settles a claimed delivery from the class of the error alone (fm_verification.py):
an unknown outcome may already be applied, so it is retried and counts an attempt; a receiver's
configuration refusal applied nothing and keeps the row open for an operator; a definitive
rejection is terminal. A proxy's error page must never be read as the receiver's verdict.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FM = ROOT / "services" / "field-management-service"
# Generated per run: no credential-shaped literal enters the history the secret scan re-reads.
ASSERTION_KEY = secrets.token_hex(24)


@pytest.fixture()
def client_module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.syspath_prepend(str(FM))
    sys.modules.pop("fm_verification_client", None)
    import fm_verification_client

    monkeypatch.setenv("VEGETATION_VERIFICATION_URL", "http://vegetation")
    monkeypatch.setenv("VEGETATION_VERIFICATION_SERVICE_TOKEN", secrets.token_hex(16))
    monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY", ASSERTION_KEY)
    monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "current")
    return fm_verification_client


def _reply(module, status, body=None, *, text=None):
    def handler(request):
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://vegetation")
    return module.VegetationVerificationClient(client)


def _error(module, status, body=None, *, text=None):
    client = _reply(module, status, body, text=text)
    with pytest.raises(module.VerificationRemoteError) as caught:
        asyncio.run(client.context("00000000-0000-0000-0000-000000000001", "urn:a:1"))
    return caught.value


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (404, "verification_bridge_disabled"),
        (503, "verification_service_credentials_unconfigured"),
        (503, "verification_service_token_not_dedicated"),
        (403, "invalid_task_service_token"),
        (403, "verification_caller_scope_invalid"),
        (403, "invalid_verification_tenant_assertion"),
    ],
)
def test_a_receiver_configuration_refusal_is_refused_not_unknown(client_module, status, detail):
    exc = _error(client_module, status, {"detail": detail})
    assert type(exc) is client_module.VerificationRemoteRefused
    assert (exc.status, exc.detail) == (status, detail)
    assert str(exc) == f"verification_remote_status:{status}:{detail}"


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (409, "aggregate_version_conflict"),
        (409, "verification_idempotency_key_reused_with_different_request"),
        (409, "verification_delivery_already_recorded"),
        (422, "verification_idempotency_key_invalid"),
        (422, [{"loc": ["body"], "msg": "field required"}]),
        (403, "verification_request_body_binding_mismatch"),
        (404, "anomaly not found"),
    ],
)
def test_a_definitive_owner_refusal_is_rejected(client_module, status, detail):
    exc = _error(client_module, status, {"detail": detail})
    assert type(exc) is client_module.VerificationRemoteRejected
    assert exc.status == status


@pytest.mark.parametrize(
    ("status", "body", "text"),
    [
        (503, None, "<html>upstream unavailable</html>"),
        (502, {"error": "bad gateway"}, None),
        (404, None, "<html>Not Found</html>"),
        (503, {"detail": "verification_anomaly_record_invalid"}, None),
        (500, {"detail": "Internal Server Error"}, None),
        (403, {"detail": "Forbidden"}, None),
        (422, None, "<html>Unprocessable</html>"),
        (409, {"error": "conflict"}, None),
    ],
)
def test_anything_else_stays_an_unknown_outcome(client_module, status, body, text):
    exc = _error(client_module, status, body, text=text)
    assert type(exc) is client_module.VerificationRemoteError


def test_an_unknown_detail_is_shown_only_as_a_short_plain_token(client_module):
    exc = _error(client_module, 503, {"detail": "<script>x</script> " + "y" * 200})
    reason = str(exc)
    assert reason.startswith("verification_remote_status:503:")
    shown = reason.removeprefix("verification_remote_status:503:")
    assert len(shown) <= 80
    assert set(shown) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-")


@pytest.mark.parametrize(
    "key_id",
    # From PR1598_ci_repairs.patch: padded, non-ASCII, tab and control-character ids too.
    ["", "  ", "a:b", "line\nbreak", "cr\rid", " current ", "مفتاح", "a\tb", "a\x1fb", "a\x7fb"],
)
def test_a_key_id_the_assertion_cannot_carry_is_not_configured(client_module, monkeypatch, key_id):
    monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", key_id)
    assert client_module.VegetationVerificationClient().configured() is False


@pytest.mark.parametrize("token", [" padded ", "رمز", "line\nbreak", "a\tb", "a\x7fb"])
def test_a_token_a_header_cannot_carry_is_not_configured(client_module, monkeypatch, token):
    # From the hospital's delta review of b7f4e3fa: a control character passes encode("ascii") and
    # used to fail inside the HTTP library after the claim, as an unknown outcome that costs an attempt.
    monkeypatch.setenv("VEGETATION_VERIFICATION_SERVICE_TOKEN", token)
    assert client_module.VegetationVerificationClient().configured() is False


@pytest.mark.parametrize("key", ["idem\nkey", "مفتاح", " idem "])
def test_an_idempotency_key_a_header_cannot_carry_is_refused_without_sending(client_module, key):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"persisted": True})

    transport = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://vegetation"
    )
    client = client_module.VegetationVerificationClient(transport)
    with pytest.raises(client_module.VerificationRemoteRefused) as caught:
        asyncio.run(
            client._request(
                "GET",
                "00000000-0000-0000-0000-000000000001",
                "urn:a:1",
                "verification-context",
                key=key,
            )
        )
    assert str(caught.value) == "verification_assertion_unsignable"
    assert sent == []


def test_a_signable_configuration_is_configured(client_module):
    assert client_module.VegetationVerificationClient().configured() is True


def test_a_rejection_shows_only_a_named_code_as_sent(client_module):
    named = _error(client_module, 403, {"detail": "verification_request_body_binding_mismatch"})
    assert str(named) == "verification_remote_status:403:verification_request_body_binding_mismatch"
    store = _error(client_module, 409, {"detail": "version conflict <b>" + "z" * 200})
    assert type(store) is client_module.VerificationRemoteRejected
    shown = str(store).removeprefix("verification_remote_status:409:")
    assert len(shown) <= 80 and "<" not in shown and " " not in shown


@pytest.mark.parametrize("tenant", ["malformed:tenant", "مستأجر"])
def test_an_unsignable_request_is_refused_without_sending(client_module, tenant):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"persisted": True})

    transport = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://vegetation"
    )
    client = client_module.VegetationVerificationClient(transport)
    with pytest.raises(client_module.VerificationRemoteRefused) as caught:
        asyncio.run(client.context(tenant, "urn:a:1"))
    assert str(caught.value) == "verification_assertion_unsignable"
    assert sent == []
