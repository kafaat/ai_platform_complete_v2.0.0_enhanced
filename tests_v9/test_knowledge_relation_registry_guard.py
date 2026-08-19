"""`KNOWLEDGE-RELATION-01` — العلاقة المُسجَّلة هي العلاقة المُنفَّذة.

**الفرق عن Ontology تقليديّة هو كلّ ما في الأمر:** ثلاثيّةٌ تُكتَب مرّةً ثمّ
تَبيت بصمت لأنّ لا شيء يقول متى خالفتها الشيفرة. وهنا السلسلة المُعلَنة تُقابَل
بـ`REQUIRED_LINKS` المقروء بـ`ast` من المُنتِج نفسه — وهو ثابتٌ **يحكم قراراً**:
كلُّ حلقةٍ غير متاحة تُضيف سببَ حجب، وأضعفُ حلقةٍ يُبنى عليها
`operational_eligible`.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "knowledge_relation_registry_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("knowledge_relation_registry_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

_SOURCE = 'REQUIRED_LINKS = ("a", "b", "c")\n'


def _tree(tmp_path: Path, source: str = _SOURCE) -> Path:
    (tmp_path / "api").mkdir(exist_ok=True)
    (tmp_path / "api" / "graph.py").write_text(source, encoding="utf-8")
    return tmp_path


def _relation(**overrides) -> list[dict]:
    base = {
        "name": "feeds",
        "from": "src",
        "to": "dst",
        "graph_role": "operational",
        "authority_semantics": "gates_operational_eligibility",
        "evidence_semantics": "not_evidence",
        "direct_execution_permitted": False,
        "semantics": {"directional": True, "temporal": True, "acyclic": True},
        "constraints": {"requires_active_relation": True},
        "chain_source_module": "api/graph.py",
        "chain_symbol": "REQUIRED_LINKS",
        "chain": ["a", "b", "c"],
        "consumers": ["api/graph.py"],
    }
    base.update(overrides)
    return [base]


def test_a_relation_matching_its_executed_chain_passes(tmp_path):
    problems, checked = guard.violations(_relation(), _tree(tmp_path))
    assert problems == []
    assert checked == 1


def test_a_chain_that_drifts_from_the_code_is_blocked(tmp_path):
    """البند الحامل: حلقةٌ تُضاف في الشيفرة ولا تُسجَّل تُغيّر قرار تشغيل."""
    root = _tree(tmp_path, 'REQUIRED_LINKS = ("a", "b", "c", "d")\n')
    problems, _ = guard.violations(_relation(), root)
    assert problems and "تخالف المُنفَّذة" in problems[0]


def test_a_reordered_chain_is_blocked(tmp_path):
    """الترتيب جزءٌ من الدلالة في علاقةٍ موجَّهة، لا زينةٌ فيها."""
    problems, _ = guard.violations(_relation(chain=["a", "c", "b"]), _tree(tmp_path))
    assert problems and "تخالف المُنفَّذة" in problems[0]


def test_a_relation_without_an_executed_symbol_is_blocked(tmp_path):
    """سلسلةٌ لا تُقابَل بشيفرةٍ تبقى رسماً — وهو ما تستثنيه الشريحة."""
    root = _tree(tmp_path, "OTHER = 1\n")
    problems, _ = guard.violations(_relation(), root)
    assert problems and "لم يُقرأ" in problems[0]


def test_a_symbol_named_only_in_a_comment_is_not_a_definition(tmp_path):
    """يُقرأ الإسناد بـ`ast` لا النصّ — وإلّا صار التعليق يُخضِر الحارس كاذباً."""
    root = _tree(tmp_path, '# REQUIRED_LINKS = ("a", "b", "c")\nX = 1\n')
    problems, checked = guard.violations(_relation(), root)
    assert problems and checked == 0


def test_a_relation_without_declared_semantics_is_blocked(tmp_path):
    problems, _ = guard.violations(_relation(semantics={}), _tree(tmp_path))
    assert problems and "بلا دلالةٍ مُعلَنة" in problems[0]


def test_an_acyclic_relation_with_a_repeated_link_is_blocked(tmp_path):
    root = _tree(tmp_path, 'REQUIRED_LINKS = ("a", "b", "a")\n')
    problems, _ = guard.violations(_relation(chain=["a", "b", "a"]), root)
    assert problems and "تكرّر حلقة" in problems[0]


def test_a_directional_relation_with_identical_ends_is_blocked(tmp_path):
    problems, _ = guard.violations(_relation(to="src"), _tree(tmp_path))
    assert problems and "طرفاها واحد" in problems[0]


def test_a_duplicate_relation_name_is_blocked(tmp_path):
    relations = _relation() + _relation(chain=["a", "b"])
    problems, _ = guard.violations(relations, _tree(tmp_path))
    assert any("مكرَّرة" in p for p in problems)


def test_a_chain_shorter_than_two_links_is_blocked(tmp_path):
    problems, _ = guard.violations(_relation(chain=["a"]), _tree(tmp_path))
    assert problems and "أقصر من حلقتين" in problems[0]


def test_a_missing_consumer_is_blocked(tmp_path):
    problems, _ = guard.violations(_relation(consumers=["api/gone.py"]), _tree(tmp_path))
    assert any("مُستهلِكٌ مُعلَنٌ غير موجود" in p for p in problems)


def test_zero_relations_checked_fails_closed(tmp_path, monkeypatch):
    registry = tmp_path / "reg.json"
    registry.write_text(
        json.dumps({"schema": "sahool.knowledge_relation_registry", "relations": _relation()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "violations", lambda relations, root: ([], 0))
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(registry), "--root", str(tmp_path)])


def test_a_missing_registry_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(tmp_path / "nope.json"), "--root", str(tmp_path)])


def test_a_wrong_schema_fails_closed(tmp_path):
    root = _tree(tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"schema": "else", "relations": _relation()}), encoding="utf-8")
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(other), "--root", str(root)])


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0


def test_the_live_relation_matches_the_irrigation_chain():
    """المسار الثاني: العلاقة الحقيقيّة مقابل الثابت الحقيقيّ.

    ولم تُخترَع هذه العلاقة: `REQUIRED_LINKS` تحكم فعلاً قرار «أضعف حلقة».
    """
    relations = guard.load_relations(guard.REGISTRY)
    assert len(relations) >= 1
    feeds = next(r for r in relations if r["name"] == "feeds")
    assert feeds["chain"] == ["well", "hydraulic", "machine", "sprinkler", "energy", "controller"]
    problems, checked = guard.violations(relations, guard.ROOT)
    assert problems == [] and checked >= 1


def test_reference_relation_cannot_claim_authority(tmp_path):
    rel = _relation(
        graph_role="reference",
        authority_semantics="decision",
        evidence_semantics="retrieval_context_only",
        direct_execution_permitted=False,
        causal_claim_permitted=False,
    )
    problems, _ = guard.violations(rel, _tree(tmp_path))
    assert any("لا يجوز أن تمنح سلطة قرار" in p for p in problems)


def test_evidence_relation_cannot_claim_causality(tmp_path):
    rel = _relation(
        graph_role="evidence",
        authority_semantics="none",
        evidence_semantics="explanatory_not_causal",
        direct_execution_permitted=False,
        causal_claim_permitted=True,
    )
    problems, _ = guard.violations(rel, _tree(tmp_path))
    assert any("لا يجوز أن تتحول إلى ادعاء سببي" in p for p in problems)


def test_no_registered_relation_can_grant_direct_execution(tmp_path):
    problems, _ = guard.violations(_relation(direct_execution_permitted=True), _tree(tmp_path))
    assert any("لا يجوز أن يمنح تنفيذًا مباشرًا" in p for p in problems)


def test_vocabulary_bound_relation_must_exist_in_executed_vocabulary(tmp_path):
    root = _tree(tmp_path, 'RELATIONS = ("supports", "has_evidence")\n')
    rel = _relation(
        name="supports",
        graph_role="evidence",
        authority_semantics="none",
        evidence_semantics="explanatory_not_causal",
        direct_execution_permitted=False,
        causal_claim_permitted=False,
        chain=None,
        chain_source_module=None,
        chain_symbol=None,
        vocabulary_source_module="api/graph.py",
        vocabulary_symbol="RELATIONS",
    )
    problems, checked = guard.violations(rel, root)
    assert problems == [] and checked == 1

    rel[0]["name"] = "invented_relation"
    problems, _ = guard.violations(rel, root)
    assert any("غير موجودة في المفردات المنفَّذة" in p for p in problems)


def test_live_registry_has_three_graph_roles_without_authority_leak():
    relations = guard.load_relations(guard.REGISTRY)
    roles = {r["graph_role"] for r in relations}
    assert roles == {"reference", "evidence", "operational"}
    assert sum(r["graph_role"] == "reference" for r in relations) == 4
    assert sum(r["graph_role"] == "evidence" for r in relations) == 2
    assert sum(r["graph_role"] == "operational" for r in relations) == 1
    assert all(r["direct_execution_permitted"] is False for r in relations)
    assert all(
        r["authority_semantics"] == "none"
        for r in relations
        if r["graph_role"] in {"reference", "evidence"}
    )
