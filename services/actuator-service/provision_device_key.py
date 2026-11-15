#!/usr/bin/env python3
"""provision_device_key.py — print one device's v2 command key and its serial provisioning lines.

Usage (the master key is read from the environment only, never from argv, so it does not land
in shell history or ``ps``)::

    CMD_HMAC_MASTER_KEY=... python services/actuator-service/provision_device_key.py \\
        --tenant 11111111-1111-1111-1111-111111111111 --device valve-a --field field_01

The output is meant for the operator's terminal, to be pasted into the device's USB serial
console (115200 baud). It contains the device key: do not redirect it into a log, a ticket
or a chat. Nothing is written to disk and nothing is logged.

Runbook: ``docs/runbooks/ACTUATOR_SIGNING_V2_FLASHING_AR.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmd_signing_v2 as sig  # noqa: E402


def provisioning_lines(*, tenant: str, device: str, field: str, device_key: str) -> list[str]:
    """The exact serial lines the firmware's provisioning handler accepts, in order."""
    return [
        f"SET_TENANT:{tenant}",
        f"SET_DEVICE:{device}",
        f"SET_FIELD:{field}",
        f"SET_CMD_KEY:{device_key}",
        "SHOW_CONFIG",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant", required=True, help="tenant UUID (canonicalised)")
    parser.add_argument("--device", required=True, help="device_id as registered in iot_devices")
    parser.add_argument(
        "--field",
        default="",
        help="field_id the device is registered to (adds SET_FIELD to the serial lines)",
    )
    args = parser.parse_args(argv)

    master = os.environ.get("CMD_HMAC_MASTER_KEY", "")
    if len(master) < sig.MASTER_KEY_MIN_LEN:
        print(
            "error: CMD_HMAC_MASTER_KEY is unset or shorter than "
            f"{sig.MASTER_KEY_MIN_LEN} characters (read from the environment only)",
            file=sys.stderr,
        )
        return 2
    tenant = sig.canonical_tenant(args.tenant)
    device = args.device.strip()
    field = args.field.strip()
    try:
        key = sig.derive_device_key(master, tenant, device)
        if field:
            sig._field("field", field)
    except sig.SigningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"# SAHOOL actuator command key v2 — tenant={tenant} device={device}")
    print("# SECRET: paste into the device serial console only; do not store or share.")
    print(f"device_key={key}")
    print("# serial provisioning lines (115200 baud, newline-terminated):")
    if not field:
        print("# --field not given: send SET_FIELD:<field_id> yourself before SHOW_CONFIG")
    for line in provisioning_lines(tenant=tenant, device=device, field=field, device_key=key):
        if line.startswith("SET_FIELD:") and not field:
            continue
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
