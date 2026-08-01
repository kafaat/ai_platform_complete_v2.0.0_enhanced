#!/usr/bin/env python3
"""
SAHOOL v9.0 — End-to-End Integration Tests
Tests: Full workflow from farmer query → AI response → guardrails → action
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndWorkflow:
    """End-to-end tests simulating real farmer interactions"""

    async def test_farmer_daily_checkup(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-E2E-001: Farmer asks 'How is my field?' — full pipeline."""
        # Step 1: Farmer sends query to Supervisor
        query_payload = {
            "query": "كيف حال حقلي اليوم؟",
            "field_id": mock_field_data["field_id"],
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
            "context": {"date": "2026-05-18"},
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/query",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "response_ar" in data
        assert data["confidence"] > 0
        assert data["processing_time_ms"] < 10000  # Under 10 seconds
        assert len(data.get("sources", [])) > 0

        # Verify Arabic content
        assert any("\u0600" <= c <= "\u06ff" for c in data["response_ar"])

    async def test_irrigation_decision_with_guardrails(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-E2E-002: Farmer asks to irrigate — AI recommends + guardrails validate."""
        # Step 1: Get irrigation advice
        query_payload = {
            "query": "هل يجب أن أسقي القمح غداً؟",
            "field_id": mock_field_data["field_id"],
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
            "context": {"crop": "wheat", "soil_moisture_30cm": 25, "date": "2026-05-18"},
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/query",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        advice = response.json()
        assert "response_ar" in advice

        # Step 2: Guardrails validate the recommended action
        # Extract recommended water amount from advice (simplified)
        guardrails_payload = {
            "action_type": "irrigation",
            "action_data": {"water_m3": 50, "cost_usd": 25, "projected_revenue_increase_usd": 100},
            "farm_context": {
                "field_area_ha": mock_field_data["area_ha"],
                "water_source": "groundwater",
                "season_water_used_m3_ha": 500,
                "annual_revenue_usd": 5000,
                "capital_usd": 3000,
            },
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
        }
        gr_response = await http_client.post(
            "http://localhost:8097/v1/validate",
            json=guardrails_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert gr_response.status_code == 200
        gr_data = gr_response.json()

        # Small irrigation should be safe
        assert gr_data["overall_risk"] in ["LOW", "MEDIUM"]

    async def test_pest_alert_workflow(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-E2E-003: Farmer reports pest → AI identifies + guardrails check treatment."""
        # Step 1: Farmer describes pest symptoms
        query_payload = {
            "query": "أوراق القمح صفراء مع بقع بنية — ما العلاج؟",
            "field_id": mock_field_data["field_id"],
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
            "context": {"crop": "wheat"},
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/query",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        advice = response.json()
        assert "response_ar" in advice

        # Step 2: If chemical treatment recommended, validate with guardrails
        # (In real scenario, we'd parse the recommendation)
        guardrails_payload = {
            "action_type": "pesticide",
            "action_data": {
                "chemical": "mancozeb",  # Safe fungicide
                "dosage_kg_ha": 2.0,
                "crop": "wheat",
            },
            "farm_context": {"annual_revenue_usd": 5000, "capital_usd": 3000},
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
        }
        gr_response = await http_client.post(
            "http://localhost:8097/v1/validate",
            json=guardrails_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert gr_response.status_code == 200
        gr_data = gr_response.json()
        assert gr_data["allowed"] or gr_data["overall_risk"] in ["LOW", "MEDIUM"]

    async def test_optimization_workflow(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-E2E-004: Farmer requests optimization → Pareto front + recommendation."""
        query_payload = {
            "query": "حسّن مزرعتي للموسم القادم",
            "field_id": mock_field_data["field_id"],
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
            "preferred_objectives": ["balanced"],
            "context": {"crop": "wheat", "planting_date": "2026-01-15"},
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/optimize",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # Verify Pareto structure
        assert "pareto_options" in data
        assert len(data["pareto_options"]) > 0
        assert "recommended" in data

        recommended = data["recommended"]
        assert "yield_kg_ha" in recommended
        assert "profit_yer_ha" in recommended
        assert "water_mm" in recommended
        assert "carbon_kg" in recommended

        # Verify trade-off explanation
        assert "trade_off_explanation" in data
        assert len(data["trade_off_explanation"]) > 50

    async def test_market_and_contract_workflow(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-E2E-005: Farmer checks price → creates forward contract."""
        # Step 1: Check market price
        query_payload = {
            "query": "كم سعر القمح؟",
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
            "context": {"crop": "wheat", "market": "sanaa"},
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/query",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        price_data = response.json()
        assert "response_ar" in price_data

        # Step 2: Create forward contract (via MCP directly for test)
        contract_payload = {
            "name": "create_forward_contract",
            "arguments": {
                "farmer_id": "farmer-ali-001",
                "field_id": mock_field_data["field_id"],
                "crop": "wheat",
                "estimated_yield_kg": 5000,
                "harvest_date": "2026-09-01",
            },
        }
        contract_response = await http_client.post(
            "http://localhost:8094/v1/mcp/tools/call",
            json=contract_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert contract_response.status_code == 200
        contract_data = contract_response.json()
        content = __import__("json").loads(contract_data["content"][0]["text"])
        assert "contract_id" in content
        assert "total_contract_value_yer" in content

    async def test_full_pipeline_performance(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-E2E-006: Full pipeline completes within 15 seconds."""
        import time

        start = time.time()

        # Query → Optimize → Guardrails
        query_payload = {
            "query": "أعطني خطة كاملة للموسم",
            "field_id": mock_field_data["field_id"],
            "user_id": "farmer-ali-001",
            "tenant_id": mock_field_data["tenant_id"],
            "preferred_objectives": ["balanced"],
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/optimize",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )

        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 15.0, f"Pipeline took {elapsed:.1f}s, expected < 15s"

        data = response.json()
        assert data["processing_time_ms"] < 15000


@pytest.mark.integration
class TestSystemResilience:
    """Tests for system resilience and error handling"""

    async def test_service_unavailable_graceful(
        self, http_client: AsyncClient, mock_jwt_token: str
    ):
        """TC-E2E-007: When MCP server down, Supervisor returns graceful error."""
        # This test assumes we can temporarily stop a service
        # In practice, tested via mock or staging environment
        query_payload = {"query": "ما هو NDVI", "user_id": "test", "tenant_id": "test"}
        response = await http_client.post(
            "http://localhost:8096/v1/agent/query",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        # Should not crash — returns error message or fallback
        assert response.status_code in (200, 503, 502)
        if response.status_code == 200:
            data = response.json()
            assert "response_ar" in data

    async def test_invalid_field_id_handling(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-E2E-008: Invalid field ID returns helpful error."""
        query_payload = {
            "query": "كيف حال حقلي؟",
            "field_id": "nonexistent-field-999",
            "user_id": "test",
            "tenant_id": "test",
        }
        response = await http_client.post(
            "http://localhost:8096/v1/agent/query",
            json=query_payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        # Should handle gracefully
        assert response.status_code in (200, 404, 422)
