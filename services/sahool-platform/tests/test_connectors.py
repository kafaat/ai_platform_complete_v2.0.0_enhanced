"""Tests for external connectors — honest behavior, no fabrication."""

from core.connectors.base import FetchStatus
from core.connectors.copernicus import CopernicusConnector, ImageryRequest
from core.connectors.weather_openmeteo import OpenMeteoConnector


class TestConnectors:
    def test_openmeteo_no_fabrication_offline(self):
        om = OpenMeteoConnector()
        r = om.fetch(lat=16.15, lon=45.30)
        # without server response, must NOT invent data
        assert r.status == FetchStatus.UNAVAILABLE
        assert not r.data

    def test_openmeteo_parses_server_response(self):
        om = OpenMeteoConnector()
        fake = {
            "daily": {
                "temperature_2m_max": [42],
                "temperature_2m_min": [22],
                "relative_humidity_2m_mean": [25],
                "wind_speed_10m_max": [12.6],
                "shortwave_radiation_sum": [28],
                "precipitation_sum": [0],
            }
        }
        r = om.fetch(lat=16.15, elevation_m=1100, _live_response=fake)
        assert r.status == FetchStatus.OK
        assert r.data["temp_max_c"] == 42
        assert abs(r.data["wind_speed_ms"] - 3.5) < 0.01  # km/h converted
        assert r.error_margin > 0  # carries provenance

    def test_openmeteo_free_no_key(self):
        om = OpenMeteoConnector()
        assert om.is_configured()  # free, no key needed

    def test_copernicus_requires_key(self):
        cop = CopernicusConnector()
        # without env key, not configured -> won't fabricate
        assert cop.requires_key
        r = cop.fetch(request=ImageryRequest([[45.3, 16.15]], "2026-05-01", "2026-05-23"))
        assert r.status == FetchStatus.UNAVAILABLE

    def test_cloud_gate_decides_radar(self):
        cop = CopernicusConnector()
        assert not cop.should_use_radar(10)  # clear -> optical
        assert cop.should_use_radar(50)  # cloudy -> radar

    def test_no_keys_in_code(self):
        # the key must come from env var name, never a literal
        cop = CopernicusConnector()
        assert cop.key_env_var == "CDSE_CLIENT_SECRET"
        assert cop._get_key() is None  # not set in test env


class TestCloudThresholdConsistency:
    """يحرس إصلاح تكرار العتبة السحرية: مصدر حقيقة واحد للعتبة (DRY)."""

    def test_shared_constant_exists(self):
        from core.connectors.base import CLOUD_THRESHOLD_PCT

        assert CLOUD_THRESHOLD_PCT == 20.0

    def test_imagery_request_uses_shared_constant(self):
        # ImageryRequest الافتراضي يطابق الثابت المشترك، لا قيمة سحرية منفصلة
        from core.connectors.base import CLOUD_THRESHOLD_PCT
        from core.connectors.copernicus import ImageryRequest

        assert ImageryRequest([], "", "").max_cloud_pct == CLOUD_THRESHOLD_PCT

    def test_radar_decision_matches_threshold(self):
        # القرار عند العتبة متّسق: تحتها بصري، عندها/فوقها رادار
        from core.connectors.base import CLOUD_THRESHOLD_PCT
        from core.connectors.copernicus import CopernicusConnector

        c = CopernicusConnector()
        assert c.should_use_radar(CLOUD_THRESHOLD_PCT - 0.1) is False
        assert c.should_use_radar(CLOUD_THRESHOLD_PCT) is True

    def test_pipeline_agrees_with_connector_at_threshold(self):
        # pipeline.decide_source و connector متّسقان عند العتبة (لا تضارب)
        from core.connectors.base import CLOUD_THRESHOLD_PCT
        from core.connectors.copernicus import CopernicusConnector
        from core.spatial.pipeline import Satellite, decide_source

        c = CopernicusConnector()
        # تحت العتبة: pipeline يختار بصري، connector لا يلجأ للرادار
        sat, _ = decide_source(CLOUD_THRESHOLD_PCT - 1)
        assert sat == Satellite.S2_OPTICAL
        assert c.should_use_radar(CLOUD_THRESHOLD_PCT - 1) is False
