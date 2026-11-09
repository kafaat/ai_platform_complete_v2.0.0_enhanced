"""Bounded redelivery and dead letters for the two JetStream consumers in sahool-platform.

Before: the canonical learning worker acked a ``blocked`` irrigation finalize (inputs not
visible yet) and term'ed validation failures with only a log line; the reservation
dispatch relay term'ed permanent refusals the same way, and both nak'ed transient
failures on a fixed delay forever. Either way an event could vanish without a trace.

Now: not-ready/transient outcomes nak with an exponential delay keyed on JetStream's
``num_delivered``; on the MAX_DELIVERIES-th delivery, and before every ``term``, the
original envelope plus the reason go to a dead-letter subject; a failed dead-letter
publish keeps the message (nak) instead of dropping it. No DB or broker is involved:
the handler, the message and the JetStream context are plain doubles.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
WORKER_PATH = PLATFORM / "workers" / "canonical_execution_learning_worker.py"
RELAY_PATH = PLATFORM / "api" / "irrigation_dispatch_relay_worker.py"


def _learning():
    spec = importlib.util.spec_from_file_location("_learning_worker_dlq", WORKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _relay():
    if str(PLATFORM / "api") not in sys.path:
        sys.path.insert(0, str(PLATFORM / "api"))
    import irrigation_dispatch_relay_worker as relay

    return relay


class _Msg:
    def __init__(self, data: bytes, *, delivered: int = 1, metadata: bool = True):
        self.data = data
        self.subject = "sahool.events.irrigation.execution.completed"
        self.settled: list[tuple] = []
        if metadata:
            self.metadata = SimpleNamespace(
                num_delivered=delivered,
                stream="sahool",
                sequence=SimpleNamespace(stream=42),
            )

    async def ack(self):
        self.settled.append(("ack",))

    async def nak(self, delay=None):
        self.settled.append(("nak", delay))

    async def term(self):
        self.settled.append(("term",))


class _JS:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.published: list[tuple[str, dict, dict | None]] = []

    async def publish(self, subject, payload, headers=None):
        if self.fail:
            raise RuntimeError("no responders")
        self.published.append((subject, json.loads(payload), headers))


def _irrigation(event_id: str = "evt-1") -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "event_type": "irrigation.execution.completed",
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "payload": {"run_id": "r-1"},
        }
    ).encode()


def _returning(result):
    async def handler(_pool, _envelope):
        return result

    return handler


def _raising(exc: Exception):
    async def handler(_pool, _envelope):
        raise exc

    return handler


def _settle(worker, msg, js, handler):
    return asyncio.run(worker.settle_delivery(msg, pool=None, js=js, handler=handler))


# ── learning worker ─────────────────────────────────────────────────────────────


def test_a_blocked_irrigation_finalize_is_redelivered_later_not_acked():
    worker = _learning()
    msg, js = _Msg(_irrigation()), _JS()
    blocked = {"status": "blocked", "reason": "DEPLETION_MEASUREMENTS_REQUIRED"}
    assert _settle(worker, msg, js, _returning(blocked)) == "nak"
    assert msg.settled == [("nak", worker.NAK_BASE_DELAY_SECONDS)]
    assert js.published == []


def test_a_blocked_finalize_on_the_last_delivery_is_dead_lettered_then_terminated():
    worker = _learning()
    msg, js = _Msg(_irrigation(), delivered=worker.MAX_DELIVERIES), _JS()
    blocked = {"status": "blocked", "reason": "IRRIGATION_RECONCILIATION_REQUIRED"}
    assert _settle(worker, msg, js, _returning(blocked)) == "term"
    assert msg.settled == [("term",)]
    [(subject, body, headers)] = js.published
    assert subject == worker.DLQ_SUBJECT == "sahool.dlq.canonical_execution_learning"
    assert json.loads(body["envelope"])["event_id"] == "evt-1"  # the original, verbatim
    assert "not_ready:IRRIGATION_RECONCILIATION_REQUIRED" in body["reason"]
    assert "deliveries_exhausted" in body["reason"]
    assert body["num_delivered"] == worker.MAX_DELIVERIES
    assert body["source_id"] == "sahool:42"
    assert headers == {"Nats-Msg-Id": f"{worker.DLQ_SUBJECT}:sahool:42"}


def test_a_blocked_season_verdict_is_final_and_acked():
    """``season.closed`` reports ``blocked`` as a persisted verdict, not as missing inputs."""
    worker = _learning()
    envelope = json.loads(_irrigation())
    envelope["event_type"] = "season.closed"
    msg, js = _Msg(json.dumps(envelope).encode()), _JS()
    assert _settle(worker, msg, js, _returning({"status": "blocked"})) == "ack"
    assert msg.settled == [("ack",)] and js.published == []


@pytest.mark.parametrize(
    "raw_or_exc",
    [ValueError("IRRIGATION_EVENT_FIELDS_REQUIRED:run_id"), KeyError("field_id"), b"[1, 2]"],
)
def test_a_permanent_failure_is_dead_lettered_before_term(raw_or_exc):
    worker = _learning()
    if isinstance(raw_or_exc, bytes):
        msg, handler = _Msg(raw_or_exc), _returning({"status": "ok"})
    else:
        msg, handler = _Msg(_irrigation()), _raising(raw_or_exc)
    js = _JS()
    assert _settle(worker, msg, js, handler) == "term"
    assert msg.settled == [("term",)]
    [(subject, body, _headers)] = js.published
    assert subject == worker.DLQ_SUBJECT
    assert body["reason"].startswith("permanent:")


def test_an_undecodable_envelope_is_dead_lettered_not_retried_forever():
    worker = _learning()
    msg, js = _Msg(b"{not json"), _JS()
    assert _settle(worker, msg, js, _returning({})) == "term"
    assert js.published[0][1]["envelope"] == "{not json"


def test_a_failed_dead_letter_publish_keeps_the_message_and_never_raises():
    worker = _learning()
    msg = _Msg(_irrigation(), delivered=3)
    assert _settle(worker, msg, _JS(fail=True), _raising(ValueError("bad"))) == "nak"
    assert msg.settled == [("nak", worker.redelivery_delay(3))]


def test_a_transient_failure_backs_off_then_dead_letters_at_the_bound():
    worker = _learning()
    early, js = _Msg(_irrigation(), delivered=2), _JS()
    assert _settle(worker, early, js, _raising(ConnectionError("pg down"))) == "nak"
    assert early.settled == [("nak", 2 * worker.NAK_BASE_DELAY_SECONDS)] and not js.published

    last = _Msg(_irrigation(), delivered=worker.MAX_DELIVERIES)
    assert _settle(worker, last, js, _raising(ConnectionError("pg down"))) == "term"
    assert js.published[0][1]["reason"].startswith("transient:ConnectionError")


def test_a_message_without_metadata_counts_as_a_first_delivery():
    worker = _learning()
    msg = _Msg(_irrigation(), metadata=False)
    assert _settle(worker, msg, _JS(), _returning({"status": "blocked"})) == "nak"


def test_the_backoff_doubles_is_capped_and_spans_hours_before_dead_letter():
    worker = _learning()
    delays = [worker.redelivery_delay(n) for n in range(1, worker.MAX_DELIVERIES)]
    assert delays[0] == worker.NAK_BASE_DELAY_SECONDS
    assert delays == sorted(delays) and max(delays) == worker.NAK_MAX_DELAY_SECONDS
    assert sum(delays) >= 2 * 3600, "a not-ready closure deserves hours, not seconds"


def test_consumers_are_created_with_a_bounded_max_deliver_above_the_code_bound():
    worker = _learning()
    pytest.importorskip("nats")
    configs: dict[str, object] = {}

    class _Bind:
        async def subscribe(self, subject, *, durable, cb, manual_ack, config=None):  # noqa: ARG002
            configs[subject] = config

    asyncio.run(worker.subscribe_subjects(_Bind(), durable_base="b", callback=None))
    assert set(configs) == set(worker.SUBJECTS)
    for config in configs.values():
        assert config.max_deliver == worker.CONSUMER_MAX_DELIVER
        assert worker.MAX_DELIVERIES < config.max_deliver  # room for a retried dead letter


# ── reservation dispatch relay ──────────────────────────────────────────────────


def _relay_envelope() -> bytes:
    return json.dumps(
        {
            "event_id": "evt-9",
            "event_type": "irrigation.reservation.dispatch_requested",
            "tenant_id": "t-1",
            "payload": {"evaluation_id": "ev-9"},
        }
    ).encode()


def _relay_handler(relay, status, js, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_DIR", str(tmp_path))
    from worker_heartbeat import HeartbeatState

    async def post(_tenant, _body):
        return status, {"detail": "x"}

    return relay.make_message_handler(post, HeartbeatState(relay.WORKER_NAME), js=js)


def test_relay_permanent_refusal_is_dead_lettered_before_term(tmp_path, monkeypatch):
    relay = _relay()
    js, msg = _JS(), _Msg(_relay_envelope())
    asyncio.run(_relay_handler(relay, 422, js, tmp_path, monkeypatch)(msg))
    assert msg.settled == [("term",)]
    [(subject, body, _headers)] = js.published
    assert subject == relay.DLQ_SUBJECT == "sahool.dlq.irrigation_dispatch_relay"
    assert json.loads(body["envelope"])["event_id"] == "evt-9"
    assert "status=422" in body["reason"]


def test_relay_malformed_envelope_is_dead_lettered(tmp_path, monkeypatch):
    relay = _relay()
    js, msg = _JS(), _Msg(b"{broken")
    asyncio.run(_relay_handler(relay, 200, js, tmp_path, monkeypatch)(msg))
    assert msg.settled == [("term",)]
    assert js.published[0][1]["envelope"] == "{broken"
    assert "malformed_json" in js.published[0][1]["reason"]


def test_relay_retry_backs_off_and_dead_letters_on_the_last_delivery(tmp_path, monkeypatch):
    relay = _relay()
    js = _JS()
    handler = _relay_handler(relay, 503, js, tmp_path, monkeypatch)
    third = _Msg(_relay_envelope(), delivered=3)
    asyncio.run(handler(third))
    assert third.settled == [("nak", 4 * relay.NAK_DELAY_SECONDS)] and not js.published

    last = _Msg(_relay_envelope(), delivered=relay.MAX_DELIVERIES)
    asyncio.run(handler(last))
    assert last.settled == [("term",)]
    assert "deliveries_exhausted" in js.published[0][1]["reason"]


def test_relay_failed_dead_letter_publish_keeps_the_message(tmp_path, monkeypatch):
    relay = _relay()
    msg = _Msg(_relay_envelope())
    asyncio.run(_relay_handler(relay, 422, _JS(fail=True), tmp_path, monkeypatch)(msg))
    assert msg.settled == [("nak", relay.NAK_DELAY_SECONDS)]


def test_relay_backoff_is_capped():
    relay = _relay()
    assert relay.redelivery_delay(1) == relay.NAK_DELAY_SECONDS
    assert relay.redelivery_delay(relay.MAX_DELIVERIES) == relay.NAK_MAX_DELAY_SECONDS
    assert relay.MAX_DELIVERIES < relay.CONSUMER_MAX_DELIVER


# ── the dead-letter subject in code is the one the broker grants ────────────────


@pytest.mark.parametrize("path", [WORKER_PATH, RELAY_PATH])
def test_the_dead_letter_publish_uses_the_declared_subject_literal(path):
    """Literal at the call site so static inventories (inspector, event graph) see it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    declared = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DLQ_SUBJECT" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    }
    published = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "publish"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert len(declared) == 1 and declared == published
    conf = (ROOT / "nats" / "nats.conf").read_text(encoding="utf-8")
    assert f'"{next(iter(declared))}"' in conf
