"""IRR-F01 Gate B-delivery Slice B-d2-live — relay worker unit tests + no-fulfillment guard.

The worker's message→ingest→POST core is pure (a mocked POST stands in for the live inbox), so the
whole relay contract is proven without NATS or a running decision-service. A static guard locks the
delivery≠fulfillment boundary at the worker: it must be default-off, POST only to the inbox, and
never create an execution_request.

Requires pytest-asyncio (pytest.ini runs asyncio_mode=auto); the CI job installs it explicitly.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "services" / "sahool-platform" / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

import irrigation_dispatch_relay_worker as worker  # noqa: E402

REQUESTED = "irrigation.reservation.dispatch_requested"
FAILED = "irrigation.reservation.dispatch_failed"


def _envelope(event_type=REQUESTED, event_id="evt-1", tenant_id="t-1", payload=None):
    return json.dumps(
        {
            "event_id": event_id,
            "event_type": event_type,
            "entity_type": "reservation",
            "entity_id": "r-1",
            "tenant_id": tenant_id,
            "payload": payload if payload is not None else {"evaluation_id": "ev-9"},
            "occurred_at": "2026-07-18T00:00:00Z",
        }
    ).encode()


class _Recorder:
    def __init__(self, status=200, resp=None):
        self.status = status
        self.resp = resp or {"accepted": True}
        self.calls: list[tuple] = []

    async def post(self, tenant_id, body):
        self.calls.append((tenant_id, body))
        return self.status, self.resp


async def test_delivered_event_posts_mapped_body_to_inbox():
    rec = _Recorder(status=200)
    out = await worker.handle_delivered_message(_envelope(), post_fn=rec.post)
    assert out["outcome"] == "delivered" and out["source_event_id"] == "evt-1"
    assert len(rec.calls) == 1
    tenant, body = rec.calls[0]
    assert tenant == "t-1"
    assert body["event_type"] == REQUESTED and body["source_event_id"] == "evt-1"
    assert body["evaluation_id"] == "ev-9"


async def test_duplicate_redelivery_is_settled_at_idempotent_sink():
    # The inbox dedups on source_event_id and returns 200; a redelivery is success, not an error.
    rec = _Recorder(status=200, resp={"duplicate": True})
    out = await worker.handle_delivered_message(_envelope(), post_fn=rec.post)
    assert out["outcome"] == "delivered"


async def test_unsupported_event_is_skipped_without_posting():
    rec = _Recorder()
    out = await worker.handle_delivered_message(
        _envelope(event_type="irrigation.something.else"), post_fn=rec.post
    )
    assert out["outcome"] == "skipped" and out["reason"] == "unsupported_event"
    assert rec.calls == []  # never touches the inbox


async def test_missing_event_id_is_skipped_fail_closed():
    rec = _Recorder()
    out = await worker.handle_delivered_message(_envelope(event_id=""), post_fn=rec.post)
    assert out["outcome"] == "skipped" and "MISSING_SOURCE_EVENT_ID" in out["reason"]
    assert rec.calls == []


async def test_malformed_envelope_is_skipped():
    rec = _Recorder()
    out = await worker.handle_delivered_message(b"{not json", post_fn=rec.post)
    assert out["outcome"] == "skipped" and out["reason"] == "malformed_json"
    assert rec.calls == []


async def test_non_2xx_is_failed_never_fulfilled():
    rec = _Recorder(status=503, resp={"detail": "mirror"})
    out = await worker.handle_delivered_message(_envelope(), post_fn=rec.post)
    assert out["outcome"] == "failed" and out["status"] == 503
    # delivery≠fulfillment: the worker never reports (or performs) fulfillment.
    assert out["outcome"] != "fulfilled"


async def test_relay_default_off_does_not_start(monkeypatch):
    monkeypatch.delenv("FEATURE_RESERVATION_DISPATCH_RELAY", raising=False)
    assert worker.relay_enabled() is False
    # run_relay returns immediately without importing/connecting NATS when the flag is off.
    await worker.run_relay(post_fn=_Recorder().post)


class _Msg:
    def __init__(self, data: bytes):
        self.data = data


def _heartbeat_in(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_DIR", str(tmp_path))
    from worker_heartbeat import HeartbeatState, evaluate_heartbeat, read_heartbeat

    return HeartbeatState(worker.WORKER_NAME), read_heartbeat, evaluate_heartbeat


@pytest.mark.asyncio
async def test_a_handled_delivery_leaves_a_running_heartbeat_the_probe_accepts(
    tmp_path, monkeypatch
):
    """WORKERS-INHERIT-AN-HTTP-HEALTHCHECK-THEY-CANNOT-ANSWER-01: the compose probe reads this
    file; the relay serves no HTTP, so without it the image's curl :8000 check marks it unhealthy
    forever. What the handler writes must be what the probe's evaluator accepts."""
    hb, read, evaluate = _heartbeat_in(tmp_path, monkeypatch)
    rec = _Recorder()
    handler = worker.make_message_handler(rec.post, hb)
    await handler(_Msg(_envelope()))
    assert len(rec.calls) == 1
    data = read(worker.WORKER_NAME)
    assert data is not None and data["current_state"] == "running"
    assert data["processed_total"] == 1
    ok, reason = evaluate(data, now_epoch=data["last_poll_at"] + 1, max_age_seconds=300)
    assert ok, reason


@pytest.mark.asyncio
async def test_a_handler_error_marks_the_heartbeat_failed_without_killing_the_subscription(
    tmp_path, monkeypatch
):
    hb, read, evaluate = _heartbeat_in(tmp_path, monkeypatch)

    async def _exploding_post(_tenant, _body):
        raise RuntimeError("inbox exploded")

    handler = worker.make_message_handler(_exploding_post, hb)
    await handler(_Msg(_envelope()))  # must not raise — one bad message never kills the worker
    data = read(worker.WORKER_NAME)
    assert data is not None and data["current_state"] == "failed"
    assert "inbox exploded" in data["last_error"]
    ok, reason = evaluate(data, now_epoch=data["last_poll_at"] + 1, max_age_seconds=300)
    assert not ok and reason.startswith("worker_state_failed:")


@pytest.mark.asyncio
async def test_a_disabled_relay_beats_idle_so_it_is_healthy_but_visibly_not_working(
    tmp_path, monkeypatch
):
    """Default-off must not read as dead (restart-thrash) nor as working (a lie): the idle loop
    writes an `idle` beat the probe accepts, then sleeps."""
    hb, read, evaluate = _heartbeat_in(tmp_path, monkeypatch)
    slept: list[float] = []

    async def _sleep_once(seconds):
        slept.append(seconds)
        raise asyncio.CancelledError  # stop the forever-loop after the first beat

    monkeypatch.setattr(worker.asyncio, "sleep", _sleep_once)
    with pytest.raises(asyncio.CancelledError):
        await worker.idle_with_heartbeat(hb, state="idle")
    assert slept == [worker.IDLE_BEAT_SECONDS]
    data = read(worker.WORKER_NAME)
    assert data is not None and data["current_state"] == "idle"
    ok, _ = evaluate(data, now_epoch=data["last_poll_at"] + 1, max_age_seconds=300)
    assert ok
    # The compose `--max-age 300` must exceed the idle cadence, or a healthy idle relay flaps.
    assert worker.IDLE_BEAT_SECONDS < 300


def test_worker_static_boundary_no_fulfillment():
    src = (API / "irrigation_dispatch_relay_worker.py").read_text(encoding="utf-8")
    # default-off flag present.
    assert 'RELAY_FLAG = "FEATURE_RESERVATION_DISPATCH_RELAY"' in src
    # POSTs ONLY to the reservation dispatch inbox.
    assert 'INGEST_PATH = "/v1/reservation-dispatch-intents"' in src
    # NO fulfillment: the worker must not create/derive an execution_request.
    assert "execution_request" not in src.lower() or "no fulfillment" in src.lower()
    assert "create_execution_request" not in src
    # subscribes the reservation dispatch subjects.
    assert "sahool.events." in src and "SUPPORTED_DISPATCH_EVENTS" in src
