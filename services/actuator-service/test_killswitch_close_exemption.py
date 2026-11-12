#!/usr/bin/env python3
"""ACTUATOR-KILLSWITCH-BLOCKS-CLOSE-01 — the kill-switch never holds CLOSE/OFF.

The emergency stop exists to stop water. Before this change every actuator path consulted
``is_actuation_halted`` without the command, so an engaged switch — or the fail-closed answer
when the database is unreachable — also refused CLOSE: a valve open when the operator hit the
switch stayed open until the firmware's 30-minute cap.

The shared helper already had ``command=`` (``shared/actuation_killswitch.py``,
``is_safe_direction``); this suite measures that each path now passes it, against the **real**
helper and a connection whose tenant-scoped switch is engaged (or whose query raises):

* manual ``/v1/command``: CLOSE goes through, OPEN is 423;
* compensation: the inverse CLOSE of an OPEN goes through, the inverse OPEN of a CLOSE is held;
* governed dispatch: a CLOSE request is claimed and sent, an OPEN request stays queued, and the
  OPEN in front no longer starves the CLOSE behind it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

SERVICE = Path(__file__).resolve().parent
ROOT = SERVICE.parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"


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


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _EngagedConn:
    """A tenant-scoped switch is engaged: it matches every consultation."""

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.queries = 0

    def transaction(self):
        return _Tx()

    async def execute(self, *_a, **_k):
        return "SELECT 1"

    async def fetch(self, *_a, **_k):
        self.queries += 1
        if self.broken:
            raise OSError("database unreachable")
        return [
            {
                "scope": "tenant",
                "field_id": None,
                "valve_id": None,
                "active": True,
                "reason": "إيقاف طوارئ",
                "expires_at": None,
            }
        ]


class _Pool:
    def __init__(self, conn) -> None:
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()


@pytest.fixture
def act(monkeypatch):
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
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
        spec = importlib.util.spec_from_file_location(
            "actuator_runtime", SERVICE / "actuator_runtime.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["actuator_runtime"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for name in names:
            sys.modules.pop(name, None)
        for name, value in saved.items():
            if value is not None:
                sys.modules[name] = value
        for name in stubbed:
            sys.modules.pop(name, None)


@pytest.fixture
def sent(act, monkeypatch):
    out: list[tuple[str, str]] = []

    async def _send(device_id, command, payload, **_kw):
        out.append((device_id, command))
        return True

    async def _noop(**_kw):
        return None

    monkeypatch.setattr(act, "send_mqtt_command", _send)
    monkeypatch.setattr(act, "record_command_queued", _noop)
    monkeypatch.setattr(act, "log_command", _noop)
    return out


# ── manual /v1/command ───────────────────────────────────────────────────────
@pytest.mark.parametrize("broken", [False, True], ids=["engaged", "db_unreachable"])
def test_manual_close_goes_through_an_engaged_or_unverifiable_killswitch(
    act, sent, monkeypatch, broken
):
    import routers.commands as router_mod
    from fastapi import HTTPException

    async def _auth(*_a, **_k):
        return "field-9"

    monkeypatch.setattr(act, "FEATURE_MANUAL_ACTUATOR_COMMANDS", "true")
    monkeypatch.setattr(act, "_authorize_device_control", _auth)
    monkeypatch.setattr(act, "_pool", _Pool(_EngagedConn(broken=broken)))
    claims = {"tenant_id": TENANT, "role": "owner", "sub": "u1"}

    out = asyncio.run(
        router_mod.send_command(act.CommandRequest(device_id="valve-a", command="close"), claims)
    )
    assert out["sent"] is True and sent == [("valve-a", "close")]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router_mod.send_command(
                act.CommandRequest(
                    device_id="valve-a", command="open", payload={"duration_sec": 60}
                ),
                claims,
            )
        )
    assert exc.value.status_code == 423
    assert sent == [("valve-a", "close")], "an OPEN slipped through the kill-switch"


# ── compensation ────────────────────────────────────────────────────────────
def test_a_compensating_close_goes_through_and_a_compensating_open_is_held(act, sent, monkeypatch):
    monkeypatch.setattr(act, "_pool", _Pool(_EngagedConn()))
    prior = [
        {"device": "valve-1", "command": "open", "payload": {}, "rule_id": "r1"},
        {"device": "valve-2", "command": "close", "payload": {}, "rule_id": "r2"},
    ]

    asyncio.run(act._compensate(prior, TENANT, "valve-3", "open", field_id="f1"))

    # Reverse order: valve-2's inverse is OPEN (held), valve-1's inverse is CLOSE (sent).
    assert sent == [("valve-1", "close")]


# ── governed dispatch ───────────────────────────────────────────────────────
def test_dispatch_sends_a_close_and_leaves_an_open_queued_under_the_killswitch(act, monkeypatch):
    claimed: list[str] = []
    published: list[tuple[str, str]] = []

    class _Resp:
        def __init__(self, code, body=None):
            self.status_code = code
            self._body = body or {}

        def json(self):
            return self._body

    items = [
        {
            "execution_request_id": "req-open",
            "target_id": "valve-a",
            "command_payload": {
                "device_id": "valve-a",
                "command": "open_valve",
                "payload": {"duration_sec": 60},
                "risk_level": "low",
            },
        },
        {
            "execution_request_id": "req-close",
            "target_id": "valve-a",
            "command_payload": {"device_id": "valve-a", "command": "close", "risk_level": "low"},
        },
    ]

    async def _request(_client, method, path, _tenant, json_body=None):
        if "recovery" in path:
            return _Resp(200, {"items": []})
        if "state=queued" in path:
            return _Resp(200, {"items": items})
        if path.endswith("/claim"):
            claimed.append(path.split("/")[-2])
        return _Resp(200)

    async def _device_ok(*_a, **_k):
        return True, "ok"

    async def _send(device_id, command, payload, **_kw):
        published.append((device_id, command))
        return True

    monkeypatch.setattr(act, "_pool", _Pool(_EngagedConn()))
    monkeypatch.setattr(act, "_decision_request", _request)
    monkeypatch.setattr(act, "_validate_dispatch_device", _device_ok)
    monkeypatch.setattr(act, "send_mqtt_command", _send)
    monkeypatch.setattr(act, "ACTUATOR_DELIVERY_TOKEN_KEY", "k" * 32)

    processed = asyncio.run(act.run_dispatch_consumer_once(None, TENANT, allowlist={"low"}))

    assert claimed == ["req-close"], "the OPEN must stay queued (unclaimed) under the halt"
    assert published == [("valve-a", "close")]
    assert processed == 1
