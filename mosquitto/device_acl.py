"""Render the dedicated device broker ACL from a reviewed registry export.

No secrets are accepted or emitted. The caller writes the returned text to the
device-acl mount, then provisions a separate password for every named identity.
ACL semantics: https://mosquitto.org/man/mosquitto-conf-5.html
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from uuid import UUID

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
_RESERVED = {"sahool-actuator-service", "sahool-mqtt-health"}


def render_device_acl(devices: Iterable[Mapping[str, str]]) -> str:
    """Bind each username (= device_id) to exactly one registry tenant and field."""
    entries = []
    seen = set()
    for device in devices:
        tenant, field, name = (device.get(key) for key in ("tenant_id", "field_id", "device_id"))
        if not all(
            isinstance(value, str) and _SEGMENT.fullmatch(value) for value in (tenant, field, name)
        ):
            raise ValueError("tenant/field/device must be safe single MQTT topic segments")
        if str(UUID(tenant)) != tenant:
            raise ValueError("tenant_id must be a canonical UUID")
        if name in seen or name in _RESERVED:
            raise ValueError("duplicate or reserved device username")
        seen.add(name)
        entries.append((tenant, field, name))
    if not entries:
        raise ValueError("at least one registry-bound device is required")
    lines = [
        "# Generated from reviewed iot_devices identities; no wildcard device grants.",
        "user sahool-actuator-service",
        "topic write sahool/actuator/+/command",
        "topic read sahool/+/actuator/+/ack",
        "topic read sahool/+/+/telemetry/+/mesh",
        "",
        "user sahool-mqtt-health",
        "topic read $SYS/broker/version",
    ]
    for tenant, field, name in sorted(entries):
        lines.extend(
            [
                "",
                f"user {name}",
                f"topic read sahool/actuator/{name}/command",
                f"topic write sahool/{tenant}/{field}/telemetry/{name}/mesh",
                f"topic write sahool/{tenant}/actuator/{name}/ack",
            ]
        )
    return "\n".join(lines) + "\n"
