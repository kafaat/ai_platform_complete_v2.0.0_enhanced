"""اختبارات resolver دورة المحصول (api.crop_cycle) — حفظ السلوك + الطبقات."""

from __future__ import annotations

from api.crop_cycle import card_cycle_days, cycle_days_to_maturity


def test_region_override_wins_over_card_sum():
    # (أ) طبقة المنطقة (130) تتجاوز مجموع مراحل بطاقة القمح (120).
    assert cycle_days_to_maturity("wheat") == 130


def test_card_cycle_days_is_neutral_baseline():
    # (ب) الأساس المحايد = مجموع kc.stage_days لبطاقة القمح = 15+25+50+30 = 120.
    assert card_cycle_days("wheat") == 120


def test_card_path_for_carded_crop_and_nonexistent_is_none():
    # (ج) مسار البطاقة لمحصول مُبطَّق (sorghum: 20+35+45+30 = 130 مثلاً) ⇐ عدد موجب.
    assert isinstance(card_cycle_days("sorghum"), int)
    assert card_cycle_days("sorghum") > 0
    # محصول لا بطاقة له ولا تجاوز ⇐ None (لا لفلفة).
    assert cycle_days_to_maturity("__nonexistent__") is None
    assert card_cycle_days("__nonexistent__") is None


def test_caller_overrides_win():
    # (د) تجاوز المُستدعي (طبقة المستأجِر) يتغلّب على طبقة المنطقة.
    assert cycle_days_to_maturity("wheat", overrides={"wheat": 99}) == 99


def test_normalization_matches_hub():
    assert cycle_days_to_maturity("  WHEAT  ") == 130
    assert cycle_days_to_maturity("") is None
    assert cycle_days_to_maturity(None) is None
