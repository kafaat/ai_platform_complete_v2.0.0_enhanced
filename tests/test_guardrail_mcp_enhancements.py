"""Enhanced guardrail/MCP maturity tests.

These tests intentionally import platform-core files by path because the service
folder name contains a hyphen.  They protect improvements that should not depend
on external services.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "services" / "sahool-platform" / "core"


def load_module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, CORE / file)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


guardrails = load_module("platform_guardrails_enhanced", "guardrails.py")
mcp = load_module("platform_mcp_registry_enhanced", "mcp_tool_registry.py")
coord = load_module("platform_context_coordinator_enhanced", "field_context_coordinator.py")


def test_ponytail_policy_blocks_fertilization_without_lab_and_traces():
    publisher = guardrails.GuardrailEventPublisher()
    ponytail = guardrails.RecommendationPonytail(publisher=publisher)
    out = ponytail.filter(
        guardrails.PonytailIntent("fertilization", "prescription", "F-1"),
        guardrails.FieldStateSnapshot(confidence=0.86),
        guardrails.EvidenceSummary(
            has_lab=False, has_weather=True, has_satellite=True, has_rag=True
        ),
    )
    assert out.action == guardrails.PonytailAction.INSUFFICIENT_EVIDENCE
    assert out.response is None
    assert any(t.rule == "fertilization_requires_lab" and t.triggered for t in out.traces)
    assert publisher.events and publisher.events[0].rule == "fertilization_requires_lab"


def test_ponytail_can_be_configured_per_policy():
    ponytail = guardrails.RecommendationPonytail(
        policy=guardrails.GuardrailPolicy(require_lab_for_fertilization=False)
    )
    out = ponytail.filter(
        guardrails.PonytailIntent("fertilization", "prescription", "F-1"),
        guardrails.FieldStateSnapshot(confidence=0.86),
        guardrails.EvidenceSummary(has_lab=False, has_weather=True, has_satellite=True),
    )
    assert out.action != guardrails.PonytailAction.INSUFFICIENT_EVIDENCE


def test_confidence_composer_weights_rag_lower_than_lab_weather():
    comp = guardrails.ConfidenceComposer()
    rag_only = comp.compose(rag=True)
    lab_weather = comp.compose(lab=True, weather=True)
    assert rag_only < lab_weather
    assert lab_weather <= 1.0


def test_mcp_forbidden_scan_is_recursive_keys_not_values():
    # The word recommendation in a value is allowed, but a structured key is not.
    ok = mcp.ToolEnvelope(
        tool="rag.search",
        kind="rag",
        output_type="annotation",
        payload={"text": "article about recommendation systems"},
    )
    assert ok.payload["text"]
    with pytest.raises(mcp.ToolDecisionLeakError):
        mcp.ToolEnvelope(
            tool="bad.tool",
            kind="weather",
            output_type="signal",
            payload={"nested": {"recommendation": "irrigate"}},
        )


def test_mcp_registry_health_cost_and_circuit_breaker():
    reg = mcp.MCPToolRegistry()
    calls = {"n": 0}

    def unstable(**kw):
        calls["n"] += 1
        raise RuntimeError("down")

    reg.register(
        mcp.ToolSpec("unstable", "weather", "signal", max_failures=2, cost_level=mcp.CostLevel.LOW),
        unstable,
    )
    for _ in range(2):
        with pytest.raises(RuntimeError):
            reg.call("unstable")
    assert reg.health()["unstable"].circuit_open is True
    with pytest.raises(mcp.ToolUnavailableError):
        reg.call("unstable")
    reg.reset_circuit("unstable")
    assert reg.health()["unstable"].circuit_open is False


def test_mcp_rag_and_kg_are_annotation_only():
    reg = mcp.default_context_registry()
    for name in ("rag.search", "kg.query"):
        env = reg.call(name, query="nitrogen")
        assert env.output_type == "annotation"
        assert env.verified is False


def test_field_context_recommendation_inputs_exclude_rag_kg_annotations():
    coordinator = coord.FieldContextCoordinator()
    bundle = coordinator.assemble(
        "F-1",
        [
            {"source": "lab", "kind": "lab", "payload": {"ec": 2.1, "verified": True}},
            {"source": "rag", "kind": "rag", "payload": {"text": "manual"}},
            {"source": "kg", "kind": "kg", "payload": {"edges": []}},
        ],
    )
    inputs = coord.recommendation_inputs(bundle)
    assert [sig.kind for sig in inputs] == ["lab"]
    assert all(sig.kind not in {"rag", "kg"} for sig in inputs)
