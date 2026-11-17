"""Declarative ``sahool`` JetStream stream and the platform publisher preflight — W3-01.

Why this exists (``events-1`` / ``events-11`` / ``x-7``, and
``JETSTREAM-STREAM-TOPOLOGY-OWNED-BY-A-CONSUMER-01``): the only stream that covers
``sahool.>`` was defined inline by a *consumer* (``agents/notification/agent.py``), and the
platform publisher (``FEATURE_NATS_PUBLISHERS``) had no way to tell, before relaying the
held ``event_outbox`` backlog, whether the stream and the consumers that must receive the
events exist. Turning the flag on was therefore a blind step.

This module is the single declaration of that topology:

* ``STREAM_SPEC`` — the stream as data. The notification agent creates the stream from
  ``stream_config()`` (the same values it used before, now stated instead of implied by
  library defaults), and ``python -m shared.nats_stream_contract apply`` creates it
  create-only under the stream owner's identity. Nothing here updates, purges or deletes
  a stream: an existing stream that differs from the spec is reported as drift, never
  rewritten.
* ``REQUIRED_CONSUMERS`` — the durable consumers that must exist before platform events are
  worth relaying (the canonical learning worker's three durables and the notification
  domain-events consumer in either of its two modes). ``required_consumer_groups()`` applies
  the environment: the worker's configured durable base, or ``not_deployed`` when the
  operator states that no learning worker runs yet.
* ``run_preflight`` — connection, credential presence (booleans only, never values),
  stream existence and drift, required consumers. The platform runs it when the flag is on
  and reports it on ``/readyz``; readiness fails closed until it passes and the relay has
  started once. After that a failed re-check is reported as ``degraded`` and readiness holds.

Honesty limit: the preflight proves the topology exists at the moment it runs. It does not
prove a consumer process is alive, only that its durable exists (messages are retained for
it either way, because the stream has limits retention without age or size limits).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

STREAM_NAME = "sahool"

#: The declarative stream. Values equal what ``StreamConfig(name, subjects)`` produced on
#: the server before (limits retention, file storage, no age/size/count limits, 2-minute
#: duplicate window, one replica), so existing deployments match without a rewrite, and
#: ``shared.notification_consumers.validate_stream`` (limits + file + unlimited retention)
#: keeps accepting it. Changing a value here is an owner decision on retention.
STREAM_SPEC: dict[str, Any] = {
    "name": STREAM_NAME,
    "subjects": ["sahool.>"],
    "retention": "limits",
    "storage": "file",
    "discard": "old",
    "max_consumers": -1,
    "max_msgs": -1,
    "max_bytes": -1,
    "max_age": 0,
    "max_msgs_per_subject": -1,
    "duplicate_window": 120.0,
    "num_replicas": 1,
}

#: Subject prefix of every platform outbox event (``event_outbox.nats_subject``).
PLATFORM_EVENT_SUBJECT = "sahool.events.>"

#: Groups of durable consumer names; each group needs at least one existing member.
#: Learning-worker names follow ``durable_for_subject("canonical-execution-learning-v1", s)``
#: and the notification names follow ``shared.notification_consumers`` — both equalities
#: are asserted by tests, so a rename on either side turns them red instead of drifting.
REQUIRED_CONSUMERS: tuple[tuple[str, ...], ...] = (
    ("canonical-execution-learning-v1-irrigation-execution-completed",),
    ("canonical-execution-learning-v1-season-closed",),
    ("canonical-execution-learning-v1-agronomy-projection-requested",),
    ("notif_domain_events", "notif_domain_events_queue_v1"),
)

#: The learning worker's durable base, read from the same variable the worker reads
#: (``CANONICAL_LEARNING_DURABLE`` in ``canonical_execution_learning_worker.main``).
LEARNING_DURABLE_ENV = "CANONICAL_LEARNING_DURABLE"
DEFAULT_LEARNING_DURABLE_BASE = "canonical-execution-learning-v1"
#: ``required`` (default): the three learning durables must exist. ``not_deployed``: the
#: operator states that no learning worker runs in this environment yet. Events are still
#: relayed and the stream keeps them (limits retention, no age limit), and a worker that
#: binds its durables later starts from the first stored message, because nats-py creates a
#: durable with ``DeliverPolicy.ALL``. The choice is reported on every preflight result, so
#: it is never silent. Any other value fails closed.
LEARNING_WORKER_ENV = "NATS_PREFLIGHT_LEARNING_WORKER"
LEARNING_WORKER_MODES = ("required", "not_deployed")
_LEARNING_SUFFIXES = (
    "irrigation-execution-completed",
    "season-closed",
    "agronomy-projection-requested",
)


def learning_worker_mode() -> str:
    """``required`` | ``not_deployed`` | ``invalid`` (an unknown value fails the preflight)."""
    raw = (os.environ.get(LEARNING_WORKER_ENV) or "required").strip().lower()
    return raw if raw in LEARNING_WORKER_MODES else "invalid"


def learning_durable_base() -> str:
    return (os.environ.get(LEARNING_DURABLE_ENV) or "").strip() or DEFAULT_LEARNING_DURABLE_BASE


def required_consumer_groups() -> tuple[tuple[str, ...], ...]:
    """The groups this environment requires: ``REQUIRED_CONSUMERS`` with the learning group
    renamed to the configured durable base, or left out when the operator declared the
    worker ``not_deployed``. The notification group is always required."""
    notification = REQUIRED_CONSUMERS[-1]
    if learning_worker_mode() == "not_deployed":
        return (notification,)
    base = learning_durable_base()
    learning = tuple((f"{base}-{suffix}",) for suffix in _LEARNING_SUFFIXES)
    return (*learning, notification)


#: Per-call bound on each broker request made by the preflight.
PREFLIGHT_TIMEOUT_SECONDS = 3.0
#: ``/readyz`` re-runs the preflight at most this often, so an operator who provisions a
#: missing consumer sees readiness recover without a restart.
PREFLIGHT_TTL_SECONDS = 30.0
#: Overall bound on one whole preflight run (it makes up to six broker requests, each bounded
#: by ``PREFLIGHT_TIMEOUT_SECONDS``). The first run happens inside platform startup, so a broker
#: whose ACL silently drops ``CONSUMER.INFO`` must not add ~18 s there; ``/readyz`` uses the same
#: bound. A run cut off by it is recorded as ``failed`` with ``preflight_timeout``.
PREFLIGHT_OVERALL_TIMEOUT_ENV = "NATS_PREFLIGHT_TIMEOUT_SECONDS"
DEFAULT_PREFLIGHT_OVERALL_TIMEOUT_SECONDS = 5.0


def preflight_overall_timeout() -> float:
    """``NATS_PREFLIGHT_TIMEOUT_SECONDS`` (positive float), else the 5 s default."""
    raw = (os.environ.get(PREFLIGHT_OVERALL_TIMEOUT_ENV) or "").strip()
    try:
        value = float(raw) if raw else DEFAULT_PREFLIGHT_OVERALL_TIMEOUT_SECONDS
    except ValueError:
        value = DEFAULT_PREFLIGHT_OVERALL_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_PREFLIGHT_OVERALL_TIMEOUT_SECONDS


def stream_config() -> Any:
    """``nats.js.api.StreamConfig`` built from ``STREAM_SPEC`` (client imported lazily)."""
    from nats.js.api import DiscardPolicy, RetentionPolicy, StorageType, StreamConfig

    spec = STREAM_SPEC
    return StreamConfig(
        name=spec["name"],
        subjects=list(spec["subjects"]),
        retention=RetentionPolicy(spec["retention"]),
        storage=StorageType(spec["storage"]),
        discard=DiscardPolicy(spec["discard"]),
        max_consumers=spec["max_consumers"],
        max_msgs=spec["max_msgs"],
        max_bytes=spec["max_bytes"],
        max_age=spec["max_age"],
        max_msgs_per_subject=spec["max_msgs_per_subject"],
        duplicate_window=spec["duplicate_window"],
        num_replicas=spec["num_replicas"],
    )


def _plain(value: Any) -> Any:
    """Enum → its value, numbers normalised, so a server config compares with the spec."""
    value = getattr(value, "value", value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def stream_drift(config: Any) -> list[str]:
    """Fields where a live stream config differs from ``STREAM_SPEC`` (pure; [] = matches).

    ``None`` on the server side means "server default" for the limit fields; the server
    always echoes explicit values for a created stream, so ``None`` is treated as a
    mismatch only for fields whose spec value is not the server default.
    """
    defaults = {"max_consumers": -1, "max_msgs": -1, "max_bytes": -1, "max_age": 0}
    drift = []
    for key, expected in STREAM_SPEC.items():
        actual = getattr(config, key, None)
        if actual is None and key in defaults and defaults[key] == expected:
            continue
        if key == "subjects":
            if sorted(actual or []) != sorted(expected):
                drift.append(f"subjects: {sorted(actual or [])} != {sorted(expected)}")
            continue
        if _plain(actual) != _plain(expected):
            drift.append(f"{key}: {_plain(actual)!r} != {_plain(expected)!r}")
    return drift


def credential_facts(url: str | None) -> dict[str, bool]:
    """Booleans only: is a user, a password, and TLS present in ``NATS_URL``. Never values."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return {
            "url_present": bool(url),
            "user_present": False,
            "password_present": False,
            "tls": False,
        }
    return {
        "url_present": bool(url),
        "user_present": bool(parts.username),
        "password_present": bool(parts.password),
        "tls": parts.scheme == "tls",
    }


def _subject_covered(stream_subjects: list[str], subject: str) -> bool:
    """Does any stream subject filter cover ``subject`` (token-wise ``*`` / ``>`` match)?"""
    target = subject.split(".")
    for pattern in stream_subjects or []:
        pat = pattern.split(".")
        ok = True
        for i, token in enumerate(pat):
            if token == ">":
                ok = len(target) > i
                break
            if i >= len(target) or (token not in ("*", target[i])):
                ok = False
                break
        else:
            ok = len(pat) == len(target)
        if ok:
            return True
    return False


async def run_preflight(nc: Any, *, flag: bool, url: str | None) -> dict[str, Any]:
    """Check the broker connection, the stream and the required consumers.

    Fails closed: any error, timeout or permission refusal marks the check failed with the
    exception type (never its text, which can carry the broker URL). Returns a JSON-safe dict
    with ``status`` = ``passed`` | ``failed``.
    """
    result: dict[str, Any] = {
        "flag": flag,
        "credentials": credential_facts(url),
        "connected": bool(nc is not None and getattr(nc, "is_connected", False)),
        "stream": {"name": STREAM_NAME, "exists": False, "covers_platform_events": False},
        "consumers": {},
        "learning_worker": {
            "mode": learning_worker_mode(),
            "durable_base": learning_durable_base(),
        },
        "errors": [],
    }
    if result["learning_worker"]["mode"] == "invalid":
        result["errors"].append(f"invalid_{LEARNING_WORKER_ENV}")
    if result["learning_worker"]["durable_base"] != DEFAULT_LEARNING_DURABLE_BASE:
        # nats/nats.conf grants the platform CONSUMER.INFO on the default names only, so a
        # renamed base is refused by the broker and would read as "missing". Say why instead.
        result["learning_worker"]["acl_note"] = (
            "non-default durable base: nats/nats.conf must grant the platform "
            "$JS.API.CONSUMER.INFO on the new names"
        )
    if not result["connected"]:
        result["errors"].append("not_connected")
    else:
        try:
            js = nc.jetstream()
            info = await asyncio.wait_for(
                js.stream_info(STREAM_NAME), timeout=PREFLIGHT_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001 — missing stream, refusal or timeout: fail closed
            result["errors"].append(f"stream_info:{type(exc).__name__}")
        else:
            subjects = list(getattr(info.config, "subjects", None) or [])
            drift = stream_drift(info.config)
            result["stream"].update(
                exists=True,
                covers_platform_events=_subject_covered(subjects, "sahool.events.x"),
                drift=drift,
            )
            if drift:
                result["errors"].append("stream_drift")
            if not result["stream"]["covers_platform_events"]:
                result["errors"].append("stream_does_not_cover_platform_events")
            for group in required_consumer_groups():
                found = None
                for name in group:
                    try:
                        await asyncio.wait_for(
                            js.consumer_info(STREAM_NAME, name), timeout=PREFLIGHT_TIMEOUT_SECONDS
                        )
                    except Exception:  # noqa: BLE001 — absent/refused ⇒ try the alternative
                        continue
                    found = name
                    break
                result["consumers"][" | ".join(group)] = found
                if found is None:
                    result["errors"].append(f"consumer_missing:{group[0]}")
    result["status"] = "failed" if result["errors"] else "passed"
    return result


async def run_preflight_bounded(
    nc: Any, *, flag: bool, url: str | None, timeout: float | None = None
) -> dict[str, Any]:
    """``run_preflight`` under one overall deadline; a run that exceeds it fails closed."""
    limit = preflight_overall_timeout() if timeout is None else timeout
    try:
        return await asyncio.wait_for(run_preflight(nc, flag=flag, url=url), timeout=limit)
    except TimeoutError:
        logger.warning("NATS preflight exceeded its overall %ss bound — recorded as failed", limit)
        return {
            "flag": flag,
            "connected": bool(nc is not None and getattr(nc, "is_connected", False)),
            "errors": ["preflight_timeout"],
            "status": "failed",
        }


class PreflightState:
    """Last preflight result as ``/readyz`` reads it, refreshed at most every TTL seconds.

    Readiness reports ``passed`` only when the topology check passed **and** the relay it
    gates is running: ``relay`` is ``None`` (no gate in this process, e.g. a test or the
    CLI), ``"held"`` (gate waiting), ``"started"`` or ``"start_failed"``. A ``/readyz``
    refresh that sees the topology pass while the gate is held wakes the gate at once, so
    readiness and the relay do not drift apart for a whole retry interval.

    Fail closed only until the relay has started once. After that a failed re-check (a NATS
    restart while nats-py reconnects reads ``not_connected``) is reported as ``degraded``,
    not as a readiness failure: a missing broker does not fail readiness once the relay runs,
    because events wait in ``event_outbox`` and the relay drains them when the broker is back.
    Failing readiness there would take every platform pod out of service on each broker blip.
    """

    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None
        self.checked_at: float | None = None
        self.gate_task: asyncio.Task | None = None
        self.relay: str | None = None
        self.relay_error: str | None = None
        self._lock: asyncio.Lock | None = None
        self._wake: asyncio.Event | None = None

    async def reset(self) -> None:
        """Cancel a pending gate (before the worker stops) and forget the last result."""
        task, self.gate_task = self.gate_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.result, self.checked_at = None, None
        self.relay, self.relay_error, self._wake = None, None, None

    async def _try_start(self, start: Callable[[], Awaitable[None]]) -> bool:
        """Run ``start``; a raise is recorded (readiness fails) instead of being lost."""
        try:
            await start()
        except Exception as exc:  # noqa: BLE001 — recorded and retried, never swallowed silently
            self.relay, self.relay_error = "start_failed", f"relay_start:{type(exc).__name__}"
            logger.exception("NATS outbox relay failed to start — retrying")
            return False
        self.relay, self.relay_error = "started", None
        return True

    async def gate(
        self,
        nc: Any,
        start: Callable[[], Awaitable[None]],
        *,
        url: str | None,
        retry_s: float = PREFLIGHT_TTL_SECONDS,
        timeout: float | None = None,
    ) -> bool:
        """Start the relay only after the preflight passes. Returns: started now.

        Why not relay first and let the publisher fail: a missing stream makes every
        ``js.publish`` raise, and ``OutboxWorker`` gives each held row only
        ``max_retries`` attempts with backoff of 2..32 s — the whole held backlog would be
        dead-lettered within about a minute of enabling the flag. Holding the relay until
        the topology exists keeps the rows ``pending`` and replayable. A failed preflight
        (or a failed start) is retried every ``retry_s`` in the background, or sooner when
        ``refresh`` sees the topology pass, so provisioning the stream or a consumer later
        starts the relay without a restart. Each run is bounded overall by ``timeout``
        (default ``preflight_overall_timeout()``), because the first one runs inside startup.
        """
        self.relay, self.relay_error = "held", None
        self._wake = asyncio.Event()
        self.record(await run_preflight_bounded(nc, flag=True, url=url, timeout=timeout))
        if self.result["status"] == "passed" and await self._try_start(start):
            return True
        if self.relay == "held":
            logger.warning(
                "NATS preflight failed (%s) — relay held, events stay pending in event_outbox; "
                "retry every %ss",
                ",".join(self.result["errors"]),
                retry_s,
            )
        wake = self._wake

        async def _retry() -> None:
            while True:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(wake.wait(), timeout=retry_s)
                wake.clear()
                self.record(await run_preflight_bounded(nc, flag=True, url=url, timeout=timeout))
                if self.result["status"] == "passed":
                    logger.info("NATS preflight passed — starting the outbox relay")
                    if await self._try_start(start):
                        return

        self.gate_task = asyncio.create_task(_retry())
        return False

    def record(self, result: dict[str, Any]) -> None:
        self.result, self.checked_at = result, time.monotonic()

    def snapshot(self, *, flag: bool) -> dict[str, Any]:
        if not flag:
            return {"status": "disabled", "flag": False}
        if self.result is None:
            return {"status": "pending", "flag": True, "errors": ["preflight_not_run"]}
        age = None if self.checked_at is None else round(time.monotonic() - self.checked_at, 1)
        out = {**self.result, "age_seconds": age, "relay": self.relay}
        if out["status"] == "passed" and self.relay == "start_failed":
            out["status"], out["errors"] = "failed", [*out["errors"], self.relay_error]
        elif out["status"] == "passed" and self.relay == "held":
            out["status"], out["errors"] = "pending", [*out["errors"], "relay_not_started_yet"]
        elif out["status"] != "passed" and self.relay == "started":
            # Started once: a later failed re-check is a degraded signal, not a 503.
            out["status"] = "degraded"
        return out

    def _fresh(self, ttl: float) -> bool:
        window = ttl if (self.result or {}).get("status") == "passed" else min(ttl, 5.0)
        return (
            self.result is not None
            and self.checked_at is not None
            and time.monotonic() - self.checked_at < window
        )

    async def refresh(
        self, nc: Any, *, flag: bool, url: str | None, ttl: float = PREFLIGHT_TTL_SECONDS
    ) -> dict[str, Any]:
        """Re-run when stale (or never run); a failed result is retried on the next call."""
        if not flag:
            return self.snapshot(flag=False)
        # A failure is re-checked sooner than a pass, but still bounded, so a probe storm on
        # /readyz cannot turn into a request storm on the broker.
        if not self._fresh(ttl):
            if self._lock is None:
                self._lock = asyncio.Lock()
            async with self._lock:
                # Re-check under the lock: callers that queued behind a run reuse its result
                # instead of each running their own preflight (single flight).
                if not self._fresh(ttl):
                    self.record(await run_preflight_bounded(nc, flag=flag, url=url))
        if self.result["status"] == "passed" and self.relay == "held" and self._wake is not None:
            self._wake.set()  # the gate starts the relay now, not at its next retry tick
        return self.snapshot(flag=True)


NATS_PREFLIGHT = PreflightState()


async def ensure_stream(js: Any, *, apply: bool) -> dict[str, Any]:
    """Create-only provisioning. Existing stream ⇒ report drift, never update or delete."""
    try:
        info = await js.stream_info(STREAM_NAME)
    except Exception as exc:  # noqa: BLE001 — only "not found" may lead to a create
        from nats.js.errors import NotFoundError

        if not isinstance(exc, NotFoundError):
            raise
        if not apply:
            return {"stream": STREAM_NAME, "exists": False, "action": "would_create"}
        await js.add_stream(stream_config())
        return {"stream": STREAM_NAME, "exists": True, "action": "created", "drift": []}
    return {
        "stream": STREAM_NAME,
        "exists": True,
        "action": "none",
        "drift": stream_drift(info.config),
    }


async def _main(args: argparse.Namespace) -> int:
    import nats

    url = os.environ.get("NATS_URL", "")
    inbox = os.environ.get("NATS_INBOX_PREFIX") or None
    kwargs = {"connect_timeout": 5, "max_reconnect_attempts": 0}
    if inbox:
        kwargs["inbox_prefix"] = inbox
    nc = await nats.connect(url, **kwargs)
    try:
        if args.command == "preflight":
            out = await run_preflight(nc, flag=True, url=url)
            code = 0 if out["status"] == "passed" else 1
        else:
            out = await ensure_stream(nc.jetstream(), apply=args.command == "apply")
            code = 1 if out.get("drift") else 0
    finally:
        await nc.drain()
    print(json.dumps(out, sort_keys=True, ensure_ascii=False))
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Declarative sahool stream: plan (read-only), apply (create-only, "
        "stream-owner identity), preflight (platform identity)."
    )
    parser.add_argument("command", choices=("plan", "apply", "preflight"))
    raise SystemExit(asyncio.run(_main(parser.parse_args())))
