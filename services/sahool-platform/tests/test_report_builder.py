"""اختبارات بنّاء التقارير (Report Builder) — api/report_builder.py.

يغطّي: الكتالوج (غير فارغ، معرّفات فريدة، لكلّ حقل data_key)، بناء المواصفة
(صالح+مجهول، صيغة سيّئة/غائبة، اختيار فارغ/مُشوَّش)، وترشيح الفئة. كلّه نقيّ
(لا قاعدة بيانات ولا شبكة)، ولا يرمي على اختيار سيّئ.
"""

from api.report_builder import (
    ALLOWED_FORMATS,
    build_report_spec,
    fields_for_category,
    get_report_field,
    list_report_fields,
)


class TestCatalog:
    """الكتالوج مُغذّى من مفاتيح حقيقيّة فقط."""

    def test_catalog_not_empty(self):
        assert list_report_fields()

    def test_ids_unique(self):
        ids = [f.id for f in list_report_fields()]
        assert len(ids) == len(set(ids))

    def test_every_field_has_data_key(self):
        for f in list_report_fields():
            assert f.data_key, f"حقل بلا data_key: {f.id}"

    def test_every_field_value_type_valid(self):
        allowed = {"number", "text", "chart", "table"}
        for f in list_report_fields():
            assert f.value_type in allowed

    def test_get_report_field_roundtrip(self):
        first = list_report_fields()[0]
        assert get_report_field(first.id) == first
        assert get_report_field("__missing__") is None


class TestFieldsForCategory:
    """ترشيح الفئة يُعيد حقول تلك الفئة فقط."""

    def test_filters_by_category(self):
        farm_fields = fields_for_category("farm")
        assert farm_fields
        assert all(f.category == "farm" for f in farm_fields)

    def test_unknown_category_empty(self):
        assert fields_for_category("__nope__") == []


class TestBuildReportSpec:
    """بناء المواصفة — نقيّ، رِفق + تحذيرات، لا يرمي."""

    def _two_valid_ids(self):
        return [f.id for f in list_report_fields()[:2]]

    def test_valid_field_ids_kept(self):
        ids = self._two_valid_ids()
        out = build_report_spec({"field_ids": ids, "format": "json"})
        assert list(out["spec"]["field_ids"]) == ids
        assert out["spec"]["format"] == "json"
        assert len(out["resolved_fields"]) == 2

    def test_unknown_field_ids_go_to_warnings(self):
        valid = self._two_valid_ids()[:1]
        out = build_report_spec({"field_ids": valid + ["__ghost__"]})
        assert list(out["spec"]["field_ids"]) == valid
        assert any("__ghost__" in w for w in out["warnings"])

    def test_resolved_fields_carry_metadata(self):
        valid = self._two_valid_ids()[:1]
        out = build_report_spec({"field_ids": valid})
        rf = out["resolved_fields"][0]
        assert rf["id"] == valid[0]
        assert rf["data_key"]
        assert "name_ar" in rf

    def test_bad_format_defaults_to_csv_with_warning(self):
        out = build_report_spec({"field_ids": [], "format": "xml"})
        assert out["spec"]["format"] == "csv"
        assert any("xml" in w for w in out["warnings"])

    def test_absent_format_defaults_to_csv(self):
        out = build_report_spec({"field_ids": []})
        assert out["spec"]["format"] == "csv"

    def test_csv_in_allowed_formats(self):
        assert "csv" in ALLOWED_FORMATS

    def test_title_and_dates_preserved(self):
        out = build_report_spec(
            {
                "title": "تقرير الموسم",
                "date_from": "2026-01-01",
                "date_to": "2026-06-15",
                "field_ids": [],
            }
        )
        assert out["spec"]["title_ar"] == "تقرير الموسم"
        assert out["spec"]["date_from"] == "2026-01-01"
        assert out["spec"]["date_to"] == "2026-06-15"

    def test_default_title_when_absent(self):
        out = build_report_spec({"field_ids": []})
        assert out["spec"]["title_ar"]

    def test_duplicate_field_ids_deduped(self):
        fid = self._two_valid_ids()[0]
        out = build_report_spec({"field_ids": [fid, fid]})
        assert list(out["spec"]["field_ids"]) == [fid]

    def test_empty_selection_does_not_raise(self):
        out = build_report_spec({})
        assert out["spec"]["field_ids"] == ()
        assert out["spec"]["format"] == "csv"

    def test_garbage_selection_does_not_raise(self):
        for garbage in [None, [], "nope", 42, {"field_ids": "notalist"}]:
            out = build_report_spec(garbage)
            assert "spec" in out
            assert isinstance(out["warnings"], list)

    def test_field_ids_non_list_warns(self):
        out = build_report_spec({"field_ids": "x"})
        assert out["spec"]["field_ids"] == ()
        assert out["warnings"]
