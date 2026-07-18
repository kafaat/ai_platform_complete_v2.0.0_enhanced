"""IRR-F01 — platform restricted activation adapter (open-ledger #1).

Certifies the fail-closed REFUSAL contract of ``irrigation_activation_gate`` without a live gate:
a fake async client stands in for the decision-service enforce endpoint. Runs under bare pytest
via asyncio.run (the convergence workflow installs pytest-asyncio, but these need neither).

Requires httpx (the restricted adapter imports it); the convergence CI job installs it explicitly.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "services" / "sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


def _load(name: str):
    path = PLATFORM / "api" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"api.{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("irrigation_activation_gate")
IrrigationActivationNotEnabled = gate.IrrigationActivationNotEnabled


class _Resp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


class _Client:
    """Records calls; returns a scripted response or raises a scripted transport error."""

    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc
        self.calls = 0

    async def post(self, url, **kw):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._resp


def _run(coro):
    return asyncio.run(coro)


def test_enforcement_off_is_a_noop_and_never_calls_the_gate(monkeypatch):
    monkeypatch.delenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", raising=False)
    client = _Client(resp=_Resp(200, {"enforced": True}))
    out = _run(gate.enforce_or_raise(env="env-x", client=client))
    assert out["enforced"] is False and client.calls == 0


def test_enabled_gate_admits(monkeypatch):
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    client = _Client(resp=_Resp(200, {"enforced": True, "gate_state": "enabled", "generation": 3}))
    out = _run(gate.enforce_or_raise(env="env-x", client=client))
    assert out["gate_state"] == "enabled" and client.calls == 1


def test_disabled_gate_refuses_403(monkeypatch):
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    client = _Client(resp=_Resp(403, {"detail": "irr_f01_reservation not activated: revoked"}))
    with pytest.raises(IrrigationActivationNotEnabled) as ex:
        _run(gate.enforce_or_raise(env="env-x", client=client))
    assert "revoked" in ex.value.reason


@pytest.mark.parametrize("code", [500, 502, 503])
def test_non_200_fails_closed(monkeypatch, code):
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    client = _Client(resp=_Resp(code))
    with pytest.raises(IrrigationActivationNotEnabled) as ex:
        _run(gate.enforce_or_raise(env="env-x", client=client))
    assert "gate_unreachable" in ex.value.reason


def test_transport_error_fails_closed(monkeypatch):
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    client = _Client(exc=ConnectionError("refused"))
    with pytest.raises(IrrigationActivationNotEnabled) as ex:
        _run(gate.enforce_or_raise(env="env-x", client=client))
    assert "gate_unreachable" in ex.value.reason


def test_activation_guard_thunk_raises_when_gate_refuses(monkeypatch):
    # The thunk injected into reserve_and_request_dispatch_db must propagate the refusal.
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    client = _Client(resp=_Resp(403, {"detail": "not activated: disabled"}))
    guard = gate.activation_guard(env="env-x", client=client)
    with pytest.raises(IrrigationActivationNotEnabled):
        _run(guard())
