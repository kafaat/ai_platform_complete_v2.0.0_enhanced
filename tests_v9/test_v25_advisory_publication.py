"""Chat publishes only selections revalidated by the current field-state owner."""

from __future__ import annotations

import copy
import importlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from services.ai_agronomist import ai_evidence_runtime as runtime
from services.ai_agronomist.ai_generation import GenResult
from services.ai_agronomist.main import AdvisorQuery
from shared.ai.structured_advisory import digest
from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, document, rehash, state

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def owner(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "services/sahool-platform"))
    importlib.import_module("api.main")
    return importlib.import_module("api.routers.internal_service")


@pytest.mark.parametrize(
    "case", ["valid", "changed", "prose", "dose", "candidate", "not_persisted", "receipt_mismatch"]
)
async def test_chat_publication_requires_current_owner_facts_and_persisted_receipt(
    monkeypatch, case
):
    module = owner(monkeypatch)
    initial = state()
    current = copy.deepcopy(initial)
    doc = document(initial)
    if case == "changed":
        current["weather"]["rain_mm"] = 4
        rehash(current)
    if case == "dose":
        doc["claims"][0]["value"] = 500
    if case == "candidate":
        doc["candidate_ids"] = ["f" * 64]
    text = "أضف جرعة غير موثقة الآن" if case == "prose" else json.dumps(doc)
    reload_state = AsyncMock(return_value=current)
    monkeypatch.setattr(module, "_compose_canonical", reload_state)
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=initial))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: True)
    monkeypatch.setattr(runtime.ai_generation, "resolve_generation", lambda _: None)
    monkeypatch.setattr(
        runtime.policy_envelope, "gate_generation", lambda *a, **k: {"decision": "allowed"}
    )
    generate = AsyncMock(return_value=GenResult(text=text, model="fixture", provider="local"))
    monkeypatch.setattr(runtime.ai_generation, "generate", generate)
    client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"annotations": [], "edges": []})
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))
    receipts = []

    async def record(**kwargs):
        receipts.append(kwargs)
        result = {"persisted": case != "not_persisted"}
        if "model_output" in kwargs:
            result["advisory_validation"] = await module._preview_advice_facts(
                object(), SimpleNamespace(**kwargs)
            )
            if case == "receipt_mismatch":
                result["advisory_validation"]["model_output_digest"] = digest("different answer")
        return result

    monkeypatch.setattr(runtime, "_record_ai_advice_event", record)
    result = await runtime.build_evidence_response(
        AdvisorQuery(question="ما قياسات الحقل؟", field_id=FIELD),
        endpoint_mode="chat",
        x_tenant_id=TENANT,
        save_agent_tool_audit=lambda _: None,
        save_pending_approval=lambda _: None,
    )
    assert "sahool.structured_advisory.v1" in generate.call_args.args[1]
    assert receipts
    if case == "valid":
        assert result["mode"] == "validated_field_facts"
        assert result["generation_status"] == "validated_structured_facts"
        assert "/weather/rain_mm: 0" in result["answer_ar"]
        assert result["advisory_validation"]["creates_decision"] is False
        assert result["guardrail_result"]["decision_validation"] == "not_requested"
        reload_state.assert_awaited_once()
        assert reload_state.call_args.kwargs == {"tenant_id": TENANT, "field_id": FIELD}
    else:
        assert result["mode"] == "evidence_only"
        assert text not in result["answer_ar"]
        assert result["generation_status"] != "validated_structured_facts"
        if case in {"not_persisted", "receipt_mismatch"}:
            for receipt in (
                result["advisory_validation"],
                result["audit_event"]["advisory_validation"],
            ):
                assert receipt["status"] == "blocked"
                assert not {"answer_ar", "claims", "candidate_previews"}.intersection(receipt)


async def test_owner_rejects_cross_tenant_field_before_validation_or_event(monkeypatch):
    module = owner(monkeypatch)

    @asynccontextmanager
    async def connection(_):
        yield object()

    monkeypatch.setattr(module.main, "tenant_connection", connection)
    monkeypatch.setattr(
        module.main, "_assert_field_in_tenant", AsyncMock(side_effect=HTTPException(404))
    )
    preview = AsyncMock()
    emit = AsyncMock()
    monkeypatch.setattr(module, "_preview_advice_facts", preview)
    monkeypatch.setattr(module.main, "_emit_domain_event", emit)
    req = module.main.InternalAIAdviceEventRequest(
        tenant_id=TENANT,
        field_id=FIELD,
        question="قياسات",
        model_output=json.dumps(document(state())),
    )
    with pytest.raises(HTTPException) as exc:
        await module.internal_ai_advice_event(req)
    assert exc.value.status_code == 404
    preview.assert_not_awaited()
    emit.assert_not_awaited()


async def test_owner_records_only_validated_receipt_not_raw_model_prose(monkeypatch):
    module = owner(monkeypatch)

    @asynccontextmanager
    async def connection(_):
        yield object()

    monkeypatch.setattr(module.main, "tenant_connection", connection)
    monkeypatch.setattr(module.main, "_assert_field_in_tenant", AsyncMock())
    monkeypatch.setattr(module, "_compose_canonical", AsyncMock(return_value=state()))
    emit = AsyncMock(return_value=True)
    monkeypatch.setattr(module.main, "_emit_domain_event", emit)
    text = json.dumps(document(state()))
    req = module.main.InternalAIAdviceEventRequest(
        tenant_id=TENANT, field_id=FIELD, question="قياسات", model_output=text
    )
    result = await module.internal_ai_advice_event(req)
    assert result["persisted"] is True
    assert result["advisory_validation"]["status"] == "verified"
    payload = emit.call_args.args[-1]
    assert payload["advisory_validation"] == result["advisory_validation"]
    assert "model_output" not in payload
    assert result["advisory_validation"]["executes_action"] is False
