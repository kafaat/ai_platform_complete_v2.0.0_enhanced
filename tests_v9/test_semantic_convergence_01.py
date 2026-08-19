"""SEMANTIC-CONVERGENCE-01 — executable semantics and graph-conditioned retrieval."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "services/ai_agronomist/ai_evidence_runtime.py"


# الثوابت المُعتمَدة تُستخرَج مع الدوالّ: بوّابة التوسعة صارت تقرأ
# `RETRIEVAL_CONTEXT_RELATIONS`، فاستخراج الدالّة وحدها ينهار بـNameError.
_WANTED_FUNCTIONS = {"_safe_graph_expansion_terms", "_graph_conditioned_retrieval_query"}
_WANTED_CONSTANTS = {"RETRIEVAL_CONTEXT_RELATIONS"}


def _runtime_helpers():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    nodes = [
        n
        for n in tree.body
        if (isinstance(n, ast.FunctionDef) and n.name in _WANTED_FUNCTIONS)
        or (
            isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") in _WANTED_CONSTANTS for t in n.targets)
        )
    ]
    ns: dict = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(RUNTIME), "exec"), ns)
    return ns


def test_reference_only_kg_edges_can_expand_retrieval():
    h = _runtime_helpers()
    payload = {
        "edges": [
            {
                "object_name": "Stripe rust",
                "relation": "historically_susceptible_to",
                "confidence": "reference",
                "prescriptive": False,
            },
            {
                "object_name": "Forbidden action",
                "relation": "historically_used_for",
                "confidence": "reference",
                "prescriptive": True,
            },
            {
                "object_name": "Unverified",
                "relation": "historically_limits",
                "confidence": "observed",
                "prescriptive": False,
            },
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
        {
            "object_id": f"term_{i}",
            "relation": "historically_limits",
            "confidence": "reference",
            "prescriptive": False,
        }
        for i in range(10)
    ]
    edges.insert(
        1,
        {
            "object_id": "term_0",
            "relation": "historically_limits",
            "confidence": "reference",
            "prescriptive": 0,
        },
    )
    terms = h["_safe_graph_expansion_terms"]({"edges": edges})
    assert len(terms) == 6
    assert len(set(terms)) == 6

    src = RUNTIME.read_text(encoding="utf-8")
    assert '"graph_retrieval_expansion"' in src
    # سلطةُ القرار معدومةٌ فعلاً ويبقى تأكيدها. أمّا `evidence_authority: "none"`
    # فكانت هنا وأثبت المالك كذبها من طرفٍ إلى طرف، فحلّ محلّها الوسم الصادق —
    # وتأكيدُه هنا يمنع العودة الصامتة إلى العبارة المُجمِّلة.
    assert '"decision_authority": "none"' in src
    assert '"evidence_authority": "indirect_unverified_evidence_influence"' in src


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


# ── بوّابةُ التوسعة تُقيَّد بالسجلّ، لا بحقلين يفرضهما المخزن أصلاً ────────────────
# رفعه المالك بقياس: `kg_store` يفرض بقيدٍ في الجدول `confidence='reference'`
# و`prescriptive=0`، فشرطٌ على هذين الحقلين يقبل **كلّ حافّةٍ يمكن للمخزن أن
# يحملها** — حشوٌ لا مُرشِّح. و`/v1/edges` لا يُلحِق `graph_role` من السجلّ، فعلاقةٌ
# جديدة غير مُسجَّلة كانت تنزلق إلى توسعة الاستدعاء بمجرّد كونها غير آمرة.

_RUNTIME_SRC = RUNTIME.read_text(encoding="utf-8")


def _expansion_fn():
    ns = _runtime_helpers()
    return ns["_safe_graph_expansion_terms"], ns["RETRIEVAL_CONTEXT_RELATIONS"]


def _edge(relation: str, **over):
    row = {
        "relation": relation,
        "confidence": "reference",
        "prescriptive": False,
        "object_name": f"term_{relation}",
    }
    row.update(over)
    return row


def test_an_unregistered_relation_cannot_expand_retrieval_even_when_non_prescriptive():
    """الحالة التي كانت تمرّ: علاقةٌ جديدة بالقيم الافتراضيّة للمخزن."""
    expand, governed = _expansion_fn()
    assert "some_future_relation" not in governed
    out = expand({"edges": [_edge("some_future_relation")]})
    assert out == [], "علاقةٌ غير مُسجَّلة دخلت توسعة الاستدعاء"


@pytest.mark.parametrize("relation", sorted(_expansion_fn()[1]))
def test_every_governed_reference_relation_still_expands(relation):
    """والتقييد لا يخنق المسار المشروع: العلاقات المُسجَّلة تعمل كما هي."""
    expand, _ = _expansion_fn()
    assert expand({"edges": [_edge(relation)]}) == [f"term {relation}".replace("_", " ")]


def test_the_executed_gate_matches_the_governed_registry_exactly():
    """الثابت المنفَّذ = ما يُصنّفه السجلّ مرجعيّاً وسياقَ استرجاعٍ فقط — لا أوسع."""
    _, governed = _expansion_fn()
    registry = json.loads(
        (ROOT / "docs/architecture/knowledge_relation_registry.json").read_text(encoding="utf-8")
    )
    expected = {
        r["name"]
        for r in registry["relations"]
        if r.get("graph_role") == "reference"
        and r.get("evidence_semantics") == "retrieval_context_only"
    }
    assert governed == expected, f"زائد={governed - expected} ناقص={expected - governed}"


def test_evidence_authority_is_not_declared_none_while_kg_shapes_evidence():
    """العبارة «none» كانت تُجمِّل واقعاً قائماً — والوسم يجب أن يقول ما يقع.

    `_extract_evidence_ids` تُدرِج كلّ حافّة KG في معرّفات الأدلّة،
    و`_confidence_from_payloads` تمنحها `EvidenceStrength.KG` بوزن 0.65 — وكلاهما
    سابقٌ لهذه الشريحة. وأضافت الشريحة أثراً ثالثاً: عبارات التوسعة تُغيّر استعلام
    RAG فتُغيّر الوثائق المُسترجَعة ⇒ التوصيفات ⇒ معرّفات الأدلّة ⇒ الثقة.
    """
    assert '"evidence_authority": "indirect_unverified_evidence_influence"' in _RUNTIME_SRC
    assert '"evidence_authority": "none"' not in _RUNTIME_SRC
    # ومسارات التأثير تُسمّى، فلا يُقرأ الوسم دعوىً بلا تفصيل.
    for path in (
        "expansion_terms_change_rag_query_selection",
        "kg_edges_enter_evidence_ids",
        "kg_edges_contribute_to_confidence",
    ):
        assert path in _RUNTIME_SRC
    # وسلطةُ القرار تبقى معدومةً فعلاً — وهذا ما لم يتغيّر.
    assert '"decision_authority": "none"' in _RUNTIME_SRC
    # والأثر القائم مقيسٌ على المصدر لا مفترَض:
    assert "EvidenceStrength.KG" in _RUNTIME_SRC
