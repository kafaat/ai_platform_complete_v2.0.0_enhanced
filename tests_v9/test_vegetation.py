"""Vegetation Analysis Tests — SAHOOL v9.1.0"""
import pytest

class TestNDVICalculation:
    @pytest.mark.unit
    def test_ndvi_formula(self):
        """NDVI = (NIR - RED) / (NIR + RED)"""
        NIR, RED = 0.8, 0.1
        ndvi = (NIR - RED) / (NIR + RED)
        assert -1 <= ndvi <= 1
        assert abs(ndvi - 0.7778) < 0.001

    @pytest.mark.unit
    def test_ndvi_healthy_threshold(self):
        """NDVI > 0.6 indicates healthy vegetation."""
        ndvi = 0.75
        is_healthy = ndvi > 0.6
        assert is_healthy

    @pytest.mark.unit
    def test_ndvi_stressed_threshold(self):
        """NDVI < 0.3 indicates stressed vegetation."""
        ndvi = 0.2
        is_stressed = ndvi < 0.3
        assert is_stressed

    @pytest.mark.unit
    def test_ndvi_range(self):
        """NDVI must be between -1 and 1."""
        test_values = [(-0.5, True), (0.0, True), (0.8, True), (1.5, False), (-1.5, False)]
        for val, expected_valid in test_values:
            is_valid = -1 <= val <= 1
            assert is_valid == expected_valid

class TestVegetationEndpoints:
    @pytest.mark.integration
    async def test_health_endpoint(self, http_client):
        from conftest import service_urls
        resp = await http_client.get(f"{service_urls['vegetation']}/healthz")
        assert resp.status_code == 200
