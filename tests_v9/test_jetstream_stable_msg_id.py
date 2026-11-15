"""C-19 — the outbox publisher can send a stable ``Nats-Msg-Id``.

The gap: ``make_jetstream_publisher`` called ``js.publish(subject, payload)`` with no
message id. A crash after the ``PubAck`` and before the outbox row is marked ``sent``
re-publishes the event, and JetStream's duplicate window cannot drop the second copy
because nothing identifies it as the same message.

The fix: an optional ``msg_id`` (the outbox relay's ``event_id``) is sent as the
``Nats-Msg-Id`` header. Callers that pass no id keep the exact call they made before.

Stated limit: the duplicate window is bounded in time, so this narrows duplicates; it
does not give exactly-once. Consumer idempotency (``processed_events``) stays the real
guarantee, and nothing here touches it.

The double below is a recording message-broker double (JetStream context), not a
database connection.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from shared.broker_url import MSG_ID_HEADER, make_jetstream_publisher

pytestmark = pytest.mark.unit


class _RecordingJetStream:
    """Records every ``publish`` call and returns a configurable PubAck (or raises)."""

    def __init__(self, ack=None, error: Exception | None = None) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self._ack = ack if ack is not None else SimpleNamespace(seq=7, duplicate=False)
        self._error = error

    async def publish(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._error is not None:
            raise self._error
        return self._ack


class _Conn:
    def __init__(self, js: _RecordingJetStream) -> None:
        self._js = js

    def jetstream(self) -> _RecordingJetStream:
        return self._js


def _publisher(js: _RecordingJetStream):
    return make_jetstream_publisher(_Conn(js))


def test_header_name_is_the_one_the_installed_client_uses():
    from nats.js.api import Header

    assert MSG_ID_HEADER == Header.MSG_ID.value == "Nats-Msg-Id"


def test_msg_id_is_sent_as_the_nats_msg_id_header():
    js = _RecordingJetStream()
    publish = _publisher(js)

    asyncio.run(publish("sahool.events.x", b"{}", msg_id="7f1c-event-id"))

    assert len(js.calls) == 1
    args, kwargs = js.calls[0]
    assert args == ("sahool.events.x", b"{}")
    assert kwargs.get("headers") == {"Nats-Msg-Id": "7f1c-event-id"}, (
        "no stable message id reached JetStream; a re-publish after a crash is stored twice"
    )


def test_a_uuid_event_id_is_sent_as_its_string_form():
    from uuid import UUID

    event_id = UUID("12345678-1234-5678-1234-567812345678")
    js = _RecordingJetStream()

    asyncio.run(_publisher(js)("s", b"p", msg_id=event_id))

    assert js.calls[0][1]["headers"] == {"Nats-Msg-Id": str(event_id)}


def test_the_same_event_id_gives_the_same_header_on_every_retry():
    js = _RecordingJetStream()
    publish = _publisher(js)

    asyncio.run(publish("s", b"p", msg_id="e-1"))
    asyncio.run(publish("s", b"p", msg_id="e-1"))

    assert js.calls[0][1]["headers"] == js.calls[1][1]["headers"] == {"Nats-Msg-Id": "e-1"}


@pytest.mark.parametrize("kwargs", [{}, {"msg_id": None}, {"msg_id": ""}])
def test_no_id_keeps_the_previous_call_unchanged(kwargs):
    """Backward compatibility: two-argument callers send exactly what they sent before."""
    js = _RecordingJetStream()

    asyncio.run(_publisher(js)("sahool.events.x", b"{}", **kwargs))

    assert js.calls == [(("sahool.events.x", b"{}"), {})]


def test_a_duplicate_puback_is_accepted():
    """JetStream answers a dropped duplicate with the original seq and ``duplicate=True``.

    That is a stored message, so the row may be marked ``sent``; refusing it would leave
    the row retrying forever against a message that is already durable.
    """
    js = _RecordingJetStream(ack=SimpleNamespace(seq=7, duplicate=True))

    asyncio.run(_publisher(js)("s", b"p", msg_id="e-1"))

    assert len(js.calls) == 1


def test_a_publish_error_still_raises_with_an_id():
    js = _RecordingJetStream(error=RuntimeError("nats: no response from stream"))

    with pytest.raises(RuntimeError, match="no response from stream"):
        asyncio.run(_publisher(js)("s", b"p", msg_id="e-1"))


@pytest.mark.parametrize("ack", [SimpleNamespace(seq=0), SimpleNamespace(seq=None)])
@pytest.mark.parametrize("kwargs", [{}, {"msg_id": "e-1"}])
def test_a_missing_puback_still_raises(ack, kwargs):
    js = _RecordingJetStream(ack=ack)

    with pytest.raises(RuntimeError, match="JETSTREAM_PUBACK_MISSING"):
        asyncio.run(_publisher(js)("s", b"p", **kwargs))


def test_a_none_puback_still_raises_with_an_id():
    class _NoneAck(_RecordingJetStream):
        async def publish(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return None

    with pytest.raises(RuntimeError, match="JETSTREAM_PUBACK_MISSING"):
        asyncio.run(_publisher(_NoneAck())("s", b"p", msg_id="e-1"))
