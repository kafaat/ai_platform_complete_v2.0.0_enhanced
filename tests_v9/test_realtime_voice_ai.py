"""Read-only voice requests never expose tenant tools or bypass current policy."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from services.ai_agronomist import ai_evidence_runtime as runtime
from services.ai_agronomist.main import AdvisorQuery

pytestmark = pytest.mark.unit
TENANT = "voice-tenant"


def policy():
    return {
        "contract": "sahool.ai_policy_envelope",
        "contract_version": 2,
        "tenant_id": TENANT,
        "version": "v52",
        "policy_mode": "local_only",
        "allowed_tools": ["get_field_state", "submit_to_decision"],
        "external_llm_allowed": False,
        "external_tts_allowed": False,
    }


async def invoke(req):
    return await runtime.build_evidence_response(
        req,
        endpoint_mode="chat",
        x_tenant_id=TENANT,
        save_agent_tool_audit=lambda _: pytest.fail("voice tool audit executed"),
        save_pending_approval=lambda _: pytest.fail("voice approval created"),
    )


@pytest.mark.parametrize("value", ["true", 1, None])
def test_voice_flag_is_strict(value):
    with pytest.raises(ValidationError):
        AdvisorQuery(question="قياسات الحقل", voice_read_only=value)


@pytest.mark.parametrize(
    "change",
    [
        {"tool_calls": [{"name": "get_field_state"}]},
        {"current_field_state": {}},
        {"field_id": None},
    ],
)
async def test_invalid_voice_request_stops_before_fetch(monkeypatch, change):
    fetch = AsyncMock()
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", fetch)
    req = AdvisorQuery(
        **({"question": "قياسات", "field_id": "f", "voice_read_only": True} | change)
    )
    with pytest.raises(HTTPException, match="voice_read_only_request_invalid"):
        await invoke(req)
    fetch.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [
        None,
        {"contract_version": True},
        {"contract_version": 3},
        {"version": "future"},
        {"tenant_id": "other"},
        {"policy_mode": "full_external"},
        {"external_llm_allowed": True},
        {"external_tts_allowed": True},
        {"allowed_tools": None},
    ],
)
async def test_untrusted_or_external_policy_stops_before_retrieval(monkeypatch, change):
    envelope = None if change is None else policy() | change
    field = {"ai_context_pack": {"ai_policy_envelope": envelope}}
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=field))
    real_client = httpx.AsyncClient
    calls = []

    def retrieval(request):
        calls.append(request)
        return httpx.Response(200, json={"annotations": [], "edges": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(retrieval), **kw),
    )
    with pytest.raises(HTTPException, match="voice_local_policy_required"):
        await invoke(AdvisorQuery(question="قياسات", field_id="f", voice_read_only=True))
    assert calls == []


async def test_voice_zeroes_tools_before_generation_even_if_tenant_grants_them(monkeypatch):
    field = {"ai_context_pack": {"ai_policy_envelope": policy()}}
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=field))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: True)
    monkeypatch.setattr(runtime.ai_generation, "resolve_generation", lambda _: None)
    generate = AsyncMock(return_value=None)
    monkeypatch.setattr(runtime.ai_generation, "generate", generate)
    monkeypatch.setattr(
        runtime, "_record_ai_advice_event", AsyncMock(return_value={"persisted": False})
    )
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"annotations": [], "edges": []})
            ),
            **kw,
        ),
    )
    result = await invoke(AdvisorQuery(question="قياسات", field_id="f", voice_read_only=True))
    assert generate.call_args.kwargs["allowed_tools"] == set()
    assert generate.call_args.kwargs["max_tool_rounds"] == 0
    assert result["tool_calls"] == result["pending_approvals"] == []
    assert result["provider_tool_rounds"] == 0


async def test_voice_rejects_external_resolved_provider(monkeypatch):
    field = {"ai_context_pack": {"ai_policy_envelope": policy()}}
    monkeypatch.setattr(
        runtime, "_fetch_canonical_field_state", AsyncMock(return_value=copy.deepcopy(field))
    )
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: True)
    monkeypatch.setattr(
        runtime.ai_generation,
        "resolve_generation",
        lambda _: SimpleNamespace(provider="openrouter"),
    )
    generate = AsyncMock()
    monkeypatch.setattr(runtime.ai_generation, "generate", generate)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"annotations": [], "edges": []})
            ),
            **kw,
        ),
    )
    with pytest.raises(HTTPException, match="voice_external_generation_forbidden"):
        await invoke(AdvisorQuery(question="قياسات", field_id="f", voice_read_only=True))
    generate.assert_not_awaited()
