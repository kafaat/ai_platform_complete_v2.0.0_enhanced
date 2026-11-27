"""v238 — actuator command delivery state on a live PostgreSQL built from MANIFEST.

Measured as the restricted role (``TEST_DATABASE_URL``, NOSUPERUSER NOBYPASSRLS):

* the v238 trigger refuses inserting a device/expiry state and every illegal edge, and allows
  the legal ones (a positive witness, so "refuse everything" is not read as correctness);
* the real actuator writers (``record_command_queued`` / ``log_command``) persist under the
  tenant RLS context — before this change ``log_command`` inserted with no ``app.current_tenant``
  and the FORCE RLS WITH CHECK refused it (swallowed as a warning: no audit row at all);
* ``handle_device_ack`` moves a published command to ``device_acked`` only for a v2 ack signed
  with the owning device's derived key on the owning tenant's topic. The same ack replayed on
  another tenant's topic is refused on its signed tenant, and another tenant's own correctly
  signed ack naming the command finds nothing under its RLS context (``unknown_command``);
* the actuator stays strict (R-C2, #1386): a v1 ack signed with the shared ``CMD_HMAC_SECRET``
  for a device not on ``ACTUATOR_LEGACY_V1_DEVICES``, or a v2 ack signed with the wrong key,
  moves nothing;
* ``expire_overdue_commands`` expires a published command past its deadline.

The acks are built exactly as the firmware builds them (``publishDeviceAck`` in
``firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino``): ``v``, ``id``, ``tenant``, ``device``,
``result``, ``ctr``, ``status`` and ``sig = HMAC(device_key, "v2ack|tenant|device|id|result|ctr")``
with the per-device key derived from ``CMD_HMAC_MASTER_KEY``.
"""

from __future__ import annotations

import importlib
import importlib.util
import itertools
import json
import os
import sys
import types
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("ACTUATOR_DELIVERY_STATE_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "actuator-service"
# v1 shared secret: set only to prove a v1 ack is still refused for a device not on the
# legacy allowlist. v2 master key: what the platform derives every device key from.
SECRET = "v238-secret-" + "k" * 24
MASTER = "v238-master-key-" + "m" * 32
DEVICE = "valve-a"

if _CERTIFICATION_REQUIRED and not (_ADMIN_DSN and _APP_DSN):
    raise RuntimeError(
        "ACTUATOR_DELIVERY_STATE_CERTIFICATION_REQUIRED=1 needs TEST_DATABASE_URL and "
        "TEST_DATABASE_ADMIN_URL"
    )

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="declared skip (not a pass): needs TEST_DATABASE_ADMIN_URL and TEST_DATABASE_URL "
        "(migrated DB, restricted role)",
    )
)


@pytest.fixture
async def tenants():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    yield a, b
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(
            "DELETE FROM device_commands_log WHERE tenant_id = ANY($1::uuid[])", [a, b]
        )
    finally:
        await admin.close()


async def _app(tenant: str | None = None):
    conn = await asyncpg.connect(_APP_DSN)
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert row is not None and not row["rolsuper"] and not row["rolbypassrls"], (
        "TEST_DATABASE_URL is not a restricted role — it would not measure RLS"
    )
    if tenant is not None:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return conn


_INSERT = """INSERT INTO device_commands_log
    (tenant_id, device_id, command, status, command_id, delivery_state, queued_at,
     published_at, ack_deadline)
    VALUES ($1::uuid, 'valve-a', 'open', 'sent', $2, $3, now(), $4, now() + interval '2 min')"""


async def test_the_trigger_refuses_illegal_delivery_edges_and_allows_legal_ones(tenants):
    a, _b = tenants
    conn = await _app(a)
    try:
        for bad in ("device_acked", "device_rejected", "expired"):
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await conn.execute(_INSERT, a, f"cmd_{bad}", bad, datetime.now(UTC))
        await conn.execute(_INSERT, a, "cmd_q", "queued", None)
        with pytest.raises(asyncpg.exceptions.CheckViolationError, match="illegal delivery"):
            await conn.execute(
                "UPDATE device_commands_log SET delivery_state='device_acked', "
                "published_at=now(), device_acked_at=now() WHERE command_id='cmd_q'"
            )
        await conn.execute(
            "UPDATE device_commands_log SET delivery_state='published', published_at=now() "
            "WHERE command_id='cmd_q'"
        )
        await conn.execute(
            "UPDATE device_commands_log SET delivery_state='device_acked', device_acked_at=now() "
            "WHERE command_id='cmd_q'"
        )
        for bad in ("expired", "device_rejected", "published", "queued"):
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await conn.execute(
                    "UPDATE device_commands_log SET delivery_state=$1, expired_at=now(), "
                    "device_rejected_at=now() WHERE command_id='cmd_q'",
                    bad,
                )
        with pytest.raises(asyncpg.exceptions.CheckViolationError, match="immutable"):
            await conn.execute(
                "UPDATE device_commands_log SET command_id='cmd_other' WHERE command_id='cmd_q'"
            )
        assert (
            await conn.fetchval(
                "SELECT delivery_state FROM device_commands_log WHERE command_id='cmd_q'"
            )
            == "device_acked"
        ), "the legal queued -> published -> device_acked path did not persist"
    finally:
        await conn.close()


async def test_another_tenant_cannot_see_or_move_a_command(tenants):
    a, b = tenants
    owner = await _app(a)
    try:
        await owner.execute(_INSERT, a, "cmd_iso", "published", datetime.now(UTC))
    finally:
        await owner.close()
    other = await _app(b)
    try:
        assert (
            await other.fetchval(
                "SELECT count(*) FROM device_commands_log WHERE command_id='cmd_iso'"
            )
            == 0
        ), "tenant B sees tenant A's command"
        result = await other.execute(
            "UPDATE device_commands_log SET delivery_state='device_acked', "
            "device_acked_at=now() WHERE command_id='cmd_iso'"
        )
        assert result == "UPDATE 0", f"tenant B moved tenant A's command: {result}"
    finally:
        await other.close()


def _stub_missing_dependencies() -> list[str]:
    """Stub the broker/JWT clients the runtime imports but these tests never call.

    Under the certification switch nothing is stubbed: a missing dependency fails the import.
    """
    inserted: list[str] = []
    if _CERTIFICATION_REQUIRED:
        return inserted
    for name in ("jwt", "aiomqtt"):
        try:
            __import__(name)
        except ImportError:
            stub = types.ModuleType(name)
            stub.Client = object
            stub.decode = lambda *_a, **_k: {}
            sys.modules[name] = stub
            inserted.append(name)
    return inserted


@pytest.fixture
async def runtime(monkeypatch):
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "real")
    # Production configuration after R-C2: every device on v2 (derived key), none on v1. The
    # v1 secret is set as well, so the refusal of a v1 ack below is the allowlist's doing.
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", MASTER)
    monkeypatch.setenv("CMD_HMAC_SECRET", SECRET)
    monkeypatch.delenv("ACTUATOR_LEGACY_V1_DEVICES", raising=False)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    names = ("actuator_runtime", "routers", "routers.commands", "command_delivery")
    for name in names:
        sys.modules.pop(name, None)
    pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=2)
    try:
        spec = importlib.util.spec_from_file_location(
            "actuator_runtime", SERVICE / "actuator_runtime.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["actuator_runtime"] = mod
        spec.loader.exec_module(mod)
        monkeypatch.setattr(mod, "_pool", pool)
        monkeypatch.setattr(mod, "_ACK_NOT_YET_PUBLISHED_DELAY_SECONDS", 0, raising=False)
        yield mod
    finally:
        await pool.close()
        for name in names:
            sys.modules.pop(name, None)
        for name in stubbed:
            sys.modules.pop(name, None)


async def _row(tenant: str, command_id: str):
    conn = await _app(tenant)
    try:
        return await conn.fetchrow(
            "SELECT * FROM device_commands_log WHERE command_id = $1", command_id
        )
    finally:
        await conn.close()


_CTR = itertools.count(1_700_000_000_000_000)


def _ack(
    runtime,
    tenant: str,
    command_id: str,
    result: str = "applied",
    *,
    key_tenant: str | None = None,
    master: str = MASTER,
) -> bytes:
    """A v2 device ack, field for field as ``publishDeviceAck`` publishes it.

    ``key_tenant`` signs with another tenant's device key (a forged or misprovisioned unit).
    """
    cs = runtime.cs
    key = cs.derive_device_key(master, key_tenant or tenant, DEVICE)
    ctr = next(_CTR)
    body = {
        "v": cs.PROTOCOL_VERSION,
        "id": command_id,
        "tenant": tenant,
        "device": DEVICE,
        "result": result,
        "ctr": ctr,
        "status": "ON",
        "sig": cs.sign_ack(key, tenant, DEVICE, command_id, result, ctr),
    }
    return json.dumps(body).encode()


def _ack_v1(runtime, command_id: str, result: str = "applied") -> bytes:
    """A legacy v1 ack signed with the shared secret (what this file sent before #1386)."""
    sig = runtime.cd.ack_signature(SECRET, command_id, DEVICE, result)
    return json.dumps({"id": command_id, "device": DEVICE, "result": result, "sig": sig}).encode()


async def _published(runtime, tenant: str) -> str:
    cid = runtime.cd.new_command_id()
    assert await runtime.record_command_queued(
        tenant_id=tenant, device_id=DEVICE, command="open", payload={}, command_id=cid
    ), "record_command_queued wrote nothing under the tenant RLS context"
    await runtime.log_command(
        None, DEVICE, "open", {}, "sent", tenant, command_id=cid, delivery_state="published"
    )
    row = await _row(tenant, cid)
    assert row["delivery_state"] == "published" and row["published_at"] is not None, dict(row)
    return cid


async def test_untracked_log_command_persists_under_rls(runtime, tenants):
    a, _b = tenants
    await runtime.log_command(None, "valve-a", "open", {}, "blocked", a)
    conn = await _app(a)
    try:
        assert (
            await conn.fetchval("SELECT count(*) FROM device_commands_log WHERE status='blocked'")
            == 1
        ), "log_command wrote nothing: insert outside the tenant RLS context"
    finally:
        await conn.close()


async def test_signed_ack_on_the_owning_tenant_topic_is_the_only_way_to_device_acked(
    runtime, tenants
):
    a, b = tenants
    cd = runtime.cd
    cid = cd.new_command_id()
    assert await runtime.record_command_queued(
        tenant_id=a, device_id=DEVICE, command="open", payload={}, command_id=cid
    ), "record_command_queued wrote nothing under the tenant RLS context"
    assert (await _row(a, cid))["delivery_state"] == "queued", "a new command must start queued"
    await runtime.log_command(
        None, DEVICE, "open", {}, "sent", a, command_id=cid, delivery_state="published"
    )
    row = await _row(a, cid)
    assert row["delivery_state"] == "published" and row["published_at"] is not None, dict(row)

    # Tenant A's device ack replayed on tenant B's topic: its signed tenant is A, refused.
    replay = await runtime.handle_device_ack(
        f"sahool/{b}/actuator/{DEVICE}/ack", _ack(runtime, a, cid)
    )
    assert (replay.accepted, replay.reason) == (False, "ack_tenant_does_not_match_topic"), replay
    # Tenant B's own device, correctly signed for B, naming A's command: the lookup runs under
    # B's RLS context and finds nothing; A's command does not move.
    cross = await runtime.handle_device_ack(
        f"sahool/{b}/actuator/{DEVICE}/ack", _ack(runtime, b, cid)
    )
    assert (cross.accepted, cross.reason) == (False, "unknown_command"), cross
    assert (await _row(a, cid))["delivery_state"] == "published", "another tenant moved the command"

    ok = await runtime.handle_device_ack(f"sahool/{a}/actuator/{DEVICE}/ack", _ack(runtime, a, cid))
    assert ok.accepted and ok.target == "device_acked", ok
    row = await _row(a, cid)
    assert row["delivery_state"] == "device_acked" and row["device_acked_at"] is not None, dict(row)

    again = await runtime.handle_device_ack(
        f"sahool/{a}/actuator/{DEVICE}/ack", _ack(runtime, a, cid, "unknown_command")
    )
    assert again.accepted is False, again
    assert (await _row(a, cid))["delivery_state"] == "device_acked", "a terminal state moved"


async def test_a_v1_or_wrongly_keyed_ack_moves_nothing(runtime, tenants):
    """The fixture change did not loosen the actuator: v1 (not allowlisted) and bad keys fail."""
    a, b = tenants
    cid = await _published(runtime, a)
    topic = f"sahool/{a}/actuator/{DEVICE}/ack"

    v1 = await runtime.handle_device_ack(topic, _ack_v1(runtime, cid))
    assert (v1.accepted, v1.reason) == (False, "legacy_v1_ack_not_allowed"), v1
    other_key = await runtime.handle_device_ack(topic, _ack(runtime, a, cid, key_tenant=b))
    assert (other_key.accepted, other_key.reason) == (False, "bad_ack_signature"), other_key
    wrong_master = await runtime.handle_device_ack(
        topic, _ack(runtime, a, cid, master="another-master-key-" + "x" * 32)
    )
    assert (wrong_master.accepted, wrong_master.reason) == (False, "bad_ack_signature"), (
        wrong_master
    )
    assert (await _row(a, cid))["delivery_state"] == "published", "a refused ack moved the command"


async def test_an_unacked_published_command_expires(runtime, tenants):
    a, _b = tenants
    cid = await _published(runtime, a)
    conn = await _app(a)
    try:
        await conn.execute(
            "UPDATE device_commands_log SET ack_deadline = now() - interval '1 second' "
            "WHERE command_id = $1",
            cid,
        )
        async with conn.transaction():
            await runtime._set_tenant(conn, a)
            assert await runtime.expire_overdue_commands(conn, a) == 1, "nothing expired"
    finally:
        await conn.close()
    row = await _row(a, cid)
    assert row["delivery_state"] == "expired" and row["expired_at"] is not None, dict(row)
    assert row["delivery_reason"] == "no_device_ack_before_deadline", dict(row)
    late = await runtime.handle_device_ack(
        f"sahool/{a}/actuator/{DEVICE}/ack", _ack(runtime, a, cid)
    )
    assert late.accepted is False and late.target is None, late
    assert (await _row(a, cid))["delivery_state"] == "expired", (
        "a late ack moved an expired command"
    )
    assert timedelta(0) <= datetime.now(UTC) - row["expired_at"] < timedelta(minutes=1), (
        f"expired_at is not the expiry time: {row['expired_at']}"
    )


async def test_a_decision_dispatched_command_reaches_device_acked_on_a_signed_ack(
    runtime, tenants, monkeypatch
):
    """W2-07 (water-1): the decision dispatch consumer records the command (queued, then
    published) under the id the wire carries, so the device's signed v2 ack moves it to
    device_acked under RLS and the v238 trigger. Before, no row existed and the ack was dropped
    as unknown_command."""
    a, _b = tenants
    master = "v238-live-master-NOT-FOR-PRODUCTION-" + "m" * 16
    monkeypatch.setenv("CMD_HMAC_MASTER_KEY", master)
    idem = f"dispatch-{uuid.uuid4().hex}"
    item = {
        "execution_request_id": str(uuid.uuid4()),
        "target_id": "valve-a",
        "requested_at": "2026-11-16T08:00:00+00:00",
        "command_payload": {
            "field_id": "field-9",
            "device_id": "valve-a",
            "command": "open_valve",
            "idempotency_key": idem,
            "payload": {"duration_sec": 60},
        },
    }
    receipts: list[str] = []
    seen_at_publish: list[str | None] = []

    class _Resp:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self._body = body or {}

        def json(self):
            return self._body

    async def decision(_client, method, path, _tenant, json_body=None):
        if method == "GET":
            return _Resp(200, {"items": [] if "recovery" in path else [item]})
        if path.endswith("/receipt"):
            receipts.append(json_body["receipt_status"])
        return _Resp(200)

    async def device_ok(_tenant, _device, field_id):
        return True, "ok", field_id

    async def clear(*_a, **_k):
        return False, None

    async def publish(device_id, command, payload, *, command_id=None, **_kw):
        row = await _row(a, command_id)
        seen_at_publish.append(row["delivery_state"] if row else None)
        return True

    monkeypatch.setattr(runtime, "_decision_request", decision)
    monkeypatch.setattr(runtime, "_validate_dispatch_device", device_ok)
    monkeypatch.setattr(runtime, "is_actuation_halted", clear)
    monkeypatch.setattr(runtime, "send_mqtt_command", publish)
    monkeypatch.setattr(runtime, "ACTUATOR_DELIVERY_TOKEN_KEY", "live-delivery-key")

    processed = await runtime.run_dispatch_consumer_once(None, a, allowlist={"low"})
    assert processed == 1 and receipts == ["accepted"], f"dispatch cycle failed: {receipts}"
    assert seen_at_publish == ["queued"], f"not queued before publish: {seen_at_publish}"
    row = await _row(a, idem)
    assert row is not None and row["delivery_state"] == "published", (
        f"the dispatched command was not recorded published: {row}"
    )
    assert row["triggered_by"] == "decision_dispatch", f"triggered_by: {row['triggered_by']}"

    cs = runtime.cs
    key = cs.derive_device_key(master, a, "valve-a")
    ack = {
        "v": 2,
        "id": idem,
        "tenant": a,
        "device": "valve-a",
        "result": "applied",
        "ctr": 1,
        "status": "ON",
        "sig": cs.sign_ack(key, a, "valve-a", idem, "applied", 1),
    }
    ok = await runtime.handle_device_ack(
        f"sahool/{a}/actuator/valve-a/ack", json.dumps(ack).encode()
    )
    assert ok.accepted and ok.target == "device_acked", f"signed ack refused: {ok.reason}"
    row = await _row(a, idem)
    assert row["delivery_state"] == "device_acked" and row["device_acked_at"] is not None, (
        f"device_acked was not persisted: {dict(row)}"
    )

    # Recovery acknowledges the existing outcome and never calls the publisher again.
    await runtime.run_dispatch_consumer_once(None, a, allowlist={"low"})
    conn = await _app(a)
    try:
        n = await conn.fetchval(
            "SELECT count(*) FROM device_commands_log WHERE command_id = $1", idem
        )
    finally:
        await conn.close()
    assert seen_at_publish == ["queued"]
    assert n == 1, f"recovery duplicated the command row ({n})"
    assert (await _row(a, idem))["delivery_state"] == "device_acked", "acked state regressed"


@pytest.fixture
def dispatch_case(runtime, monkeypatch):
    """Real queue/outcome transactions and signed wire messages. Only the broker and
    upstream decision/device inputs are synthetic."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    receipts, messages, queued_at_publish = [], [], []
    field = "field-9"
    item = {
        "execution_request_id": "req-1636",
        "target_id": DEVICE,
        "requested_at": "2026-11-26T12:00:00+00:00",
        "command_payload": {
            "device_id": DEVICE,
            "command": "start",
            "payload": {"duration_sec": 60},
        },
    }

    async def decision(_client, method, path, _tenant, json_body=None):
        if method == "GET":
            return SimpleNamespace(
                status_code=200, json=lambda: {"items": [item] if "recovery" in path else []}
            )
        if path.endswith("/receipt"):
            receipts.append(json_body)
        return SimpleNamespace(status_code=200)

    class Broker:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def publish(self, topic, message, qos):
            wire = json.loads(message)
            messages.append(wire)
            row = await _row(wire["tenant"], wire["id"])
            queued_at_publish.append(row["delivery_state"] if row else None)

    async def run(tenant):
        return await runtime.run_dispatch_consumer_once(None, tenant, allowlist={"low"})

    monkeypatch.setattr(runtime, "_decision_request", decision)
    monkeypatch.setattr(
        runtime, "_validate_dispatch_device", AsyncMock(return_value=(True, "ok", field))
    )
    monkeypatch.setattr(runtime, "_device_field", AsyncMock(return_value=field))
    monkeypatch.setattr(runtime, "is_actuation_halted", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(runtime, "ACTUATOR_DELIVERY_TOKEN_KEY", "test-fixture-key")
    monkeypatch.setattr(runtime, "MQTTClient", Broker)
    return SimpleNamespace(
        run=run,
        item=item,
        messages=messages,
        receipts=receipts,
        states=queued_at_publish,
        cid=item["execution_request_id"],
    )


async def test_queue_gate_concurrent_recovery_and_tenant_isolation(dispatch_case, tenants):
    import asyncio

    c = dispatch_case
    a, b = tenants
    await asyncio.gather(c.run(a), c.run(a))
    await c.run(a)
    await c.run(b)
    assert [(m["tenant"], m["id"]) for m in c.messages] == [(a, c.cid), (b, c.cid)]
    assert c.states == ["queued", "queued"]
    assert c.receipts[-2]["receipt_status"] == "accepted"


@pytest.mark.parametrize("changed", ["payload", "device", "command", "field", "origin"])
async def test_queue_gate_id_conflict_preserves_row(dispatch_case, tenants, changed):
    c = dispatch_case
    a, _ = tenants
    await c.run(a)
    if changed == "origin":
        conn = await _app(a)
        try:
            await conn.execute(
                "UPDATE device_commands_log SET triggered_by='manual' WHERE command_id=$1", c.cid
            )
        finally:
            await conn.close()
    before = dict(await _row(a, c.cid))
    command = c.item["command_payload"]
    if changed == "payload":
        command["payload"]["duration_sec"] = 61
    elif changed == "device":
        c.item["target_id"] = command["device_id"] = "valve-b"
    elif changed == "command":
        command["command"] = "off"
    elif changed == "field":
        command["field_id"] = "field-b"
    await c.run(a)
    assert len(c.messages) == 1
    assert c.receipts[-1]["receipt_status"] == "failed"
    assert c.receipts[-1]["receipt_payload"]["reason"] == "command_id_conflict"
    assert dict(await _row(a, c.cid)) == before


async def test_queue_gate_recovery_after_unknown_publish_and_expiry(
    dispatch_case, runtime, tenants, monkeypatch
):
    from unittest.mock import AsyncMock

    c = dispatch_case
    a, _ = tenants
    # Simulate a crash after the broker accepted, before writing the outcome.
    with monkeypatch.context() as mp:
        mp.setattr(runtime, "log_command", AsyncMock())
        await c.run(a)
    assert (await _row(a, c.cid))["delivery_state"] == "queued"
    await c.run(a)
    assert len(c.messages) == 1
    conn = await _app(a)
    try:
        await conn.execute(
            "UPDATE device_commands_log SET ack_deadline=now()-interval '1 second' WHERE command_id=$1",
            c.cid,
        )
    finally:
        await conn.close()
    await c.run(a)
    assert len(c.messages) == 1
    assert c.receipts[-1]["receipt_status"] == "failed"
    assert c.receipts[-1]["receipt_payload"]["reason"] == "existing_expired"


async def test_queue_gate_lock_timeout(dispatch_case, runtime, tenants, monkeypatch):
    c = dispatch_case
    a, _ = tenants
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        async with asyncpg.create_pool(
            _APP_DSN, min_size=1, max_size=2, server_settings={"lock_timeout": "100ms"}
        ) as pool:
            monkeypatch.setattr(runtime, "_pool", pool)
            async with admin.transaction():
                await admin.execute("LOCK TABLE device_commands_log IN SHARE MODE")
                await c.run(a)
    finally:
        await admin.close()
    assert c.messages == []
    assert c.receipts[-1]["receipt_status"] == "failed"
    assert await _row(a, c.cid) is None


async def test_queue_gate_compensating_start_fk_failure(runtime, tenants, monkeypatch):
    from unittest.mock import AsyncMock

    a, _ = tenants
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(runtime, "_consult_killswitch", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(runtime, "send_mqtt_command", send)
    prior = [
        {
            "device": DEVICE,
            "command": "stop",
            "payload": {"duration_sec": 10},
            "rule_id": str(uuid.uuid4()),
        }
    ]
    await runtime._compensate(prior, a, "other-valve", "start", field_id="field-9")
    send.assert_not_awaited()


async def test_queue_gate_ack_during_publish(dispatch_case, runtime, tenants, monkeypatch):
    import asyncio

    case = dispatch_case
    a, _ = tenants
    early_ack = asyncio.Event()
    evaluate = runtime.cd.evaluate_ack
    original_publish = runtime.MQTTClient.publish
    tasks = []

    def observe(*args, **kwargs):
        decision = evaluate(*args, **kwargs)
        if decision.reason == "not_yet_published":
            early_ack.set()
        return decision

    async def publish(broker, topic, message, qos):
        await original_publish(broker, topic, message, qos)
        tasks.append(
            asyncio.create_task(
                runtime.handle_device_ack(
                    f"sahool/{a}/actuator/{DEVICE}/ack", _ack(runtime, a, case.cid)
                )
            )
        )
        await asyncio.wait_for(early_ack.wait(), 2)

    monkeypatch.setattr(runtime.cd, "evaluate_ack", observe)
    monkeypatch.setattr(runtime.MQTTClient, "publish", publish)
    monkeypatch.setattr(runtime, "_ACK_NOT_YET_PUBLISHED_DELAY_SECONDS", 0.05)
    await case.run(a)
    assert early_ack.is_set()
    assert (await tasks[0]).accepted
    assert (await _row(a, case.cid))["delivery_state"] == "device_acked"
    await case.run(a)
    assert len(case.messages) == 1


async def test_queue_gate_stop_during_write_outage(dispatch_case, runtime, tenants, monkeypatch):
    from unittest.mock import AsyncMock

    case = dispatch_case
    a, _ = tenants
    await case.run(a)
    case.item["command_payload"]["command"] = "off"
    monkeypatch.setattr(runtime, "record_command_queued", AsyncMock(side_effect=TimeoutError))
    await case.run(a)
    await case.run(a)
    opened, first, retry = case.messages
    assert first["cmd"] == retry["cmd"] == "CLOSE"
    assert opened["id"] != first["id"] == retry["id"]
    assert first["v"] == 2 and retry["ctr"] > first["ctr"]
    assert case.states == ["queued", None, None]
    ack = await runtime.handle_device_ack(
        f"sahool/{a}/actuator/{DEVICE}/ack", _ack(runtime, a, first["id"])
    )
    assert ack.reason == "unknown_command"
    assert (await _row(a, opened["id"]))["delivery_state"] == "published"


@pytest.mark.parametrize("identifier", [" req-1636 ", "safestop_v1_reserved"])
async def test_queue_gate_noncanonical_id(dispatch_case, tenants, identifier):
    case = dispatch_case
    a, _ = tenants
    case.item["command_payload"]["idempotency_key"] = identifier
    await case.run(a)
    assert case.messages == []
    assert case.receipts[-1]["receipt_payload"]["reason"] == "invalid_command_id"


async def test_queue_gate_missing_pool(runtime, tenants, monkeypatch):
    from unittest.mock import AsyncMock

    a, _ = tenants
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(runtime, "_pool", None)
    monkeypatch.setattr(runtime, "send_mqtt_command", send)
    assert not await runtime.record_command_queued(
        tenant_id=a,
        device_id=DEVICE,
        command="open",
        payload={"duration_sec": 10},
        command_id="test",
    )
    prior = [
        {"device": DEVICE, "command": cmd, "payload": {"duration_sec": 10}, "field_id": "field-9"}
        for cmd in ("open", "close")
    ]
    await runtime._compensate(prior, a, "another-device", "start", field_id="field-9")
    assert [call.args[1] for call in send.await_args_list] == ["close"]
    assert send.await_args.kwargs["field_id"] == "field-9"


async def test_queue_gate_recovers_pending_close(dispatch_case, runtime, tenants):
    case = dispatch_case
    a, _ = tenants
    command = case.item["command_payload"]
    command["command"] = "off"
    assert await runtime.record_command_queued(
        tenant_id=a,
        device_id=DEVICE,
        command="off",
        payload={**command["payload"], "field_id": "field-9"},
        command_id=case.cid,
        triggered_by="decision_dispatch",
    )
    await case.run(a)
    await case.run(a)
    assert [(m["id"], m["cmd"]) for m in case.messages] == [(case.cid, "CLOSE")]
    assert case.receipts[0]["receipt_payload"]["reason"] == "retry_queued_close"
    assert (await _row(a, case.cid))["delivery_state"] == "published"
