"""اختبارات سجلّ جودة البيانات (core.data_quality) — منطق صرف offline.

يغطّي: إطلاق مخالفة المدى الفيزيائيّ، عدم إطلاقها على قيمة صالحة، تجاوز
الحقل الغائب (graceful)، عدم الرمي على قيمة غير رقميّة، واستبطان القواعد
(غير فارغ، معرّفات فريدة). لا حاجة لقاعدة أو شبكة — كلّه نقيّ.
"""

from core.data_quality import (
    QualityRule,
    evaluate_record,
    list_rules,
    rules_for,
)


class TestRangeViolation:
    def test_ndvi_below_range_flags(self):
        """(أ) NDVI = -0.5 (خارج [-1, 1]؟ لا — لكن نختبر قيمة خارج المدى)."""
        # قيمة خارج المدى الفيزيائيّ تُطلِق المخالفة.
        out = evaluate_record({"ndvi": -1.5})
        assert any(v["rule_id"] == "ndvi_physical_range" for v in out)

    def test_ndvi_negative_in_range_no_violation(self):
        """NDVI = -0.5 ضمن [-1, 1] فيزيائيّاً ⇒ لا مخالفة (قيمة صالحة)."""
        assert evaluate_record({"ndvi": -0.5}) == []

    def test_ndvi_valid_no_violation(self):
        """(ب) NDVI = 0.6 قيمة صالحة ⇒ لا مخالفة."""
        assert evaluate_record({"ndvi": 0.6}) == []

    def test_ndvi_above_range_flags(self):
        out = evaluate_record({"ndvi": 1.2})
        assert any(v["rule_id"] == "ndvi_physical_range" for v in out)


class TestGraceful:
    def test_absent_field_no_violation(self):
        """(ج) حقل غائب ⇒ لا مخالفة (لا تلفيق قراءة غير متوفّرة)."""
        assert evaluate_record({"unrelated": 5}) == []
        assert evaluate_record({}) == []

    def test_non_numeric_does_not_raise(self):
        """(د) قيمة غير رقميّة لا ترمي استثناءً، وتُسجَّل مخالفةً."""
        out = evaluate_record({"ndvi": "bad"})
        assert isinstance(out, list)
        assert any(v["field"] == "ndvi" and v["value"] == "bad" for v in out)

    def test_none_value_numeric_check_flags(self):
        out = evaluate_record({"ndvi": None})
        assert any(v["field"] == "ndvi" for v in out)


class TestPercentRules:
    def test_soil_moisture_out_of_range(self):
        out = evaluate_record({"soil_moisture_pct": 150})
        assert any(v["rule_id"] == "soil_moisture_pct_range" for v in out)

    def test_humidity_valid(self):
        assert evaluate_record({"humidity_pct": 55}) == []

    def test_temperature_extreme_flags(self):
        out = evaluate_record({"temperature_c": -120})
        assert any(v["rule_id"] == "temperature_c_physical_range" for v in out)

    def test_temperature_valid(self):
        assert evaluate_record({"temperature_c": 25.0}) == []


class TestIntrospection:
    def test_list_rules_non_empty_unique_ids(self):
        """(هـ) list_rules غير فارغة ومعرّفاتها فريدة."""
        rules = list_rules()
        assert rules
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids))

    def test_rules_for_field(self):
        ndvi_rules = rules_for("ndvi")
        assert ndvi_rules
        assert all(isinstance(r, QualityRule) for r in ndvi_rules)
        assert all(r.field == "ndvi" for r in ndvi_rules)

    def test_rules_for_unknown_field_empty(self):
        assert rules_for("does_not_exist") == []


class TestCustomRules:
    def test_custom_min_rule(self):
        """مُقيّم يقبل قواعد مُمرَّرة بدل السجلّ المبدئيّ."""
        rule = QualityRule(id="x", field="yield", check="min", low=0.0, severity="info")
        assert evaluate_record({"yield": -3}, [rule])
        assert evaluate_record({"yield": 5}, [rule]) == []

    def test_custom_not_null_rule(self):
        rule = QualityRule(id="nn", field="lai", check="not_null")
        assert evaluate_record({"lai": None}, [rule])
        assert evaluate_record({"lai": 2.0}, [rule]) == []
