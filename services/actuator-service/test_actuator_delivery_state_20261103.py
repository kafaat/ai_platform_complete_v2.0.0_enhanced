#!/usr/bin/env python3
"""Actuator command delivery state (v238): queued -> published -> device_acked | device_rejected
| expired, driven only by a signed device ack naming the command id.

Before this change a command row said ``sent`` once the *broker* accepted the QoS 1 publish;
nothing distinguished "dispatched" from "the device applied it", the wire carried no id for
manual/rule commands, and an ack (mesh broadcast, no id) could not be correlated at all.

Every test runs the real function. The pure state machine is tested directly; the ack handler
and HTTP handlers run against a dict-backed fake table that mimics RLS (rows of another tenant are
invisible under the tenant context) and the v238 transition trigger.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

SERVICE = Path(__file__).resolve().parent
ROOT = SERVICE.parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
SECRET = "s" * 32


def _load_cd():
    spec = importlib.util.spec_from_file_location(
        "command_delivery_under_test", SERVICE / "command_delivery.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


cd = _load_cd()
NOW = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


# ══ state machine ════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("current", "target", "cause"),
    [
        (cd.QUEUED, cd.PUBLISHED, cd.CAUSE_PUBLISH),
        (cd.QUEUED, cd.SIMULATED, cd.CAUSE_PUBLISH),
        (cd.QUEUED, cd.PUBLISH_FAILED, cd.CAUSE_PUBLISH),
        (cd.QUEUED, cd.EXPIRED, cd.CAUSE_EXPIRY),
        (cd.PUBLISHED, cd.DEVICE_ACKED, cd.CAUSE_DEVICE_ACK),
        (cd.PUBLISHED, cd.DEVICE_REJECTED, cd.CAUSE_DEVICE_ACK),
        (cd.PUBLISHED, cd.EXPIRED, cd.CAUSE_EXPIRY),
    ],
)
def test_every_legal_edge_is_accepted(current, target, cause):
    assert cd.transition(current, target, cause=cause) == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (cd.QUEUED, cd.DEVICE_ACKED),  # skipping publish
        (cd.PUBLISHED, cd.PUBLISHED),
        (cd.PUBLISHED, cd.QUEUED),
        (cd.DEVICE_ACKED, cd.EXPIRED),
        (cd.DEVICE_ACKED, cd.DEVICE_REJECTED),
        (cd.DEVICE_REJECTED, cd.DEVICE_ACKED),
        (cd.EXPIRED, cd.DEVICE_ACKED),  # late ack cannot resurrect
        (cd.SIMULATED, cd.DEVICE_ACKED),  # simulation never claims a device ack
        (cd.PUBLISH_FAILED, cd.DEVICE_ACKED),
        (None, cd.DEVICE_ACKED),  # legacy/untracked row
    ],
)
def test_illegal_transitions_are_refused(current, target):
    with pytest.raises(cd.IllegalDeliveryTransition, match="illegal_transition"):
        cd.transition(current, target, cause=cd.CAUSE_DEVICE_ACK)


def test_only_a_device_ack_can_reach_device_acked():
    for cause in (cd.CAUSE_PUBLISH, cd.CAUSE_EXPIRY):
        with pytest.raises(cd.IllegalDeliveryTransition, match="illegal_cause"):
            cd.transition(cd.PUBLISHED, cd.DEVICE_ACKED, cause=cause)
    with pytest.raises(cd.IllegalDeliveryTransition, match="illegal_cause"):
        cd.transition(cd.PUBLISHED, cd.EXPIRED, cause=cd.CAUSE_DEVICE_ACK)


def test_publish_outcome_is_honest_about_simulation_and_failure():
    assert cd.state_after_publish(True, "real") == cd.PUBLISHED
    assert cd.state_after_publish(True, "simulation") == cd.SIMULATED
    assert cd.state_after_publish(False, "real") == cd.PUBLISH_FAILED
    assert cd.state_after_publish(False, "disabled") == cd.PUBLISH_FAILED


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 120.0),
        ("", 120.0),
        ("abc", 120.0),
        ("nan", 120.0),
        ("0", 5.0),
        ("-30", 5.0),
        ("45", 45.0),
        ("999999", 3600.0),
        ("inf", 3600.0),
    ],
)
def test_ack_timeout_is_bounded(raw, expected):
    assert cd.resolve_ack_timeout(raw) == expected


def test_a_pending_command_past_its_deadline_reads_expired():
    row = {"delivery_state": cd.PUBLISHED, "ack_deadline": NOW}
    assert cd.effective_state(row, NOW) == cd.PUBLISHED
    assert cd.effective_state(row, NOW + timedelta(seconds=1)) == cd.EXPIRED
    acked = {"delivery_state": cd.DEVICE_ACKED, "ack_deadline": NOW}
    assert cd.effective_state(acked, NOW + timedelta(days=1)) == cd.DEVICE_ACKED
    assert cd.effective_state({"delivery_state": None}, NOW) == cd.UNTRACKED


def test_ack_topic_carries_a_uuid_tenant_and_a_device():
    assert cd.parse_ack_topic(f"sahool/{TENANT}/actuator/valve-a/ack") == (TENANT, "valve-a")
    for bad in (
        "sahool/default/actuator/valve-a/ack",  # firmware default tenant is not a UUID
        f"sahool/{TENANT}/actuator//ack",
        f"sahool/{TENANT}/actuator/valve-a/command",
        "sahool/actuator/valve-a/ack",
    ):
        assert cd.parse_ack_topic(bad) is None, bad


# ══ ack evaluation ═══════════════════════════════════════════════════════════
def _ack(command_id="cmd_1", device="valve-a", result="applied", *, secret=SECRET, sig=None):
    body = {"id": command_id, "device": device, "result": result, "status": "ON"}
    body["sig"] = sig if sig is not None else cd.ack_signature(secret, command_id, device, result)
    return body


def _record(state=cd.PUBLISHED, *, tenant=TENANT, device="valve-a", deadline=None):
    return {
        "tenant_id": tenant,
        "device_id": device,
        "command_id": "cmd_1",
        "delivery_state": state,
        "ack_deadline": deadline or NOW + timedelta(minutes=2),
    }


def _evaluate(record, ack, *, tenant=TENANT, device="valve-a", secret=SECRET, now=NOW):
    return cd.evaluate_ack(
        record, ack, topic_tenant=tenant, topic_device=device, secret=secret, now=now
    )


def test_a_signed_ack_for_a_published_command_is_accepted():
    d = _evaluate(_record(), _ack())
    assert (d.accepted, d.target) == (True, cd.DEVICE_ACKED)
    d = _evaluate(_record(), _ack(result="unknown_command"))
    assert (d.accepted, d.target) == (True, cd.DEVICE_REJECTED)


@pytest.mark.parametrize(
    ("ack", "reason"),
    [
        ("not-json-object", "malformed_ack"),
        ({"device": "valve-a", "result": "applied"}, "ack_without_command_id"),
        (_ack(device="valve-b"), "ack_device_does_not_match_topic"),
        (_ack(result="done"), "unknown_ack_result:done"),
        (_ack(sig="0" * 64), "bad_ack_signature"),
        (_ack(sig="أ" * 64), "bad_ack_signature"),
        (_ack(secret="x" * 32), "bad_ack_signature"),
        ({**_ack(), "sig": None}, "bad_ack_signature"),
    ],
)
def test_malformed_or_unsigned_acks_are_refused(ack, reason):
    d = _evaluate(_record(), ack)
    assert (d.accepted, d.reason, d.target) == (False, reason, None)


def test_without_a_signing_secret_no_ack_is_trusted():
    d = _evaluate(_record(), _ack(), secret="")
    assert (d.accepted, d.reason) == (False, "ack_signing_secret_unset")


def test_an_ack_for_an_unknown_or_other_tenant_command_is_refused():
    # Under the topic tenant's RLS context another tenant's command is simply not found.
    assert _evaluate(None, _ack()).reason == "unknown_command"
    # Defence in depth if a row of another tenant ever reached the evaluator.
    d = _evaluate(_record(tenant=OTHER_TENANT), _ack())
    assert (d.accepted, d.reason, d.target) == (False, "tenant_mismatch", None)


def test_an_ack_from_another_device_cannot_ack_this_command():
    ack = _ack(device="valve-b")
    d = _evaluate(_record(device="valve-a"), ack, device="valve-b")
    assert (d.accepted, d.reason) == (False, "ack_device_does_not_match_command")


def test_a_valid_signature_for_another_command_cannot_advance_the_row():
    decision = _evaluate(_record(), _ack(command_id="cmd_2"))
    assert (decision.accepted, decision.reason, decision.target) == (
        False,
        "ack_command_id_mismatch",
        None,
    )


def test_a_late_ack_does_not_ack_and_materialises_expiry():
    late = NOW + timedelta(minutes=3)
    d = _evaluate(_record(deadline=NOW), _ack(), now=late)
    assert (d.accepted, d.reason, d.target) == (False, "ack_after_expiry", cd.EXPIRED)


def test_a_second_ack_cannot_rewrite_a_terminal_state():
    d = _evaluate(_record(state=cd.DEVICE_REJECTED), _ack())
    assert d.accepted is False and d.reason.startswith("illegal_transition:device_rejected")
    d = _evaluate(_record(state=cd.SIMULATED), _ack())
    assert d.accepted is False and d.reason.startswith("illegal_transition:simulated")


def test_an_ack_before_the_publish_write_is_retryable_not_accepted():
    d = _evaluate(_record(state=cd.QUEUED), _ack())
    assert (d.accepted, d.reason, d.target) == (False, "not_yet_published", None)


def test_the_firmware_signs_and_publishes_the_ack_the_platform_verifies():
    """Wire contract: firmware HMAC message and topic match ack_signature/parse_ack_topic."""
    src = (ROOT / "firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino").read_text("utf-8")
    assert re.search(r'snprintf\(msg, sizeof\(msg\), "%s\|%s\|%s", cmdId, DEVICE_ID, result\)', src)
    assert '"sahool/") + TENANT_ID + "/actuator/" + DEVICE_ID + "/ack"' in src
    assert 'ack["id"] = cmdId;' in src and 'ack["sig"] = sig;' in src
    assert re.search(r'publishDeviceAck\(cmdId, known \? "applied" : "unknown_command"\)', src)
    assert set(re.findall(r'"(applied|unknown_command)"', src)) <= set(cd.ACK_RESULTS)


# ══ runtime: dict-backed fake device_commands_log with RLS + v238 trigger ═══════════
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


@pytest.fixture
def act(monkeypatch):
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    monkeypatch.setenv("CMD_HMAC_SECRET", SECRET)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    names = ("actuator_runtime", "routers", "routers.commands", "command_delivery")
    saved = {k: sys.modules.get(k) for k in names}
    for name in names:
        sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location(
            "actuator_runtime", SERVICE / "actuator_runtime.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["actuator_runtime"] = mod
        spec.loader.exec_module(mod)
        monkeypatch.setattr(mod, "_ACK_NOT_YET_PUBLISHED_DELAY_SECONDS", 0, raising=False)
        yield mod
    finally:
        for name in names:
            sys.modules.pop(name, None)
        for name, value in saved.items():
            if value is not None:
                sys.modules[name] = value
        for name in stubbed:
            sys.modules.pop(name, None)


_ALLOWED = {
    ("queued", "published"),
    ("queued", "simulated"),
    ("queued", "publish_failed"),
    ("queued", "expired"),
    ("published", "device_acked"),
    ("published", "device_rejected"),
    ("published", "expired"),
}


class _Table:
    """device_commands_log rows; enforces tenant visibility and the v238 trigger edges."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def visible(self, tenant):
        return [r for r in self.rows if tenant is not None and r["tenant_id"] == tenant]

    def find(self, tenant, command_id):
        return next((r for r in self.visible(tenant) if r["command_id"] == command_id), None)

    def move(self, row, new_state, **cols):
        if (row["delivery_state"], new_state) not in _ALLOWED:
            raise AssertionError(f"trigger: illegal {row['delivery_state']} -> {new_state}")
        row.update(delivery_state=new_state, **cols)


class _Conn:
    def __init__(self, table: _Table) -> None:
        self.t = table
        self.tenant: str | None = None

    def transaction(self):
        class _Tx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

        return _Tx()

    async def execute(self, sql, *args):
        now = datetime.now(UTC)
        if "set_config('app.current_tenant'" in sql:
            self.tenant = args[0]
            return "SELECT 1"
        if sql.lstrip().startswith("INSERT INTO device_commands_log"):
            if self.tenant != args[0]:
                raise AssertionError("RLS WITH CHECK: insert outside the tenant context")
            if "command_id" not in sql:
                self.t.rows.append({"tenant_id": args[0], "command_id": None, "status": args[5]})
                return "INSERT 0 1"
            cid = args[7] if "'queued'" in sql else args[8]
            row = self.t.find(args[0], cid)
            if "'queued'" in sql:  # record_command_queued
                if row is None:
                    self.t.rows.append(
                        {
                            "tenant_id": args[0],
                            "device_id": args[2],
                            "command": args[3],
                            "status": "queued",
                            "triggered_by": args[6],
                            "command_id": cid,
                            "delivery_state": "queued",
                            "queued_at": args[8],
                            "ack_deadline": args[9],
                            "sent_at": args[8],
                        }
                    )
                return "INSERT 0 1"
            state, published_at, deadline = args[9], args[11], args[12]
            if row is None:
                self.t.rows.append(
                    {
                        "tenant_id": args[0],
                        "device_id": args[2],
                        "command": args[3],
                        "status": args[5],
                        "triggered_by": args[7],
                        "command_id": cid,
                        "delivery_state": state,
                        "queued_at": args[10],
                        "published_at": published_at,
                        "ack_deadline": deadline,
                        "sent_at": args[10],
                    }
                )
            else:
                self.t.move(
                    row, state, status=args[5], published_at=published_at, ack_deadline=deadline
                )
            return "INSERT 0 1"
        if sql.lstrip().startswith("UPDATE device_commands_log"):
            if "ack_deadline < now()" in sql:  # expire_overdue_commands
                n = 0
                for r in self.t.visible(self.tenant):
                    deadline = r.get("ack_deadline")
                    if r.get("delivery_state") in ("queued", "published") and deadline < now:
                        self.t.move(r, "expired", expired_at=now)
                        n += 1
                return f"UPDATE {n}"
            row = self.t.find(args[0], args[1])
            if row is None:
                return "UPDATE 0"
            target = re.search(r"SET delivery_state = '(\w+)'", sql).group(1)
            stamp = {"device_acked": "device_acked_at", "device_rejected": "device_rejected_at"}
            self.t.move(
                row, target, delivery_reason=args[2], **{stamp.get(target, "expired_at"): now}
            )
            return "UPDATE 1"
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    async def fetchrow(self, sql, *args):
        if "FROM iot_devices" in sql:
            return {"tenant_id": TENANT, "field_id": "field-9"}
        row = self.t.find(args[0], args[1])
        return dict(row) if row is not None else None

    async def fetch(self, sql, *args):
        return [dict(r) for r in self.t.visible(args[0])][: args[1]]


class _Pool:
    def __init__(self) -> None:
        self.table = _Table()

    def acquire(self):
        table = self.table

        class _Ctx:
            async def __aenter__(self):
                return _Conn(table)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()


class _FakeMQTT:
    published: list[tuple] = []

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def publish(self, topic, message, qos=0, retain=False):
        type(self).published.append((topic, json.loads(message)))


@pytest.fixture
def wired(act, monkeypatch):
    import routers.commands as router_mod

    pool = _Pool()
    _FakeMQTT.published = []
    monkeypatch.setattr(act, "_pool", pool)
    monkeypatch.setattr(act, "FEATURE_MANUAL_ACTUATOR_COMMANDS", "true")
    monkeypatch.setattr(act, "ACTUATOR_MODE", "real")
    monkeypatch.setattr(act, "MQTTClient", _FakeMQTT)

    async def _clear(*_a, **_k):
        return False, None

    monkeypatch.setattr(router_mod, "is_actuation_halted", _clear)
    return act, router_mod, pool


def _claims(tenant=TENANT):
    return {"tenant_id": tenant, "role": "owner", "sub": "user-1"}


def _send(act, router_mod, device="valve-a", command="open"):
    # ACTUATOR-OPEN-WITHOUT-DURATION-01: فتحٌ بلا مدّة يُرفَض 422 قبل أيّ عمل.
    req = act.CommandRequest(device_id=device, command=command, payload={"duration_sec": 60})
    return asyncio.run(router_mod.send_command(req, _claims()))


def _ack_topic(tenant=TENANT, device="valve-a"):
    return f"sahool/{tenant}/actuator/{device}/ack"


def test_manual_command_is_published_with_its_id_and_reports_published_not_acked(wired):
    act, router_mod, pool = wired
    out = _send(act, router_mod)

    assert out["delivery_state"] == "published" and out["sent"] is True
    ((topic, wire),) = _FakeMQTT.published
    assert topic == "sahool/actuator/valve-a/command"
    assert wire["id"] == out["command_id"], "the wire must carry the id the device acks"
    row = pool.table.find(TENANT, out["command_id"])
    assert row["delivery_state"] == "published" and row["triggered_by"] == "manual"
    assert row["published_at"] is not None and row["ack_deadline"] > row["published_at"]


@pytest.mark.parametrize("result", ["applied", "rejected", "unknown_command"])
def test_exact_redelivery_preserves_the_first_accepted_evidence(wired, result):
    act, router_mod, pool = wired
    cid = _send(act, router_mod)["command_id"]
    raw = json.dumps(_ack(command_id=cid, result=result)).encode()
    first = asyncio.run(act.handle_device_ack(_ack_topic(), raw))
    original = dict(pool.table.find(TENANT, cid))
    repeat = asyncio.run(act.handle_device_ack(_ack_topic(), raw))
    assert first.accepted
    assert (repeat.accepted, repeat.reason, repeat.target) == (True, "already_recorded", None)
    assert original == pool.table.find(TENANT, cid)
    other = "rejected" if result != "rejected" else "unknown_command"
    conflict = asyncio.run(act.handle_device_ack(_ack_topic(), json.dumps(_ack(cid, result=other))))
    assert not conflict.accepted
    assert original == pool.table.find(TENANT, cid)


def test_a_signed_device_ack_moves_the_command_to_device_acked_and_http_shows_it(wired):
    act, router_mod, pool = wired
    cid = _send(act, router_mod)["command_id"]

    decision = asyncio.run(
        act.handle_device_ack(_ack_topic(), json.dumps(_ack(command_id=cid)).encode())
    )

    assert decision.accepted and decision.target == "device_acked"
    view = asyncio.run(router_mod.get_command(cid, _claims()))
    assert view["delivery_state"] == "device_acked"
    assert view["published_at"] and view["device_acked_at"] and view["expired_at"] is None
    listed = asyncio.run(router_mod.list_commands(50, _claims()))["commands"]
    assert [(c["command_id"], c["delivery_state"]) for c in listed] == [(cid, "device_acked")]


def test_a_cross_tenant_ack_is_refused_logged_and_changes_nothing(wired, caplog):
    act, router_mod, pool = wired
    cid = _send(act, router_mod)["command_id"]  # belongs to TENANT

    caplog.set_level("WARNING", logger="actuator-service")
    ack = json.dumps(_ack(command_id=cid)).encode()
    decision = asyncio.run(act.handle_device_ack(_ack_topic(tenant=OTHER_TENANT), ack))

    assert (decision.accepted, decision.reason) == (False, "unknown_command")
    assert pool.table.find(TENANT, cid)["delivery_state"] == "published"
    assert any("unknown_command" in r.getMessage() for r in caplog.records)


def test_a_forged_ack_never_reaches_the_database(wired, monkeypatch):
    act, router_mod, pool = wired
    cid = _send(act, router_mod)["command_id"]

    class _NoDB:
        def acquire(self):
            raise AssertionError("an unsigned ack touched the database")

    monkeypatch.setattr(act, "_pool", _NoDB())
    forged = json.dumps(_ack(command_id=cid, secret="attacker" * 4)).encode()
    decision = asyncio.run(act.handle_device_ack(_ack_topic(), forged))
    assert (decision.accepted, decision.reason) == (False, "bad_ack_signature")


def test_an_unacked_command_expires_after_its_deadline(wired, monkeypatch):
    act, router_mod, pool = wired
    cid = _send(act, router_mod)["command_id"]
    row = pool.table.find(TENANT, cid)
    row["ack_deadline"] = datetime.now(UTC) - timedelta(seconds=1)

    view = asyncio.run(router_mod.get_command(cid, _claims()))

    assert view["delivery_state"] == "expired" and view["expired_at"]
    assert row["delivery_state"] == "expired", "expiry must be persisted, not only projected"
    late = asyncio.run(
        act.handle_device_ack(_ack_topic(), json.dumps(_ack(command_id=cid)).encode())
    )
    assert late.accepted is False and row["delivery_state"] == "expired"


def test_status_of_another_tenants_command_is_404(wired):
    from fastapi import HTTPException

    act, router_mod, _pool = wired
    cid = _send(act, router_mod)["command_id"]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(router_mod.get_command(cid, _claims(OTHER_TENANT)))
    assert exc.value.status_code == 404


def test_simulation_is_reported_as_simulated_and_cannot_be_acked(wired, monkeypatch):
    act, router_mod, pool = wired
    monkeypatch.setattr(act, "ACTUATOR_MODE", "simulation")
    out = _send(act, router_mod)
    assert out["delivery_state"] == "simulated" and _FakeMQTT.published == []
    decision = asyncio.run(
        act.handle_device_ack(_ack_topic(), json.dumps(_ack(command_id=out["command_id"])))
    )
    assert decision.accepted is False
    assert pool.table.find(TENANT, out["command_id"])["delivery_state"] == "simulated"


def test_a_failed_publish_is_publish_failed(wired, monkeypatch):
    act, router_mod, pool = wired

    class _Down(_FakeMQTT):
        async def __aenter__(self):
            raise OSError("broker down")

    monkeypatch.setattr(act, "MQTTClient", _Down)
    out = _send(act, router_mod)
    assert (out["sent"], out["delivery_state"]) == (False, "publish_failed")


def test_writes_run_under_the_tenant_rls_context(wired):
    """device_commands_log is FORCE RLS: an insert without app.current_tenant is refused
    (v237 removed the no-context escape arm). The fake table raises in that case."""
    act, _router_mod, pool = wired
    asyncio.run(act.log_command(None, "valve-a", "open", {}, "blocked", TENANT))
    assert [r["status"] for r in pool.table.rows] == ["blocked"]
