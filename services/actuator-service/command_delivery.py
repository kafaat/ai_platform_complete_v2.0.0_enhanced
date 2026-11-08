"""command_delivery.py — explicit delivery state for actuator commands (pure, no I/O).

Before this module a command row said ``sent`` the moment the broker accepted the publish
(QoS 1 = *broker* ack). Nothing recorded whether the **device** received and applied it, so
"sent" and "the valve moved" were indistinguishable in the log and in the HTTP status.

The state machine (only the listed edges exist; everything else is refused)::

    queued ──publish ok (real)────▶ published ──device ack "applied"──▶ device_acked
       │   ──publish ok (simulation)▶ simulated   ──device ack refusal──▶ device_rejected
       │   ──publish failed────────▶ publish_failed
       └──deadline passed──────────▶ expired ◀──deadline passed── published

* ``device_acked`` / ``device_rejected`` are reachable **only** from ``published`` and **only**
  with cause ``device_ack`` — i.e. a signed ack from the device that names this command id.
* ``expired`` is reachable only with cause ``expiry`` after ``ack_deadline`` (bounded timeout).
* ``simulated`` is terminal: simulation never claims a device acknowledgement.

The same edges are enforced again by a database trigger (migration v238), so a code path that
bypasses this module cannot write an illegal transition either.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

QUEUED = "queued"
PUBLISHED = "published"
DEVICE_ACKED = "device_acked"
DEVICE_REJECTED = "device_rejected"
EXPIRED = "expired"
PUBLISH_FAILED = "publish_failed"
SIMULATED = "simulated"
UNTRACKED = "untracked"  # legacy rows written before v238 (delivery_state IS NULL)

STATES = frozenset(
    {QUEUED, PUBLISHED, DEVICE_ACKED, DEVICE_REJECTED, EXPIRED, PUBLISH_FAILED, SIMULATED}
)
TERMINAL = frozenset({DEVICE_ACKED, DEVICE_REJECTED, EXPIRED, PUBLISH_FAILED, SIMULATED})

CAUSE_PUBLISH = "publish"
CAUSE_DEVICE_ACK = "device_ack"
CAUSE_EXPIRY = "expiry"

# (from, to) -> the only cause allowed to drive that edge.
TRANSITIONS: dict[tuple[str, str], str] = {
    (QUEUED, PUBLISHED): CAUSE_PUBLISH,
    (QUEUED, SIMULATED): CAUSE_PUBLISH,
    (QUEUED, PUBLISH_FAILED): CAUSE_PUBLISH,
    (QUEUED, EXPIRED): CAUSE_EXPIRY,
    (PUBLISHED, DEVICE_ACKED): CAUSE_DEVICE_ACK,
    (PUBLISHED, DEVICE_REJECTED): CAUSE_DEVICE_ACK,
    (PUBLISHED, EXPIRED): CAUSE_EXPIRY,
}

# Ack timeout: bounded so a misconfiguration can neither expire instantly nor wait forever.
ACK_TIMEOUT_DEFAULT_SECONDS = 120.0
ACK_TIMEOUT_MIN_SECONDS = 5.0
ACK_TIMEOUT_MAX_SECONDS = 3600.0

# Firmware ``result`` vocabulary -> terminal device state.
ACK_RESULTS: dict[str, str] = {
    "applied": DEVICE_ACKED,
    "unknown_command": DEVICE_REJECTED,
    "rejected": DEVICE_REJECTED,
}


class IllegalDeliveryTransition(ValueError):
    """A transition that is not an edge of the delivery state machine."""


def transition(current: str | None, target: str, *, cause: str) -> str:
    """Return ``target`` if ``current -> target`` is a legal edge driven by ``cause``."""
    required = TRANSITIONS.get((str(current), target))
    if required is None:
        raise IllegalDeliveryTransition(f"illegal_transition:{current}->{target}")
    if required != cause:
        raise IllegalDeliveryTransition(
            f"illegal_cause:{current}->{target} requires {required}, got {cause}"
        )
    return target


def resolve_ack_timeout(env_value: str | None) -> float:
    """Parse ``ACTUATOR_ACK_TIMEOUT_SECONDS``; invalid -> default, out of range -> clamped."""
    try:
        seconds = float(str(env_value).strip()) if env_value not in (None, "") else None
    except ValueError:
        seconds = None
    if seconds is None or seconds != seconds:  # NaN
        return ACK_TIMEOUT_DEFAULT_SECONDS
    return min(max(seconds, ACK_TIMEOUT_MIN_SECONDS), ACK_TIMEOUT_MAX_SECONDS)


def state_after_publish(sent: bool, actuator_mode: str) -> str:
    """Outcome of the publish step. Simulation is never ``published`` (no device will ack)."""
    if not sent:
        return PUBLISH_FAILED
    return PUBLISHED if actuator_mode == "real" else SIMULATED


def ack_deadline(start: datetime, timeout_seconds: float) -> datetime:
    return start + timedelta(seconds=float(timeout_seconds))


def new_command_id() -> str:
    """Correlation id carried on the wire (``id``) and echoed by the device ack."""
    return "cmd_" + uuid.uuid4().hex


def ack_signature(secret: str, command_id: str, device_id: str, result: str) -> str:
    """HMAC-SHA256(secret, ``id|device|result``) — what the firmware signs its ack with."""
    msg = f"{command_id}|{device_id}|{result}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def parse_ack_topic(topic: str) -> tuple[str, str] | None:
    """``sahool/<tenant-uuid>/actuator/<device>/ack`` -> (tenant, device), else ``None``.

    The topic is a lookup key only (anyone on the broker can publish any topic); trust comes
    from the signature and from the command row the tenant already owns.
    """
    parts = str(topic).split("/")
    if len(parts) != 5 or parts[0] != "sahool" or parts[2] != "actuator" or parts[4] != "ack":
        return None
    tenant, device = parts[1], parts[3]
    try:
        tenant = str(uuid.UUID(tenant))
    except ValueError:
        return None
    if not device:
        return None
    return tenant, device


def effective_state(row: dict, now: datetime) -> str:
    """Delivery state as of ``now``: a pending command past its deadline reads ``expired``."""
    state = row.get("delivery_state")
    if state is None:
        return UNTRACKED
    deadline = row.get("ack_deadline")
    if state in (QUEUED, PUBLISHED) and deadline is not None and now > deadline:
        return EXPIRED
    return str(state)


@dataclass(frozen=True)
class AckDecision:
    accepted: bool
    reason: str
    target: str | None = None  # state to persist (also set for a late ack -> expired)


def evaluate_ack(
    record: dict | None,
    ack: object,
    *,
    topic_tenant: str,
    topic_device: str,
    secret: str,
    now: datetime,
) -> AckDecision:
    """Decide what a device ack may do to the command ``record`` it names.

    ``record`` is the row looked up **under the topic tenant's RLS context** by command id, so
    a command of another tenant is simply ``None`` here: it is refused as unknown and nothing
    about the other tenant leaks.
    """
    if not isinstance(ack, dict):
        return AckDecision(False, "malformed_ack")
    command_id = ack.get("id")
    device = ack.get("device")
    result = ack.get("result")
    if not isinstance(command_id, str) or not command_id.strip():
        return AckDecision(False, "ack_without_command_id")
    if device != topic_device:
        return AckDecision(False, "ack_device_does_not_match_topic")
    if not isinstance(result, str) or result not in ACK_RESULTS:
        return AckDecision(False, f"unknown_ack_result:{result}")
    if not secret:
        return AckDecision(False, "ack_signing_secret_unset")
    sig = ack.get("sig")
    expected = ack_signature(secret, command_id, topic_device, result)
    if not isinstance(sig, str) or not hmac.compare_digest(sig, expected):
        return AckDecision(False, "bad_ack_signature")
    if record is None:
        return AckDecision(False, "unknown_command")
    if str(record.get("tenant_id")) != topic_tenant:
        return AckDecision(False, "tenant_mismatch")
    if record.get("device_id") != topic_device:
        return AckDecision(False, "ack_device_does_not_match_command")
    target = ACK_RESULTS[result]
    current = record.get("delivery_state")
    if effective_state(record, now) == EXPIRED and current in (QUEUED, PUBLISHED):
        return AckDecision(False, "ack_after_expiry", target=EXPIRED)
    if current == QUEUED:
        return AckDecision(False, "not_yet_published")
    try:
        transition(current, target, cause=CAUSE_DEVICE_ACK)
    except IllegalDeliveryTransition as exc:
        return AckDecision(False, str(exc))
    return AckDecision(True, result, target=target)


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def delivery_view(row: dict, now: datetime) -> dict:
    """HTTP projection of one command's delivery state and its timestamps."""
    return {
        "command_id": row.get("command_id"),
        "delivery_state": effective_state(row, now),
        "delivery_reason": row.get("delivery_reason"),
        "queued_at": _iso(row.get("queued_at")),
        "published_at": _iso(row.get("published_at")),
        "ack_deadline": _iso(row.get("ack_deadline")),
        "device_acked_at": _iso(row.get("device_acked_at")),
        "device_rejected_at": _iso(row.get("device_rejected_at")),
        "expired_at": _iso(row.get("expired_at")),
    }
