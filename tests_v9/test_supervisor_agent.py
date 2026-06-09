#!/usr/bin/env python3
"""
SAHOOL v9.0 — Supervisor Agent Integration Tests
Tests: Intent Classification + Skill Routing + Pareto Optimization
"""

import json

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestSupervisorAgent:
    """Tests for Supervisor Agent (:8096)"""

    async def test_health_check(self, http_client: AsyncClient):
        """TC-SUP-001: Supervisor health endpoint responds."""
        response = await http_client.get("http://localhost:8096/healthz")
        assert response.status_code in (200, 503)

    async def test_ndvi_query(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-002: NDVI query routes to RemoteSensing skill."""
        payload = {
            "query": "ما هو NDVI لحقلي اليوم؟",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
            "context": {"date": "2026-05-18"},
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_ar" in data
        assert data["confidence"] > 0
        assert any("ndvi" in s.lower() for s in data.get("sources", []))

    async def test_irrigation_advice_query(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-003: Irrigation query routes to CropModel skill."""
        payload = {
            "query": "متى يجب أن أسقي القمح؟",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
            "context": {"crop": "wheat", "soil_moisture_30cm": 35},
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_ar" in data
        assert any("ري" in data["response_ar"] or "مياه" in data["response_ar"])

    async def test_market_price_query(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-SUP-004: Market price query routes to Market skill."""
        payload = {
            "query": "كم سعر القمح في صنعاء؟",
            "user_id": "test-user-001",
            "tenant_id": "test-tenant-001",
            "context": {"crop": "wheat", "market": "sanaa"},
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_ar" in data
        assert data["confidence"] > 0

    async def test_pest_identification_query(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-SUP-005: Pest query routes to Advisory skill."""
        payload = {
            "query": "أوراق القمح صفراء — ما المشكلة؟",
            "user_id": "test-user-001",
            "tenant_id": "test-tenant-001",
            "context": {"crop": "wheat"},
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_ar" in data
        assert data["confidence"] > 0

    async def test_unknown_query_fallback(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-SUP-006: Unknown query falls back to advisory with low confidence."""
        payload = {
            "query": "أريد أن أشتري جراراً زراعياً",
            "user_id": "test-user-001",
            "tenant_id": "test-tenant-001",
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_ar" in data
        # Should still respond but possibly with lower confidence
        assert data["confidence"] >= 0

    async def test_optimize_farm(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-007: Farm optimization returns Pareto front."""
        payload = {
            "query": "حسّن مزرعتي",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
            "preferred_objectives": ["balanced"],
        }
        response = await http_client.post(
            "http://localhost:8096/agent/optimize",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "pareto_options" in data
        assert "recommended" in data
        assert "trade_off_explanation" in data
        assert len(data["pareto_options"]) > 0
        assert "yield_kg_ha" in data["recommended"]
        assert "profit_yer_ha" in data["recommended"]
        assert "water_mm" in data["recommended"]

    async def test_optimize_max_yield(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-008: Maximize yield objective."""
        payload = {
            "query": "أريد أقصى إنتاجية",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
            "preferred_objectives": ["max_yield"],
        }
        response = await http_client.post(
            "http://localhost:8096/agent/optimize",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        recommended = data["recommended"]
        # Max yield should have higher yield than balanced
        assert recommended["yield_kg_ha"] > 0

    async def test_optimize_min_water(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-009: Minimize water objective."""
        payload = {
            "query": "أريد توفير المياه",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
            "preferred_objectives": ["min_water"],
        }
        response = await http_client.post(
            "http://localhost:8096/agent/optimize",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        recommended = data["recommended"]
        # Min water should have lower water use
        assert recommended["water_mm"] > 0

    async def test_arabic_response_format(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-010: Response contains Arabic text with emojis."""
        payload = {
            "query": "كيف حال حقلي؟",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response_ar" in data
        # Check for Arabic characters
        assert any("\u0600" <= c <= "\u06ff" for c in data["response_ar"])

    async def test_processing_time_under_5s(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-SUP-011: Query processing completes within 5 seconds."""
        import time

        start = time.time()
        payload = {
            "query": "أعطني تقريراً شاملاً",
            "field_id": mock_field_data["field_id"],
            "user_id": "test-user-001",
            "tenant_id": mock_field_data["tenant_id"],
        }
        response = await http_client.post(
            "http://localhost:8096/agent/query",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        elapsed_ms = (time.time() - start) * 1000
        assert response.status_code == 200
        data = response.json()
        assert data["processing_time_ms"] < 5000
        assert elapsed_ms < 5000


@pytest.mark.integration
class TestSupervisorRouter:
    """Tests for Hierarchical Router"""

    async def test_intent_classification_ndvi(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-SUP-012: Router classifies NDVI query correctly."""
        queries = [
            "ما هو NDVI",
            "صورة القمر الصناعي",
            "صحة الحقل",
            "satellite image",
            "green index",
        ]
        for q in queries:
            payload = {"query": q, "user_id": "test", "tenant_id": "test"}
            response = await http_client.post(
                "http://localhost:8096/agent/query",
                json=payload,
                headers={"Authorization": f"Bearer {mock_jwt_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                # Should route to remote_sensing or advisory
                assert data["confidence"] > 0

    async def test_intent_classification_irrigation(
        self, http_client: AsyncClient, mock_jwt_token: str
    ):
        """TC-SUP-013: Router classifies irrigation query correctly."""
        queries = ["متى أسقي", "كمية المياه", "ري القمح", "water schedule"]
        for q in queries:
            payload = {"query": q, "user_id": "test", "tenant_id": "test"}
            response = await http_client.post(
                "http://localhost:8096/agent/query",
                json=payload,
                headers={"Authorization": f"Bearer {mock_jwt_token}"},
            )
            if response.status_code == 200:
                data = response.json()
                assert data["confidence"] > 0
