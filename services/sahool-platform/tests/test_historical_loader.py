"""Tests for historical_loader: imports past seasons into calibration loop.
Strict validation, no invention, physical range enforcement, multi-tenant aware."""

from core.historical_loader import (
    HistoricalRow,
    LoadResult,
    group_by_tenant,
    import_summary,
    load_csv,
    load_json,
    to_calibration_records,
)


class TestCSVValidation:
    def test_valid_row_accepted(self):
        csv_text = "tenant_id,field_id,season,crop_id,actual_yield_t_ha\nt1,f1,2024,wheat,3.5"
        r = load_csv(csv_text)
        assert r.accepted_count == 1
        assert r.accepted_rows[0].actual_yield_t_ha == 3.5

    def test_missing_required_field_rejected(self):
        # CRITICAL: حقل ناقص = رفض صريح، لا اختراع
        csv_text = "tenant_id,field_id,season,crop_id,actual_yield_t_ha\nt1,,2024,wheat,3.5"
        r = load_csv(csv_text)
        assert r.accepted_count == 0
        assert "field_id" in r.rejections[0]["reason"]

    def test_non_numeric_yield_rejected(self):
        csv_text = (
            "tenant_id,field_id,season,crop_id,actual_yield_t_ha\nt1,f1,2024,wheat,not_a_number"
        )
        r = load_csv(csv_text)
        assert r.accepted_count == 0
        assert "غير رقمي" in r.rejections[0]["reason"]

    def test_negative_yield_rejected(self):
        # حصاد فاشل (yield=0) يجب توثيقه بحقل منفصل، لا كصفر إنتاجية
        csv_text = "tenant_id,field_id,season,crop_id,actual_yield_t_ha\nt1,f1,2024,wheat,-2.0"
        r = load_csv(csv_text)
        assert r.accepted_count == 0

    def test_yield_out_of_physical_range_rejected(self):
        # CRITICAL: قمح بـ500 ط/هـ مستحيل فيزيائياً = خطأ إدخال
        csv_text = "tenant_id,field_id,season,crop_id,actual_yield_t_ha\nt1,f1,2024,wheat,500.0"
        r = load_csv(csv_text)
        assert r.accepted_count == 0
        assert "خارج النطاق الفيزيائي" in r.rejections[0]["reason"]

    def test_crop_specific_ranges(self):
        # طماطم 50 ط/هـ مقبولة، قمح 50 ط/هـ مرفوض (نطاق محصول مختلف)
        csv_text = (
            "tenant_id,field_id,season,crop_id,actual_yield_t_ha\n"
            "t1,f1,2024,tomato,50.0\n"
            "t1,f2,2024,wheat,50.0"
        )
        r = load_csv(csv_text)
        assert r.accepted_count == 1  # الطماطم فقط
        assert r.rejected_count == 1

    def test_invalid_date_format_rejected(self):
        # تاريخ ليس ISO YYYY-MM-DD
        csv_text = (
            "tenant_id,field_id,season,crop_id,actual_yield_t_ha,harvest_date\n"
            "t1,f1,2024,wheat,3.5,15-05-2024"
        )
        r = load_csv(csv_text)
        assert r.accepted_count == 0
        assert "ISO" in r.rejections[0]["reason"]

    def test_optional_fields_accepted(self):
        csv_text = "tenant_id,field_id,season,crop_id,actual_yield_t_ha\nt1,f1,2024,wheat,3.5"
        r = load_csv(csv_text)
        assert r.accepted_count == 1
        assert r.accepted_rows[0].planted_area_ha is None  # اختياري


class TestJSONLoad:
    def test_valid_json_list_accepted(self):
        json_text = (
            '[{"tenant_id":"t1","field_id":"f1","season":"2024",'
            '"crop_id":"wheat","actual_yield_t_ha":3.5}]'
        )
        r = load_json(json_text)
        assert r.accepted_count == 1

    def test_malformed_json_graceful_rejection(self):
        # CRITICAL: لا crash — رفض صريح
        r = load_json("{not valid json}")
        assert r.accepted_count == 0
        assert "JSON غير صالح" in r.rejections[0]["reason"]

    def test_non_list_json_rejected(self):
        # JSON كائن لا قائمة
        r = load_json('{"tenant_id":"t1"}')
        assert r.accepted_count == 0
        assert "قائمة" in r.rejections[0]["reason"]


class TestCalibrationBridge:
    def test_to_calibration_records_format(self):
        rows = [
            HistoricalRow(
                tenant_id="t1",
                field_id="f1",
                season="2024",
                crop_id="wheat",
                actual_yield_t_ha=3.5,
                planted_area_ha=2.0,
                source_file="test.csv",
            )
        ]
        records = to_calibration_records(rows)
        assert len(records) == 1
        # تنسيق calibration_loop.read_yield_history المتوقّع
        for required in ("field_id", "season", "actual_yield", "crop_id"):
            assert required in records[0]
        assert records[0]["actual_yield"] == 3.5

    def test_group_by_tenant_separates_correctly(self):
        # CRITICAL: المعايرة على مستوى المستأجر، يجب فصل البيانات
        rows = [
            HistoricalRow("t1", "f1", "2024", "wheat", 3.5),
            HistoricalRow("t1", "f2", "2024", "wheat", 3.7),
            HistoricalRow("t2", "f3", "2024", "wheat", 3.2),
        ]
        grouped = group_by_tenant(rows)
        assert len(grouped) == 2
        assert len(grouped["t1"]) == 2
        assert len(grouped["t2"]) == 1


class TestSummary:
    def test_summary_counts_unique_entities(self):
        csv_text = (
            "tenant_id,field_id,season,crop_id,actual_yield_t_ha\n"
            "t1,f1,2024,wheat,3.5\n"
            "t1,f1,2025,wheat,3.7\n"
            "t2,f2,2024,sorghum,2.8"
        )
        r = load_csv(csv_text)
        s = import_summary(r)
        assert s["unique_tenants"] == 2
        assert s["unique_fields"] == 2  # (t1,f1) و(t2,f2)
        assert s["unique_seasons"] == 2
        assert s["unique_crops"] == 2

    def test_zero_accepted_warns(self):
        # CRITICAL: ملف فاشل تماماً = تحذير صريح، لا صمت
        csv_text = "tenant_id,field_id,season,crop_id,actual_yield_t_ha\n,,,,bad"
        r = load_csv(csv_text)
        assert r.accepted_count == 0
        assert any("لم يُقبل" in w for w in r.warnings_ar)
