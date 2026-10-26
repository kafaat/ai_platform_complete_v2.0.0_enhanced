"""Productivity zoning must not let a tool call override evidence or stall the service.

- A grid in the evidence context (raster pipeline) wins over ``params["ndvi_grid"]``,
  which the client or the model controls through ``tool_calls``.
- A grid larger than ``MAX_GRID_SIDE`` per side is refused as ``insufficient_data``
  quickly instead of being clustered in pure Python for tens of seconds.
- The chat tool loop runs in a worker thread, never on the event loop.
- ``AdvisorQuery.tool_calls`` is bounded.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import productivity_zones as PZ  # noqa: E402
from services.ai_agronomist import productivity_zones_clustering as C  # noqa: E402

_BBOX = [44.0, 15.0, 44.01, 15.01]


def _split_grid(n: int, low: float, high: float) -> list[list[float]]:
    return [[low if c < n // 2 else high for c in range(n)] for _ in range(n)]


def test_params_grid_does_not_override_evidence_grid():
    evidence = _split_grid(6, 0.2, 0.8)
    forged = _split_grid(6, 0.9, 0.9)
    assert C.extract_ndvi_grid({"ndvi_grid": forged}, {"ndvi_grid": evidence}) is evidence
    # Without evidence the caller grid is still usable (documented opt-in path).
    assert C.extract_ndvi_grid({"ndvi_grid": forged}, {}) is forged


def test_params_aux_grid_does_not_override_evidence_aux_grid():
    ndvi = _split_grid(4, 0.2, 0.8)
    ev_ndmi = _split_grid(4, 0.1, 0.3)
    forged = _split_grid(4, 0.9, 0.9)
    aux = C.extract_aux_grids({"ndmi_grid": forged}, {"ndmi_grid": ev_ndmi}, ndvi_grid=ndvi)
    assert aux is not None and aux["ndmi"] is ev_ndmi


def test_zoning_uses_evidence_centroids_not_forged_params():
    out = PZ.propose_productivity_zones(
        {"bbox": _BBOX, "zone_count": 2, "ndvi_grid": _split_grid(6, -0.9, -0.5)},
        field_id="f1",
        evidence_context={"ndvi_grid": _split_grid(6, 0.2, 0.8)},
    )
    assert out["method"] == "ndvi_kmeans_clustering"
    assert sorted(out["ndvi_centroids"]) == [0.2, 0.8]


@pytest.mark.parametrize("where", ["params", "evidence"])
def test_oversize_grid_is_refused_quickly(where):
    n = C.MAX_GRID_SIDE + 1
    grid = [[(r * 7 + c * 13) % 100 / 100 for c in range(n)] for r in range(n)]
    params = {"bbox": _BBOX}
    evidence: dict = {}
    (params if where == "params" else evidence)["ndvi_grid"] = grid
    if where == "evidence":
        # An oversize evidence grid must not fall back to a caller-supplied one.
        params["ndvi_grid"] = _split_grid(6, 0.2, 0.8)
    t0 = time.monotonic()
    out = PZ.propose_productivity_zones(params, field_id="f1", evidence_context=evidence)
    assert time.monotonic() - t0 < 2.0
    assert out["status"] == "insufficient_data"
    assert out["productivity_zones"] == []
    assert "indicator_grid_exceeds_size_cap" in out["reason_codes"]


def test_wide_grid_with_few_rows_is_also_refused():
    grid = [[0.5] * (C.MAX_GRID_SIDE + 1) for _ in range(3)]
    assert C.extract_ndvi_grid({"ndvi_grid": grid}, None) is None
    assert C.ndvi_grid_exceeds_cap({"ndvi_grid": grid}, None) is True


def test_grid_at_cap_is_accepted():
    grid = [[0.5] * C.MAX_GRID_SIDE for _ in range(C.MAX_GRID_SIDE)]
    assert C.extract_ndvi_grid({"ndvi_grid": grid}, None) is grid
    assert C.ndvi_grid_exceeds_cap({"ndvi_grid": grid}, None) is False


def test_advisor_query_bounds_tool_calls():
    pydantic = pytest.importorskip("pydantic")
    pytest.importorskip("fastapi")
    from services.ai_agronomist import main as M

    M.AdvisorQuery(question="q", tool_calls=[{"tool": "get_field_state"}] * 9)
    with pytest.raises(pydantic.ValidationError):
        M.AdvisorQuery(question="q", tool_calls=[{"tool": "get_field_state"}] * 1000)


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_generate_runs_provider_tool_loop_off_the_event_loop(monkeypatch):
    httpx = pytest.importorskip("httpx")
    from services.ai_agronomist import ai_generation as G

    monkeypatch.setenv("AI_GENERATION_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    monkeypatch.delenv("AI_MODELS", raising=False)

    calls: list[bool] = []

    def fake_loop(*a, **k):
        calls.append(_on_event_loop())
        return {"tool_calls": [], "pending_approvals": [], "handled_count": 0}

    monkeypatch.setattr(G.tool_loop, "run_tool_calls", fake_loop)
    sent: list[int] = []

    def handler(req):
        sent.append(1)
        if len(sent) == 1:
            call = {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_field_state", "arguments": json.dumps({})},
            }
            msg = {"content": None, "tool_calls": [call]}
            return httpx.Response(200, json={"choices": [{"message": msg}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    orig = httpx.AsyncClient

    class _Client(orig):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)

    monkeypatch.setattr(G.httpx, "AsyncClient", _Client)
    out = asyncio.run(
        G.generate(
            "q",
            "ctx",
            policy={"data_sharing_level": "full_external"},
            tool_fetcher=lambda n, p: {},
            tenant_id="t1",
            max_tool_rounds=1,
        )
    )
    assert out is not None and out.text == "ok"
    assert calls == [False], "tool loop ran on the event loop"


def test_query_endpoint_runs_tool_loop_off_the_event_loop(monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.ai_agronomist import ai_evidence_runtime as R
    from services.ai_agronomist import main as M

    monkeypatch.setenv("AI_GENERATION_ENABLED", "false")
    monkeypatch.setattr(R, "AGENT_TOKEN", "svc")

    def handler(req):
        u = str(req.url)
        if "/internal/fields/" in u:
            pack = {"field_id": "f1", "tenant_id": "t1"}
            return httpx.Response(
                200,
                json={
                    "canonical_field_state": {
                        "schema_version": "canonical_field_state.v1",
                        "field_id": "f1",
                    },
                    "ai_context_pack": pack,
                },
            )
        if "/v1/edges" in u:
            return httpx.Response(200, json={"edges": []})
        if "/v1/search" in u:
            return httpx.Response(200, json={"annotations": []})
        if "/internal/events" in u:
            return httpx.Response(200, json={"persisted": True})
        return httpx.Response(404)

    orig = httpx.AsyncClient

    class _Client(orig):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)

    monkeypatch.setattr(R.httpx, "AsyncClient", _Client)
    calls: list[bool] = []

    def fake_loop(*a, **k):
        calls.append(_on_event_loop())
        return {"tool_calls": [], "pending_approvals": [], "truncated": False}

    monkeypatch.setattr(R.tool_loop, "run_tool_calls", fake_loop)
    client = TestClient(M.app)
    resp = client.post(
        "/v1/query",
        json={"question": "zones?", "field_id": "f1", "tool_calls": [{"tool": "get_field_state"}]},
        headers={"X-Tenant-Id": "t1"},
    )
    assert resp.status_code == 200, resp.text
    assert calls == [False], "tool loop ran on the event loop"
