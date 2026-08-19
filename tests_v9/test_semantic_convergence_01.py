"""SEMANTIC-CONVERGENCE-01 — executable semantics and graph-conditioned retrieval."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "services/ai_agronomist/ai_evidence_runtime.py"


def _runtime_helpers():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    wanted = {"_safe_graph_expansion_terms", "_graph_conditioned_retrieval_query"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    ns = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(RUNTIME), "exec"), ns)
    return ns


def test_reference_only_kg_edges_can_expand_retrieval():
    h = _runtime_helpers()
    payload = {
        "edges": [
            {"object_name": "Stripe rust", "confidence": "reference", "prescriptive": False},
            {"object_name": "Forbidden action", "confidence": "reference", "prescriptive": True},
            {"object_name": "Unverified", "confidence": "observed", "prescriptive": False},
        ]
    }
    q, terms = h["_graph_conditioned_retrieval_query"]("wheat disease", payload)
    assert terms == ["Stripe rust"]
    assert q.startswith("wheat disease\nReference graph context:")
    assert "Forbidden action" not in q and "Unverified" not in q


def test_missing_or_unsafe_graph_context_does_not_change_query():
    h = _runtime_helpers()
    q, terms = h["_graph_conditioned_retrieval_query"](
        "original question", {"edges": [{"object_id": "x", "prescriptive": False}]}
    )
    assert q == "original question"
    assert terms == []


def test_graph_expansion_is_bounded_deduplicated_and_auditable():
    h = _runtime_helpers()
    edges = [
        {"object_id": f"term_{i}", "confidence": "reference", "prescriptive": False}
        for i in range(10)
    ]
    edges.insert(1, {"object_id": "term_0", "confidence": "reference", "prescriptive": 0})
    terms = h["_safe_graph_expansion_terms"]({"edges": edges})
    assert len(terms) == 6
    assert len(set(terms)) == 6

    src = RUNTIME.read_text(encoding="utf-8")
    assert '"graph_retrieval_expansion"' in src
    assert '"decision_authority": "none"' in src
    assert '"evidence_authority": "none"' in src


def test_kg_is_resolved_before_rag_search_for_graph_conditioning():
    src = RUNTIME.read_text(encoding="utf-8")
    kg = src.index("/v1/edges")
    rag = src.index("/v1/search")
    assert kg < rag


def test_existing_graph_vocabularies_are_explicit_executable_constants():
    evidence = (ROOT / "services/sahool-platform/core/evidence_graph.py").read_text(
        encoding="utf-8"
    )
    kg = (ROOT / "services/knowledge-graph/kg_store.py").read_text(encoding="utf-8")
    assert 'EVIDENCE_RELATIONS = ("has_evidence", "supports")' in evidence
    assert "SEED_REFERENCE_RELATIONS = (" in kg
    for rel in (
        "historically_susceptible_to",
        "historically_favored_by",
        "historically_limits",
        "historically_used_for",
    ):
        assert rel in kg


# ── «KG غاب» لا يجوز أن يُطابق «KG لم يجد» ────────────────────────────────────
# العطل الذي تمنعه هذه الحالة: ٤xx من knowledge-graph (رفض حارس المستأجر مثلاً)
# يُهبَط به إلى `{"edges": []}` — وهو فاشلٌ-مغلق صحيح — لكنّه بلا عَلَم يصير
# مطابقاً حرفيّاً لحالة «KG أجاب ولم يجد حوافّ». فيقرأ المستهلك ثقةً محسوبةً بلا
# دليل رسمٍ بيانيّ ولا شيء يقول له إنّ المصدر كان غائباً أصلاً.


def test_knowledge_graph_unavailability_is_declared_not_disguised():
    source = RUNTIME.read_text(encoding="utf-8")
    # التوفّر يُقاس من رمز الحالة، لا يُفترض
    assert "kg_available = kg_resp.status_code < 400" in source
    assert 'kg_payload = kg_resp.json() if kg_available else {"edges": []}' in source
    # ويُعلَن في الحمولة المُخرَجة بجوار حدود السلطة
    assert '"knowledge_graph_available": kg_available' in source


def test_cross_service_tenant_forwarding_keeps_its_stated_reason():
    """ترويسةٌ بلا سببٍ مكتوب تُحذَف في أوّل تنظيف — والسبب هو الحارس الحقيقيّ."""
    source = RUNTIME.read_text(encoding="utf-8")
    assert source.count('"X-Tenant-Id": tenant_id') >= 2
    assert "SEC-3" in source, "سبب تمرير المستأجر إلى rag-retrieval"
    assert "C2:" in source, "سبب تمرير المستأجر إلى knowledge-graph"
