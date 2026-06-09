"""Tests for crop card template conformance and region-agnostic neutrality."""
from core.crop_cards.loader import (
    load_crop_card, list_crop_cards, validate_crop_card)


class TestCropCards:
    def test_real_crops_present(self):
        cards = list_crop_cards()
        for crop in ("wheat", "barley", "millet", "sorghum"):
            assert crop in cards

    def test_all_cards_valid(self):
        # every card must conform to the standard template
        for cid in list_crop_cards():
            v = validate_crop_card(load_crop_card(cid))
            assert v["valid"], f"{cid}: {v['errors']}"

    def test_wheat_salinity_threshold_realistic(self):
        # wheat threshold ~6 dS/m (Maas-Hoffman)
        card = load_crop_card("wheat")
        assert 5.0 <= card["salinity"]["threshold_ece_ds_m"] <= 8.0

    def test_barley_most_salt_tolerant_cereal(self):
        # barley should tolerate more salt than wheat
        barley = load_crop_card("barley")["salinity"]["threshold_ece_ds_m"]
        wheat = load_crop_card("wheat")["salinity"]["threshold_ece_ds_m"]
        assert barley > wheat

    def test_cards_have_sources(self):
        # every physical block must cite a source (no fabricated numbers)
        for cid in list_crop_cards():
            card = load_crop_card(cid)
            assert "source" in card["kc"]
            assert "source" in card["salinity"]

    def test_no_calibration_in_cards(self):
        # region-agnostic: cards must NOT contain calibration/yield/region
        for cid in list_crop_cards():
            card = load_crop_card(cid)
            assert "calibration" not in card
            assert "yield" not in card
            assert "zone_factor" not in card

    def test_missing_crop_returns_none(self):
        assert load_crop_card("nonexistent_crop") is None

    def test_germination_salinity_stricter(self):
        # germination threshold should be <= general threshold (sensitive stage)
        for cid in ("wheat", "barley"):
            card = load_crop_card(cid)
            sal = card["salinity"]
            if "germination_ece_max" in sal:
                assert sal["germination_ece_max"] <= sal["threshold_ece_ds_m"]


class TestVarietyCards:
    def test_varieties_present(self):
        from core.crop_cards.loader import list_variety_cards
        cards = list_variety_cards()
        assert "wheat_local_highland" in cards
        assert "sorghum_local_qairaa" in cards

    def test_all_varieties_valid(self):
        from core.crop_cards.loader import list_variety_cards, load_variety_card, validate_variety_card
        for vid in list_variety_cards():
            v = validate_variety_card(load_variety_card(vid))
            assert v["valid"], f"{vid}: {v['errors']}"

    def test_variety_links_to_existing_crop(self):
        # every variety must link to a real parent crop card
        from core.crop_cards.loader import load_variety_card, load_crop_card
        v = load_variety_card("wheat_local_highland")
        assert load_crop_card(v["parent_crop_id"]) is not None

    def test_varieties_of_crop(self):
        from core.crop_cards.loader import varieties_of_crop
        assert "wheat_local_highland" in varieties_of_crop("wheat")
        assert varieties_of_crop("nonexistent") == []

    def test_variety_has_passport(self):
        # UPOV/Bioversity: must have passport with origin + source
        from core.crop_cards.loader import load_variety_card
        v = load_variety_card("sorghum_local_qairaa")
        assert v["passport"]["origin_type"] in ("landrace", "improved", "introduced")
        assert "source_ar" in v["passport"]

    def test_variety_region_agnostic(self):
        from core.crop_cards.loader import list_variety_cards, load_variety_card
        for vid in list_variety_cards():
            v = load_variety_card(vid)
            assert "calibration" not in v
            assert "yield" not in v

    def test_orphan_variety_rejected(self):
        # a variety pointing to a non-existent crop must fail validation
        from core.crop_cards.loader import validate_variety_card
        fake = {"variety_id": "x", "parent_crop_id": "ghost_crop",
                "name_ar": "x", "name_en": "x",
                "passport": {"origin_type": "landrace", "source_ar": "x"},
                "distinctness": {}, "variety_traits": {}}
        assert validate_variety_card(fake)["valid"] is False


class TestCranberryCounterExample:
    """Cranberry is an intentional COUNTER-EXAMPLE: a crop that must be rejected
    for hot/dry/alkaline Yemen conditions. Review correctly flagged this was untested."""

    def test_cranberry_loads_and_validates(self):
        from core.crop_cards.loader import load_crop_card, validate_crop_card
        card = load_crop_card("cranberry")
        assert card is not None
        result = validate_crop_card(card)
        assert result["valid"], f"card structure invalid: {result}"

    def test_cranberry_extreme_salt_sensitivity(self):
        # ECe threshold 1.0 = far below any Yemeni soil → counter-example
        from core.crop_cards.loader import load_crop_card
        card = load_crop_card("cranberry")
        assert card["salinity"]["threshold_ece_ds_m"] <= 1.5

    def test_cranberry_chilling_unmet_in_hot_climate(self):
        # needs 800+ chilling hours — impossible in hot Yemeni lowlands
        from core.crop_cards.loader import load_crop_card
        card = load_crop_card("cranberry")
        assert card["thermal"]["chilling_hours_required"] >= 800

    def test_cranberry_acidic_ph_incompatible_with_alkaline_soil(self):
        # needs pH 4-6 (acidic); Yemeni soils typically alkaline (pH>7.5)
        # pH is correctly under 'governing' (strict governor), not 'modifying'
        from core.crop_cards.loader import load_crop_card
        card = load_crop_card("cranberry")
        assert card["governing"]["ph"]["max"] <= 6.0

    def test_cranberry_neutral_no_location_leak(self):
        # even the counter-example must stay region-agnostic
        import io
        card_text = open("core/crop_cards/cranberry.yaml", encoding="utf-8").read()
        for token in ("sakha", "6.17", "142ha", "aljawf", "الجوف"):
            assert token not in card_text
