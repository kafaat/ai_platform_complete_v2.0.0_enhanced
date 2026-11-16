"""v238 — actuator command delivery state on a live PostgreSQL built from MANIFEST.

Measured as the restricted role (``TEST_DATABASE_URL``, NOSUPERUSER NOBYPASSRLS):

* the v238 trigger refuses inserting a device/expiry state and every illegal edge, and allows
  the legal ones (a positive witness, so "refuse everything" is not read as correctness);
* the real actuator writers (``record_command_queued`` / ``log_command``) persist under the
  tenant RLS context — before this change ``log_command`` inserted with no ``app.current_tenant``
  and the FORCE RLS WITH CHECK refused it (swallowed as a warning: no audit row at all);
* ``handle_device_ack`` moves a published command to ``device_acked`` only for a signed ack on
  the owning tenant's topic; the same ack on another tenant's topic changes nothing;
* ``expire_overdue_commands`` expires a published command past its deadline.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

asyncpg = pytest.importorskip("asyncpg")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "actuator-service"
SECRET = "v238-secret-" + "k" * 24

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="needs TEST_DATABASE_ADMIN_URL and TEST_DATABASE_URL (migrated DB, restricted role)",
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
        )
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
        )
        result = await other.execute(
            "UPDATE device_commands_log SET delivery_state='device_acked', "
            "device_acked_at=now() WHERE command_id='cmd_iso'"
        )
        assert result == "UPDATE 0"
    finally:
        await other.close()


def _stub_missing_dependencies() -> list[str]:
    inserted: list[str] = []
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
    monkeypatch.setenv("CMD_HMAC_SECRET", SECRET)
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


def _ack(cd, command_id: str, result: str = "applied") -> bytes:
    sig = cd.ack_signature(SECRET, command_id, "valve-a", result)
    body = {"id": command_id, "device": "valve-a", "result": result, "sig": sig}
    return json.dumps(body).encode()


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
        tenant_id=a, device_id="valve-a", command="open", payload={}, command_id=cid
    )
    assert (await _row(a, cid))["delivery_state"] == "queued"
    await runtime.log_command(
        None, "valve-a", "open", {}, "sent", a, command_id=cid, delivery_state="published"
    )
    row = await _row(a, cid)
    assert row["delivery_state"] == "published" and row["published_at"] is not None

    cross = await runtime.handle_device_ack(f"sahool/{b}/actuator/valve-a/ack", _ack(cd, cid))
    assert (cross.accepted, cross.reason) == (False, "unknown_command")
    assert (await _row(a, cid))["delivery_state"] == "published"

    ok = await runtime.handle_device_ack(f"sahool/{a}/actuator/valve-a/ack", _ack(cd, cid))
    assert ok.accepted and ok.target == "device_acked"
    row = await _row(a, cid)
    assert row["delivery_state"] == "device_acked" and row["device_acked_at"] is not None

    again = await runtime.handle_device_ack(
        f"sahool/{a}/actuator/valve-a/ack", _ack(cd, cid, "unknown_command")
    )
    assert again.accepted is False
    assert (await _row(a, cid))["delivery_state"] == "device_acked"


async def test_an_unacked_published_command_expires(runtime, tenants):
    a, _b = tenants
    cid = runtime.cd.new_command_id()
    await runtime.log_command(
        None, "valve-a", "open", {}, "sent", a, command_id=cid, delivery_state="published"
    )
    conn = await _app(a)
    try:
        await conn.execute(
            "UPDATE device_commands_log SET ack_deadline = now() - interval '1 second' "
            "WHERE command_id = $1",
            cid,
        )
        async with conn.transaction():
            await runtime._set_tenant(conn, a)
            assert await runtime.expire_overdue_commands(conn, a) == 1
    finally:
        await conn.close()
    row = await _row(a, cid)
    assert row["delivery_state"] == "expired" and row["expired_at"] is not None
    assert row["delivery_reason"] == "no_device_ack_before_deadline"
    late = await runtime.handle_device_ack(
        f"sahool/{a}/actuator/valve-a/ack", _ack(runtime.cd, cid)
    )
    assert late.accepted is False
    assert (await _row(a, cid))["delivery_state"] == "expired"
    assert timedelta(0) <= datetime.now(UTC) - row["expired_at"] < timedelta(minutes=1)


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

    # A recovery republish keeps the id: no duplicate row, and the trigger keeps device_acked.
    await runtime.run_dispatch_consumer_once(None, a, allowlist={"low"})
    conn = await _app(a)
    try:
        n = await conn.fetchval(
            "SELECT count(*) FROM device_commands_log WHERE command_id = $1", idem
        )
    finally:
        await conn.close()
    assert n == 1, f"a republish duplicated the command row ({n})"
    assert (await _row(a, idem))["delivery_state"] == "device_acked", "acked state regressed"
