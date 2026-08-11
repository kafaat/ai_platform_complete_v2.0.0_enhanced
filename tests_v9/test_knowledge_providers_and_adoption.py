"""التبنّي: الطبقة تحمل قراراً حقيقيّاً، لا تُعلَن وحدها.

**ولماذا هذا المِلَفّ أصلاً:** قِيس بعد دمج الشريحة الأولى أنّ مُستدعي
`ContextResolver` خارج الاختبارات **صفر** ومُنتِجي `KnowledgeValue` **صفر**.
فطبقةٌ لا يستدعيها مسارٌ إنتاجيّ توثيقٌ مهما كثرت اختباراتها: ما تحرسه لا يقع
على أحد.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from shared.knowledge.context_resolver import ContextResolver  # noqa: E402
from shared.knowledge.irrigation_context import (  # noqa: E402
    IRRIGATION_RECOMMENDATION_CONTEXT,
    SPRINKLER_RUNOFF_CAPABILITY_CONTEXT,
)
from shared.knowledge.providers import (  # noqa: E402
    irrigation_capability_provider,
    root_zone_provider,
    sprinkler_provider,
)
from shared.knowledge.source_registry import load_registry  # noqa: E402

_GRAPH_SOT = "canonical_irrigation_capability_graph"


def _graph(**overrides) -> dict:
    base = {
        "maximum_safe_depth_mm_event": 12.0,
        "capability_digest": "d" * 64,
        "product_version": "graph/1.0.0",
        "status": "verified",
    }
    base.update(overrides)
    return base


def _resolve(graph: dict):
    return ContextResolver({_GRAPH_SOT: irrigation_capability_provider(graph)}).resolve(
        IRRIGATION_RECOMMENDATION_CONTEXT
    )


def test_a_complete_capability_graph_satisfies_the_recommendation_contract():
    ctx = _resolve(_graph())
    assert ctx.satisfied
    assert ctx.require("irrigation.maximum_safe_depth_mm_event") == 12.0


def test_the_resolved_value_carries_its_producer_not_the_sprinklers():
    """النَّسَب يجب أن يسمّي **مُنتِج القيمة**، والرسم البيانيّ هو مُنتِجُها.

    قيمتُه `min(machine_depth, safe_event_depth)` — لا قيمة الرشّ حرفيّاً؛
    فنسبتُها إلى `canonical_sprinkler_runoff_capability` نَسَبٌ كاذب.
    """
    prov = _resolve(_graph()).provenance("irrigation.maximum_safe_depth_mm_event")
    assert prov.source_of_truth == _GRAPH_SOT
    assert prov.evidence_refs == ("d" * 64,)


def test_a_value_without_its_producers_digest_is_refused():
    """الصنف المقيس في M2.6: قيمةٌ تُسلَّم ونَسَبُها فارغ.

    وهي أسوأ من الغياب لأنّ من يقرأ القيمة لا يعود ينظر في الأدلّة.
    """
    ctx = _resolve(_graph(capability_digest=""))
    assert not ctx.satisfied
    assert any("KNOWLEDGE_UNAVAILABLE" in r for r in ctx.blocking_reasons)


@pytest.mark.parametrize("bad", [None, "12.0", float("nan"), float("inf"), True])
def test_a_non_finite_or_non_numeric_value_is_refused(bad):
    """`True` في القائمة عمداً: `bool` نوعٌ فرعيّ من `int` في بايثون،

    فيمرّ على فحصٍ ساذج ويصير عمقاً = ١ مليمتر.
    """
    ctx = _resolve(_graph(maximum_safe_depth_mm_event=bad))
    assert not ctx.satisfied


def test_a_missing_key_in_the_field_map_yields_nothing_rather_than_guessing():
    """مُزوِّدٌ سُئِل عن مفتاحٍ لا يعرفه يصمت — ولا يُخمّن حقلاً بالاسم."""
    ctx = ContextResolver({"canonical_root_zone_profile": root_zone_provider(_graph())}).resolve(
        SPRINKLER_RUNOFF_CAPABILITY_CONTEXT
    )
    assert not ctx.satisfied


def test_the_root_zone_provider_reads_its_own_field():
    profile = {"root_zone_refill_cap_mm": 48.6, "profile_digest": "p" * 64}
    ctx = ContextResolver({"canonical_root_zone_profile": root_zone_provider(profile)}).resolve(
        SPRINKLER_RUNOFF_CAPABILITY_CONTEXT
    )
    assert ctx.satisfied
    assert ctx.require("root_zone.root_zone_refill_cap_mm") == 48.6


def test_the_sprinkler_provider_is_labelled_with_the_sprinkler_source():
    from shared.knowledge.contracts import KnowledgeRequirement

    value = sprinkler_provider({"maximum_safe_depth_mm_event": 9.0, "capability_digest": "s" * 64})(
        KnowledgeRequirement(
            key="sprinkler.maximum_safe_depth_mm_event",
            source_of_truth="canonical_sprinkler_runoff_capability",
        )
    )
    assert value is not None
    assert value.source_of_truth == "canonical_sprinkler_runoff_capability"


# ── العقود مقابل السجلّ الحيّ ────────────────────────────────────────────


@pytest.mark.parametrize(
    "contract", [IRRIGATION_RECOMMENDATION_CONTEXT, SPRINKLER_RUNOFF_CAPABILITY_CONTEXT]
)
def test_every_declared_contract_agrees_with_the_live_registry(contract):
    sources = load_registry()
    for req in contract.requirements:
        assert req.key in sources, f"{contract.task}: مفتاحٌ مُعلَنٌ غير مُسجَّل — {req.key}"
        assert sources[req.key].source_of_truth == req.source_of_truth


def test_the_two_tasks_do_not_share_a_requirement():
    """عقدٌ لكلّ مهمّة: خلطُهما جعل المُنسِّق يحمل عبء معرفةٍ لا يجلبها.

    وهذا مقيس: ربطُ العقد المُوحَّد بـ`orchestrate_irrigation_recommendation`
    كان **يحجب كلّ توصية**، لأنّ المُنسِّق لا يجلب مِلَفَّ منطقة الجذر أصلاً.
    """
    a = set(IRRIGATION_RECOMMENDATION_CONTEXT.keys)
    b = set(SPRINKLER_RUNOFF_CAPABILITY_CONTEXT.keys)
    assert a and b and not (a & b)


def test_the_orchestrator_resolves_the_contract_before_scheduling():
    """المُنسِّق الحقيقيّ يستدعي المُحلِّل — وهذا ما يجعل الطبقة حاملة.

    يُقاس بالاستيراد لا بالنصّ: استيرادٌ يُحذَف يُسقِط هذا التأكيد، بينما
    تعليقٌ يذكر الاسم كان سيُبقيه أخضر.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (
        root / "services" / "sahool-platform" / "api" / "irrigation_runtime_orchestrator.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("shared.knowledge")
        for alias in node.names
    }
    assert {
        "ContextResolver",
        "IRRIGATION_RECOMMENDATION_CONTEXT",
        "irrigation_capability_provider",
    } <= imported, f"المُنسِّق لا يستورد طبقة المعرفة: {sorted(imported)}"

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "ContextResolver" in called, "الاستيراد وحده لا يكفي — يجب أن يُستدعى"
