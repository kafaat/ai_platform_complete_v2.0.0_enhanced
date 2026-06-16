"""اختبارات إرشاد الدورة الزراعيّة (api.crop_rotation) — دوالّ نقيّة offline.

يتحقّق من `_resolve` (إنجليزي/عربي/مجهول)، ومن `evaluate_rotation`: عقوبة نفس
العائلة (avoid + تحذير غالب)، تعاقب عائلتين مختلفتين (جيّد)، القاعدة الذهبيّة
بقولي↔حبوب (مكافأة نيتروجين)، والتعامل اللطيف مع محصول مجهول (supported=False).
كلّ القيم مشتقّة من جدول `_CROP_INFO` ونظام النقاط في الوحدة نفسها لا من افتراض.
"""

import pytest
from api.crop_rotation import (
    CropFamily,
    RotationAdvice,
    _resolve,
    evaluate_rotation,
    rotation_principles,
    suggest_next_crop,
)

pytestmark = pytest.mark.unit


# ─── _resolve: التعرّف على المحصول ───────────────────────────────────────


def test_resolve_english_key_case_insensitive():
    assert _resolve("Wheat") == "wheat"
    assert _resolve("  SORGHUM ") == "sorghum"


def test_resolve_arabic_alias():
    assert _resolve("قمح") == "wheat"
    assert _resolve("عدس") == "lentil"
    assert _resolve("برسيم") == "alfalfa"


def test_resolve_unknown_returns_none():
    assert _resolve("banana") is None
    assert _resolve("موز") is None


# ─── evaluate_rotation: العائلة والقواعد ─────────────────────────────────


def test_same_family_is_avoid_with_dominant_penalty():
    # القمح والشعير كلاهما نجيليّ ⇒ نفس العائلة ⇒ avoid مهما كان باقي السياق.
    res = evaluate_rotation("wheat", "barley")
    assert res["supported"] is True
    assert res["rating"] == "avoid"
    assert res["rating_ar"] == "يُفضّل تجنّبه ✗"
    assert any("نفس العائلة" in r for r in res["reasons_ar"])


def test_different_families_break_pest_cycle():
    # الطماطم (باذنجانيّة) ← البصل (بصليّة): عائلتان مختلفتان + جذور + موسم ⇒ جيّد.
    res = evaluate_rotation("tomato", "onion")
    assert res["supported"] is True
    assert res["rating"] == "good"
    assert any("عائلتان مختلفتان" in r for r in res["reasons_ar"])


def test_legume_after_grass_is_good_with_nitrogen_bonus():
    # القمح (نجيلي) ← العدس (بقولي): القاعدة الذهبيّة ⇒ مكافأة تثبيت النيتروجين.
    res = evaluate_rotation("wheat", "lentil")
    assert res["rating"] == "good"
    assert res["previous_crop"] == "القمح"
    assert res["candidate_crop"] == "العدس"
    assert any("بقولي بعد حبوب" in r for r in res["reasons_ar"])


def test_grass_after_legume_uses_residual_nitrogen():
    # العدس (بقولي) ← القمح (نجيلي): العكس يستفيد من النيتروجين المتبقّي.
    res = evaluate_rotation("lentil", "wheat")
    assert res["rating"] == "good"
    assert any("حبوب بعد بقولي" in r for r in res["reasons_ar"])


def test_forage_legume_after_grass_also_gets_bonus():
    # البرسيم (علفي/بقولي) بعد الذرة الرفيعة (نجيلي) ⇒ يشمله شرط البقولي بعد الحبوب.
    res = evaluate_rotation("sorghum", "alfalfa")
    assert res["rating"] == "good"
    assert any("بقولي بعد حبوب" in r for r in res["reasons_ar"])


def test_acceptable_when_only_family_differs():
    # البصل ← القمح: عائلتان مختلفتان (+1) لكن نفس الجذر السطحي ونفس الموسم الشتوي
    # ⇒ النقاط = 1 ⇒ مقبول لا جيّد.
    res = evaluate_rotation("onion", "wheat")
    assert res["rating"] == "acceptable"
    assert res["rating_ar"] == "مقبول"


def test_unknown_previous_handled_gracefully():
    res = evaluate_rotation("banana", "wheat")
    assert res["supported"] is False
    assert "banana" in res["message_ar"]


def test_unknown_candidate_handled_gracefully():
    res = evaluate_rotation("wheat", "banana")
    assert res["supported"] is False
    assert "banana" in res["message_ar"]


def test_evaluate_rotation_returns_expected_keys():
    res = evaluate_rotation("wheat", "lentil")
    for key in (
        "previous_crop",
        "candidate_crop",
        "rating",
        "rating_ar",
        "reasons_ar",
        "supported",
    ):
        assert key in res


# ─── RotationAdvice + suggest_next_crop + المبادئ ────────────────────────


def test_rotation_advice_to_dict_roundtrip():
    adv = RotationAdvice("القمح", "العدس", "good", "تعاقب جيّد ✓", ["سبب"])
    d = adv.to_dict()
    assert d == {
        "previous_crop": "القمح",
        "candidate_crop": "العدس",
        "rating": "good",
        "rating_ar": "تعاقب جيّد ✓",
        "reasons_ar": ["سبب"],
    }


def test_suggest_next_crop_ranks_good_first_and_excludes_self():
    res = suggest_next_crop("wheat")
    assert res["supported"] is True
    ratings = [c["rating"] for c in res["ranked"]]
    # مرتّبة: good قبل acceptable قبل avoid (رتبة 2/1/0 تنازليّاً).
    order = {"good": 2, "acceptable": 1, "avoid": 0}
    assert [order[r] for r in ratings] == sorted([order[r] for r in ratings], reverse=True)
    # لا يقترح القمح على نفسه.
    assert all(c["candidate_crop"] != "القمح" for c in res["ranked"])


def test_suggest_next_crop_unknown_is_unsupported():
    res = suggest_next_crop("banana")
    assert res["supported"] is False


def test_rotation_principles_lists_supported_crops():
    res = rotation_principles()
    assert res["principles_ar"]
    crops = {c["crop"] for c in res["supported_crops"]}
    assert {"wheat", "lentil", "alfalfa", "tomato"} <= crops


def test_crop_family_enum_values():
    assert CropFamily.GRASS.value == "grass"
    assert CropFamily.LEGUME.value == "legume"
    assert CropFamily.FORAGE.value == "forage"
