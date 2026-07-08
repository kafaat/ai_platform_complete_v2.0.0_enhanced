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
        # توافق رجعيّ: بطاقة بلا phenology ⇒ valid + مراحل فارغة (لا يكسر القديم).
        # (cranberry بلا كتلة phenology بعد إضافة الحبوب الأربعة.)
        from core.crop_cards.loader import growth_stages, load_crop_card, validate_crop_card

        assert validate_crop_card(load_crop_card("cranberry"))["valid"]
        assert growth_stages("cranberry") == []
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


class TestCerealPhenology:
    """مراحل النمو (phenology) للحبوب الأساسية الأربعة — مُحاذاة لمراحل FAO-56،
    حدودها اليوميّة هي المجاميع التراكميّة لـ kc.stage_days لكلّ بطاقة. المرحلة
    الوسطى (mid) هي مرحلة الإزهار/السنبلة الأكثر حساسيّة للإجهاد."""

    # (المحصول، إجمالي الدورة، kc.mid) — الحدود مشتقّة من stage_days الفعليّة.
    CEREALS = {
        "wheat": (120, 1.15),
        "barley": (120, 1.15),
        "sorghum": (125, 1.05),
        "millet": (105, 1.00),
    }

    def test_all_cereals_validate_with_phenology(self):
        for cid in self.CEREALS:
            card = load_crop_card(cid)
            assert validate_crop_card(card)["valid"], cid
            assert "phenology" in card
            assert "source" in card["phenology"]
            assert "FAO-56" in card["phenology"]["source"]

    def test_each_cereal_has_four_ordered_stages(self):
        from core.crop_cards.loader import growth_stages

        for cid, (total, _kc_mid) in self.CEREALS.items():
            stages = growth_stages(cid)
            assert len(stages) == 4, cid
            assert [s["stage"] for s in stages] == [
                "initial",
                "development",
                "mid",
                "late",
            ], cid
            # تبدأ من 0 وتنتهي عند الإجمالي الحقيقيّ (مجموع stage_days).
            assert stages[0]["day_start"] == 0, cid
            assert stages[-1]["day_end"] == total, cid

    def test_stage_ranges_match_cumulative_stage_days(self):
        # الحدود اليوميّة = المجاميع التراكميّة لـ kc.stage_days (متّصلة، بلا فجوات).
        from core.crop_cards.loader import growth_stages

        for cid in self.CEREALS:
            card = load_crop_card(cid)
            stage_days = card["kc"]["stage_days"]
            stages = growth_stages(cid)
            cum = 0
            for sd, st in zip(stage_days, stages, strict=True):
                assert st["day_start"] == cum, cid
                cum += sd
                assert st["day_end"] == cum, cid
            assert cum == card["phenology"]["total_cycle_days"], cid

    def test_mid_stage_is_peak_kc_matching_card_mid(self):
        # المرحلة الوسطى = ذروة Kc = kc.mid للبطاقة (تقود تصعيد الإجهاد المائي/الحراري).
        from core.crop_cards.loader import growth_stages

        for cid, (_total, kc_mid) in self.CEREALS.items():
            mid = next(s for s in growth_stages(cid) if s["stage"] == "mid")
            assert mid["kc"] == kc_mid, cid

    def test_stage_kc_endpoints_track_card_kc(self):
        # initial→kc.initial، late→kc.end، والتطوّر يرتقي إلى kc.mid (kc_end).
        from core.crop_cards.loader import growth_stages

        for cid in self.CEREALS:
            card = load_crop_card(cid)
            by_stage = {s["stage"]: s for s in growth_stages(cid)}
            assert by_stage["initial"]["kc"] == card["kc"]["initial"], cid
            assert by_stage["late"]["kc"] == card["kc"]["end"], cid
            assert by_stage["development"]["kc_end"] == card["kc"]["mid"], cid

    def test_wheat_mid_stage_names_heading_flowering(self):
        # المرحلة الوسطى للقمح هي مرحلة السنبلة/الإزهار (الأكثر حساسيّة للإجهاد).
        from core.crop_cards.loader import growth_stages

        mid = next(s for s in growth_stages("wheat") if s["stage"] == "mid")
        assert "إزهار" in mid["name_ar"] or "سنبلة" in mid["name_ar"]

    def test_wheat_explicit_day_ranges(self):
        # توثيق صريح: قمح stage_days [15,25,50,30] ⇒ [0–15,15–40,40–90,90–120].
        from core.crop_cards.loader import growth_stages

        bounds = [(s["day_start"], s["day_end"]) for s in growth_stages("wheat")]
        assert bounds == [(0, 15), (15, 40), (40, 90), (90, 120)]

    def test_cereal_phenology_region_agnostic(self):
        # الكتلة محايدة الموقع: لا غلّة/منطقة/معايرة في phenology.
        for cid in self.CEREALS:
            ph = load_crop_card(cid)["phenology"]
            assert "yield" not in ph
            assert "region" not in ph
            assert "calibration" not in ph


class TestYemenStaplesBatch1:
    """المحاصيل الأساسية اليمنية (الدفعة 1): الذرة الشامية · السمسم · البطاطس · البُنّ.
    فيزياء وفسيولوجيا فقط (FAO-56 Kc/T23 · ECOCROP · أدبيّات الملوحة)؛ محايدة الموقع.
    البُنّ مُعمِّر ⇒ بلا كتلة phenology حوليّة (صدق: لا مراحل مُلفَّقة لمُعمِّر)."""

    STAPLES = ("maize", "sesame", "potato", "coffee")

    def test_all_present_and_valid(self):
        cards = list_crop_cards()
        for cid in self.STAPLES:
            assert cid in cards, cid
            v = validate_crop_card(load_crop_card(cid))
            assert v["valid"], f"{cid}: {v['errors']}"

    def test_families_are_correct(self):
        fam = {cid: load_crop_card(cid)["crop_family"] for cid in self.STAPLES}
        assert fam["maize"] == "cereal_C4"  # حبوب دافئة C4
        assert fam["sesame"] == "oilseed_C3"
        assert fam["potato"] == "tuber_C3"
        assert fam["coffee"] == "tree_C3"  # مُعمِّر

    def test_annual_staples_have_consistent_phenology(self):
        # الحوليّة الثلاثة: 4 مراحل، حدودها = المجاميع التراكميّة لـ kc.stage_days.
        from core.crop_cards.loader import growth_stages

        for cid in ("maize", "sesame", "potato"):
            card = load_crop_card(cid)
            stages = growth_stages(cid)
            assert len(stages) == 4, cid
            cum = 0
            for sd, st in zip(card["kc"]["stage_days"], stages, strict=True):
                assert st["day_start"] == cum, cid
                cum += sd
                assert st["day_end"] == cum, cid
            assert cum == card["phenology"]["total_cycle_days"], cid

    def test_coffee_is_perennial_no_annual_phenology(self):
        # مُعمِّر: بلا كتلة phenology ⇒ growth_stages فارغة، وبلا «نضج» حوليّ.
        from core.crop_cards.loader import growth_stages

        assert growth_stages("coffee") == []
        assert load_crop_card("coffee")["thermal"]["gdd_to_maturity"] == 0

    def test_coffee_prefers_acidic_soil(self):
        # أرابيكا تفضّل تربة حمضيّة (pH أقصى ≤ 6.5) — عكس أغلب محاصيلنا القلويّة.
        assert load_crop_card("coffee")["governing"]["ph"]["max"] <= 6.5

    def test_potato_is_heavy_potassium_feeder(self):
        # البطاطس مُستهلِك بوتاسيوم مرتفع جدّاً (K > N) — جودة الدرنات.
        m = load_crop_card("potato")["modifying"]
        assert m["potassium_kg_ha_required"] > m["nitrogen_kg_ha_required"]

    def test_maize_more_salt_sensitive_than_wheat(self):
        # الذرة الشامية (1.7) أحسّ للملوحة من القمح (6.0) والشعير.
        maize = load_crop_card("maize")["salinity"]["threshold_ece_ds_m"]
        wheat = load_crop_card("wheat")["salinity"]["threshold_ece_ds_m"]
        assert maize < wheat

    def test_sesame_is_hot_season_high_base_temp(self):
        # السمسم محصول حارّ — حرارة أساس مرتفعة (≥ 15°م، أعلى من القمح البارد base 0).
        t = load_crop_card("sesame")["thermal"]
        assert t["gdd_base_c"] >= 15.0
        assert t["chilling_hours_required"] == 0

    def test_germination_not_stricter_violated(self):
        # حيث تُذكر عتبة الإنبات، يجب أن تكون ≤ العتبة العامّة (مرحلة حسّاسة).
        for cid in self.STAPLES:
            sal = load_crop_card(cid)["salinity"]
            if "germination_ece_max" in sal:
                assert sal["germination_ece_max"] <= sal["threshold_ece_ds_m"], cid

    def test_staples_region_agnostic_no_calibration(self):
        for cid in self.STAPLES:
            card = load_crop_card(cid)
            for forbidden in ("yield", "calibration", "zone_factor", "region"):
                assert forbidden not in card, (cid, forbidden)

    def test_all_staples_cite_sources(self):
        # صدق: كل كتلة فيزيائيّة تذكر مصدرها (لا أرقام مُختلَقة).
        for cid in self.STAPLES:
            card = load_crop_card(cid)
            assert "source" in card["kc"]
            assert "source" in card["salinity"]
            assert "source" in card["thermal"]


class TestYemenCropsBatch2:
    """محاصيل يمنيّة إضافيّة (الدفعة 2): خضراوات/ألياف/علف/فاكهة/قرعيّات/بقوليّات.
    FAO-56 Kc/T23 معياريّة حيث تتوفّر؛ القيم خارج T23 مُعلَّمة «indicative» بصدق.
    المُعمِّرات (نخيل/عنب/برسيم) بلا كتلة phenology حوليّة."""

    ANNUALS = ("tomato", "onion", "cotton", "cowpea", "chickpea", "sunflower", "watermelon")
    PERENNIALS = ("date_palm", "grape", "alfalfa")

    def test_all_present_and_valid(self):
        cards = list_crop_cards()
        for cid in self.ANNUALS + self.PERENNIALS:
            assert cid in cards, cid
            v = validate_crop_card(load_crop_card(cid))
            assert v["valid"], f"{cid}: {v['errors']}"

    def test_annual_phenology_consistent_with_stage_days(self):
        from core.crop_cards.loader import growth_stages

        for cid in self.ANNUALS:
            card = load_crop_card(cid)
            stages = growth_stages(cid)
            assert len(stages) == 4, cid
            cum = 0
            for sd, st in zip(card["kc"]["stage_days"], stages, strict=True):
                assert st["day_start"] == cum, cid
                cum += sd
                assert st["day_end"] == cum, cid
            assert cum == card["phenology"]["total_cycle_days"], cid

    def test_perennials_have_no_annual_phenology(self):
        from core.crop_cards.loader import growth_stages

        for cid in self.PERENNIALS:
            assert growth_stages(cid) == [], cid
            # مُعمِّر ⇒ لا «نضج» حوليّ.
            assert load_crop_card(cid)["thermal"]["gdd_to_maturity"] == 0, cid

    def test_date_palm_is_most_salt_tolerant_added(self):
        # النخيل من أكثر المحاصيل تحمّلاً للملوحة (عتبة 4.0 > حسّاسة كالبصل 1.2).
        palm = load_crop_card("date_palm")["salinity"]["threshold_ece_ds_m"]
        onion = load_crop_card("onion")["salinity"]["threshold_ece_ds_m"]
        assert palm > onion

    def test_cotton_salt_tolerant_high_threshold(self):
        # القطن متحمّل للملوحة (عتبة ~7.7 Maas-Hoffman) — من الأعلى في مجموعتنا.
        assert load_crop_card("cotton")["salinity"]["threshold_ece_ds_m"] >= 7.0

    def test_onion_is_salt_sensitive(self):
        # البصل من أحسّ الخضراوات للملوحة (عتبة 1.2).
        assert load_crop_card("onion")["salinity"]["threshold_ece_ds_m"] <= 1.5

    def test_legumes_fix_nitrogen_low_n_requirement(self):
        # البقوليّات (لوبيا/حمّص/برسيم) تثبّت النيتروجين ⇒ احتياج آزوتيّ منخفض.
        wheat_n = load_crop_card("wheat")["modifying"]["nitrogen_kg_ha_required"]
        for cid in ("cowpea", "chickpea", "alfalfa"):
            assert load_crop_card(cid)["modifying"]["nitrogen_kg_ha_required"] < wheat_n, cid

    def test_grape_needs_some_winter_chill(self):
        # العنب مُتساقط يحتاج بردَ سُبات (ساعات برودة > 0) — عكس المحاصيل الحوليّة.
        assert load_crop_card("grape")["thermal"]["chilling_hours_required"] > 0

    def test_indicative_salinity_flagged_honestly(self):
        # القيم خارج FAO-56 T23 يجب أن تُعلَّم بصدق (لا ادّعاء معياريّة Maas-Hoffman).
        for cid in ("chickpea", "sunflower", "watermelon"):
            src = load_crop_card(cid)["salinity"]["source"].lower()
            assert "not in fao-56 t23" in src or "indicative" in src, cid

    def test_all_cite_sources_region_agnostic(self):
        for cid in self.ANNUALS + self.PERENNIALS:
            card = load_crop_card(cid)
            assert "source" in card["kc"] and "source" in card["salinity"]
            for forbidden in ("yield", "calibration", "zone_factor", "region"):
                assert forbidden not in card, (cid, forbidden)


class TestYemenVegetablesBatch3a:
    """خضراوات يمنيّة (الدفعة 3أ): خيار · فلفل · باذنجان · بامية · ثوم · شمّام.
    حوليّة بـ4 مراحل FAO-56؛ القيم خارج جداول FAO-56 مُعلَّمة بصدق."""

    VEG = ("cucumber", "pepper", "eggplant", "okra", "garlic", "melon")

    def test_all_present_valid_with_phenology(self):
        from core.crop_cards.loader import growth_stages

        cards = list_crop_cards()
        for cid in self.VEG:
            assert cid in cards, cid
            card = load_crop_card(cid)
            assert validate_crop_card(card)["valid"], cid
            stages = growth_stages(cid)
            assert len(stages) == 4, cid
            cum = 0
            for sd, st in zip(card["kc"]["stage_days"], stages, strict=True):
                assert st["day_start"] == cum, cid
                cum += sd
                assert st["day_end"] == cum, cid
            assert cum == card["phenology"]["total_cycle_days"], cid

    def test_pepper_flower_drop_heat_threshold(self):
        # الفلفل: تساقط الأزهار فوق ~32°م (حسّاسيّة حراريّة موثّقة).
        assert load_crop_card("pepper")["thermal"]["flowering_safe_max_c"] <= 32.0

    def test_okra_is_hot_season_high_base_temp(self):
        # البامية محصول حارّ — حرارة أساس مرتفعة (≥ 15°م).
        assert load_crop_card("okra")["thermal"]["gdd_base_c"] >= 15.0

    def test_garlic_salt_sensitive_allium(self):
        # الثوم من الثوميّات الحسّاسة للملوحة (عتبة ≤ 1.5).
        assert load_crop_card("garlic")["salinity"]["threshold_ece_ds_m"] <= 1.5

    def test_region_agnostic_and_sourced(self):
        for cid in self.VEG:
            card = load_crop_card(cid)
            assert "source" in card["kc"] and "source" in card["salinity"]
            for forbidden in ("yield", "calibration", "zone_factor", "region"):
                assert forbidden not in card, (cid, forbidden)


class TestYemenFruitsAndQatBatch3b:
    """فواكه مُعمِّرة + القات (الدفعة 3ب): موز · مانجو · بابايا · حمضيات · رمّان ·
    تين · جوافة · قات. كلّها مُعمِّرة ⇒ بلا كتلة phenology حوليّة (صدق: لا مراحل
    مُلفَّقة لمُعمِّر). أغلب القيم «indicative» (خارج FAO-56/ECOCROP المعياريّ)."""

    PERENNIALS = ("banana", "mango", "papaya", "citrus", "pomegranate", "fig", "guava", "qat")

    def test_all_present_valid_perennial(self):
        from core.crop_cards.loader import growth_stages

        cards = list_crop_cards()
        for cid in self.PERENNIALS:
            assert cid in cards, cid
            card = load_crop_card(cid)
            assert validate_crop_card(card)["valid"], cid
            # مُعمِّر ⇒ لا كتلة phenology حوليّة، ولا «نضج» حوليّ.
            assert growth_stages(cid) == [], cid
            assert card["thermal"]["gdd_to_maturity"] == 0, cid

    def test_citrus_uses_standard_maas_hoffman(self):
        # الحمضيات (البرتقال) في FAO-56 T23 فعليّاً — عتبة 1.7 حسّاسة.
        sal = load_crop_card("citrus")["salinity"]
        assert sal["threshold_ece_ds_m"] == 1.7
        assert "FAO-56" in sal["source"] or "Maas" in sal["source"]

    def test_indicative_values_flagged_honestly(self):
        # ما لا مصدر معياريّ له (موز/مانجو/بابايا/رمّان/تين/جوافة/قات) يُعلَّم بصدق.
        for cid in ("banana", "mango", "papaya", "pomegranate", "fig", "guava", "qat"):
            src = load_crop_card(cid)["salinity"]["source"].lower()
            assert "indicative" in src or "no standard" in src, cid

    def test_qat_is_neutral_indicative_and_honest_empty_pests(self):
        # القات: إدراج واقعيّ لا ترويجيّ — كلّ قيمه «indicative»، وآفاته قائمة فارغة
        # بصدق (غير موثّقة معياريّاً) لا مُختلَقة.
        qat = load_crop_card("qat")
        assert qat["pest_susceptibility"]["pests"] == []
        assert "indicative" in qat["kc"]["source"].lower()
        assert "no fao-56" in qat["kc"]["source"].lower()

    def test_deciduous_fruits_need_winter_chill(self):
        # الرمّان والتين مُتساقطان ⇒ يحتاجان بردَ سُبات (ساعات برودة > 0).
        for cid in ("pomegranate", "fig"):
            assert load_crop_card(cid)["thermal"]["chilling_hours_required"] > 0, cid

    def test_banana_heavy_potassium_feeder(self):
        # الموز مُستهلِك بوتاسيوم مرتفع جدّاً (K > N).
        m = load_crop_card("banana")["modifying"]
        assert m["potassium_kg_ha_required"] > m["nitrogen_kg_ha_required"]

    def test_all_region_agnostic_and_sourced(self):
        for cid in self.PERENNIALS:
            card = load_crop_card(cid)
            assert "source" in card["kc"] and "source" in card["salinity"]
            for forbidden in ("yield", "calibration", "zone_factor", "region"):
                assert forbidden not in card, (cid, forbidden)


class TestYemenVarietyCardsResearched:
    """أصناف يمنيّة موثّقة من بحث (2026-07-08): حبوب + بُنّ + عنب + نخيل + قات + مانجو.
    صدق: فقط الأصناف المُسمّاة بمصدر تُدرَج؛ الأسماء غير الموثّقة لم تُختلَق. بُنّ: الأسماء
    العاميّة موثّقة لكن DNA أثبت أنّها ليست أصنافاً جينيّة متمايزة (MDPI 2022)."""

    NEW = (
        "wheat_aziz",
        "barley_bakkur",
        "sorghum_ghurbah",
        "maize_thulathi",
        "maize_rubai",
        "maize_khumasi",
        "coffee_yemenia",
        "coffee_udaini",
        "coffee_tuffahi",
        "coffee_burai",
        "coffee_dawairi",
        "grape_razqi",
        "grape_aswad",
        "grape_asmi",
        "date_palm_hamra",
        "date_palm_mijraf",
        "date_palm_sokotri",
        "date_palm_serfaneh",
        "qat_shami",
        "qat_baladi",
        "mango_taimoor",
        "mango_badami",
    )

    def test_all_present_valid_linked_to_real_parent(self):
        from core.crop_cards.loader import (
            list_variety_cards,
            load_crop_card,
            load_variety_card,
            validate_variety_card,
        )

        cards = list_variety_cards()
        for vid in self.NEW:
            assert vid in cards, vid
            v = load_variety_card(vid)
            assert validate_variety_card(v)["valid"], f"{vid}: {validate_variety_card(v)['errors']}"
            # كلّ صنف مربوط بمحصول أمّ موجود فعلاً (لا صنف يتيم).
            assert load_crop_card(v["parent_crop_id"]) is not None, vid

    def test_every_variety_cites_a_source(self):
        # صدق: لا صنف بلا مصدر (passport.source_ar).
        from core.crop_cards.loader import load_variety_card

        for vid in self.NEW:
            assert load_variety_card(vid)["passport"]["source_ar"].strip(), vid

    def test_varieties_region_agnostic_no_yield_calibration(self):
        from core.crop_cards.loader import load_variety_card

        for vid in self.NEW:
            v = load_variety_card(vid)
            for forbidden in ("yield", "calibration", "zone_factor", "region"):
                assert forbidden not in v, (vid, forbidden)

    def test_coffee_vernacular_carries_genetic_caveat(self):
        # صدق حاسم: بطاقات البُنّ العاميّة يجب أن تُصرّح بأنّها ليست أصنافاً جينيّة متمايزة.
        from core.crop_cards.loader import load_variety_card

        for vid in ("coffee_udaini", "coffee_tuffahi", "coffee_burai", "coffee_dawairi"):
            text = " ".join(str(v) for v in load_variety_card(vid).values())
            assert "عاميّ" in text or "MDPI" in text, vid
        # المجموعة الجينيّة المُتحقَّقة الوحيدة:
        yem = load_variety_card("coffee_yemenia")
        assert "Montagnon" in yem["passport"]["source_ar"]

    def test_maize_folk_classes_labeled_not_registered(self):
        # فئات الذرة الشعبيّة يجب أن تُصرَّح كفئة نضج شعبيّة لا صنفاً مُسجَّلاً.
        from core.crop_cards.loader import load_variety_card

        classes = {
            "maize_thulathi": "early",
            "maize_rubai": "medium",
            "maize_khumasi": "late",
        }
        for vid, mat in classes.items():
            v = load_variety_card(vid)
            assert v["distinctness"]["maturity_class"] == mat, vid
            assert "شعبيّة" in v["passport"]["collection_note_ar"], vid

    def test_qat_varieties_neutral_not_promotional(self):
        # القات: إدراج واقعيّ — البطاقة تُصرّح «لا ترويجيّ» وقيمها indicative موروثة.
        from core.crop_cards.loader import load_variety_card

        for vid in ("qat_shami", "qat_baladi"):
            note = load_variety_card(vid)["passport"]["collection_note_ar"]
            assert "ترويجيّ" in note, vid
