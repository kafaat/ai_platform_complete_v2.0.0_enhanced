from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import ai_generation as G  # noqa: E402
from services.ai_agronomist import tool_loop  # noqa: E402
from shared.ai import tool_schema  # noqa: E402


def test_pending_approval_audit_preserves_input_hash_and_field_id():
    audits = []
    approvals = []
    out = tool_loop.run_tool_calls(
        [
            {
                "id": "save-boundary-1",
                "tool": "save_detected_boundary",
                "params": {"field_id": "field-1", "proposal_id": "proposal-1"},
            }
        ],
        allowed_capabilities=["can_manage_field_boundaries"],
        fetcher=lambda *_: {},
        tenant_id="tenant-1",
        actor="user-1",
        timestamp="2026-07-01T00:00:00Z",
        audit_saver=audits.append,
        approval_saver=approvals.append,
        provider="openrouter",
        model="model-1",
    )

    assert out["pending_approvals"]
    assert approvals[0]["input_hash"] == out["pending_approvals"][0]["input_hash"]
    audit = audits[0]
    assert audit["outcome"] == "pending_approval"
    assert audit["field_id"] == "field-1"
    assert audit["params"]["proposal_id"] == "proposal-1"
    assert audit["input_hash"] == approvals[0]["input_hash"]
    assert audit["provider"] == "openrouter"
    assert audit["model"] == "model-1"


def test_tool_schema_includes_operational_guidance_and_enums():
    defs = {
        d["name"]: d
        for d in tool_schema.tool_definitions(
            ["can_read_historical_imagery", "can_manage_field_boundaries"]
        )
    }
    boundary = defs["detect_field_boundaries"]
    assert "When to use" in boundary["description"]
    assert boundary["x_sahool"]["input_examples"]
    assert boundary["parameters"]["properties"]["source"]["enum"] == [
        "truecolor",
        "ndvi",
        "multi_index",
    ]
    save = defs["save_detected_boundary"]
    assert save["x_sahool"]["requires_approval"] is True
    assert "Requires explicit human approval" in save["description"]


class _LengthResp:
    status_code = 200

    def json(self):
        return {"choices": [{"finish_reason": "length", "message": {"content": "جواب مقطوع"}}]}


class _LengthClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _LengthResp()


@pytest.mark.asyncio
async def test_generation_marks_incomplete_stop_reason(monkeypatch):
    monkeypatch.setenv("AI_GENERATION_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(G.httpx, "AsyncClient", _LengthClient)

    gen = await G.generate(
        "سؤال",
        "context",
        policy={"data_sharing_level": "redacted_external"},
        allowed_capabilities=["can_read_field_data"],
        tenant_id="tenant-1",
    )

    assert gen is not None
    assert gen.stop_reason == "length"
    assert gen.incomplete is True
    assert "أوقف المزوّد" in gen.text
