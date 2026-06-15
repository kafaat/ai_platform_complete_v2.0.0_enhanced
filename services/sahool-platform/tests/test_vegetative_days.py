"""اختبارات حلّ أيّام النموّ الخضريّ (vegetative_growing_days).

يتحقّق من الطبقات الثلاث: تجاوز القاموس الموثوق ⇐ اشتقاق البطاقة
(مجموع المراحل الثلاث الأولى) ⇐ None. ويؤكّد أنّ القيم الحاليّة محفوظة حرفيّاً.
"""

from api.yield_heuristics import CROP_TYPICAL_GROWING_DAYS, vegetative_growing_days
from core.crop_cards.loader import load_crop_card


class TestVegetativeGrowingDays:
    def test_dict_override_wheat(self):
        # الطبقة ١: قاموس التجاوز يُرجع القيمة الموثوقة كما هي
        assert vegetative_growing_days("wheat") == 90

    def test_all_dict_values_byte_identical(self):
        # كلّ قيمة في القاموس تُحلّ مطابقةً تماماً (حفظ السلوك الصارم)
        for crop, days in CROP_TYPICAL_GROWING_DAYS.items():
            assert vegetative_growing_days(crop) == days

    def test_wheat_card_sum_first_three_confirms_metric(self):
        # تأكيد المقياس: مجموع المراحل الثلاث الأولى لبطاقة القمح = ٩٠
        card = load_crop_card("wheat")
        assert sum(card["kc"]["stage_days"][:3]) == 90

    def test_carded_crop_not_in_dict_derives_from_card(self):
        # الطبقة ٢: محصول له بطاقة وغير موجود في القاموس يُشتقّ من المجموع
        assert "millet" not in CROP_TYPICAL_GROWING_DAYS
        card = load_crop_card("millet")
        expected = sum(card["kc"]["stage_days"][:3])  # 15+25+40 = 80
        assert vegetative_growing_days("millet") == expected == 80

    def test_carded_cranberry_derives_from_card(self):
        # طبقة البطاقة لمحصول آخر غير مُدرَج (cranberry → 30+40+60 = 130)
        assert "cranberry" not in CROP_TYPICAL_GROWING_DAYS
        card = load_crop_card("cranberry")
        expected = sum(card["kc"]["stage_days"][:3])
        assert vegetative_growing_days("cranberry") == expected == 130

    def test_unknown_crop_returns_none(self):
        # الطبقة ٣: لا بطاقة ولا تجاوز ⇐ None
        assert vegetative_growing_days("__nope__") is None
