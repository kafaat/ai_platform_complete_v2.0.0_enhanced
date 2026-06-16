"""اختبارات طبقة المعرفة الإقليميّة (districts) — أجزاء صرفة، بلا خدمات.

تغطّي: مطابقة كلّ المناطق للقالب، وصدق active_pests (يُرجع الآفات المتوقّعة
لشهر مختار وقائمة فارغة لشهر خارج النافذة / منطقة مجهولة)، ورفض المتحقّق
لنافذة بشهر خطر خاطئ (13) أو بلا مصدر، وأنّ list_districts يُرجع المعرّفات الثلاثة.
"""

import pytest
from core.districts.loader import (
    active_pests,
    list_districts,
    load_district,
    validate_district,
)

pytestmark = pytest.mark.unit

DISTRICT_IDS = ("central_highlands", "tihama_coastal", "eastern_plateau")


class TestDistricts:
    def test_list_districts_returns_the_three_ids(self):
        assert sorted(list_districts()) == sorted(DISTRICT_IDS)

    def test_all_districts_validate(self):
        for did in list_districts():
            v = validate_district(load_district(did))
            assert v["valid"], f"{did}: {v['errors']}"
            assert v["district_id"] == did

    def test_every_window_cites_a_source(self):
        # صدق: لا نافذة خطر بلا مصدر معرفيّ.
        for did in list_districts():
            for win in load_district(did)["pest_windows"]:
                assert win.get("source"), f"{did}: نافذة بلا مصدر"

    def test_risk_months_within_range(self):
        for did in list_districts():
            for win in load_district(did)["pest_windows"]:
                for m in win["risk_months"]:
                    assert 1 <= m <= 12

    def test_missing_district_returns_none(self):
        assert load_district("nonexistent_district") is None
        # حماية من path traversal.
        assert load_district("../crop_cards/wheat") is None

    def test_active_pests_returns_expected_for_chosen_month(self):
        # المرتفعات الوسطى في يناير (1): البقعة الشوكولاتيّة + المنّ نشطان.
        active = active_pests("central_highlands", 1)
        pests = {w["pest"] for w in active}
        assert "faba_bean_chocolate_spot" in pests
        assert "aphids" in pests
        # دودة الحشد (صيفيّة) ليست نشطة في يناير.
        assert "fall_armyworm" not in pests

    def test_active_pests_summer_window(self):
        # دودة الحشد الخريفيّة نشطة في يوليو (7) بالمرتفعات الوسطى.
        active = active_pests("central_highlands", 7)
        assert "fall_armyworm" in {w["pest"] for w in active}

    def test_active_pests_off_month_is_empty(self):
        # المرتفعات الوسطى في أكتوبر (10): لا نافذة تنطبق (بين الموسمين).
        assert active_pests("central_highlands", 10) == []

    def test_active_pests_unknown_district_is_empty(self):
        # صدق بلا اختلاق: منطقة مجهولة ⇒ قائمة فارغة.
        assert active_pests("nonexistent_district", 6) == []

    def test_active_pests_out_of_range_month_is_empty(self):
        assert active_pests("central_highlands", 0) == []
        assert active_pests("central_highlands", 13) == []

    def test_validator_rejects_bad_risk_month(self):
        bad = {
            "district_id": "x",
            "name_ar": "س",
            "agro_ecological_zone_ar": "منطقة",
            "altitude_range_m": [0, 100],
            "pest_windows": [
                {
                    "pest": "aphids",
                    "pest_ar": "المنّ",
                    "crops": ["wheat"],
                    "risk_months": [1, 13],  # 13 خارج النطاق
                    "severity": "low",
                    "scouting_cue_ar": "x",
                    "source": "x",
                }
            ],
        }
        assert validate_district(bad)["valid"] is False

    def test_validator_rejects_missing_source(self):
        bad = {
            "district_id": "x",
            "name_ar": "س",
            "agro_ecological_zone_ar": "منطقة",
            "altitude_range_m": [0, 100],
            "pest_windows": [
                {
                    "pest": "aphids",
                    "pest_ar": "المنّ",
                    "crops": ["wheat"],
                    "risk_months": [1, 2],
                    "severity": "low",
                    "scouting_cue_ar": "x",
                    # source مفقود
                }
            ],
        }
        assert validate_district(bad)["valid"] is False

    def test_validator_rejects_bad_severity(self):
        bad = {
            "district_id": "x",
            "name_ar": "س",
            "agro_ecological_zone_ar": "منطقة",
            "altitude_range_m": [0, 100],
            "pest_windows": [
                {
                    "pest": "aphids",
                    "pest_ar": "المنّ",
                    "crops": ["wheat"],
                    "risk_months": [1],
                    "severity": "catastrophic",  # غير صالحة
                    "scouting_cue_ar": "x",
                    "source": "x",
                }
            ],
        }
        assert validate_district(bad)["valid"] is False

    def test_validator_rejects_missing_top_keys(self):
        assert validate_district({})["valid"] is False
        assert validate_district(None)["valid"] is False
