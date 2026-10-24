"""Voice publication accepts only persisted authenticated owner facts."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.unit
SPEC = importlib.util.spec_from_file_location(
    "voice_provider_boundary",
    Path(__file__).resolve().parents[1] / "services/realtime-agent/realtime_agent/providers.py",
)
provider = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider)


def context():
    return {
        "tenant_id": "tenant",
        "field_id": "field",
        "bearer": "disposable-bearer",
        "policy_envelope": {
            "contract": "sahool.ai_policy_envelope",
            "contract_version": 2,
            "version": "v52",
            "tenant_id": "tenant",
            "policy_mode": "local_only",
            "external_llm_allowed": False,
            "external_tts_allowed": False,
            "allowed_tools": ["get_field_state"],
        },
    }


def receipt():
    validation = {
        "status": "verified",
        "schema_version": "sahool.structured_advisory.v1",
        "tenant_id": "tenant",
        "field_id": "field",
        "executes_action": False,
        "creates_decision": False,
        "candidate_previews": [],
        "claims": [{"value": 22}],
        "model_output_digest": "a" * 64,
        "answer_ar": "درجة الحرارة ٢٢",
    }
    return {
        "mode": "validated_field_facts",
        "generation_status": "validated_structured_facts",
        "generation_surfaced": True,
        "tenant_id": "tenant",
        "field_id": "field",
        "tool_calls": [],
        "pending_approvals": [],
        "provider_tool_rounds": 0,
        "tool_calls_truncated": False,
        "advisory_validation": validation,
        "audit_event": {"persisted": True, "advisory_validation": copy.deepcopy(validation)},
        "answer_ar": validation["answer_ar"],
    }


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("", "mode", "generated_grounded"),
        ("", "generation_status", "succeeded"),
        ("", "generation_surfaced", False),
        ("", "tenant_id", "other"),
        ("", "field_id", "other"),
        ("", "tool_calls", [{}]),
        ("", "pending_approvals", [{}]),
        ("", "provider_tool_rounds", 1),
        ("", "tool_calls_truncated", True),
        ("", "answer_ar", "different"),
        ("advisory_validation", "status", "blocked"),
        ("advisory_validation", "schema_version", "unknown"),
        ("advisory_validation", "model_output_digest", "not-a-digest"),
        ("advisory_validation", "executes_action", True),
        ("advisory_validation", "creates_decision", True),
        ("advisory_validation", "candidate_previews", [{}]),
        ("advisory_validation", "claims", []),
        ("audit_event", "persisted", False),
    ],
)
def test_unaccepted_or_mismatched_publication_never_reaches_speech(section, key, value):
    payload = receipt()
    (payload[section] if section else payload)[key] = value
    with pytest.raises(provider.VoiceProviderError, match="voice_publication_rejected"):
        provider.published_answer(payload, context())


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:secret@host",
        "https://host/path",
        "https://host?x=1",
        "file:///tmp",
        "https://host/#fragment",
    ],
)
def test_config_rejects_credential_path_or_non_http_origins(origin):
    with pytest.raises(provider.VoiceProviderError, match="voice_provider_origin_invalid"):
        provider.HttpVoiceProviders(origin, "http://frontend")


async def test_fixed_bff_paths_send_only_user_authorization_and_no_store():
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer disposable-bearer"
        assert "X-Agent-Token" not in request.headers
        assert "X-Tenant-Id" not in request.headers
        if request.url.path == "/api/ai-agronomist/chat":
            assert request.read().find(b'"voice_read_only":true') >= 0
            return httpx.Response(200, json=receipt())
        assert request.url.path == "/tts/synthesize"
        assert b'"no_store":true' in request.read()
        assert b'"provider":"piper"' in request.read()
        return httpx.Response(
            200,
            content=b"synthetic-wav",
            headers={"Content-Type": "audio/wav", "Cache-Control": "no-store", "X-Cache": "BYPASS"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = provider.HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        answer = await gateway.answer(context(), "ما حرارة الحقل؟")
        assert answer == receipt()["answer_ar"]
        assert await gateway.synthesize(context(), answer) == b"synthetic-wav"
    assert len(requests) == 2


async def test_policy_revocation_prevents_any_provider_request():
    requests = []
    ctx = context()
    ctx["policy_envelope"]["policy_mode"] = "full_external"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: requests.append(r))
    ) as client:
        gateway = provider.HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        with pytest.raises(provider.VoiceProviderError, match="voice_local_policy_required"):
            await gateway.answer(ctx, "قياسات")
    assert requests == []


async def test_redirect_is_not_followed_with_user_bearer():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "http://other.invalid/leak"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        gateway = provider.HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        with pytest.raises(provider.VoiceProviderError, match="voice_provider_unavailable"):
            await gateway.answer(context(), "قياسات")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "audio/wav", "Cache-Control": "private, max-age=86400", "X-Cache": "HIT"},
        {"Content-Type": "text/html", "Cache-Control": "no-store", "X-Cache": "BYPASS"},
    ],
)
async def test_audio_cache_or_type_mismatch_refuses_speech(headers):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"data", headers=headers)
        )
    ) as client:
        gateway = provider.HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        with pytest.raises(provider.VoiceProviderError, match="voice_audio_rejected"):
            await gateway.synthesize(context(), "قياسات")


@pytest.mark.parametrize("change", [{"contract_version": 3}, {"version": "future"}])
async def test_unknown_future_policy_is_rejected_before_network(change):
    ctx = context()
    ctx["policy_envelope"].update(change)
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: calls.append(r))
    ) as client:
        gateway = provider.HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        with pytest.raises(provider.VoiceProviderError, match="voice_local_policy_required"):
            await gateway.answer(ctx, "قياسات")
    assert calls == []
