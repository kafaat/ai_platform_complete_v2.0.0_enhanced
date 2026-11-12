"""cmd_signing_v2.py — actuator command signing, protocol v2 (pure, no I/O).

Why v2 (R-C2, ``SUP-08-DEVICE-COMMAND-SIGNATURE-UNBOUND-TO-DEVICE-01``): v1 signed only
``cmd|ts|duration_ms`` with one ``CMD_HMAC_SECRET`` shared by every device, and the firmware
kept replay protection in a 16-entry RAM ring of ``ts`` strings. A captured command could be
replayed to another tenant's valve (same secret, nothing bound the device/field/tenant) and to
the same valve after a reboot (the ring is lost).

v2:

* **Per-device key, derived server-side** — ``HMAC_SHA256(master, "sahool-cmd-key-v2|tenant|device")``
  as 64 hex chars. Nothing is stored per device; the device gets its key once over USB serial.
  The HMAC key used for signing is the 32 raw bytes of that hex (``bytes.fromhex``).
* **Bound message** — ``v2|tenant|device|field|id|cmd|duration_ms|iat|exp|ctr``.
* **Strictly monotonic counter** ``ctr`` persisted by the device in NVS (survives reboot).
  ``ctr = epoch_ms * 1000 + sub`` with ``sub`` in ``[0, 999]``: a decimal integer below 2**53,
  so every JSON parser reads it exactly.
* **Expiry** ``exp = iat + expiry`` (default 120 s), checked by the device only when its clock is
  SNTP-synced. CLOSE is never refused for expiry: closing is the safe state.

The firmware mirror of :func:`reference_verify` is ``firmware/esp32_mesh_gateway/cmd_auth_v2.h``;
both are tested against one vectors file (``firmware/esp32_mesh_gateway/test/cmd_auth_v2_vectors.json``).
Keys are never logged by anything in this module.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

PROTOCOL_VERSION = 2
KDF_LABEL = "sahool-cmd-key-v2"
MASTER_KEY_MIN_LEN = 32
CTR_SUB_RANGE = 1000

EXPIRY_DEFAULT_SECONDS = 120
EXPIRY_MIN_SECONDS = 10
EXPIRY_MAX_SECONDS = 3600

# Firmware wire commands that return the actuator to its safe state.
SAFE_WIRE_COMMANDS = frozenset({"CLOSE", "OFF"})
WIRE_COMMANDS = frozenset({"OPEN", "ON", "CLOSE", "OFF"})

# Device-side reasons (identical strings in cmd_auth_v2.h ``reason()``).
ACCEPT = "accept"
REJ_NOT_PROVISIONED = "not_provisioned"
REJ_VERSION = "bad_version"
REJ_MALFORMED = "malformed"
REJ_SIGNATURE = "bad_signature"
REJ_BINDING = "binding_mismatch"
REJ_REPLAY = "replay"
REJ_EXPIRED = "expired"


class SigningError(ValueError):
    """A key or message cannot be built safely (empty/ambiguous field, short master key)."""


FIELD_MAX_LEN = 63  # the firmware stores each identity in a 64-byte NVS buffer
ID_MAX_LEN = 96


def _field(name: str, value: object, max_len: int = FIELD_MAX_LEN) -> str:
    """One signed field, exactly as given: non-empty, no ``|`` (the separator), bounded."""
    if not isinstance(value, str) or not value:
        raise SigningError(f"empty_{name}")
    if "|" in value:
        raise SigningError(f"pipe_in_{name}")
    if len(value) > max_len:
        raise SigningError(f"{name}_too_long")
    return value


def canonical_tenant(tenant_id: object) -> str:
    """UUID tenants in canonical lower-case form; anything else stripped, as given."""
    text = str(tenant_id if tenant_id is not None else "").strip()
    try:
        return str(uuid.UUID(text))
    except ValueError:
        return text


def derive_device_key(master_key: str, tenant_id: object, device_id: object) -> str:
    """``HMAC_SHA256(master, "sahool-cmd-key-v2|tenant|device")`` as lower-case hex."""
    if not master_key or len(master_key) < MASTER_KEY_MIN_LEN:
        raise SigningError("master_key_unset_or_short")
    tenant = _field("tenant", canonical_tenant(tenant_id))
    device = _field("device", str(device_id if device_id is not None else "").strip())
    msg = f"{KDF_LABEL}|{tenant}|{device}".encode()
    return hmac.new(master_key.encode(), msg, hashlib.sha256).hexdigest()


def _key_bytes(device_key_hex: str) -> bytes:
    if not isinstance(device_key_hex, str) or len(device_key_hex) != 64:
        raise SigningError("device_key_not_64_hex")
    try:
        return bytes.fromhex(device_key_hex)
    except ValueError as exc:
        raise SigningError("device_key_not_64_hex") from exc


def command_signing_string(
    *,
    tenant: str,
    device: str,
    field: str,
    command_id: str,
    cmd: str,
    duration_ms: int,
    iat: int,
    exp: int,
    ctr: int,
) -> str:
    parts = (
        "v2",
        _field("tenant", tenant),
        _field("device", device),
        _field("field", field),
        _field("id", command_id, ID_MAX_LEN),
        _field("cmd", cmd),
        str(int(duration_ms)),
        str(int(iat)),
        str(int(exp)),
        str(int(ctr)),
    )
    return "|".join(parts)


def sign_command(device_key_hex: str, **fields) -> str:
    msg = command_signing_string(**fields).encode()
    return hmac.new(_key_bytes(device_key_hex), msg, hashlib.sha256).hexdigest()


def build_command(
    device_key_hex: str,
    *,
    tenant: str,
    device: str,
    field: str,
    command_id: str,
    cmd: str,
    payload: dict | None,
    duration_ms: int,
    iat: int,
    exp: int,
    ctr: int,
) -> dict:
    """The v2 wire object. ``payload.duration_ms`` is the signed duration (0 ⇒ omitted)."""
    wire_payload = dict(payload or {})
    wire_payload.pop("duration_ms", None)
    if duration_ms:
        wire_payload["duration_ms"] = int(duration_ms)
    signed = {
        "tenant": canonical_tenant(tenant),
        "device": str(device).strip(),
        "field": str(field).strip(),
        "command_id": str(command_id).strip(),
        "cmd": cmd,
        "duration_ms": int(duration_ms),
        "iat": int(iat),
        "exp": int(exp),
        "ctr": int(ctr),
    }
    sig = sign_command(device_key_hex, **signed)
    return {
        "v": PROTOCOL_VERSION,
        "id": signed["command_id"],
        "cmd": cmd,
        "payload": wire_payload,
        "tenant": signed["tenant"],
        "device": signed["device"],
        "field": signed["field"],
        "iat": signed["iat"],
        "exp": signed["exp"],
        "ctr": signed["ctr"],
        "sig": sig,
    }


def ack_signing_string(tenant: str, device: str, command_id: str, result: str, ctr: int) -> str:
    return "|".join(
        (
            "v2ack",
            _field("tenant", tenant),
            _field("device", device),
            _field("id", command_id, ID_MAX_LEN),
            _field("result", result),
            str(int(ctr)),
        )
    )


def sign_ack(device_key_hex: str, tenant: str, device: str, command_id: str, result, ctr) -> str:
    msg = ack_signing_string(tenant, device, command_id, result, ctr).encode()
    return hmac.new(_key_bytes(device_key_hex), msg, hashlib.sha256).hexdigest()


def verify_ack(device_key_hex: str, ack: dict) -> bool:
    """Constant-time check of a v2 ack's ``sig`` over its own tenant/device/id/result/ctr."""
    try:
        ctr = ack.get("ctr")
        if isinstance(ctr, bool) or not isinstance(ctr, int) or ctr < 0:
            return False
        expected = sign_ack(
            device_key_hex,
            ack.get("tenant"),
            ack.get("device"),
            ack.get("id"),
            ack.get("result"),
            ctr,
        )
    except SigningError:
        return False
    sig = ack.get("sig")
    return isinstance(sig, str) and hmac.compare_digest(sig, expected)


# ── configuration parsing ────────────────────────────────────────────────────
def resolve_expiry_seconds(env_value: str | None) -> int:
    """``ACTUATOR_CMD_EXPIRY_SECONDS``: invalid ⇒ 120, out of range ⇒ clamped to [10, 3600]."""
    try:
        seconds = int(str(env_value).strip()) if env_value not in (None, "") else None
    except ValueError:
        seconds = None
    if seconds is None:
        return EXPIRY_DEFAULT_SECONDS
    return min(max(seconds, EXPIRY_MIN_SECONDS), EXPIRY_MAX_SECONDS)


def parse_legacy_devices(env_value: str | None) -> frozenset[str]:
    """``ACTUATOR_LEGACY_V1_DEVICES``: explicit comma list of device ids; nothing else."""
    return frozenset(d.strip() for d in str(env_value or "").split(",") if d.strip())


@dataclass(frozen=True)
class SigningPlan:
    """What the publisher may do for one device: ``v2``, ``v1`` (legacy) or ``refuse``."""

    mode: str
    reason: str


def plan_signing(
    device_id: str, *, master_key: str, legacy_devices: frozenset[str], legacy_secret: str
) -> SigningPlan:
    """Fail-closed choice of protocol for one device.

    A device listed in ``ACTUATOR_LEGACY_V1_DEVICES`` is an unflashed unit: it only understands
    v1, so it gets v1 (and only if ``CMD_HMAC_SECRET`` is set). Every other device gets v2, and
    only if ``CMD_HMAC_MASTER_KEY`` is set. Otherwise nothing is published.
    """
    if str(device_id).strip() in legacy_devices:
        if not legacy_secret:
            return SigningPlan("refuse", "legacy_v1_device_without_cmd_hmac_secret")
        return SigningPlan("v1", "legacy_v1_allowlisted")
    if not master_key or len(master_key) < MASTER_KEY_MIN_LEN:
        return SigningPlan("refuse", "cmd_hmac_master_key_unset")
    return SigningPlan("v2", "ok")


# ── counter ─────────────────────────────────────────────────────────────────
def _epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def stable_counter(issued_at: str, command_id: str) -> int | None:
    """Counter for a command whose identity must survive a republish (dispatch recovery).

    ``issued_at`` is ``_dispatch_wire_identity``'s ``"<requested_at>~<tag>"``; the counter is
    ``requested_at`` in epoch ms × 1000 plus a sub-millisecond slot from the command id, so a
    republish carries the same ``ctr`` and the device drops it as a replay. ``None`` if
    ``requested_at`` does not parse (caller falls back to a live counter).
    """
    head = str(issued_at or "").split("~", 1)[0].strip()
    if not head:
        return None
    try:
        dt = datetime.fromisoformat(head.replace(" ", "T", 1) if "T" not in head else head)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    sub = int(hashlib.sha256(str(command_id).encode()).hexdigest()[:8], 16) % CTR_SUB_RANGE
    return _epoch_ms(dt) * CTR_SUB_RANGE + sub


class LiveCounter:
    """Process-local strictly increasing counter: ``max(now_ms * 1000, last + 1)``."""

    def __init__(self) -> None:
        self._last = 0
        self._lock = threading.Lock()

    def next(self, now_ms: int) -> int:
        with self._lock:
            self._last = max(int(now_ms) * CTR_SUB_RANGE, self._last + 1)
            return self._last


# ── reference verifier: the firmware's decision, in Python ───────────────────
@dataclass
class DeviceState:
    """What the firmware keeps in NVS. ``key_hex`` empty ⇒ not provisioned."""

    tenant: str = ""
    device: str = ""
    field: str = ""
    key_hex: str = ""
    last_ctr: int = 0

    @property
    def provisioned(self) -> bool:
        return bool(self.tenant and self.device and self.field and len(self.key_hex) == 64)


def _uint(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def reference_verify(
    state: DeviceState, msg: object, *, time_synced: bool, now_ms: int
) -> tuple[str, bool]:
    """Mirror of ``cmdauth::verify_command`` (same order, same reasons).

    Returns ``(reason, is_close)``. On ``accept`` the caller persists ``ctr`` as ``last_ctr``
    *before* actuating (:func:`reference_apply` does both).
    """
    if not state.provisioned:
        return REJ_NOT_PROVISIONED, False
    if not isinstance(msg, dict):
        return REJ_MALFORMED, False
    if type(msg.get("v")) is not int or msg.get("v") != PROTOCOL_VERSION:
        return REJ_VERSION, False
    cmd = msg.get("cmd")
    strings = [msg.get(k) for k in ("id", "tenant", "device", "field", "sig")]
    payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
    duration_ms = _uint(payload.get("duration_ms", 0))
    iat, exp, ctr = (_uint(msg.get(k)) for k in ("iat", "exp", "ctr"))
    if (
        cmd not in WIRE_COMMANDS
        or not all(isinstance(s, str) and s for s in strings)
        or None in (duration_ms, iat, exp, ctr)
    ):
        return REJ_MALFORMED, False
    is_close = cmd in SAFE_WIRE_COMMANDS
    try:
        expected = sign_command(
            state.key_hex,
            tenant=msg["tenant"],
            device=msg["device"],
            field=msg["field"],
            command_id=msg["id"],
            cmd=cmd,
            duration_ms=duration_ms,
            iat=iat,
            exp=exp,
            ctr=ctr,
        )
    except SigningError:
        return REJ_MALFORMED, is_close
    if not hmac.compare_digest(str(msg["sig"]), expected):
        return REJ_SIGNATURE, is_close
    if (msg["tenant"], msg["device"], msg["field"]) != (state.tenant, state.device, state.field):
        return REJ_BINDING, is_close
    if ctr <= state.last_ctr:
        return REJ_REPLAY, is_close
    if time_synced and not is_close and now_ms > exp:
        return REJ_EXPIRED, is_close
    return ACCEPT, is_close


def reference_apply(state: DeviceState, msg: object, *, time_synced: bool, now_ms: int) -> str:
    reason, _ = reference_verify(state, msg, time_synced=time_synced, now_ms=now_ms)
    if reason == ACCEPT:
        state.last_ctr = int(msg["ctr"])  # type: ignore[index]
    return reason
