"""Phase 2 P2-c — proof tests for the raster-service live consumer of the satellite_cdse gate.

Deterministic unit tests over the restricted adapter (``imagery_source_gate``): the state→provider
mapping, fail-closed behaviour on every error, default-off no-op, generation binding for the job
race, and the provenance carried into a consumer's evidence. HTTP is faked with
``httpx.MockTransport`` (the repo's established pattern — no live services).
"""

from __future__ import annotations

import httpx
import imagery_source_gate as gate
import pytest

pytestmark = pytest.mark.unit

ENV = "env-cdse-test"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _source_response(source: str, *, gate_state: str, generation: int, fallback: bool, reason=None):
    body = {
        "source": source,
        "gate_state": gate_state,
        "generation": generation,
        "build_sha": "a" * 64,
        "fallback": fallback,
        "environment_id": ENV,
    }
    if reason is not None:
        body["reason"] = reason

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return handler


async def test_enforcement_off_is_a_noop_and_never_calls_the_gate(monkeypatch):
    monkeypatch.delenv("RASTER_ACTIVATION_GATE_ENFORCE", raising=False)

    def explode(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("gate must not be contacted when enforcement is off")

    async with _client(explode) as c:
        decision = await gate.resolve_active_source(env=ENV, client=c)
    assert decision.enforced is False
    assert decision.gate_state == "not_enforced"


async def test_enabled_selects_cdse(monkeypatch):
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")
    handler = _source_response("cdse", gate_state="enabled", generation=5, fallback=False)
    async with _client(handler) as c:
        d = await gate.resolve_active_source(env=ENV, client=c)
    assert d.use_cdse is True and d.provider == "cdse"
    assert d.generation == 5 and d.enforced is True and d.degraded is False and d.fallback is False


@pytest.mark.parametrize("state", ["degraded", "disabled", "revoked", "evaluating"])
async def test_non_enabled_states_route_to_element84(monkeypatch, state):
    """degraded/disabled/revoked/evaluating all fall to the safe Element84 source (proofs #2, #3):
    the /source endpoint already collapses them, and the consumer never speculates CDSE."""
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")
    handler = _source_response(
        "element84", gate_state=state, generation=7, fallback=True, reason=state
    )
    async with _client(handler) as c:
        d = await gate.resolve_active_source(env=ENV, client=c)
    assert d.use_cdse is False and d.provider == "element84"
    assert d.fallback is True and d.reason == state and d.enforced is True


async def test_gate_unreachable_fails_closed(monkeypatch):
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")

    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to decision-service")

    async with _client(boom) as c:
        d = await gate.resolve_active_source(env=ENV, client=c)
    assert d.use_cdse is False and d.provider == "element84"
    assert d.degraded is True and d.reason.startswith("gate_unreachable:")


async def test_mirror_503_fails_closed(monkeypatch):
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")

    def mirror(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "activation gate requires the system-of-record"})

    async with _client(mirror) as c:
        d = await gate.resolve_active_source(env=ENV, client=c)
    assert d.provider == "element84" and d.degraded is True
    assert d.reason == "gate_unreachable:http_503"


async def test_unknown_source_is_defensively_element84(monkeypatch):
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")
    handler = _source_response(
        "mystery-provider", gate_state="enabled", generation=9, fallback=False
    )
    async with _client(handler) as c:
        d = await gate.resolve_active_source(env=ENV, client=c)
    # a contract drift must never upgrade the consumer to CDSE
    assert d.provider == "element84" and d.degraded is True and d.reason == "unknown_source"


async def test_generation_race_rebinds_provider_and_generation(monkeypatch):
    """Proof #4: a job authorized at generation N is bound to N; a concurrent revoke bumps the
    generation, so a fresh resolve returns Element84 under N+1 — the flip is observable."""
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")
    state = {"phase": "enabled"}

    def handler(_request: httpx.Request) -> httpx.Response:
        if state["phase"] == "enabled":
            return httpx.Response(
                200,
                json={
                    "source": "cdse",
                    "gate_state": "enabled",
                    "generation": 5,
                    "fallback": False,
                    "environment_id": ENV,
                },
            )
        return httpx.Response(
            200,
            json={
                "source": "element84",
                "gate_state": "revoked",
                "generation": 6,
                "fallback": True,
                "reason": "revoked",
                "environment_id": ENV,
            },
        )

    async with _client(handler) as c:
        at_start = await gate.resolve_active_source(env=ENV, client=c)
        assert at_start.use_cdse is True and at_start.generation == 5
        state["phase"] = "revoked"  # operator revokes mid-flight
        after = await gate.resolve_active_source(env=ENV, client=c)
    assert after.use_cdse is False and after.generation == 6
    assert after.generation != at_start.generation  # generation change is the race signal


async def test_evidence_carries_full_provenance(monkeypatch):
    """Proof #5: the evidence a consumer persists includes generation, provider, timestamp,
    gate state, and environment."""
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")
    handler = _source_response("cdse", gate_state="enabled", generation=11, fallback=False)
    async with _client(handler) as c:
        d = await gate.resolve_active_source(env=ENV, client=c)
    ev = d.evidence()
    assert ev["gate_generation"] == 11
    assert ev["selected_provider"] == "cdse"
    assert ev["gate_state"] == "enabled"
    assert ev["environment_id"] == ENV
    assert isinstance(ev["decision_timestamp"], str) and ev["decision_timestamp"]


async def test_tile_render_blocked_when_gate_not_enabled(monkeypatch):
    """The live tile path refuses to render CDSE tiles when the gate is enforced and not enabled —
    normalize_cdse_request returns None (same fail-closed contract as the unconfigured branch),
    before any catalogue/DB work."""
    import cdse_client
    import imagery_source_gate
    import raster_cdse_tile_runtime as rt

    monkeypatch.setattr(cdse_client, "is_configured", lambda: True)
    monkeypatch.setattr(imagery_source_gate, "enforce_enabled", lambda: True)

    async def _fallback(**_kwargs):
        return imagery_source_gate.decision_from_source_payload(
            {"source": "element84", "gate_state": "revoked", "reason": "revoked"}, env="env-x"
        )

    monkeypatch.setattr(imagery_source_gate, "resolve_active_source", _fallback)
    out = await rt.normalize_cdse_request(
        "field-1", "ndvi", "latest", (None, None, None, None), None
    )
    assert out is None


def test_pure_mapping_of_source_payload():
    d_cdse = gate.decision_from_source_payload(
        {"source": "cdse", "gate_state": "enabled", "generation": 3}, env=ENV
    )
    assert d_cdse.use_cdse is True and d_cdse.generation == 3
    d_e84 = gate.decision_from_source_payload(
        {"source": "element84", "gate_state": "disabled", "fallback": True, "reason": "disabled"},
        env=ENV,
    )
    assert d_e84.provider == "element84" and d_e84.reason == "disabled"
    d_unknown = gate.decision_from_source_payload({"source": "??"}, env=ENV)
    assert d_unknown.provider == "element84" and d_unknown.degraded is True
