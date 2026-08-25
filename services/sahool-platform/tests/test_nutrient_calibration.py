"""عقد المعايرة الغذائيّة الإقليميّة + حلّ الطبقتين — نفس نمط RZ-VARIETY.

يقيس ثلاث خواصّ: (١) المدقّق فاشل-مغلق على بنية المعايرة والمدخلة غير
المعايَرة خاملة بالعقد (٢) الحلّ بطبقتين: صنف المنطقة > عامّ المنطقة > بطاقة
فقط، ومدخلات uncalibrated لا تُطبَّق أبداً (٣) ``locally_calibrated`` لا تكذب.
"""

from __future__ import annotations

import pytest
from core.crop_cards.nutrient_resolution import resolve_stage_nutrient_demand
from core.districts.loader import list_districts, load_district, validate_district

pytestmark = pytest.mark.unit


def _district(entries=None, **over):
    card = {
        "district_id": "test_zone",
        "name_ar": "منطقة اختبار",
        "agro_ecological_zone_ar": "اختبارية",
        "altitude_range_m": [0, 100],
        "pest_windows": [],
    }
    if entries is not None:
        card["nutrient_calibration"] = entries
    card.update(over)
    return card


def _entry(
    crop="wheat", variety="", status="validated", n=1.1, p=0.9, k=1.0, source="مصدر إرشاد مصدَّق"
):
    return {
        "crop": crop,
        "variety": variety,
        "status": status,
        "n_factor": n,
        "p_factor": p,
        "k_factor": k,
        "source": source,
    }


# ───────────────────── المدقّق: البنية والخمول ─────────────────────


def test_valid_calibration_block_passes():
    assert validate_district(_district([_entry()]))["valid"] is True


def test_uncalibrated_entry_must_be_inert():
    """أرقام غير معايَرة لا تعيش في مدخلة uncalibrated — تُرفَض بنيويّاً."""
    bad = _entry(status="uncalibrated", n=1.2)
    verdict = validate_district(_district([bad]))
    assert verdict["valid"] is False
    assert any("خاملة بالعقد" in e for e in verdict["errors"])


def test_uncalibrated_inert_entry_passes():
    ok = _entry(status="uncalibrated", n=1.0, p=1.0, k=1.0)
    assert validate_district(_district([ok]))["valid"] is True


def test_missing_source_is_rejected():
    verdict = validate_district(_district([_entry(source="  ")]))
    assert verdict["valid"] is False


def test_factor_outside_physical_range_is_rejected():
    for bad in (0.0, -0.5, 5.1, float("nan"), True):
        verdict = validate_district(_district([_entry(n=bad)]))
        assert verdict["valid"] is False, f"قبل معاملاً غير صالح: {bad!r}"


def test_unknown_status_is_rejected():
    verdict = validate_district(_district([_entry(status="draft")]))
    assert verdict["valid"] is False


def test_duplicate_crop_variety_entry_is_rejected():
    """صفّ المعايرة إعلان الحالة الوحيد لزوجه — نفس درس تفرّد صفوف السجلّ."""
    verdict = validate_district(_district([_entry(), _entry()]))
    assert verdict["valid"] is False
    assert any("مكرَّرة" in e for e in verdict["errors"])


def test_calibration_block_is_optional():
    assert validate_district(_district())["valid"] is True


# ───────────────────── الحلّ بطبقتين (على منطقة وهمية) ─────────────────────


@pytest.fixture
def fake_district(monkeypatch):
    def _install(entries):
        import core.crop_cards.nutrient_resolution as nr

        card = _district(entries)
        monkeypatch.setattr(nr, "load_district", lambda _id: card)
        return card

    return _install


def test_variety_tier_wins_over_generic(fake_district):
    fake_district(
        [
            _entry(variety="imam", n=1.2, p=1.2, k=1.2, source="معايرة صنف"),
            _entry(variety="", n=0.8, p=0.8, k=0.8, source="معايرة عامّة"),
        ]
    )
    out = resolve_stage_nutrient_demand("wheat", district_id="x", variety="imam")
    assert out["status"] == "resolved"
    assert out["tier"] == "district_variety"
    assert out["element_factors"]["n_factor"] == 1.2
    assert out["locally_calibrated"] is True


def test_unknown_variety_falls_back_to_generic_tier(fake_district):
    fake_district([_entry(variety="", n=0.8, p=0.8, k=0.8)])
    out = resolve_stage_nutrient_demand("wheat", district_id="x", variety="unknown")
    assert out["tier"] == "district_generic"
    assert out["element_factors"]["n_factor"] == 0.8


def test_uncalibrated_entry_is_never_applied(fake_district):
    """وجود مدخلة uncalibrated لا يرفع معاملاً ولا يدّعي معايرة — يُعلَن فقط."""
    fake_district([_entry(status="uncalibrated", n=1.0, p=1.0, k=1.0)])
    out = resolve_stage_nutrient_demand("wheat", district_id="x")
    assert out["tier"] == "card_baseline"
    assert out["calibration_status"] == "uncalibrated"
    assert out["locally_calibrated"] is False
    assert out["element_factors"] == {"n_factor": 1.0, "p_factor": 1.0, "k_factor": 1.0}


def test_no_entries_for_crop_reads_absent(fake_district):
    fake_district([_entry(crop="sorghum")])
    out = resolve_stage_nutrient_demand("wheat", district_id="x")
    assert out["calibration_status"] == "absent"
    assert out["locally_calibrated"] is False


def test_card_without_curves_is_blocked():
    out = resolve_stage_nutrient_demand("barley")
    assert out == {
        "status": "blocked",
        "reason": "crop_card_nutrient_curves_missing",
        "crop": "barley",
    }


def test_unknown_district_is_blocked_not_silently_baseline():
    out = resolve_stage_nutrient_demand("wheat", district_id="no_such_zone")
    assert out["status"] == "blocked"
    assert out["reason"] == "district_unknown"


def test_invalid_district_card_is_blocked(fake_district):
    fake_district([_entry(status="draft")])
    out = resolve_stage_nutrient_demand("wheat", district_id="x")
    assert out["status"] == "blocked"
    assert out["reason"] == "district_card_invalid"


def test_factors_never_touch_stage_fractions(fake_district):
    """المعاملات موسميّة للمستهلك المطلق — الكسور توزيع زمنيّ يبقى جمعه 1.00."""
    fake_district([_entry(variety="", n=2.0, p=2.0, k=2.0)])
    out = resolve_stage_nutrient_demand("wheat", district_id="x")
    for element in ("n_fraction", "p_fraction", "k_fraction"):
        assert abs(sum(st[element] for st in out["stages"]) - 1.0) < 1e-9


# ───────────────────── الشجرة الحيّة: البطاقات والمناطق الفعليّة ─────────────────────


def test_wheat_and_sorghum_curves_resolve_from_real_cards():
    for crop in ("wheat", "sorghum"):
        out = resolve_stage_nutrient_demand(crop)
        assert out["status"] == "resolved", out
        assert len(out["stages"]) == 4
        assert out["locally_calibrated"] is False
        assert out["sources"], "المرجع الأوّليّ يجب أن يُحمَل في الناتج"


def test_all_real_districts_validate_including_calibration_blocks():
    for did in list_districts():
        verdict = validate_district(load_district(did))
        assert verdict["valid"] is True, (did, verdict["errors"])


def test_real_placeholder_entries_stay_inert_end_to_end():
    out = resolve_stage_nutrient_demand("wheat", district_id="central_highlands")
    assert out["status"] == "resolved"
    assert out["calibration_status"] == "uncalibrated"
    assert out["locally_calibrated"] is False
    out2 = resolve_stage_nutrient_demand("sorghum", district_id="tihama_coastal")
    assert out2["calibration_status"] == "uncalibrated"
    assert out2["locally_calibrated"] is False
