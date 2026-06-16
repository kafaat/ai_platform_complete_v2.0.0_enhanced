"""tests/test_field_completeness.py — اختبارات منطق صرف لدرجة اكتمال بيانات الحقل.

حتميّة بالكامل (لا DB، لا شبكة) — تختبر النواة النقيّة
``core.field_completeness.score_field_completeness`` فقط. تغطّي: حقل كامل ⇒ درجة
عالية/مستوى rich/لا نواقص؛ حقل شحيح (هندسة فقط) ⇒ درجة منخفضة/sparse + نواقص
حاكمة مع إرشاد «كيف»؛ رتابة الدرجة (إضافة بُعد لا تُنقصها)؛ وضوح note_ar (حضور
بيانات لا صحّة محصول)؛ مدخل فارغ/فوضى ⇒ درجة منخفضة/صفر بصدق بلا استثناء.
"""

import pytest
from core.field_completeness import _DIMENSIONS, score_field_completeness

pytestmark = pytest.mark.unit

# كلّ مفاتيح الأبعاد (مصدر واحد للحقيقة من النواة) — لبناء حقل كامل دون نسخ يدويّ.
_ALL_KEYS = [d[0] for d in _DIMENSIONS]


def _full_signals() -> dict:
    return {k: True for k in _ALL_KEYS}


class TestFieldCompleteness:
    def test_full_field_is_rich_no_missing(self):
        r = score_field_completeness(_full_signals())
        assert r["score_pct"] == 100
        assert r["level"] == "rich"
        assert r["missing"] == []
        assert r["improvements_ar"] == []
        assert set(r["present"]) == set(_ALL_KEYS)

    def test_sparse_field_only_geometry(self):
        r = score_field_completeness({"has_geometry": True})
        assert r["level"] == "sparse"
        assert r["score_pct"] < 45  # تحت حدّ moderate
        # نواقص حاكمة/إثرائيّة موجودة
        assert "has_soil_lab" in r["missing"]
        assert "has_ndvi" in r["missing"]
        assert "has_active_season" in r["missing"]
        # كلّ ناقص يحمل إرشاد «كيف تُضيفه» غير فارغ
        missing_dims = {imp["dimension"] for imp in r["improvements_ar"]}
        assert {"has_soil_lab", "has_ndvi", "has_active_season"} <= missing_dims
        for imp in r["improvements_ar"]:
            assert imp["how_ar"].strip()
            assert imp["why_ar"].strip()

    def test_improvements_sorted_by_weight_desc(self):
        # الأهمّ أوّلاً: أعلى وزن في رأس قائمة التحسينات
        r = score_field_completeness({})
        weights = [imp["weight"] for imp in r["improvements_ar"]]
        assert weights == sorted(weights, reverse=True)

    def test_score_monotonic_adding_dimension_never_decreases(self):
        base = {"has_geometry": True}
        prev = score_field_completeness(base)["score_pct"]
        acc = dict(base)
        for key in _ALL_KEYS:
            acc[key] = True
            cur = score_field_completeness(acc)["score_pct"]
            assert cur >= prev  # رتابة: لا انخفاض عند إضافة بُعد حاضر
            prev = cur
        assert prev == 100

    def test_levels_cross_cutoffs(self):
        # حقل أساسيّ + موسم (هندسة+إحداثيّات+موسم نشط) يتجاوز حدّ moderate
        moderate = score_field_completeness(
            {"has_geometry": True, "has_coords": True, "has_active_season": True}
        )
        assert moderate["level"] == "moderate"
        assert 45 <= moderate["score_pct"] < 80
        # إضافة تحليل التربة الحاكم يرفعه إلى rich
        rich = score_field_completeness(
            {
                "has_geometry": True,
                "has_coords": True,
                "has_active_season": True,
                "has_soil_lab": True,
                "has_sowing_date": True,
            }
        )
        assert rich["level"] == "rich"

    def test_note_clarifies_data_presence_not_crop_health(self):
        r = score_field_completeness(_full_signals())
        note = r["note_ar"]
        assert "حضور" in note  # يقيس حضور البيانات
        assert "صحّة المحصول" in note  # لا صحّة المحصول

    def test_empty_signals_zero_score_no_exception(self):
        r = score_field_completeness({})
        assert r["score_pct"] == 0
        assert r["level"] == "sparse"
        assert r["present"] == []
        assert set(r["missing"]) == set(_ALL_KEYS)
        assert r["note_ar"]

    def test_garbage_signals_honest_low_score_no_exception(self):
        # قيم falsy/فوضى لا تُحسَب حاضرة، ومفاتيح غريبة تُتجاهَل — بلا استثناء.
        r = score_field_completeness(
            {
                "has_geometry": None,
                "has_coords": 0,
                "has_soil_lab": "",
                "has_ndvi": [],
                "bogus_key": True,
                "another": "نص لا يعني بُعداً",
            }
        )
        assert r["score_pct"] == 0
        assert r["level"] == "sparse"
        assert r["present"] == []

    def test_non_dict_input_is_handled_safely(self):
        # مدخل ليس قاموساً (None) ⇒ كلّ الأبعاد غائبة، صفر، بلا استثناء.
        r = score_field_completeness(None)
        assert r["score_pct"] == 0
        assert r["level"] == "sparse"

    def test_truthy_values_count_as_present(self):
        # قيم truthy غير True (رقم/نصّ/قاموس) تُعدّ حضوراً
        r = score_field_completeness(
            {"has_geometry": {"type": "Polygon"}, "has_coords": 1, "has_soil_lab": "yes"}
        )
        assert "has_geometry" in r["present"]
        assert "has_coords" in r["present"]
        assert "has_soil_lab" in r["present"]
        assert r["score_pct"] > 0
