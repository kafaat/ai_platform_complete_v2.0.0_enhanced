import pytest
from core.ai_artifacts import AIArtifact, ArtifactBuilder, UnsafeArtifactError
from core.decision_firewall import from_context_bundle
from core.field_context_coordinator import FieldContextCoordinator
from core.kg_autoseed import InMemoryGraphStore, autoseed_if_empty
from core.kg_graphql_readonly import KnowledgeEdge
from core.mcp_tool_registry import (
    MCPToolRegistry,
    ToolDecisionLeakError,
    ToolSpec,
    default_context_registry,
)
from core.resumable_sse import MemoryRedis, RedisResumableStream
from core.review_fork import ReviewForkManager
from core.sla_monitor import SlaMonitor


def test_mcp_registry_discovers_tools_and_blocks_decision_leaks():
    registry = default_context_registry()
    assert [spec.name for spec in registry.discover(kind="lab")] == ["lab.latest_results"]
    envelope = registry.call("lab.latest_results", name="soil_ec", value=4.2, verified=True)
    assert envelope.as_context_result()["kind"] == "lab"
    assert envelope.verified is True

    unsafe = MCPToolRegistry()
    unsafe.register(
        ToolSpec("bad.weather", "weather", "signal"), lambda **_: {"recommendation": "irrigate"}
    )
    with pytest.raises(ToolDecisionLeakError):
        unsafe.call("bad.weather")


def test_mcp_rag_kg_are_annotation_only_and_do_not_enter_firewall_inputs():
    registry = default_context_registry()
    rows = [
        registry.call("rag.search", query="nitrogen wheat").as_context_result(),
        registry.call("kg.query", query="wheat disease").as_context_result(),
        registry.call("weather.get_daily", et0=6.1, verified=True).as_context_result(),
    ]
    bundle = FieldContextCoordinator().assemble("F10", rows)
    firewall = from_context_bundle(bundle)
    assert "weather" in firewall.recommendation_inputs()
    assert len(firewall.annotations) == 2
    assert all(not ann.verified for ann in firewall.annotations)


def test_redis_resumable_stream_recovers_after_disconnect():
    stream = RedisResumableStream(MemoryRedis())
    stream.append("daily:f1", "part-1")
    stream.append("daily:f1", "part-2")
    stream.append("daily:f1", "done", event="complete")
    resumed = stream.resume("daily:f1", after_offset=0)
    assert [e.data for e in resumed] == ["part-2", "done"]
    assert stream.sse_lines("daily:f1", after_offset=1)[0].startswith("id: 2")


def test_review_fork_compare_and_approval_do_not_create_tasks():
    manager = ReviewForkManager()
    lab_only = manager.fork("rec-1", "Lab only", "أضف 30 كجم/هكتار", "lab_only")
    lab_rag = manager.fork("rec-1", "Lab plus RAG", "أضف 25 كجم/هكتار", "lab_plus_reference")
    comparison = manager.compare(lab_only, lab_rag)
    assert comparison.changed is True
    assert "30" in comparison.diff_text and "25" in comparison.diff_text
    approved = manager.approve(lab_only, "اعتماد نسخة المختبر فقط")
    assert approved.status == "approved"
    with pytest.raises(AttributeError):
        _ = approved.task


def test_artifacts_are_presentation_only_and_reject_operational_commands():
    builder = ArtifactBuilder()
    diagram = builder.evidence_mermaid("a1", ["Lab EC", "Field State", "Recommendation Review"])
    assert diagram.kind == "mermaid"
    assert diagram.presentation_only is True
    table = builder.lab_table("a2", [{"name": "EC", "value": 3.1, "unit": "dS/m"}])
    assert "<table>" in table.content
    with pytest.raises(UnsafeArtifactError):
        AIArtifact("bad", "markdown", "سيئ", "POST /api/tasks create_task(")


def test_kg_autoseed_only_when_empty_and_reference_only():
    store = InMemoryGraphStore(edges=[])
    first = autoseed_if_empty(store)
    second = autoseed_if_empty(store)
    assert first["seeded"] is True and first["inserted"] >= 1
    assert second == {"seeded": False, "inserted": 0, "reason": "graph_not_empty"}
    bad_store = InMemoryGraphStore(edges=[])
    with pytest.raises(ValueError):
        autoseed_if_empty(bad_store, [KnowledgeEdge("x", "treats", "y", prescriptive=True)])


def test_sla_monitor_reports_violations():
    monitor = SlaMonitor()
    monitor.record("kg.query", elapsed_ms=120, target_ms=300)
    monitor.record("rag.search", elapsed_ms=650, target_ms=500)
    summary = monitor.summary()
    assert summary["pass_rate"] == 0.5
    assert summary["violations"] == ["rag.search"]
