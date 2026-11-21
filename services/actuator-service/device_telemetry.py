"""Device-bound mesh telemetry, independent of MQTT and the rule engine.

Only the dedicated TLS/ACL device profile may feed this contract. A payload is
not proof of identity: the broker binds the device topic to its username, and the
caller must still attest tenant/field/device against iot_devices before use.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
MAX_AGE_MS = 120_000
MAX_FUTURE_MS = 30_000
MAX_PAYLOAD_BYTES = 4096
# Firmware names include units; rule names are explicit, not inferred by stripping suffixes.
_SENSORS = {
    "air_temp_c": ("air_temperature", "degC", -40.0, 80.0),
    "air_humidity_pct": ("air_humidity", "%", 0.0, 100.0),
    "soil_moisture_pct": ("soil_moisture", "%", 0.0, 100.0),
}


@dataclass(frozen=True)
class MeshReading:
    sensor_type: str
    value: float
    unit: str


@dataclass(frozen=True)
class MeshSample:
    tenant_id: str
    field_id: str
    device_id: str
    measured_at_ms: int
    readings: tuple[MeshReading, ...]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_mesh_sample(topic: str, raw: bytes | str, *, now_ms: int) -> MeshSample | None:
    """Reject ambiguous identities, uptime-as-epoch, old/future or invalid readings.

    Diagnostic fields (soil_raw, relay_state, mesh_nodes, is_root) never become
    rule inputs. Invalid sensor values are omitted rather than coerced to zero.
    """
    parts = topic.split("/")
    if (
        len(parts) != 6
        or parts[0] != "sahool"
        or parts[3] != "telemetry"
        or parts[5] != "mesh"
        or not all(_SEGMENT.fullmatch(value) for value in (parts[1], parts[2], parts[4]))
    ):
        return None
    try:
        if not isinstance(raw, bytes | bytearray | str):
            return None
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > MAX_PAYLOAD_BYTES:
            return None
        payload = json.loads(encoded, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(payload, dict):
        return None
    tenant, field, device = parts[1], parts[2], parts[4]
    if (
        type(payload.get("v")) is not int
        or payload["v"] != 1
        or payload.get("tenant_id") != tenant
        or payload.get("field_id") != field
        or payload.get("device_id") != device
        or payload.get("source") != "device_local"
    ):
        return None
    measured = payload.get("measured_at_ms")
    if (
        type(measured) is not int
        or measured < 1_700_000_000_000
        or not -MAX_FUTURE_MS <= now_ms - measured <= MAX_AGE_MS
    ):
        return None
    data, units = payload.get("data"), payload.get("units")
    if not isinstance(data, dict) or not isinstance(units, dict):
        return None
    readings = []
    for key, (sensor, unit, lower, upper) in _SENSORS.items():
        value = data.get(key)
        if (
            type(value) in (int, float)
            and lower <= value <= upper
            and math.isfinite(value)
            and units.get(key) == unit
            and (key != "soil_moisture_pct" or payload.get("soil_calibrated") is True)
        ):
            readings.append(MeshReading(sensor, float(value), unit))
    if not readings:
        return None
    return MeshSample(tenant, field, device, measured, tuple(readings))


class MeshReplayWindow:
    """Bounded process-local duplicate window; command replay has its own durable gate.

    A restart loses this cache. It is not a replacement for command idempotency,
    NVS counters or the broker's per-device ACL.
    """

    def __init__(self, max_devices: int = 4096):
        self.max_devices = max_devices
        self._last: dict[tuple[str, str, str], int] = {}

    def accept(self, sample: MeshSample, *, now_ms: int) -> bool:
        cutoff = now_ms - MAX_AGE_MS
        self._last = {key: ts for key, ts in self._last.items() if ts >= cutoff}
        key = (sample.tenant_id, sample.field_id, sample.device_id)
        previous = self._last.get(key)
        if previous is not None and sample.measured_at_ms <= previous:
            return False
        if previous is None and len(self._last) >= self.max_devices:
            return False
        self._last[key] = sample.measured_at_ms
        return True
