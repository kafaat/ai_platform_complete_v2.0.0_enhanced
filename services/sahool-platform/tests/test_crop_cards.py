"""Tests for crop card template conformance and region-agnostic neutrality."""

from core.crop_cards.loader import list_crop_cards, load_crop_card, validate_crop_card


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
        from core.crop_cards.loader import (
            list_variety_cards,
            load_variety_card,
            validate_variety_card,
        )

        for vid in list_variety_cards():
            v = validate_variety_card(load_variety_card(vid))
            assert v["valid"], f"{vid}: {v['errors']}"

    def test_variety_links_to_existing_crop(self):
        # every variety must link to a real parent crop card
        from core.crop_cards.loader import load_crop_card, load_variety_card

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

        fake = {
            "variety_id": "x",
            "parent_crop_id": "ghost_crop",
            "name_ar": "x",
            "name_en": "x",
            "passport": {"origin_type": "landrace", "source_ar": "x"},
            "distinctness": {},
            "variety_traits": {},
        }
        assert validate_variety_card(fake)["valid"] is False


class TestCommonBeanFromLegumesGuide:
    """الفاصولياء وأصنافها اليمنية الثلاثة — مُضافة من «الدليل الزراعي للبقوليات الحبية
    الغذائية» (2023). فيزياء المحصول من FAO-56/Maas-Hoffman؛ الأصناف من الدليل."""

    def test_common_bean_crop_card_present_and_valid(self):
        card = load_crop_card("common_bean")
        assert card is not None
        assert validate_crop_card(card)["valid"]
        assert card["crop_family"] == "legume_C3"

    def test_common_bean_is_salt_sensitive(self):
        # الفاصولياء حسّاسة للملوحة (عتبة 1.0) — أقلّ تحمّلاً من القمح (6.0) والشعير.
        from core.crop_cards.loader import load_crop_card as _lc

        bean = _lc("common_bean")["salinity"]["threshold_ece_ds_m"]
        wheat = _lc("wheat")["salinity"]["threshold_ece_ds_m"]
        assert bean == 1.0
        assert bean < wheat
        # انحدار حادّ (Maas-Hoffman): 19% نقص لكل dS/m فوق العتبة.
        assert _lc("common_bean")["salinity"]["slope_pct_per_ds_m"] == 19.0

    def test_common_bean_warm_season_legume_thermal(self):
        t = load_crop_card("common_bean")["thermal"]
        assert t["gdd_base_c"] == 10.0  # بقوليّة دافئة (لا قمح بارد base 0)
        assert t["chilling_hours_required"] == 0
        assert t["flowering_safe_max_c"] == 32.0

    def test_common_bean_low_nitrogen_due_to_fixation(self):
        # بقوليّة مثبّتة للنيتروجين ⇒ احتياج منخفض مقابل القمح (120).
        bean_n = load_crop_card("common_bean")["modifying"]["nitrogen_kg_ha_required"]
        wheat_n = load_crop_card("wheat")["modifying"]["nitrogen_kg_ha_required"]
        assert bean_n < wheat_n

    def test_three_yemeni_varieties_linked_and_valid(self):
        from core.crop_cards.loader import (
            load_variety_card,
            validate_variety_card,
            varieties_of_crop,
        )

        vids = varieties_of_crop("common_bean")
        for v in ("common_bean_yemen_1", "common_bean_liena_24", "common_bean_rajm_1"):
            assert v in vids
            card = load_variety_card(v)
            assert validate_variety_card(card)["valid"]
            assert card["parent_crop_id"] == "common_bean"

    def test_variety_passport_origin_types_match_guide(self):
        from core.crop_cards.loader import load_variety_card

        # يمن-1: مُنتخَب من سلالات محلّية ⇒ landrace.
        assert load_variety_card("common_bean_yemen_1")["passport"]["origin_type"] == "landrace"
        # لينا-24: مُدخَل من CIAT ⇒ introduced.
        assert load_variety_card("common_bean_liena_24")["passport"]["origin_type"] == "introduced"
        # رجم-1: مُستنبَط حديثاً ⇒ improved.
        assert load_variety_card("common_bean_rajm_1")["passport"]["origin_type"] == "improved"

    def test_rajm_1_is_earliest_maturity_class(self):
        from core.crop_cards.loader import load_variety_card

        # رجم-1 أبكر نضجاً (95 يوماً) ⇒ early؛ يمن-1/لينا-24 (~105) ⇒ medium.
        assert load_variety_card("common_bean_rajm_1")["distinctness"]["maturity_class"] == "early"
        assert (
            load_variety_card("common_bean_yemen_1")["distinctness"]["maturity_class"] == "medium"
        )

    def test_liena_24_is_snap_bean_distinct_morphology(self):
        from core.crop_cards.loader import load_variety_card

        v = load_variety_card("common_bean_liena_24")
        assert "موازيك الفاصولية" in " ".join(v["variety_traits"]["disease_resistance_ar"])
        assert v["distinctness"]["plant_height_cm"] == 35  # قصير (نمو قائم)

    def test_variety_cards_stay_region_agnostic_no_yield(self):
        # الصنف محايد الموقع: لا غلّة/معايرة/منطقة كحقول عليا (رغم وفرتها في الدليل).
        import core.crop_cards.loader as ldr

        for v in ("common_bean_yemen_1", "common_bean_liena_24", "common_bean_rajm_1"):
            card = ldr.load_variety_card(v)
            assert "yield" not in card and "calibration" not in card and "region" not in card

    def test_rajm_1_honest_empty_disease_resistance(self):
        # الدليل لم يوثّق تحمّلاً مرضيّاً لرجم-1 ⇒ قائمة فارغة (صدق: لا يُخترَع).
        from core.crop_cards.loader import load_variety_card

        assert (
            load_variety_card("common_bean_rajm_1")["variety_traits"]["disease_resistance_ar"] == []
        )


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


class TestPhenologyGrowthStages:
    """مراحل النمو (phenology) — كتلة اختياريّة محايدة الموقع تُتحقَّق فقط إن وُجدت."""

    def test_growth_stages_returns_ordered_named_stages(self):
        from core.crop_cards.loader import growth_stages

        stages = growth_stages("common_bean")
        assert [s["stage"] for s in stages] == ["initial", "development", "mid", "late"]
        # تسلسل غير متراجع + تطابق مع kc.stage_days التراكميّة (0→110).
        assert stages[0]["day_start"] == 0
        assert stages[-1]["day_end"] == 110
        prev = 0
        for s in stages:
            assert s["day_start"] >= prev - 0 and s["day_start"] < s["day_end"]
            prev = s["day_end"]

    def test_mid_stage_is_peak_kc_flowering(self):
        from core.crop_cards.loader import growth_stages

        mid = next(s for s in growth_stages("common_bean") if s["stage"] == "mid")
        assert mid["kc"] == 1.15  # ذروة الاحتياج المائي
        assert "التزهير" in mid["name_ar"]

    def test_cards_without_phenology_still_valid_and_empty(self):
        # توافق رجعيّ: القمح بلا phenology ⇒ valid + مراحل فارغة (لا يكسر القديم).
        from core.crop_cards.loader import growth_stages, load_crop_card, validate_crop_card

        assert validate_crop_card(load_crop_card("wheat"))["valid"]
        assert growth_stages("wheat") == []
        assert growth_stages("nonexistent") == []

    def test_invalid_phenology_caught_by_validator(self):
        # حارس: مراحل متراجعة/ناقصة تُرفَض (يحمي التوسعة المستقبليّة).
        from core.crop_cards.loader import validate_crop_card

        base = load_crop_card("common_bean")
        bad = dict(base)
        bad["phenology"] = {
            "source": "x",
            "stages": [
                {"stage": "a", "name_ar": "أ", "day_start": 0, "day_end": 30},
                {"stage": "b", "name_ar": "ب", "day_start": 10, "day_end": 40},  # تداخل
            ],
        }
        assert validate_crop_card(bad)["valid"] is False
        worse = dict(base)
        worse["phenology"] = {"stages": [{"stage": "a"}]}  # بلا مصدر + مفاتيح ناقصة
        assert validate_crop_card(worse)["valid"] is False

    def test_variety_phenology_timing_from_guide(self):
        from core.crop_cards.loader import load_variety_card

        # توقيت الصنف محايد الموقع: تزهير/نضج من الدليل، مع مصدر.
        rajm = load_variety_card("common_bean_rajm_1")["phenology"]
        assert rajm["days_to_maturity"] == 95 and rajm["days_to_50pct_flowering"] == 53
        liena = load_variety_card("common_bean_liena_24")["phenology"]
        assert liena["days_to_50pct_green_pods"] == 72  # خاصّ بصنف القرون الخضراء

    def test_variety_phenology_requires_source_and_maturity(self):
        from core.crop_cards.loader import validate_variety_card

        base = load_crop_card  # noqa: F841 (تأكيد توفّر المحصول الأمّ)
        bad = {
            "variety_id": "x",
            "parent_crop_id": "common_bean",
            "name_ar": "x",
            "name_en": "x",
            "passport": {"origin_type": "landrace", "source_ar": "x"},
            "distinctness": {},
            "variety_traits": {},
            "phenology": {"days_to_50pct_flowering": 50},  # بلا مصدر + بلا نضج
        }
        assert validate_variety_card(bad)["valid"] is False
