"""Tests for sensor intake: validates IoT/manual sensor readings, no invention,
physical range enforcement, sensor as INDICATION not EVIDENCE (medium ceiling)."""
from core.sensor_intake import ingest_reading, ingest_batch


class TestValidation:
    def test_valid_reading_accepted(self):
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_moisture", value=35.5)
        assert r.accepted
        assert r.observation["confidence"] == "medium"
        assert r.observation["source"] == "sensor"

    def test_none_value_rejected_explicitly(self):
        # CRITICAL: لا اختراع — None → رفض صريح
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_moisture", value=None)
        assert not r.accepted
        assert "معطّل" in r.rejection_reason_ar or "فارغ" in r.rejection_reason_ar

    def test_out_of_range_rejected(self):
        # CRITICAL: قيمة جنونية = حسّاس معطّل، لا قياس
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_temperature", value=500.0)
        assert not r.accepted

    def test_negative_humidity_rejected(self):
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="air_humidity", value=-10)
        assert not r.accepted

    def test_unknown_sensor_type_rejected(self):
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="alien_sensor", value=5)
        assert not r.accepted

    def test_sensor_ceiling_is_medium_not_high(self):
        # CRITICAL: الحسّاس قرينة قويّة، لا دليل مخبري — سقف medium
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_ec", value=2.5)
        assert r.observation["confidence"] == "medium"
        # ليس high (المختبر فقط high)

    def test_missing_timestamp_warns(self):
        # تحذير لا رفض — يُستخدم وقت الاستقبال
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_moisture", value=40)
        assert r.accepted
        assert any("طابع زمني" in w for w in r.warnings_ar)


class TestObservationOutput:
    def test_maps_to_correct_observable_id(self):
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_ec", value=3.0)
        assert r.observation["observable_id"] == "soil_ec_ds_m"

    def test_geo_tag_preserved(self):
        r = ingest_reading(tenant_id="t1", field_id="f1",
            sensor_type="soil_moisture", value=40,
            lon=44.5, lat=16.2)
        assert r.observation["lon"] == 44.5
        assert r.observation["lat"] == 16.2


class TestBatchIngest:
    def test_batch_separates_accepted_and_rejected(self):
        result = ingest_batch([
            {"tenant_id":"t1","field_id":"f1","sensor_type":"soil_moisture","value":40},
            {"tenant_id":"t1","field_id":"f1","sensor_type":"soil_moisture","value":-5},
            {"tenant_id":"t1","field_id":"f1","sensor_type":"air_humidity","value":70},
        ])
        assert result["accepted_count"] == 2
        assert result["rejected_count"] == 1
        assert len(result["observations"]) == 2

    def test_missing_required_field_rejected_gracefully(self):
        # حقل ناقص لا يُسقط الدفعة كلّها
        result = ingest_batch([
            {"value": 40},  # ناقص tenant_id, field_id, sensor_type
            {"tenant_id":"t1","field_id":"f1","sensor_type":"soil_moisture","value":35},
        ])
        assert result["accepted_count"] == 1
        assert result["rejected_count"] == 1
