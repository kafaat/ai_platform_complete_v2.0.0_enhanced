"""اختبارات سجلّ حوكمة التكلفة (Cost Governance).

تتحقّق من: السجلّ غير فارغ، المُعرّفات فريدة، الرُّتب ضمن المجموعات المسموحة،
get_profile يعمل ويُعيد None للمجهول، cheapest("ai_model") يُعيد أدنى نموذج،
for_kind يصفّي بشكل صحيح. كلّ ذلك نقيّ (لا قاعدة/شبكة).
"""

from __future__ import annotations

from api import cost_governance as cg

_COST = {"low", "medium", "high"}
_LATENCY = {"low", "medium", "high"}
_KINDS = {"service", "ai_model", "imagery"}


def test_registry_non_empty():
    profiles = cg.list_profiles()
    assert len(profiles) > 0


def test_ids_unique():
    ids = [p["id"] for p in cg.list_profiles()]
    assert len(ids) == len(set(ids))


def test_tiers_and_kinds_in_allowed_sets():
    for p in cg.list_profiles():
        assert p["cost_tier"] in _COST
        assert p["latency_tier"] in _LATENCY
        assert p["kind"] in _KINDS
        # رُتب نسبيّة لا مبالغ ماليّة: الوحدة نصّ، وملاحظة عربيّة موجودة.
        assert isinstance(p["unit"], str) and p["unit"]
        assert isinstance(p["notes_ar"], str) and p["notes_ar"]


def test_get_profile_known_and_unknown():
    known_id = cg.list_profiles()[0]["id"]
    got = cg.get_profile(known_id)
    assert got is not None
    assert got["id"] == known_id
    assert cg.get_profile("__does_not_exist__") is None


def test_for_kind_filters_correctly():
    models = cg.for_kind("ai_model")
    assert models  # يوجد نموذج واحد على الأقلّ
    assert all(p["kind"] == "ai_model" for p in models)
    # لا تسرّب أنواع أخرى
    services = cg.for_kind("service")
    assert all(p["kind"] == "service" for p in services)
    model_ids = {p["id"] for p in models}
    service_ids = {p["id"] for p in services}
    assert model_ids.isdisjoint(service_ids)


def test_cheapest_ai_model_is_lowest_tier():
    cheap = cg.cheapest("ai_model")
    assert cheap is not None
    assert cheap["kind"] == "ai_model"
    order = {"low": 0, "medium": 1, "high": 2}
    for p in cg.for_kind("ai_model"):
        # لا يوجد نموذج أرخص (cost ثمّ latency) من المُعاد.
        assert (order[cheap["cost_tier"]], order[cheap["latency_tier"]]) <= (
            order[p["cost_tier"]],
            order[p["latency_tier"]],
        )
    # في السجلّ الحاليّ، TabPFN هو الأرخص/الأسرع بين النماذج.
    assert cheap["id"] == "tabpfn_small_data"


def test_cheapest_unknown_kind_is_none():
    assert cg.cheapest("__nope__") is None
