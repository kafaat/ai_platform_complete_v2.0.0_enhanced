import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest

MODULE = Path(__file__).with_name("post_execution_bridge.py")
spec = importlib.util.spec_from_file_location("post_execution_bridge", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_idempotency_is_deterministic():
    a = mod.PostExecutionBridge._idempotency("t", "f", "e", "2026-07-20")
    b = mod.PostExecutionBridge._idempotency("t", "f", "e", "2026-07-20")
    assert a == b and a.startswith("idmp_rs10_")


def test_follow_up_fails_closed(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return httpx.Response(503, request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kwargs: Client())
    bridge = mod.PostExecutionBridge()
    with pytest.raises(RuntimeError, match="raster_follow_up_rejected:503"):
        asyncio.run(
            bridge.schedule_follow_up(
                field_id="fld_x",
                season_id="sea_x",
                execution_request_id="exe_x",
                authorization="Bearer x",
                tenant_id="00000000-0000-0000-0000-000000000001",
                days_after=5,
                indicators=["ndvi"],
            )
        )


def test_outcome_delegates_to_decision_service(monkeypatch):
    captured = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            return httpx.Response(
                200,
                json={"accepted": True, "outcome_id": "out_1"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kwargs: Client())
    result = asyncio.run(
        mod.PostExecutionBridge().verify_outcome(
            execution_request_id="exe_1",
            authorization="Bearer x",
            tenant_id="t",
            verified_by="usr_1",
            payload={"x": 1},
        )
    )
    assert result["accepted"] is True
    assert (
        captured["url"]
        == "http://sahool-platform:8000/api/v1/execution-requests/exe_1/verify-outcome"
    )
    assert captured["headers"]["Authorization"] == "Bearer x"
    assert "X-Verified-By" not in captured["headers"]
    assert "X-Tenant-Id" not in captured["headers"]


def test_attribution_uses_session_boundary_without_caller_actor(monkeypatch):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(403, json={"detail": "permission denied"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "must-not-reach-user-boundary")
    with pytest.raises(RuntimeError, match="learning_attribution_rejected:403"):
        asyncio.run(
            mod.PostExecutionBridge().attribute_learning(
                outcome_id="out_1",
                authorization="Bearer user-jwt",
                tenant_id="t",
                attributed_by="forged-owner",
                payload={"idempotency_key": "request-1"},
            )
        )
    assert len(captured) == 1
    request = captured[0]
    assert (
        str(request.url) == "http://sahool-platform:8000/api/v1/outcomes/out_1/learning-attribution"
    )
    assert request.headers["Authorization"] == "Bearer user-jwt"
    assert "X-Attributed-By" not in request.headers
    assert "X-Tenant-Id" not in request.headers
    assert "must-not-reach-user-boundary" not in str(request.headers)
