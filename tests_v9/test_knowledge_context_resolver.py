"""عقد سياق المهمّة ومُحلِّله — الغياب صوتٌ لا صمت.

**الخاصّيّة المركزيّة المُختبَرة هنا** ليست «يعمل في الحالة السعيدة»، بل أنّ كلّ
طريقٍ إلى الفشل يُنتِج **حجباً مُعلَّلاً** لا قيمةً ناقصة. لأنّ القيمة الناقصة هي
ما يدفع المستهلك إلى `value or fallback` — أي الالتفاف الذي يمنعه
`canonical_consumer_bypass_guard`. فالطبقتان تحرسان الشيء نفسه من طرفيه:
هذه عند التشغيل، وذاك عند الترجمة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from shared.knowledge.context_resolver import ContextResolver  # noqa: E402
from shared.knowledge.contracts import (  # noqa: E402
    ContextResolutionError,
    KnowledgeRequirement,
    KnowledgeValue,
    ResolvedContext,
    TaskContextContract,
)
from shared.knowledge.irrigation_context import (  # noqa: E402
    IRRIGATION_RECOMMENDATION_CONTEXT,
)
from shared.knowledge.source_registry import (  # noqa: E402
    KnowledgeSource,
    RegistryError,
    load_registry,
)

_KEY = "root_zone.maximum_safe_depth_mm_event"
_SOT = "canonical_sprinkler_runoff_capability"


def _sources() -> dict[str, KnowledgeSource]:
    return {
        _KEY: KnowledgeSource(
            key=_KEY,
            source_of_truth=_SOT,
            producer_module="prod.py",
            producer_field="maximum_safe_depth_mm_event",
            forbidden_raw_inputs=("raw_mm",),
            forbidden_reason_ar="سبب",
            consumers=("cons.py",),
        )
    }


def _contract(**overrides) -> TaskContextContract:
    base = {"key": _KEY, "source_of_truth": _SOT, "fail_closed": True}
    base.update(overrides)
    return TaskContextContract(task="t", requirements=(KnowledgeRequirement(**base),))


def _value(**overrides) -> KnowledgeValue:
    base = {"value": 12.0, "source_of_truth": _SOT, "producer": "svc"}
    base.update(overrides)
    return KnowledgeValue(**base)


def _resolver(provider, sources=None) -> ContextResolver:
    return ContextResolver({_SOT: provider}, sources=sources or _sources())


def test_a_satisfied_contract_yields_the_value_with_its_provenance():
    ctx = _resolver(lambda req: _value()).resolve(_contract())
    assert ctx.satisfied
    assert ctx.require(_KEY) == 12.0
    assert ctx.provenance(_KEY).source_of_truth == _SOT


def test_require_raises_instead_of_returning_none():
    """الإرجاع الصامت هو ما يُغري بـ`value or fallback`؛ فالغياب يرفع."""
    ctx = _resolver(lambda req: None).resolve(_contract())
    assert not ctx.satisfied
    with pytest.raises(ContextResolutionError):
        ctx.require(_KEY)


def test_the_raised_message_carries_the_blocking_reason():
    """رسالةٌ تقول «غير محلول» بلا سبب تترك قارئها يخمّن."""
    ctx = _resolver(lambda req: None).resolve(_contract())
    with pytest.raises(ContextResolutionError) as exc:
        ctx.require(_KEY)
    assert "KNOWLEDGE_UNAVAILABLE" in str(exc.value)


def test_a_fail_closed_requirement_blocks_when_absent():
    ctx = _resolver(lambda req: None).resolve(_contract())
    assert any("KNOWLEDGE_UNAVAILABLE" in r for r in ctx.blocking_reasons)


def test_an_optional_requirement_limits_but_does_not_block():
    """قيدٌ لا حجب — لكنّه **يُسجَّل**: سياقٌ ناقصٌ لا يقول ذلك يُقرأ كاملاً."""
    ctx = _resolver(lambda req: None).resolve(_contract(fail_closed=False, required=False))
    assert ctx.satisfied
    assert any("KNOWLEDGE_UNAVAILABLE" in x for x in ctx.limitations)


def test_a_shadow_source_of_truth_is_blocked():
    """عقدٌ يُسمّي مصدراً غير المُسجَّل يُنشئ مصدرَ حقيقةٍ ظلّاً بإعلانٍ واحد."""
    ctx = _resolver(lambda req: _value()).resolve(_contract(source_of_truth="other_module"))
    assert any("SHADOW_SOURCE_OF_TRUTH" in r for r in ctx.blocking_reasons)


def test_an_unregistered_key_is_blocked():
    ctx = _resolver(lambda req: _value()).resolve(
        TaskContextContract(
            task="t",
            requirements=(KnowledgeRequirement(key="nope", source_of_truth=_SOT),),
        )
    )
    assert any("UNREGISTERED_KNOWLEDGE_KEY" in r for r in ctx.blocking_reasons)


def test_a_provider_that_mislabels_its_provenance_is_blocked():
    """قيمةٌ صحيحة بنَسَبٍ كاذب أخطرُ من غياب: تمرّ ويُبنى عليها."""
    ctx = _resolver(lambda req: _value(source_of_truth="elsewhere")).resolve(_contract())
    assert any("PROVENANCE_MISMATCH" in r for r in ctx.blocking_reasons)


def test_a_stale_value_is_blocked_when_freshness_is_declared():
    old = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    ctx = _resolver(lambda req: _value(observed_at=old)).resolve(
        _contract(max_age_seconds=3600),
        now_epoch=datetime.now(UTC).timestamp(),
    )
    assert any("KNOWLEDGE_STALE" in r for r in ctx.blocking_reasons)


def test_a_fresh_value_passes_the_same_freshness_clause():
    """المسار الموجب لبند الطزاجة — وإلّا كان الحجب قد يقع لأيّ سبب."""
    now = datetime.now(UTC)
    ctx = _resolver(
        lambda req: _value(observed_at=(now - timedelta(seconds=5)).isoformat())
    ).resolve(_contract(max_age_seconds=3600), now_epoch=now.timestamp())
    assert ctx.satisfied and ctx.require(_KEY) == 12.0


def test_unmeasurable_freshness_is_blocked_not_assumed_fresh():
    """«لم يُقَس العمر» ليس «طازج» — والافتراض الآمن هو الحجب."""
    ctx = _resolver(lambda req: _value(observed_at=None)).resolve(
        _contract(max_age_seconds=3600), now_epoch=datetime.now(UTC).timestamp()
    )
    assert any("FRESHNESS_UNMEASURABLE" in r for r in ctx.blocking_reasons)


def test_a_missing_provider_is_blocked_not_silently_skipped():
    ctx = ContextResolver({}, sources=_sources()).resolve(_contract())
    assert any("NO_PROVIDER_REGISTERED" in r for r in ctx.blocking_reasons)


def test_an_unreadable_registry_blocks_everything(tmp_path, monkeypatch):
    """سجلٌّ لا يُقرأ ⇒ حجبٌ كامل. «لم يُعرَف» ليس «لا قيد»."""
    import shared.knowledge.context_resolver as mod

    def boom():
        raise RegistryError("مكسور")

    monkeypatch.setattr(mod, "registry", boom)
    ctx = ContextResolver({_SOT: lambda req: _value()}).resolve(_contract())
    assert not ctx.satisfied
    assert any("KNOWLEDGE_REGISTRY_UNREADABLE" in r for r in ctx.blocking_reasons)


def test_provenance_raises_for_an_unresolved_key():
    ctx = ResolvedContext(task="t")
    with pytest.raises(ContextResolutionError):
        ctx.provenance(_KEY)


# ── السجلّ نفسه: بنيةٌ تُفحَص ولا تُفترَض ────────────────────────────────


def _write(tmp_path: Path, payload: object) -> Path:
    target = tmp_path / "reg.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def _entry(**overrides) -> dict:
    base = {
        "key": _KEY,
        "source_of_truth": _SOT,
        "producer_module": "prod.py",
        "producer_field": "f",
        "forbidden_raw_inputs": ["raw_mm"],
        "forbidden_reason_ar": "سبب",
        "consumers": ["cons.py"],
    }
    base.update(overrides)
    return base


def _payload(entries: list[dict]) -> dict:
    return {"schema": "sahool.knowledge_source_registry", "version": 1, "keys": entries}


def test_a_duplicate_key_is_rejected(tmp_path):
    """مفتاحٌ مكرَّر يعني مصدرَي حقيقةٍ لشيءٍ واحد — نقيض غرض السجلّ."""
    path = _write(tmp_path, _payload([_entry(), _entry(source_of_truth="other")]))
    with pytest.raises(RegistryError):
        load_registry(path)


def test_an_empty_forbidden_list_is_rejected(tmp_path):
    path = _write(tmp_path, _payload([_entry(forbidden_raw_inputs=[])]))
    with pytest.raises(RegistryError):
        load_registry(path)


def test_a_missing_registry_raises_rather_than_reading_zero_keys(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(tmp_path / "absent.json")


def test_a_wrong_schema_is_rejected(tmp_path):
    path = _write(tmp_path, {"schema": "other", "keys": [_entry()]})
    with pytest.raises(RegistryError):
        load_registry(path)


def test_the_live_registry_loads_and_matches_the_declared_contract():
    """المسار الثاني: عقد الريّ الحقيقيّ مقابل السجلّ الحقيقيّ.

    إعلانُ مصدرٍ في العقد يخالف السجلّ هو تعريف «مصدر الحقيقة الظلّ»، وهذه
    أرخص لحظةٍ يُلتقَط فيها.
    """
    sources = load_registry()
    for req in IRRIGATION_RECOMMENDATION_CONTEXT.requirements:
        assert req.key in sources, f"مفتاحٌ مُعلَنٌ غير مُسجَّل: {req.key}"
        assert sources[req.key].source_of_truth == req.source_of_truth
        assert req.fail_closed, f"{req.key}: متطلَّبٌ حاجبٌ بالعقد"
