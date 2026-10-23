"""Raw streamed bodies are bounded before FastAPI parsing and bearer checks."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/realtime-session"))
from realtime_session.session_runtime import create_app  # noqa: E402
from realtime_session.body_limit import BodyLimitMiddleware  # noqa: E402

# Keep other services' legacy main imports independent of this test module.
sys.path.remove(str(ROOT / "services/realtime-session"))

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _scope(headers=()):
    return {"type": "http", "headers": list(headers)}


async def _direct(messages, *, headers=(), read_timeout=5.0):
    sent = []
    consumed = 0
    backend_calls = 0

    async def receive():
        nonlocal consumed
        if consumed >= len(messages):
            await asyncio.sleep(60)
        message = messages[consumed]
        consumed += 1
        return message

    async def send(message):
        sent.append(message)

    async def backend(scope, receive, send):
        nonlocal backend_calls
        backend_calls += 1
        body = await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body["body"]})

    await BodyLimitMiddleware(backend, read_timeout=read_timeout)(_scope(headers), receive, send)
    return sent, consumed, backend_calls


async def test_unauthenticated_chunked_json_stops_before_framework_reads_complete_body():
    consumed = 0

    async def oversized_body():
        nonlocal consumed
        yield b'{"field_id":"'
        for _ in range(256):
            consumed += 1
            yield b"x" * 1024
        yield b'","consent":true}'

    # Test the service factory wiring, without a second test-only middleware
    # that could conceal a missing production body cap.
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/realtime/sessions",
            content=oversized_body(),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 413, "Raw body rejection precedes bearer checks and JSON parsing"
    assert consumed <= 5, "The middleware must not consume the remaining large chunked request"
    assert response.headers["cache-control"] == "no-store", (
        "Direct body-limit errors remain private"
    )


async def test_service_factory_rejects_declared_oversize_without_reading_unauthenticated_body():
    received = 0

    async def body():
        nonlocal received
        received += 1
        yield b"x" * 8192

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/realtime/sessions",
            content=body(),
            headers={"Content-Type": "application/json", "Content-Length": "8192"},
        )
    assert response.status_code == 413, "The real app rejects excessive declared bodies before auth"
    assert received == 0, "Production middleware wiring rejects before requesting body bytes"
    assert response.headers["cache-control"] == "no-store", "Early factory errors cannot be cached"


async def test_http_create_serializes_inflight_room_creation_against_stale_pending_cleanup(
    tmp_path,
):
    from realtime_session.contracts import Principal
    from realtime_session.engine import SessionService
    from realtime_session.store import SessionStore

    create_started = asyncio.Event()
    release_create = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_scan_started = asyncio.Event()
    deleted = []
    clock = [100]

    class Authority:
        async def identity(self, bearer):
            return Principal("tenant-a", "actor-a")

        async def authorize_field(self, bearer, principal, field_id):
            return None

    class Gateway:
        async def create_room(self, session):
            create_started.set()
            await release_create.wait()

        def participant_token(self, session, now, ttl):
            return "synthetic-participant-token"

        async def delete_room(self, room):
            deleted.append(room)

    class ObservedStore(SessionStore):
        async def cleanup_candidates(self, now):
            cleanup_scan_started.set()
            return await super().cleanup_candidates(now)

    store = ObservedStore(tmp_path / "concurrent.sqlite")
    await store.initialize()
    service = SessionService(
        Authority(), store, Gateway(), "wss://media.example", clock=lambda: clock[0]
    )

    async def cleanup():
        cleanup_started.set()
        await service.cleanup()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)), base_url="http://test"
    ) as client:
        request_task = asyncio.create_task(
            client.post(
                "/api/v1/realtime/sessions",
                headers={"Authorization": "Bearer synthetic"},
                json={"field_id": "field-a", "consent": True},
            )
        )
        await asyncio.wait_for(create_started.wait(), timeout=1)
        # Without the shared lifecycle lock, the pending row would qualify for
        # cleanup now, while create_room is still running.
        clock[0] = 111
        cleanup_task = asyncio.create_task(cleanup())
        try:
            await asyncio.wait_for(cleanup_started.wait(), timeout=1)
            await asyncio.sleep(0)
            assert not cleanup_task.done(), "Cleanup waits for the in-flight room operation lock"
            assert not cleanup_scan_started.is_set(), (
                "Cleanup cannot even scan pending leases until room creation releases the lock"
            )
            assert deleted == [], "A room cannot be deleted before its create RPC completes"
        finally:
            release_create.set()
            response = await asyncio.wait_for(request_task, timeout=2)
            await asyncio.wait_for(cleanup_task, timeout=2)
    assert response.status_code == 201, "A valid create survives a competing stale-pending sweep"
    assert response.json()["status"] == "ACTIVE", "Activation precedes cleanup state re-evaluation"
    assert deleted == [], "Cleanup re-reads the activated lease rather than stale pending state"
    saved = await store.get(response.json()["session_id"])
    assert saved.status == "ACTIVE", "Durable state remains active after serialized cleanup"


@pytest.mark.parametrize("headers", [(), ((b"content-length", b"1"),)])
async def test_actual_chunk_bytes_override_a_missing_or_falsely_small_content_length(headers):
    messages = [{"type": "http.request", "body": b"x" * 1024, "more_body": True}] * 20
    sent, consumed, backend_calls = await _direct(messages, headers=headers)
    assert sent[0]["status"] == 413, "A false or absent length cannot evade the actual byte cap"
    assert consumed == 5, "Only the first over-limit chunk is consumed"
    assert backend_calls == 0, "Oversized content never reaches the application parser"


async def test_declared_oversize_rejects_before_receiving_any_body():
    sent, consumed, backend_calls = await _direct([], headers=((b"content-length", b"4097"),))
    assert sent[0]["status"] == 413, "Known excessive bodies are rejected immediately"
    assert consumed == 0 and backend_calls == 0, (
        "Header rejection reads no body and invokes no route"
    )


@pytest.mark.parametrize("value", [b"", b"-1", b"+1", b" 1", b"1,1", b"x", b"9" * 21])
async def test_invalid_content_length_is_a_sanitized_private_400(value):
    sent, consumed, backend_calls = await _direct([], headers=((b"content-length", value),))
    assert sent[0]["status"] == 400, "Ambiguous Content-Length syntax fails before reading"
    assert (b"cache-control", b"no-store") in sent[0]["headers"], (
        "Early 400 responses are not cacheable"
    )
    assert consumed == 0 and backend_calls == 0, "Malformed lengths do not reach the backend"


@pytest.mark.parametrize(
    "headers",
    [
        ((b"content-length", b"1"), (b"Content-Length", b"1")),
        ((b"content-length", b"1"), (b"transfer-encoding", b"chunked")),
    ],
)
async def test_duplicate_or_transfer_encoded_length_is_rejected(headers):
    sent, consumed, backend_calls = await _direct([], headers=headers)
    assert sent[0]["status"] == 400, "Conflicting framing declarations are never forwarded"
    assert consumed == 0 and backend_calls == 0, "Ambiguous framing performs no body read"


async def test_small_valid_route_receives_the_exact_reassembled_body():
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return {"body": (await request.body()).decode()}

    async def chunks():
        yield b"small "
        yield b"request"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=BodyLimitMiddleware(app)), base_url="http://test"
    ) as client:
        response = await client.post("/echo", content=chunks())
    assert response.status_code == 200, "Valid bounded requests continue to the intended route"
    assert response.json() == {"body": "small request"}, (
        "Chunk replay preserves the complete payload"
    )


async def test_a_small_declared_body_must_match_the_actual_length():
    sent, _, backend_calls = await _direct(
        [{"type": "http.request", "body": b"xy", "more_body": False}],
        headers=((b"content-length", b"1"),),
    )
    assert sent[0]["status"] == 400, "Even an in-limit body cannot contradict its declared framing"
    assert backend_calls == 0, "Length mismatches never reach application code"


async def test_total_body_deadline_rejects_an_incomplete_request():
    messages = [{"type": "http.request", "body": b"x", "more_body": True}]
    started = asyncio.get_running_loop().time()
    sent, consumed, backend_calls = await _direct(messages, read_timeout=0.01)
    elapsed = asyncio.get_running_loop().time() - started
    assert sent[0]["status"] == 408, "An incomplete body cannot retain the worker indefinitely"
    assert elapsed < 0.5, "The total-read deadline does not wait for a per-chunk inactivity cycle"
    assert consumed == 1 and backend_calls == 0, "Timed-out partial bodies are not parsed"


async def test_disconnect_during_body_read_sends_no_response_and_invokes_no_route():
    sent, consumed, backend_calls = await _direct(
        [
            {"type": "http.request", "body": b"partial", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    assert sent == [], "A disconnected client must not receive a synthetic error response"
    assert consumed == 2 and backend_calls == 0, "Disconnect stops request processing"


async def test_empty_immediately_available_chunks_cannot_starve_the_total_deadline():
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": True}

    async def send(message):
        sent.append(message)

    async def backend(*_):
        raise AssertionError("An incomplete stream must not invoke the backend")

    started = asyncio.get_running_loop().time()
    await BodyLimitMiddleware(backend, read_timeout=0.01)(_scope(), receive, send)
    assert sent[0]["status"] == 408, "Empty chunks cannot evade the total body deadline"
    assert asyncio.get_running_loop().time() - started < 0.5, (
        "The middleware yields so deadline cancellation can run even without network suspension"
    )


async def test_slow_error_response_send_does_not_start_a_second_timeout_response():
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"x" * 4097, "more_body": False}

    async def send(message):
        sent.append(message)
        await asyncio.sleep(0.02)

    async def backend(*_):
        raise AssertionError("An oversized stream must not invoke the backend")

    await BodyLimitMiddleware(backend, read_timeout=0.01)(_scope(), receive, send)
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert [message["status"] for message in starts] == [413], (
        "The read deadline must not cancel an error write and send a second response"
    )


async def test_non_http_scopes_bypass_body_processing():
    calls = []

    async def backend(scope, receive, send):
        calls.append(scope["type"])

    async def unexpected():
        raise AssertionError("Non-HTTP body receive must not be used")

    await BodyLimitMiddleware(backend)({"type": "websocket"}, unexpected, unexpected)
    assert calls == ["websocket"], (
        "WebSocket and lifespan protocols keep their own receive contracts"
    )
