"""Tests for Farmonaut connector — SAR fallback, validation, no fabrication."""

import os

from core.connectors.base import FetchStatus
from core.connectors.farmonaut import (
    FarmonautConnector,
    ImageType,
    estimate_monthly_credits,
    validate_field_polygon,
)


class TestFarmonaut:
    def test_polygon_validation_yemen(self):
        ok, _ = validate_field_polygon(
            {
                "a": {"Latitude": 16.08, "Longitude": 44.94},
                "P_1": {"Latitude": 16.09, "Longitude": 44.95},
                "P_2": {"Latitude": 16.07, "Longitude": 44.96},
            }
        )
        assert ok

    def test_polygon_rejects_outside_yemen(self):
        ok, _ = validate_field_polygon(
            {
                "a": {"Latitude": 48.8, "Longitude": 2.3},
                "P_1": {"Latitude": 48.9, "Longitude": 2.4},
                "P_2": {"Latitude": 48.7, "Longitude": 2.5},
            }
        )
        assert not ok

    def test_polygon_requires_three_points(self):
        ok, _ = validate_field_polygon({"a": {"Latitude": 16.0, "Longitude": 44.0}})
        assert not ok

    def test_sar_fallback_on_cloud(self):
        fc = FarmonautConnector()
        # cloudy -> RVI radar (penetrates clouds)
        assert fc.decide_image_type(ImageType.NDVI, is_cloudy=True) == ImageType.RVI
        # clear -> requested optical
        assert fc.decide_image_type(ImageType.NDVI, is_cloudy=False) == ImageType.NDVI

    def test_no_fabrication_without_key(self):
        # ensure no env key
        os.environ.pop("FARMONAUT_API_KEY", None)
        fc = FarmonautConnector()
        r = fc.fetch(field_id="F1")
        assert r.status == FetchStatus.UNAVAILABLE
        assert not r.data

    def test_credit_estimate_reasonable(self):
        est = estimate_monthly_credits(hectares=1000, fields_count=500)
        assert est.total_units > 0
        assert est.cost_usd > 0

    def test_no_hardcoded_key(self):
        fc = FarmonautConnector()
        assert fc.key_env_var == "FARMONAUT_API_KEY"
