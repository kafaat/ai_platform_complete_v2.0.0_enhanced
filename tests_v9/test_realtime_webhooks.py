"""Signed receipt ingestion; events cannot become session/lease authority."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest

api = pytest.importorskip("livekit.api")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/realtime-session"))
from realtime_session.session_runtime import create_app  # noqa: E402
from realtime_session.webhooks import WebhookReceiptStore  # noqa: E402

pytestmark = pytest.mark.unit
KEY = "webhook-fixture"
SECRET = "receipt-fixture-" * 3


def signed(body: bytes, secret=SECRET):
    return (
        api.AccessToken(KEY, secret)
        .with_sha256(base64.b64encode(hashlib.sha256(body).digest()).decode())
        .to_jwt()
    )


def payload(event_id="ev-1", **extra):
    return json.dumps(
        {
            "id": event_id,
            "event": "room_finished",
            "createdAt": "1",
            "room": {"name": "unknown-room", "metadata": "must-not-persist"},
            **extra,
        },
        separators=(",", ":"),
    ).encode()


@pytest.fixture
async def service(tmp_path):
    app = create_app()
    store = WebhookReceiptStore(str(tmp_path / "receipts.sqlite"))
    await store.initialize()
    app.state.webhook_receipts = store
    app.state.webhook_receiver = api.WebhookReceiver(api.TokenVerifier(KEY, SECRET))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, store


async def post(client, body, token=None):
    return await client.post(
        "/api/v1/realtime/hooks/livekit",
        content=body,
        headers={"Authorization": token or signed(body)},
    )


@pytest.mark.asyncio
async def test_verified_unknown_room_is_acknowledged_without_session_service(service):
    client, _ = service
    r = await post(client, payload())
    assert r.status_code == 200
    assert r.json() == {"accepted": True, "duplicate": False}
    assert r.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_duplicate_and_out_of_order_hints_are_idempotent(service):
    client, _ = service
    body = payload()
    assert (await post(client, body)).status_code == 200
    assert (await post(client, body)).json()["duplicate"] is True
    assert (await post(client, payload("older", createdAt="0"))).status_code == 200


@pytest.mark.asyncio
async def test_same_event_identity_with_changed_signed_body_is_conflict(service):
    client, _ = service
    await post(client, payload())
    r = await post(client, payload(event="participant_left"))
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "webhook_event_conflict"


@pytest.mark.asyncio
async def test_receipt_storage_contains_no_raw_payload_or_metadata(service):
    client, store = service
    await post(client, payload())
    with sqlite3.connect(store.path) as db:
        assert [r[1] for r in db.execute("PRAGMA table_info(realtime_hook_receipts)")] == [
            "event_id",
            "event_type",
            "room_name",
            "created_at",
            "payload_digest",
        ]
        row = db.execute("SELECT * FROM realtime_hook_receipts").fetchone()
    assert row[:4] == ("ev-1", "room_finished", "unknown-room", 1)
    assert row[4] == hashlib.sha256(payload()).hexdigest()
    assert "must-not-persist" not in Path(store.path).read_bytes().decode(errors="ignore")


@pytest.mark.asyncio
async def test_raw_body_tampering_is_rejected(service):
    client, _ = service
    original = payload()
    r = await post(client, original + b" ", signed(original))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_signing_key_is_rejected_without_echo(service):
    client, _ = service
    r = await post(client, payload(), signed(payload(), "wrong-secret-fixture-at-least-thirty-two"))
    assert r.status_code == 401
    assert SECRET not in r.text and "must-not-persist" not in r.text


@pytest.mark.asyncio
async def test_unsigned_request_is_rejected(service):
    client, _ = service
    assert (
        await client.post("/api/v1/realtime/hooks/livekit", content=payload())
    ).status_code == 401


@pytest.mark.asyncio
async def test_oversized_body_is_rejected_before_verification(service):
    client, _ = service
    assert (await post(client, b"x" * 4097)).status_code == 413


@pytest.mark.asyncio
async def test_signed_invalid_json_is_rejected(service):
    client, _ = service
    assert (await post(client, b"not-json")).status_code == 401


@pytest.mark.asyncio
async def test_signed_missing_event_id_is_rejected(service):
    client, _ = service
    assert (await post(client, payload(event_id=""))).status_code == 422


@pytest.mark.asyncio
async def test_concurrent_duplicate_receipts_are_atomic(service):
    _, store = service
    results = await asyncio.gather(
        *[store.record("same", "room_finished", "room", 1, "a" * 64) for _ in range(12)]
    )
    assert results.count(True) == 1
    assert results.count(False) == 11


@pytest.mark.asyncio
async def test_receipts_survive_restart(service):
    client, store = service
    await post(client, payload())
    reopened = WebhookReceiptStore(store.path)
    await reopened.initialize()
    assert (
        await reopened.record(
            "ev-1", "room_finished", "unknown-room", 1, hashlib.sha256(payload()).hexdigest()
        )
        is False
    )


@pytest.mark.asyncio
async def test_disabled_service_does_not_accept_unverified_events():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await post(c, payload())).status_code == 503
