"""ARCH-S2 — dependency truth must be measured, typed, deterministic, and complete."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "architecture" / "build_platform_catalog.py"


def _load():
    spec = importlib.util.spec_from_file_location("platform_catalog_s2_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_s2_current_tree_passes_and_examines_real_edges():
    bundle = _load().build()
    gate = bundle["catalog"]["governance"]["s2_dependency_truth"]
    assert gate["passed"], gate["failures"]
    assert gate["edge_count"] > 0, "0 edges examined is not a dependency proof"
    assert bundle["graph"]["schema"] == "sahool.dependency_graph.v2"


def test_s2_all_required_relation_families_have_evidence():
    graph = _load().build()["graph"]
    required = {"CALLS", "EMITS", "CONSUMES", "READS", "WRITES", "ROUTES_TO"}
    assert set(graph["relation_counts"]) == required
    missing = sorted(r for r in required if graph["relation_counts"][r] <= 0)
    assert not missing, f"S2 relation families with zero measured edges: {missing}"
    for edge in graph["edges"]:
        assert edge["evidence"], edge
        assert edge["protocol"], edge
        assert edge["resource"], edge


def test_s2_frontend_calls_are_endpoint_evidence_not_component_name_matches():
    graph = _load().build()["graph"]
    ui_calls = [
        e
        for e in graph["edges"]
        if e["from"] in {"frontend", "mobile"} and e["relation"] == "CALLS"
    ]
    assert ui_calls, "frontend/mobile consumer reality disappeared from S2"
    assert all(e["resource"].startswith("/") for e in ui_calls), ui_calls[:5]
    assert all(".test." not in e["evidence"] and ".spec." not in e["evidence"] for e in ui_calls)


def test_s2_runtime_name_aliases_resolve_known_compose_units():
    catalog = _load().build()["catalog"]
    by_id = {c["component_id"]: c for c in catalog["components"]}
    expected = {
        "ai_agronomist": "sahool-ai-agronomist",
        "edge-inference": "sahool-edge",
        "field-management-service": "sahool-field-management",
        "frontend": "sahool-frontend",
        "scout-ingest-service": "sahool-scout-ingest",
        "vegetation-analysis-service": "sahool-vegetation-analysis",
    }
    for cid, unit in expected.items():
        # v2 (تكامل S2): وحدات النشر قوائم مقيسة من build — العضويّة هي العقد.
        assert unit in by_id[cid]["deployment_units"]
        assert unit in by_id[cid]["runtime"]["compose_services"]


def test_s2_runtime_contract_coverage_fails_closed(monkeypatch):
    mod = _load()
    bundle = mod.build()
    components = {c["component_id"]: c for c in bundle["catalog"]["components"]}
    overrides = mod.load_overrides()
    services = mod._load_json("service_inventory.generated.json")
    services = services if isinstance(services, list) else services["services"]
    known = {s["service"] for s in services} | set(overrides["canonical_aliases"].values())
    known |= {e["component_id"] for e in overrides["extra_components"]}
    canonical = mod.make_canonicalizer(overrides, known)
    registry = mod.load_component_registry()
    source_to_component = {
        e["source_path"]: cid for cid, e in registry["components"].items() if e.get("source_path")
    }
    compose, _resolution = mod.discover_compose(canonical, source_to_component)
    gate_rows, _ = mod.run_consumer_gate(canonical)
    source_prefixes = sorted(source_to_component.items(), key=lambda t: -len(t[0]))
    original = mod._load_json

    def fake_load(rel):
        data = original(rel)
        if rel == "runtime-contracts/generated/runtime_contracts.json":
            data = dict(data)
            data["services"] = [
                r for r in data["services"] if r.get("service") != "actuator-service"
            ]
        return data

    monkeypatch.setattr(mod, "_load_json", fake_load)
    _graph, failures = mod.build_dependency_truth(
        components=components,
        compose=compose,
        canonical=canonical,
        gate_rows=gate_rows,
        source_prefixes=source_prefixes,
    )
    assert any("runtime contract missing" in f and "actuator-service" in f for f in failures)


def test_generated_dependency_graph_matches_compiler():
    mod = _load()
    expected = mod.render(mod.build())["dependency_graph.generated.json"]
    assert (ROOT / "dependency_graph.generated.json").read_text(encoding="utf-8") == expected


def test_s2_gateway_never_drops_measured_upstreams():
    mod = _load()
    graph = mod.build()["graph"]
    stats = graph["source_resolution"]["gateway"]
    routes = [e for e in graph["edges"] if e["relation"] == "ROUTES_TO"]
    assert stats["observed"] == len(routes)
    assert stats["runtime_upstream_targets"] > 0, (
        "fixture must exercise non-component upstream retention"
    )
    assert any(e["to_kind"] == "runtime_upstream" for e in routes)
    assert all(e["from_kind"] == "gateway" for e in routes)


def test_s2_component_owned_evidence_that_cannot_resolve_fails_closed(monkeypatch):
    mod = _load()
    bundle = mod.build()
    components = {c["component_id"]: c for c in bundle["catalog"]["components"]}
    overrides = mod.load_overrides()
    services = mod._load_json("service_inventory.generated.json")
    services = services if isinstance(services, list) else services["services"]
    known = {s["service"] for s in services} | set(overrides["canonical_aliases"].values())
    known |= {e["component_id"] for e in overrides["extra_components"]}
    canonical = mod.make_canonicalizer(overrides, known)
    registry = mod.load_component_registry()
    source_to_component = {
        e["source_path"]: cid for cid, e in registry["components"].items() if e.get("source_path")
    }
    compose, _resolution = mod.discover_compose(canonical, source_to_component)
    gate_rows, _ = mod.run_consumer_gate(canonical)
    source_prefixes = sorted(source_to_component.items(), key=lambda t: -len(t[0]))
    original = mod._load_json

    def fake_load(rel):
        data = original(rel)
        if rel == "event-audit/generated/event_contract_graph.json":
            data = dict(data)
            data["subjects"] = list(data.get("subjects") or []) + [
                {
                    "subject": "sahool.test.unresolved",
                    "producers": [
                        {"file": "services/not-a-canonical-component/main.py", "line": 1}
                    ],
                    "consumers": [],
                }
            ]
        return data

    monkeypatch.setattr(mod, "_load_json", fake_load)
    _graph, failures = mod.build_dependency_truth(
        components=components,
        compose=compose,
        canonical=canonical,
        gate_rows=gate_rows,
        source_prefixes=source_prefixes,
    )
    assert any("unresolved nats component evidence path" in f for f in failures)


def test_s2_resource_edges_are_typed_not_ambiguous_component_edges():
    graph = _load().build()["graph"]
    for edge in graph["edges"]:
        assert edge["from_kind"] in {"component", "gateway"}, edge
        assert edge["to_kind"] in {"component", "resource", "runtime_upstream"}, edge
        if edge["relation"] in {"READS", "WRITES", "EMITS", "CONSUMES"}:
            assert edge["to_kind"] == "resource", edge
        if edge["relation"] == "CALLS":
            assert edge["from_kind"] == edge["to_kind"] == "component", edge
