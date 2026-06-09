"""tests/test_historical_onboarding.py — اختبارات إطار الاستيعاب."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.historical_onboarding import (
    CanonicalCategory,
    FieldType,
    _try_parse_date,
    _try_parse_number,
    build_report,
    format_report_ar,
    infer_column_type,
    ingest_csv_string,
    profile_column,
    suggest_mapping_for_column,
)


class TestTypeInference:
    def test_integer_column(self):
        assert infer_column_type([1, 2, 3, 4, 5]) == FieldType.INTEGER
        assert infer_column_type(["1", "2", "3"]) == FieldType.INTEGER

    def test_float_column(self):
        assert infer_column_type([1.5, 2.7, 3.1]) == FieldType.FLOAT
        assert infer_column_type(["1.5", "2.7"]) == FieldType.FLOAT

    def test_date_column(self):
        assert infer_column_type(["2025-11-01", "2025-12-15"]) == FieldType.DATE
        assert infer_column_type(["01/11/2025"]) == FieldType.DATE

    def test_string_column(self):
        assert infer_column_type(["wheat", "barley", "millet"]) == FieldType.STRING

    def test_empty_column(self):
        assert infer_column_type([None, "", "  "]) == FieldType.EMPTY

    def test_identifier_column(self):
        ids = [f"farm-{i}" for i in range(20)]
        # كلّ ID فريد → IDENTIFIER
        assert infer_column_type(ids) == FieldType.IDENTIFIER

    def test_arabic_numbers(self):
        """الأرقام العربيّة تُستنبَط كـnumeric."""
        # ٠١٢٣ = 0123
        assert _try_parse_number("١٢٣") == 123.0
        assert _try_parse_number("١٫٥") is None  # ١٫٥ غير مدعوم بعد
        # لكن "1,234" مدعوم
        assert _try_parse_number("1,234") == 1234.0


class TestMappingSuggestion:
    def test_yield_column_mapped(self):
        cat, conf = suggest_mapping_for_column("yield_kg_ha", FieldType.FLOAT)
        assert cat == CanonicalCategory.YIELD_KG_HA
        assert conf > 0.9

    def test_arabic_column_mapped(self):
        cat, conf = suggest_mapping_for_column("المساحة", FieldType.FLOAT)
        assert cat == CanonicalCategory.AREA_HA
        assert conf > 0.7

    def test_ph_mapped(self):
        cat, _ = suggest_mapping_for_column("pH", FieldType.FLOAT)
        assert cat == CanonicalCategory.SOIL_PH

    def test_sowing_date_mapped(self):
        cat, _ = suggest_mapping_for_column("sowing_date", FieldType.DATE)
        assert cat == CanonicalCategory.SOWING_DATE

    def test_unknown_column_no_mapping(self):
        cat, conf = suggest_mapping_for_column("xyz_random_qwer", FieldType.STRING)
        assert cat is None
        assert conf == 0.0

    def test_type_mismatch_reduces_confidence(self):
        """عمود اسمه ph لكن النوع STRING → confidence منخفض."""
        cat_correct, conf_correct = suggest_mapping_for_column("ph", FieldType.FLOAT)
        cat_mismatch, conf_mismatch = suggest_mapping_for_column("ph", FieldType.STRING)
        assert conf_correct > conf_mismatch


class TestColumnProfile:
    def test_profile_yield_column(self):
        values = [3500, 4200, 5100, None, 3800, 4500]
        p = profile_column("yield_kg_ha", values)
        assert p.raw_type == FieldType.INTEGER
        assert p.null_count == 1
        assert p.null_pct > 16 and p.null_pct < 17
        assert p.min_val == 3500
        assert p.max_val == 5100
        assert p.suggested_mapping == CanonicalCategory.YIELD_KG_HA
        assert p.looks_plausible

    def test_implausible_ph(self):
        """pH خارج النطاق ٣.٥-١٠ → not plausible."""
        values = [12.5, 13.0, 11.8]
        p = profile_column("pH", values)
        assert p.suggested_mapping == CanonicalCategory.SOIL_PH
        assert not p.looks_plausible
        assert len(p.plausibility_notes) >= 1

    def test_unit_confusion_detected(self):
        """yield في الطن/هكتار قد تبدو خارج النطاق kg/ha."""
        # 3.5 ton/ha = 3500 kg/ha
        # لو المستخدم أدخل بـton/ha، النظام يكشف "أقل من المتوقَّع"
        values = [3.5, 4.2, 5.1]
        p = profile_column("yield_kg_ha", values)
        # القيم تبدو معقولة عددياً (range 0-30000)
        # لكنّ المُستخدم قد يخطئ
        # حالياً النظام لا يكشف هذا (false negative — ميزة لاحقة)
        # الاختبار يوثّق الحدّ الحالي
        assert p.looks_plausible


class TestBuildReport:
    def test_basic_csv_report(self):
        """تقرير بسيط لـCSV نموذجي."""
        csv_data = """field_id,crop,area_ha,sowing_date,yield_kg_ha
FLD001,wheat,2.5,2024-11-01,4500
FLD002,wheat,3.0,2024-11-05,4200
FLD003,barley,1.5,2024-11-10,3800"""
        report = ingest_csv_string(csv_data)
        assert report.row_count == 3
        assert report.column_count == 5
        # كلّ الأعمدة مُربَطة
        assert report.mapping_coverage_pct == 100
        assert report.readiness == "ready"

    def test_high_null_warning(self):
        """عمود بـ>50٪ null يُولّد warning."""
        csv_data = """id,value
1,
2,
3,5.0
4,"""
        report = ingest_csv_string(csv_data)
        warnings = [i for i in report.issues if i.severity == "warning"]
        assert len(warnings) >= 1
        assert any("value" in w.column for w in warnings if w.column)

    def test_blocked_on_empty_column(self):
        """عمود فارغ كلّياً → readiness=blocked."""
        csv_data = """id,name,empty_col
1,a,
2,b,
3,c,"""
        report = ingest_csv_string(csv_data)
        # empty_col كل قيمه فارغة
        assert report.readiness == "blocked"
        errors = [i for i in report.issues if i.severity == "error"]
        assert len(errors) >= 1

    def test_implausible_warning(self):
        """قيم pH خاطئة → warning."""
        csv_data = """field_id,pH
F1,15.0
F2,20.0
F3,18.5"""
        report = ingest_csv_string(csv_data)
        warnings = [i for i in report.issues if i.severity == "warning"]
        # pH خارج النطاق ٣.٥-١٠
        assert any("متوقَّع" in w.message_ar for w in warnings)

    def test_arabic_columns(self):
        """الأعمدة العربيّة تُربَط."""
        csv_data = """المحصول,المساحة,الإنتاج
قمح,2.5,4500
شعير,3.0,3800"""
        report = ingest_csv_string(csv_data)
        # المحصول → CROP، المساحة → AREA_HA
        crop_col = next((p for p in report.columns if p.column_name == "المحصول"), None)
        assert crop_col is not None
        assert crop_col.suggested_mapping == CanonicalCategory.CROP

        area_col = next((p for p in report.columns if p.column_name == "المساحة"), None)
        assert area_col is not None
        assert area_col.suggested_mapping == CanonicalCategory.AREA_HA

    def test_format_arabic(self):
        """التقرير العربي مفهوم."""
        csv_data = """field_id,crop,yield_kg_ha
F1,wheat,4500"""
        report = ingest_csv_string(csv_data)
        text = format_report_ar(report)
        assert "تقرير استيعاب" in text
        assert "yield_kg_ha" in text

    def test_empty_csv_raises(self):
        """CSV فارغ يرفع ValueError."""
        try:
            ingest_csv_string("")
            raise AssertionError
        except ValueError:
            pass

    def test_readiness_classification(self):
        """3 مستويات readiness صحيحة."""
        # ready
        clean = """id,crop,area_ha
F1,wheat,2.0
F2,barley,3.0"""
        r1 = ingest_csv_string(clean)
        assert r1.readiness == "ready"

        # needs_review (coverage<50%)
        weird = """xyz,abc,qwe
1,2,3
4,5,6"""
        r2 = ingest_csv_string(weird)
        assert r2.readiness == "needs_review"

        # blocked (empty column)
        broken = """id,empty
1,
2,"""
        r3 = ingest_csv_string(broken)
        assert r3.readiness == "blocked"
