"""The learning worker must actually start.

Found by running the worker rather than inspecting it. Every static signal was green
— the module is registered, its compose service is declared, ``--preflight`` exits
zero and prints its facts — and the process still died on startup:

    nats.js.errors.Error: nats: JetStream.Error consumer is already bound to a
    subscription

Three subjects were subscribed under one durable name, and a JetStream durable
consumer binds to exactly one subscription. The crash landed on the second loop
iteration, before the worker reached its idle loop, so it never processed an event.

These tests exercise the real ``subscribe_subjects``/``durable_for_subject`` against a
double whose single rule — one binding per durable name — was measured against
nats-server v2.10.22, not assumed: with the pre-fix code the double raises exactly
where the live server did, and with the fix all three subscriptions bind in both.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "scripts/workers/canonical_execution_learning_worker.py"


def _worker():
    spec = importlib.util.spec_from_file_location("_canonical_learning_worker", WORKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeJetStream:
    """A JetStream double that refuses a durable name already bound to a subscription.

    That single rule is the whole server behaviour under test, and it is the behaviour
    measured live: binding a second subject to an existing durable raised
    ``consumer is already bound to a subscription`` on nats-server v2.10.22.
    """

    def __init__(self) -> None:
        self.bindings: dict[str, str] = {}

    async def subscribe(self, subject, *, durable, cb, manual_ack):  # noqa: ARG002
        if durable in self.bindings:
            raise RuntimeError(
                "nats: JetStream.Error consumer is already bound to a subscription "
                f"(durable={durable!r} already serves {self.bindings[durable]!r})"
            )
        self.bindings[durable] = subject


async def _noop(msg):  # pragma: no cover - never invoked; subscription is what is tested
    return None


def test_the_worker_binds_every_subject_instead_of_dying_on_the_second():
    worker = _worker()
    js = FakeJetStream()

    bound = asyncio.run(
        worker.subscribe_subjects(
            js, durable_base="canonical-execution-learning-v1", callback=_noop
        )
    )

    assert set(bound) == set(worker.SUBJECTS), "every declared subject must end up subscribed"
    assert len(set(bound.values())) == len(worker.SUBJECTS), (
        "each subject needs its own durable consumer; sharing one is the startup crash"
    )
    assert js.bindings == {durable: subject for subject, durable in bound.items()}


def test_durable_names_survive_subjects_that_share_a_last_token():
    """The near-miss fix — suffixing with the last token — reinstates the crash.

    ``sahool.events.season.closed`` and a plausible ``sahool.events.irrigation.closed``
    both end in ``closed``. A last-token suffix makes them the same durable name again,
    under a name that reads as though it were distinct.
    """
    worker = _worker()
    base = "canonical-execution-learning-v1"

    a = worker.durable_for_subject(base, "sahool.events.season.closed")
    b = worker.durable_for_subject(base, "sahool.events.irrigation.closed")

    assert a != b, f"colliding durable names: {a}"


def test_durable_names_are_legal_jetstream_consumer_names():
    """Dots, wildcards and whitespace are rejected by the server, not by us."""
    worker = _worker()
    for subject in worker.SUBJECTS:
        durable = worker.durable_for_subject("canonical-execution-learning-v1", subject)
        assert re.fullmatch(r"[A-Za-z0-9_-]+", durable), f"illegal consumer name: {durable!r}"
        assert durable.startswith("canonical-execution-learning-v1-"), (
            "the operator-configured base name must remain recognisable in the consumer"
        )


def test_the_configured_base_name_is_honoured():
    """``CANONICAL_LEARNING_DURABLE`` is a compose-level knob; it must still steer."""
    worker = _worker()
    bound = asyncio.run(
        worker.subscribe_subjects(FakeJetStream(), durable_base="alt-base", callback=_noop)
    )
    assert all(d.startswith("alt-base-") for d in bound.values()), bound
