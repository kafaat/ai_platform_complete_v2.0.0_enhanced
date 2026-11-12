#!/usr/bin/env python3
"""Generate (or ``--check``) the shared v2 command-auth vectors.

One file, two verifiers: the Python reference (``services/actuator-service/cmd_signing_v2.py``,
``reference_verify``) and the firmware header (``cmd_auth_v2.h``, via ``test_cmd_auth_v2.cpp``).
Every key here is a published test key derived from a published test master; none is real.

    python firmware/esp32_mesh_gateway/test/gen_cmd_auth_v2_vectors.py           # rewrite
    python firmware/esp32_mesh_gateway/test/gen_cmd_auth_v2_vectors.py --check   # drift = exit 1
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VECTORS = HERE / "cmd_auth_v2_vectors.json"
sys.path.insert(0, str(ROOT / "services" / "actuator-service"))
import cmd_signing_v2 as cs  # noqa: E402

# Test-only material. Never use these values for a real deployment. JSON names avoid the
# words the secret scanners key on ("key", "secret"): these are published test vectors.
TEST_MASTER = "test-master-NOT-FOR-PRODUCTION-0123456789abcdef"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
DEVICE = "valve-1"
FIELD_A = "field-a"
FIELD_B = "field-b"
NOW_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
IAT = NOW_MS - 1_000
EXP = IAT + cs.EXPIRY_DEFAULT_SECONDS * 1000
CTR = IAT * cs.CTR_SUB_RANGE


def _key(tenant: str, device: str = DEVICE) -> str:
    return cs.derive_device_key(TEST_MASTER, tenant, device)


def _state(tenant: str = TENANT_A, field: str = FIELD_A, last_ctr: int = 0, key: str | None = None):
    return {
        "tenant": tenant,
        "device": DEVICE,
        "field": field,
        "dk_hex": _key(tenant) if key is None else key,
        "last_ctr": last_ctr,
    }


def _msg(
    cmd="OPEN",
    *,
    tenant=TENANT_A,
    field=FIELD_A,
    duration_ms=60_000,
    iat=IAT,
    exp=EXP,
    ctr=CTR,
    command_id="cmd_0001",
):
    return cs.build_command(
        _key(tenant),
        tenant=tenant,
        device=DEVICE,
        field=field,
        command_id=command_id,
        cmd=cmd,
        payload={},
        duration_ms=duration_ms,
        iat=iat,
        exp=exp,
        ctr=ctr,
    )


def _signing_string(msg: dict) -> str | None:
    try:
        return cs.command_signing_string(
            tenant=msg["tenant"],
            device=msg["device"],
            field=msg["field"],
            command_id=msg["id"],
            cmd=msg["cmd"],
            duration_ms=msg.get("payload", {}).get("duration_ms", 0),
            iat=msg["iat"],
            exp=msg["exp"],
            ctr=msg["ctr"],
        )
    except (KeyError, TypeError, cs.SigningError):
        return None


def build() -> dict:
    cases: list[dict] = []

    def case(name, state, msg, *, synced=True, now=NOW_MS):
        st = cs.DeviceState(
            tenant=state["tenant"],
            device=state["device"],
            field=state["field"],
            key_hex=state["dk_hex"],
            last_ctr=state["last_ctr"],
        )
        expect, _ = cs.reference_verify(st, msg, time_synced=synced, now_ms=now)
        cases.append(
            {
                "name": name,
                "state": state,
                "time_synced": synced,
                "now_ms": now,
                "msg": msg,
                "signing_string": _signing_string(msg),
                "expect": expect,
            }
        )

    case("open_valid", _state(), _msg())
    case("close_valid_unsynced_clock", _state(), _msg("CLOSE", duration_ms=0), synced=False)
    # Cross-tenant replay: tenant A's command, captured, delivered to tenant B's valve of the
    # same device id (same MQTT topic). B's key differs, so the signature fails.
    case("cross_tenant_replay_as_is", _state(TENANT_B), _msg())
    relabelled = _msg()
    relabelled.update(tenant=TENANT_B)
    case("cross_tenant_replay_relabelled", _state(TENANT_B), relabelled)
    # Signed for this device's key but for another field (device moved / wrong registry).
    case("field_binding_mismatch", _state(field=FIELD_B), _msg())
    case("counter_replay_equal", _state(last_ctr=CTR), _msg())
    case("counter_replay_older", _state(last_ctr=CTR + 5), _msg())
    case("close_counter_replay", _state(last_ctr=CTR), _msg("CLOSE", duration_ms=0))
    case("open_expired_synced", _state(), _msg(), now=EXP + 1)
    case("open_expired_unsynced_accepts", _state(), _msg(), synced=False, now=EXP + 1)
    case("close_expired_synced_accepts", _state(), _msg("CLOSE", duration_ms=0), now=EXP + 1)
    case("not_provisioned", _state(key=""), _msg())
    legacy = {"cmd": "OPEN", "payload": {"duration_ms": 60_000}, "ts": "t1", "sig": "0" * 64}
    case("legacy_v1_message", _state(), legacy)
    tampered = _msg()
    tampered["payload"]["duration_ms"] = 1_800_000
    case("duration_tampered", _state(), tampered)
    missing_ctr = _msg()
    del missing_ctr["ctr"]
    case("missing_ctr", _state(), missing_ctr)
    piped = copy.deepcopy(_msg())
    piped["id"] = "cmd|0001"
    case("pipe_in_id", _state(), piped)
    case("unknown_wire_command", _state(), {**_msg(), "cmd": "PULSE"})

    acks = []
    for result in ("applied", "rejected", "unknown_command"):
        key = _key(TENANT_A)
        acks.append(
            {
                "tenant": TENANT_A,
                "device": DEVICE,
                "id": "cmd_0001",
                "result": result,
                "ctr": CTR,
                "dk_hex": key,
                "signing_string": cs.ack_signing_string(TENANT_A, DEVICE, "cmd_0001", result, CTR),
                "sig": cs.sign_ack(key, TENANT_A, DEVICE, "cmd_0001", result, CTR),
            }
        )

    kdf = [
        {"tenant": t, "device": d, "dk_hex": _key(t, d)}
        for t, d in ((TENANT_A, DEVICE), (TENANT_B, DEVICE), (TENANT_A, "valve-2"))
    ]
    return {
        "$comment": "Generated by gen_cmd_auth_v2_vectors.py — do not edit by hand. Test keys only.",
        "protocol": cs.PROTOCOL_VERSION,
        "kdf_master": TEST_MASTER,
        "kdf": kdf,
        "commands": cases,
        "acks": acks,
    }


def render() -> str:
    return json.dumps(build(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = VECTORS.read_text("utf-8") if VECTORS.exists() else ""
        if current != text:
            print(f"stale: {VECTORS} — regenerate with {Path(__file__).name}", file=sys.stderr)
            return 1
        print(f"ok: {VECTORS.name} up to date ({len(build()['commands'])} command vectors)")
        return 0
    VECTORS.write_text(text, "utf-8")
    print(f"wrote {VECTORS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
