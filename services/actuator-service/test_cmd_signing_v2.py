#!/usr/bin/env python3
"""R-C2 — actuator command signing protocol v2 (``SUP-08-DEVICE-COMMAND-SIGNATURE-UNBOUND-TO-DEVICE-01``).

v1 signed ``cmd|ts|duration_ms`` with one shared ``CMD_HMAC_SECRET``; the firmware's replay
window was 16 ``ts`` strings in RAM. So a captured command replayed onto another tenant's valve
(same secret, nothing bound tenant/device/field) and onto the same valve after a reboot.

These tests run the real code: the pure module (``cmd_signing_v2``), the Python reference of the
firmware decision (``reference_verify``, mirrored by ``firmware/.../cmd_auth_v2.h`` and checked
against the same vectors by the g++ host test), the publisher ``send_mqtt_command`` against a
fake broker, the ack evaluator and the provisioning CLI.
"""

from __future__ import annotations

import asyncio
import functools
import importlib.util
import json
import logging
import subprocess
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

SERVICE = Path(__file__).resolve().parent
ROOT = SERVICE.parents[1]
FW_TEST = ROOT / "firmware" / "esp32_mesh_gateway" / "test"
VECTORS = FW_TEST / "cmd_auth_v2_vectors.json"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
MASTER = "unit-test-master-NOT-FOR-PRODUCTION-0123456789"
LEGACY_SECRET = "s" * 32


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


cs = _load("cmd_signing_v2_under_test", SERVICE / "cmd_signing_v2.py")
cd = _load("command_delivery_under_test_v2", SERVICE / "command_delivery.py")
NOW_MS = 1_767_225_600_000


def _msg(
    cmd="OPEN",
    *,
    tenant=TENANT_A,
    device="valve-1",
    field="field-a",
    ctr=None,
    iat=None,
    exp=None,
    duration_ms=60_000,
    command_id="cmd_1",
    master=MASTER,
):
    iat = NOW_MS if iat is None else iat
    return cs.build_command(
        cs.derive_device_key(master, tenant, device),
        tenant=tenant,
        device=device,
        field=field,
        command_id=command_id,
        cmd=cmd,
        payload={},
        duration_ms=duration_ms,
        iat=iat,
        exp=iat + 120_000 if exp is None else exp,
        ctr=iat * 1000 if ctr is None else ctr,
    )


def _device(tenant=TENANT_A, device="valve-1", field="field-a", last_ctr=0, master=MASTER):
    return cs.DeviceState(
        tenant=tenant,
        device=device,
        field=field,
        key_hex=cs.derive_device_key(master, tenant, device),
        last_ctr=last_ctr,
    )


# ══ KDF ══════════════════════════════════════════════════════════════════════
def test_kdf_is_deterministic_and_distinct_per_tenant_and_device():
    k = cs.derive_device_key(MASTER, TENANT_A, "valve-1")
    assert k == cs.derive_device_key(MASTER, TENANT_A, "valve-1")
    assert len(k) == 64 and int(k, 16) >= 0
    others = {
        cs.derive_device_key(MASTER, TENANT_B, "valve-1"),  # same device id, other tenant
        cs.derive_device_key(MASTER, TENANT_A, "valve-2"),
        cs.derive_device_key(MASTER + "x", TENANT_A, "valve-1"),  # rotated master
    }
    assert k not in others and len(others) == 3


def test_kdf_matches_the_documented_construction_and_canonical_tenant():
    import hashlib
    import hmac

    expected = hmac.new(
        MASTER.encode(), f"sahool-cmd-key-v2|{TENANT_A}|valve-1".encode(), hashlib.sha256
    ).hexdigest()
    assert cs.derive_device_key(MASTER, TENANT_A.upper(), " valve-1 ") == expected


@pytest.mark.parametrize(
    ("master", "tenant", "device", "reason"),
    [
        ("", TENANT_A, "v", "master_key_unset_or_short"),
        ("short", TENANT_A, "v", "master_key_unset_or_short"),
        (MASTER, "", "v", "empty_tenant"),
        (MASTER, TENANT_A, "", "empty_device"),
        (MASTER, TENANT_A, "a|b", "pipe_in_device"),
    ],
)
def test_kdf_refuses_what_cannot_be_bound_safely(master, tenant, device, reason):
    with pytest.raises(cs.SigningError, match=reason):
        cs.derive_device_key(master, tenant, device)


# ══ shared vectors (also verified by the g++ host test) ══════════════════════
def test_the_committed_vectors_are_what_the_reference_generates():
    gen = _load("gen_cmd_auth_v2_vectors_under_test", FW_TEST / "gen_cmd_auth_v2_vectors.py")
    assert VECTORS.read_text("utf-8") == gen.render(), "regenerate: gen_cmd_auth_v2_vectors.py"


def _vectors():
    return json.loads(VECTORS.read_text("utf-8"))


@pytest.mark.parametrize("case", _vectors()["commands"], ids=lambda c: c["name"])
def test_command_vectors_reference_verdict_and_signing_string(case):
    st = case["state"]
    state = cs.DeviceState(st["tenant"], st["device"], st["field"], st["dk_hex"], st["last_ctr"])
    reason, _ = cs.reference_verify(
        state, case["msg"], time_synced=case["time_synced"], now_ms=case["now_ms"]
    )
    assert reason == case["expect"]
    msg = case["msg"]
    if case["signing_string"] is not None:
        assert case["signing_string"] == (
            f"v2|{msg['tenant']}|{msg['device']}|{msg['field']}|{msg['id']}|{msg['cmd']}|"
            f"{msg['payload'].get('duration_ms', 0)}|{msg['iat']}|{msg['exp']}|{msg['ctr']}"
        )


def test_vectors_cover_every_device_verdict():
    seen = {c["expect"] for c in _vectors()["commands"]}
    assert seen == {
        cs.ACCEPT,
        cs.REJ_NOT_PROVISIONED,
        cs.REJ_VERSION,
        cs.REJ_MALFORMED,
        cs.REJ_SIGNATURE,
        cs.REJ_BINDING,
        cs.REJ_REPLAY,
        cs.REJ_EXPIRED,
    }


@pytest.mark.parametrize("ack", _vectors()["acks"], ids=lambda a: a["result"])
def test_ack_vectors(ack):
    assert (
        cs.sign_ack(
            ack["dk_hex"], ack["tenant"], ack["device"], ack["id"], ack["result"], ack["ctr"]
        )
        == ack["sig"]
    )
    assert cs.verify_ack(ack["dk_hex"], ack)


def test_the_firmware_uses_the_header_and_no_shared_secret():
    fw = (ROOT / "firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino").read_text("utf-8")
    header = (ROOT / "firmware/esp32_mesh_gateway/cmd_auth_v2.h").read_text("utf-8")
    assert '#include "cmd_auth_v2.h"' in fw
    assert "CMD_HMAC_SECRET" not in fw and "seenCmdTs" not in fw, "v1 secret/RAM ring remain"
    assert "cmdauth::verify_command(g_cfg, m, clockSynced(), nowEpochMs())" in fw
    callback = fw[fw.index("void mqttCallback(") :]
    # last_ctr is persisted before the relay moves.
    assert callback.index("persistLastCtr(m.ctr)") < callback.index("setRelay(")
    for cmd in (
        "SET_DEVICE:",
        "SET_TENANT:",
        "SET_FIELD:",
        "SET_CMD_KEY:",
        "SHOW_CONFIG",
        "CLEAR_CMD_KEY",
    ):
        assert f'"{cmd}' in fw, cmd
    for name, reason in (("REJ_REPLAY", "replay"), ("REJ_EXPIRED", "expired")):
        assert f'case {name}: return "{reason}";' in header


# ══ the attacks R-C2 closes ═════════════════════════════════════════════════
def test_a_cross_tenant_replay_is_rejected():
    """Tenants A and B both own a device called ``valve-1`` (same MQTT topic)."""
    captured = _msg(tenant=TENANT_A)
    victim = _device(tenant=TENANT_B)
    assert cs.reference_apply(victim, captured, time_synced=True, now_ms=NOW_MS) == cs.REJ_SIGNATURE
    relabelled = dict(captured, tenant=TENANT_B)
    assert (
        cs.reference_apply(victim, relabelled, time_synced=True, now_ms=NOW_MS) == cs.REJ_SIGNATURE
    )
    assert victim.last_ctr == 0
    # The legitimate owner accepts it.
    assert cs.reference_apply(_device(), captured, time_synced=True, now_ms=NOW_MS) == cs.ACCEPT


def test_a_command_for_another_field_is_rejected_even_with_the_right_key():
    dev = _device(field="field-b")
    assert cs.reference_apply(dev, _msg(field="field-a"), time_synced=True, now_ms=NOW_MS) == (
        cs.REJ_BINDING
    )


def test_counter_replay_is_rejected_and_survives_a_reboot():
    dev = _device()
    first = _msg()
    assert cs.reference_apply(dev, first, time_synced=True, now_ms=NOW_MS) == cs.ACCEPT
    assert cs.reference_apply(dev, first, time_synced=True, now_ms=NOW_MS) == cs.REJ_REPLAY
    # Reboot: NVS keeps last_ctr (the v1 RAM ring did not).
    rebooted = _device(last_ctr=dev.last_ctr)
    assert cs.reference_apply(rebooted, first, time_synced=False, now_ms=0) == cs.REJ_REPLAY
    older = _msg(ctr=first["ctr"] - 1, command_id="cmd_0")
    assert cs.reference_apply(rebooted, older, time_synced=True, now_ms=NOW_MS) == cs.REJ_REPLAY
    newer = _msg(ctr=first["ctr"] + 1, command_id="cmd_2")
    assert cs.reference_apply(rebooted, newer, time_synced=True, now_ms=NOW_MS) == cs.ACCEPT


def test_expiry_applies_to_open_only_with_a_synced_clock():
    late = NOW_MS + 121_000
    assert cs.reference_apply(_device(), _msg(), time_synced=True, now_ms=late) == cs.REJ_EXPIRED
    assert cs.reference_apply(_device(), _msg(), time_synced=False, now_ms=late) == cs.ACCEPT


def test_close_is_never_refused_for_expiry_but_keeps_signature_binding_and_counter():
    late = NOW_MS + 3_600_000
    close = _msg("CLOSE", duration_ms=0)
    assert cs.reference_apply(_device(), close, time_synced=True, now_ms=late) == cs.ACCEPT
    assert cs.reference_apply(_device(tenant=TENANT_B), close, time_synced=True, now_ms=late) == (
        cs.REJ_SIGNATURE
    )
    assert cs.reference_apply(_device(field="x"), close, time_synced=True, now_ms=late) == (
        cs.REJ_BINDING
    )
    assert (
        cs.reference_apply(_device(last_ctr=close["ctr"]), close, time_synced=True, now_ms=late)
        == cs.REJ_REPLAY
    )


def test_an_unprovisioned_device_rejects_everything():
    for state in (
        cs.DeviceState(),
        cs.DeviceState(TENANT_A, "valve-1", "field-a", "", 0),
        cs.DeviceState(TENANT_A, "valve-1", "", "a" * 64, 0),
    ):
        assert cs.reference_apply(state, _msg(), time_synced=True, now_ms=NOW_MS) == (
            cs.REJ_NOT_PROVISIONED
        )


def test_a_v1_message_is_not_accepted_by_v2_firmware():
    v1 = {"cmd": "OPEN", "payload": {}, "ts": "t", "sig": "0" * 64}
    assert cs.reference_apply(_device(), v1, time_synced=True, now_ms=NOW_MS) == cs.REJ_VERSION
    assert (
        cs.reference_apply(_device(), {**_msg(), "v": 2.0}, time_synced=True, now_ms=NOW_MS)
        == cs.REJ_VERSION
    )


def test_tampering_with_any_signed_field_breaks_the_signature():
    for key, value in (
        ("id", "cmd_x"),
        ("cmd", "ON"),
        ("iat", 1),
        ("exp", NOW_MS * 2),
        ("ctr", NOW_MS * 1000 + 7),
    ):
        assert (
            cs.reference_apply(_device(), {**_msg(), key: value}, time_synced=True, now_ms=NOW_MS)
            == cs.REJ_SIGNATURE
        ), key
    longer = _msg()
    longer["payload"]["duration_ms"] = 1_800_000
    assert (
        cs.reference_apply(_device(), longer, time_synced=True, now_ms=NOW_MS) == cs.REJ_SIGNATURE
    )


# ══ counters and configuration ══════════════════════════════════════════════
def test_live_counter_is_strictly_monotonic_even_within_one_millisecond_or_a_clock_step_back():
    c = cs.LiveCounter()
    values = [c.next(NOW_MS), c.next(NOW_MS), c.next(NOW_MS - 5_000), c.next(NOW_MS + 1)]
    assert values == sorted(values) and len(set(values)) == 4
    assert values[0] == NOW_MS * 1000 and max(values) < 2**53


def test_stable_counter_survives_a_republish_and_separates_one_transaction():
    same_tx = "2026-11-01 09:00:00.123456+00:00"
    a = cs.stable_counter(f"{same_tx}~abc", "k-open")
    assert a == cs.stable_counter(f"{same_tx}~abc", "k-open")
    assert a != cs.stable_counter(f"{same_tx}~def", "k-close")
    assert a // 1000 == int(datetime.fromisoformat(same_tx).timestamp() * 1000)
    assert cs.stable_counter("not-a-date~x", "k") is None
    assert cs.stable_counter("2026-11-01T09:00:00", "k") is None  # naive: refuse to guess


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def test_a_queued_close_overtaken_by_a_live_open_is_still_applied():
    """Review of #1386, H1 (a): CLOSE queued at T0, a manual OPEN published live at T0+5 s,
    then the dispatcher publishes the queued CLOSE. The device must apply it."""
    live, dev = cs.LiveCounter(), _device()
    t0 = NOW_MS
    open_ctr = cs.dispatch_counter("OPEN", None, live, t0 + 5_000)
    assert (
        cs.reference_apply(
            dev, _msg("OPEN", ctr=open_ctr, iat=t0 + 5_000), time_synced=True, now_ms=t0 + 5_000
        )
        == cs.ACCEPT
    )
    stable = cs.stable_counter(f"{_iso(t0)}~tag", "k-close")
    assert stable < open_ctr  # the old counter alone is what dropped the CLOSE
    close_ctr = cs.dispatch_counter("CLOSE", stable, live, t0 + 10_000)
    close = _msg("CLOSE", ctr=close_ctr, iat=t0 + 10_000, duration_ms=0, command_id="k-close")
    assert cs.reference_apply(dev, close, time_synced=True, now_ms=t0 + 10_000) == cs.ACCEPT


@pytest.mark.parametrize("close_first", [True, False])
def test_open_and_close_from_one_transaction_never_drop_the_close(close_first):
    """Review of #1386, H1 (b): two commands share ``requested_at``. Whatever the order of
    dispatch, the CLOSE is applied and the valve ends closed or never opens."""
    for i in range(200):
        live, dev = cs.LiveCounter(), _device()
        requested = _iso(NOW_MS)
        ids = {"OPEN": f"open-{i}", "CLOSE": f"close-{i}"}
        order = ["CLOSE", "OPEN"] if close_first else ["OPEN", "CLOSE"]
        outcomes = {}
        for step, wire in enumerate(order):
            now = NOW_MS + 10_000 + step
            stable = cs.stable_counter(f"{requested}~t", ids[wire])
            ctr = cs.dispatch_counter(wire, stable, live, now)
            msg = _msg(
                wire,
                ctr=ctr,
                iat=now,
                duration_ms=60_000 if wire == "OPEN" else 0,
                command_id=ids[wire],
            )
            outcomes[wire] = cs.reference_apply(dev, msg, time_synced=True, now_ms=now)
        assert outcomes["CLOSE"] == cs.ACCEPT, (i, outcomes)
        if close_first:  # an OPEN older than the applied CLOSE is refused, not run late
            assert outcomes["OPEN"] == cs.REJ_REPLAY, (i, outcomes)


def test_an_open_republish_keeps_its_counter_and_a_close_republish_is_newer():
    live = cs.LiveCounter()
    stable = cs.stable_counter(f"{_iso(NOW_MS)}~t", "k")
    assert cs.dispatch_counter("OPEN", stable, live, NOW_MS + 1) == stable
    assert cs.dispatch_counter("OPEN", stable, live, NOW_MS + 9) == stable
    first = cs.dispatch_counter("CLOSE", stable, live, NOW_MS + 1)
    again = cs.dispatch_counter("CLOSE", stable, live, NOW_MS + 1)
    assert stable < first < again
    # never below its own stable value, even with the clock behind the request time
    assert cs.dispatch_counter("CLOSE", stable, cs.LiveCounter(), NOW_MS - 60_000) > stable


def test_a_close_after_an_open_stamped_by_a_clock_ahead_of_this_host_is_applied():
    """Follow-up review of #1386: the database clock behind ``requested_at`` runs 3 s ahead.
    The dispatched OPEN carries a counter in this host's future; a manual CLOSE one second
    later must still be newer."""
    live, dev = cs.LiveCounter(), _device()
    stable = cs.stable_counter(f"{_iso(NOW_MS + 3_000)}~t", "k-open")
    open_ctr = cs.dispatch_counter("OPEN", stable, live, NOW_MS)
    assert open_ctr == stable
    opened = _msg("OPEN", ctr=open_ctr, iat=NOW_MS, command_id="k-open")
    assert cs.reference_apply(dev, opened, time_synced=True, now_ms=NOW_MS) == cs.ACCEPT
    close_ctr = cs.dispatch_counter("CLOSE", None, live, NOW_MS + 1_000)
    close = _msg("CLOSE", ctr=close_ctr, iat=NOW_MS + 1_000, duration_ms=0, command_id="m-close")
    assert cs.reference_apply(dev, close, time_synced=True, now_ms=NOW_MS + 1_000) == cs.ACCEPT


def test_the_live_counter_has_one_writer_the_service_runs_one_process():
    """``LiveCounter`` is process-local: two workers or replicas with skewed clocks could give a
    CLOSE a counter below an OPEN another process already published (follow-up review of #1386).
    The image runs one uvicorn worker; scaling it out needs a shared counter first."""
    dockerfile = (Path(__file__).resolve().parent / "Dockerfile").read_text(encoding="utf-8")
    assert '"--workers", "1"' in dockerfile, (
        "actuator-service must run one process (see LiveCounter)"
    )


def test_the_legacy_allowlist_names_one_tenants_device_only():
    """Review of #1386, M1: ``<tenant>:<device>``. Another tenant's device of the same name
    stays on v2, and a bare device id or a malformed tenant is ignored (fail closed)."""
    legacy = cs.parse_legacy_devices(f"{TENANT_A}:valve-1,valve-2,not-a-uuid:valve-3,{TENANT_B}:")
    assert legacy == {(TENANT_A, "valve-1")}
    kw = {"master_key": MASTER, "legacy_devices": legacy, "legacy_secret": LEGACY_SECRET}
    assert cs.plan_signing("valve-1", tenant_id=TENANT_A, **kw).mode == "v1"
    assert cs.plan_signing("valve-1", tenant_id=TENANT_B, **kw).mode == "v2"
    assert cs.plan_signing("valve-2", tenant_id=TENANT_A, **kw).mode == "v2"
    assert cs.plan_signing("valve-1", tenant_id="", **kw).mode == "v2"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 120), ("", 120), ("abc", 120), ("60", 60), ("1", 10), ("999999", 3600)],
)
def test_expiry_configuration_is_bounded(raw, expected):
    assert cs.resolve_expiry_seconds(raw) == expected


def test_signing_plan_is_v2_by_default_and_v1_only_for_listed_devices():
    legacy = cs.parse_legacy_devices(f" {TENANT_A}:old-1 , ,{TENANT_A.upper()}:old-2")
    assert legacy == {(TENANT_A, "old-1"), (TENANT_A, "old-2")}
    plan = functools.partial(cs.plan_signing, tenant_id=TENANT_A)
    assert plan("valve-1", master_key=MASTER, legacy_devices=legacy, legacy_secret="").mode == "v2"
    assert (
        plan("old-1", master_key=MASTER, legacy_devices=legacy, legacy_secret=LEGACY_SECRET).mode
        == "v1"
    )
    assert plan("old-1", master_key=MASTER, legacy_devices=legacy, legacy_secret="") == (
        cs.SigningPlan("refuse", "legacy_v1_device_without_cmd_hmac_secret")
    )
    # A shared v1 secret alone never signs an unlisted device any more.
    assert plan(
        "valve-1", master_key="", legacy_devices=legacy, legacy_secret=LEGACY_SECRET
    ) == cs.SigningPlan("refuse", "cmd_hmac_master_key_unset")


# ══ the publisher (send_mqtt_command) against a fake broker ══════════════════
def _stub_missing_dependencies() -> list[str]:
    inserted: list[str] = []
    for name, build in (
        ("asyncpg", lambda m: setattr(m, "Pool", object)),
        ("jwt", lambda m: setattr(m, "decode", lambda *_a, **_k: {})),
        ("aiomqtt", lambda m: setattr(m, "Client", object)),
    ):
        if name in sys.modules:
            continue
        try:
            __import__(name)
            continue
        except ImportError:
            pass
        stub = types.ModuleType(name)
        build(stub)
        sys.modules[name] = stub
        inserted.append(name)
    return inserted


class _FakeMQTT:
    published: list = []

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def publish(self, topic, message, qos=0, retain=False):
        type(self).published.append((topic, json.loads(message)))


@pytest.fixture
def act(monkeypatch):
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    for var in (
        "CMD_HMAC_MASTER_KEY",
        "CMD_HMAC_SECRET",
        "ACTUATOR_LEGACY_V1_DEVICES",
        "ACTUATOR_CMD_EXPIRY_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    names = (
        "actuator_runtime",
        "routers",
        "routers.commands",
        "command_delivery",
        "cmd_signing_v2",
    )
    saved = {k: sys.modules.get(k) for k in names}
    for name in names:
        sys.modules.pop(name, None)
    try:
        mod = _load("actuator_runtime", SERVICE / "actuator_runtime.py")
        _FakeMQTT.published = []
        monkeypatch.setattr(mod, "ACTUATOR_MODE", "real")
        monkeypatch.setattr(mod, "MQTTClient", _FakeMQTT)
        yield mod
    finally:
        for name in names:
            sys.modules.pop(name, None)
        for name, value in saved.items():
            if value is not None:
                sys.modules[name] = value
        for name in stubbed:
            sys.modules.pop(name, None)


def _send(act, device="valve-1", command="open", payload=None, **kw):
    payload = {"duration_sec": 60} if payload is None else payload
    kw.setdefault("tenant_id", TENANT_A)
    kw.setdefault("field_id", "field-a")
    return asyncio.run(act.send_mqtt_command(device, command, payload, command_id="cmd_9", **kw))


def test_without_any_key_nothing_is_published(act):
    assert _send(act) is False
    assert _send(act, command="close", payload={}) is False
    assert _FakeMQTT.published == []


def test_a_shared_v1_secret_alone_no_longer_signs_an_unlisted_device(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_SECRET", LEGACY_SECRET)
    assert _send(act) is False and _FakeMQTT.published == []


def test_v2_is_published_by_default_and_the_device_accepts_it(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    assert _send(act) is True
    ((topic, wire),) = _FakeMQTT.published
    assert topic == "sahool/actuator/valve-1/command"
    assert (wire["v"], wire["cmd"], wire["tenant"], wire["device"], wire["field"], wire["id"]) == (
        2,
        "OPEN",
        TENANT_A,
        "valve-1",
        "field-a",
        "cmd_9",
    )
    assert wire["payload"]["duration_ms"] == 60_000
    assert wire["exp"] - wire["iat"] == 120_000
    now_ms = wire["iat"]
    assert cs.reference_apply(_device(), wire, time_synced=True, now_ms=now_ms) == cs.ACCEPT
    # The same publish to tenant B's identically named valve is refused there.
    assert (
        cs.reference_apply(_device(tenant=TENANT_B), wire, time_synced=True, now_ms=now_ms)
        == cs.REJ_SIGNATURE
    )


def test_consecutive_publishes_carry_increasing_counters(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    assert _send(act) and _send(act, command="close", payload={})
    (_, a), (_, b) = _FakeMQTT.published
    assert b["ctr"] > a["ctr"]
    dev = _device()
    assert cs.reference_apply(dev, a, time_synced=True, now_ms=a["iat"]) == cs.ACCEPT
    assert cs.reference_apply(dev, b, time_synced=True, now_ms=b["iat"]) == cs.ACCEPT


def test_expiry_is_configurable(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    monkeypatch.setenv("ACTUATOR_CMD_EXPIRY_SECONDS", "30")
    assert _send(act)
    wire = _FakeMQTT.published[0][1]
    assert wire["exp"] - wire["iat"] == 30_000


def test_v2_without_tenant_or_field_is_refused(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    assert _send(act, tenant_id=None) is False
    monkeypatch.setattr(act, "_pool", None)  # no registry to read the device's field from
    assert _send(act, field_id=None) is False
    assert _FakeMQTT.published == []


def test_v2_reads_the_field_from_the_registry_when_the_caller_has_none(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)

    async def _registry(tenant_id, device_id):
        return {"tenant_id": tenant_id, "device_id": device_id, "field_id": "field-a"}

    monkeypatch.setattr(act, "_registry_device", _registry)
    assert _send(act, field_id=None) is True
    assert _FakeMQTT.published[0][1]["field"] == "field-a"


def test_a_republished_dispatch_command_keeps_its_counter(act, monkeypatch):
    """A5 + v2: the recovery republish carries the same ``ctr``; the device drops it as replay."""
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    issued = "2026-11-01T08:00:00.123456+00:00~0123456789ab"
    for _ in range(2):
        assert asyncio.run(
            act.send_mqtt_command(
                "valve-1",
                "open_valve",
                {"duration_sec": 60},
                command_id="wtrcmd_1",
                issued_at=issued,
                tenant_id=TENANT_A,
                field_id="field-a",
            )
        )
    (_, m1), (_, m2) = _FakeMQTT.published
    assert m1["ctr"] == m2["ctr"] and m1["id"] == m2["id"] == "wtrcmd_1"
    dev = _device()
    assert cs.reference_apply(dev, m1, time_synced=True, now_ms=m1["iat"]) == cs.ACCEPT
    assert cs.reference_apply(dev, m2, time_synced=True, now_ms=m2["iat"]) == cs.REJ_REPLAY


def test_legacy_v1_only_for_listed_devices_with_a_warning_per_send(act, monkeypatch, caplog):
    import hashlib
    import hmac

    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    monkeypatch.setenv("CMD_HMAC_SECRET", LEGACY_SECRET)
    monkeypatch.setenv("ACTUATOR_LEGACY_V1_DEVICES", f"{TENANT_A}:old-1")
    caplog.set_level(logging.WARNING)
    assert _send(act, device="old-1") is True
    assert _send(act, device="old-1", command="close", payload={}) is True
    assert _send(act, device="valve-1") is True
    (t1, v1), (_, v1b), (_, v2) = _FakeMQTT.published
    assert t1 == "sahool/actuator/old-1/command" and "v" not in v1
    assert (
        v1["sig"]
        == hmac.new(
            LEGACY_SECRET.encode(), f"OPEN|{v1['ts']}|60000".encode(), hashlib.sha256
        ).hexdigest()
    )
    assert "v" not in v1b and v2["v"] == 2
    warnings = [r for r in caplog.records if "LEGACY v1" in r.getMessage()]
    assert len(warnings) == 2 and all("old-1" in r.getMessage() for r in warnings)


def test_no_key_material_is_logged(act, monkeypatch, caplog):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    caplog.set_level(logging.DEBUG)
    assert _send(act)
    key = cs.derive_device_key(MASTER, TENANT_A, "valve-1")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert MASTER not in text and key not in text


# ══ device acks ══════════════════════════════════════════════════════════════
NOW = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


def _record(tenant=TENANT_A, device="valve-1", state="published"):
    return {
        "tenant_id": tenant,
        "device_id": device,
        "command_id": "cmd_1",
        "delivery_state": state,
        "ack_deadline": NOW + timedelta(minutes=2),
    }


def _ack_v2(tenant=TENANT_A, device="valve-1", result="applied", master=MASTER, ctr=5):
    key = cs.derive_device_key(master, tenant, device)
    return {
        "v": 2,
        "id": "cmd_1",
        "tenant": tenant,
        "device": device,
        "result": result,
        "ctr": ctr,
        "sig": cs.sign_ack(key, tenant, device, "cmd_1", result, ctr),
    }


def _evaluate(record, ack, *, tenant=TENANT_A, device="valve-1", legacy=False, secret=""):
    key = cs.derive_device_key(MASTER, tenant, device)
    return cd.evaluate_ack(
        record,
        ack,
        topic_tenant=tenant,
        topic_device=device,
        now=NOW,
        device_key=key,
        legacy_v1=legacy,
        secret=secret,
    )


def test_a_v2_ack_signed_with_the_derived_key_is_accepted():
    d = _evaluate(_record(), _ack_v2())
    assert (d.accepted, d.target) == (True, cd.DEVICE_ACKED)
    d = _evaluate(_record(), _ack_v2(result="rejected"))
    assert (d.accepted, d.target) == (True, cd.DEVICE_REJECTED)


def test_a_v2_ack_for_another_tenant_is_refused():
    # Tenant B's device acks, published on tenant A's topic.
    d = _evaluate(_record(), _ack_v2(tenant=TENANT_B))
    assert (d.accepted, d.reason) == (False, "ack_tenant_does_not_match_topic")
    # Tenant B's key relabelled as tenant A: signature fails.
    forged = dict(_ack_v2(tenant=TENANT_B), tenant=TENANT_A)
    assert _evaluate(_record(), forged).reason == "bad_ack_signature"
    # A correctly signed ack of tenant B, on B's topic, cannot touch A's command row.
    d = _evaluate(_record(tenant=TENANT_A), _ack_v2(tenant=TENANT_B), tenant=TENANT_B)
    assert (d.accepted, d.reason) == (False, "tenant_mismatch")


def test_a_v2_ack_without_the_master_key_or_with_a_tampered_counter_is_refused():
    no_key = cd.evaluate_ack(
        _record(), _ack_v2(), topic_tenant=TENANT_A, topic_device="valve-1", now=NOW
    )
    assert no_key.reason == "ack_signing_key_unset"
    assert _evaluate(_record(), {**_ack_v2(), "ctr": 6}).reason == "bad_ack_signature"


def test_a_v1_ack_is_accepted_only_for_an_allowlisted_device():
    v1 = {
        "id": "cmd_1",
        "device": "valve-1",
        "result": "applied",
        "sig": cd.ack_signature(LEGACY_SECRET, "cmd_1", "valve-1", "applied"),
    }
    assert _evaluate(_record(), v1, secret=LEGACY_SECRET).reason == "legacy_v1_ack_not_allowed"
    d = _evaluate(_record(), v1, legacy=True, secret=LEGACY_SECRET)
    assert (d.accepted, d.target) == (True, cd.DEVICE_ACKED)


def test_the_runtime_derives_ack_keys_and_allows_v1_only_when_listed(act, monkeypatch):
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    monkeypatch.setenv("CMD_HMAC_SECRET", LEGACY_SECRET)
    monkeypatch.setenv("ACTUATOR_LEGACY_V1_DEVICES", f"{TENANT_A}:old-1")
    assert act._ack_keys(TENANT_A, "valve-1") == {
        "device_key": cs.derive_device_key(MASTER, TENANT_A, "valve-1"),
        "legacy_v1": False,
        "secret": "",
    }
    assert act._ack_keys(TENANT_A, "old-1")["legacy_v1"] is True
    assert act._ack_keys(TENANT_A, "old-1")["secret"] == LEGACY_SECRET
    # the same device name under another tenant accepts no v1 ack
    assert act._ack_keys(TENANT_B, "old-1") == {
        "device_key": cs.derive_device_key(MASTER, TENANT_B, "old-1"),
        "legacy_v1": False,
        "secret": "",
    }


# ══ provisioning CLI ═════════════════════════════════════════════════════════
def _cli(*args, env_master=MASTER):
    env = {"PATH": "/usr/bin:/bin"}
    if env_master is not None:
        env["CMD_HMAC_MASTER_KEY"] = env_master
    return subprocess.run(
        [sys.executable, str(SERVICE / "provision_device_key.py"), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_cli_prints_the_derived_key_and_the_exact_serial_lines():
    out = _cli("--tenant", TENANT_A.upper(), "--device", "valve-1", "--field", "field-a")
    assert out.returncode == 0, out.stderr
    key = cs.derive_device_key(MASTER, TENANT_A, "valve-1")
    lines = out.stdout.splitlines()
    assert f"device_key={key}" in lines
    serial = [ln for ln in lines if not ln.startswith("#") and "=" not in ln.split(":")[0]]
    assert serial[-5:] == [
        f"SET_TENANT:{TENANT_A}",
        "SET_DEVICE:valve-1",
        "SET_FIELD:field-a",
        f"SET_CMD_KEY:{key}",
        "SHOW_CONFIG",
    ]
    assert MASTER not in out.stdout + out.stderr


def test_cli_reads_the_master_key_from_the_environment_only():
    out = _cli("--tenant", TENANT_A, "--device", "valve-1", env_master=None)
    assert out.returncode == 2 and "CMD_HMAC_MASTER_KEY" in out.stderr and not out.stdout
    assert _cli("--tenant", TENANT_A, "--device", "valve-1", env_master="short").returncode == 2
    assert _cli("--master", MASTER, "--tenant", TENANT_A, "--device", "v").returncode == 2


@pytest.mark.parametrize("ack", _vectors()["acks"], ids=lambda a: a["result"])
def test_a_non_ascii_ack_signature_is_refused_not_a_crash(ack):
    # compare_digest raises TypeError on a non-ASCII str; main's v1 path already guards this
    # (sig.isascii()), and the v2 verifier must refuse such a sig the same way.
    forged = {**ack, "sig": "\u0661" * 64}
    assert cs.verify_ack(ack["dk_hex"], forged) is False
