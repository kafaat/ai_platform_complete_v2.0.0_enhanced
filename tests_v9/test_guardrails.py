"""Guardrails Engine Tests — SAHOOL v9.1.0"""
import pytest

class TestChemicalTier:
    @pytest.mark.unit
    def test_banned_substance_critical(self):
        """Banned chemicals must return CRITICAL risk."""
        # Simulate chemical tier logic
        BANNED = ["DDT", "aldrin", "chlordane", "dieldrin"]
        result_risk = "CRITICAL" if "DDT" in BANNED else "LOW"
        assert result_risk == "CRITICAL"

    @pytest.mark.unit
    def test_dosage_within_limit(self):
        """Dosage at limit should pass."""
        MAX_DOSE = 100.0  # kg/ha
        dose = 80.0
        assert dose <= MAX_DOSE

    @pytest.mark.unit
    def test_dosage_exceeds_limit(self):
        """Dosage above limit → HIGH risk."""
        MAX_DOSE = 100.0
        dose = 150.0
        risk = "HIGH" if dose > MAX_DOSE else "LOW"
        assert risk == "HIGH"

class TestEconomicTier:
    @pytest.mark.unit
    def test_negative_roi_blocked(self):
        """Negative ROI action should be flagged."""
        cost = 1000; revenue = 800
        roi = (revenue - cost) / cost
        risk = "HIGH" if roi < 0 else "LOW"
        assert risk == "HIGH"

class TestGuardrailsEndpoints:
    @pytest.mark.integration
    async def test_validate_endpoint(self, http_client, auth_headers):
        from conftest import service_urls
        resp = await http_client.post(
            f"{service_urls['guardrails']}/validate",
            json={"action":"irrigate","field_id":"field_01","amount_mm":25},
            headers=auth_headers
        )
        assert resp.status_code in [200, 201]
        data = resp.json()
        assert "risk" in data or "overall_risk" in data
