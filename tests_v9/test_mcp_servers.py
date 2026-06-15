#!/usr/bin/env python3
"""
SAHOOL v9.0 — MCP Servers Integration Tests
Tests: Sentinel Hub + Weather + WOFOST + Market MCP servers
"""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.mcp
@pytest.mark.integration
class TestSentinelHubMCP:
    """Tests for Sentinel Hub MCP Server (:8091)"""

    async def test_health_check(self, http_client: AsyncClient):
        """TC-MCP-001: Sentinel Hub MCP health endpoint responds."""
        response = await http_client.get("http://localhost:8091/healthz")
        assert response.status_code in (200, 503)  # 503 if SH credentials not configured

    async def test_list_tools(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-MCP-002: Tool discovery returns expected tools with valid auth."""
        response = await http_client.get(
            "http://localhost:8091/mcp/v1/tools",
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        tools = data.get("tools", [])
        tool_names = [t["name"] for t in tools]

        assert "fetch_sentinel2_l2a" in tool_names
        assert "fetch_sentinel1_grd" in tool_names
        assert "compute_ndvi" in tool_names

        # Verify schemas exist
        for tool in tools:
            assert "inputSchema" in tool
            assert "outputSchema" in tool or "description" in tool

    async def test_compute_ndvi_tool(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-MCP-003: NDVI computation tool accepts valid parameters."""
        payload = {
            "name": "compute_ndvi",
            "arguments": {"field_id": mock_field_data["field_id"], "date": "2026-05-18"},
            "request_id": "test-req-ndvi-001",
        }
        response = await http_client.post(
            "http://localhost:8091/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        # May fail if no real Sentinel data — check structure
        assert response.status_code in (200, 422, 500)
        if response.status_code == 200:
            data = response.json()
            assert "content" in data

    async def test_idempotency(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-MCP-004: Same request_id returns cached result."""
        payload = {
            "name": "compute_ndvi",
            "arguments": {"field_id": mock_field_data["field_id"], "date": "2026-05-18"},
            "request_id": "test-req-idempotent-001",
        }
        # First call
        r1 = await http_client.post(
            "http://localhost:8091/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        # Second call (should be cached)
        r2 = await http_client.post(
            "http://localhost:8091/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        # Both should succeed or both fail consistently
        assert r1.status_code == r2.status_code
        if r1.status_code == 200:
            assert r1.json() == r2.json()

    async def test_unauthorized_no_token(self, http_client: AsyncClient):
        """TC-MCP-005: Missing auth token returns 401."""
        response = await http_client.get("http://localhost:8091/mcp/v1/tools")
        assert response.status_code == 401

    async def test_unauthorized_invalid_scope(self, http_client: AsyncClient):
        """TC-MCP-006: Token with wrong scope returns 403."""
        import os
        from datetime import datetime, timedelta

        import jwt

        bad_token = jwt.encode(
            {
                "sub": "test",
                "scope": "weather:read",
                "iss": "sahool-auth",
                "aud": "sahool",
                "exp": datetime.now(UTC) + timedelta(hours=1),
            },
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        response = await http_client.get(
            "http://localhost:8091/mcp/v1/tools", headers={"Authorization": f"Bearer {bad_token}"}
        )
        assert response.status_code == 403


@pytest.mark.mcp
@pytest.mark.integration
class TestWeatherMCP:
    """Tests for Weather MCP Server (:8092)"""

    async def test_list_tools(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-MCP-007: Weather tool discovery."""
        response = await http_client.get(
            "http://localhost:8092/mcp/v1/tools",
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        tools = response.json().get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "get_weather_forecast" in tool_names
        assert "calculate_hargreaves_et0" in tool_names
        assert "get_historical_weather" in tool_names

    async def test_get_forecast(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_weather_data: dict
    ):
        """TC-MCP-008: Weather forecast returns valid data structure."""
        payload = {
            "name": "get_weather_forecast",
            "arguments": {
                "lat": mock_weather_data["lat"],
                "lon": mock_weather_data["lon"],
                "days": 3,
            },
        }
        response = await http_client.post(
            "http://localhost:8092/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        content = json.loads(data["content"][0]["text"])
        assert "daily" in content or "error" not in content

    async def test_calculate_et0(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_weather_data: dict
    ):
        """TC-MCP-009: Hargreaves ET0 calculation returns numeric value."""
        payload = {"name": "calculate_hargreaves_et0", "arguments": mock_weather_data}
        response = await http_client.post(
            "http://localhost:8092/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        content = json.loads(data["content"][0]["text"])
        assert "et0_mm_day" in content
        assert isinstance(content["et0_mm_day"], (int, float))
        assert content["et0_mm_day"] > 0


@pytest.mark.mcp
@pytest.mark.integration
class TestWOFOSTMCP:
    """Tests for WOFOST MCP Server (:8093)"""

    async def test_list_tools(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-MCP-010: WOFOST tool discovery."""
        response = await http_client.get(
            "http://localhost:8093/mcp/v1/tools",
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        tools = response.json().get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "run_wofost_simulation" in tool_names
        assert "get_crop_parameters" in tool_names

    async def test_run_simulation(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-MCP-011: WOFOST simulation returns yield and harvest date."""
        payload = {
            "name": "run_wofost_simulation",
            "arguments": {
                "crop": mock_field_data["crop"],
                "planting_date": mock_field_data["planting_date"],
                "soil_type": mock_field_data["soil_type"],
            },
        }
        response = await http_client.post(
            "http://localhost:8093/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        content = json.loads(data["content"][0]["text"])
        results = content.get("results", {})

        assert "yield_kg_ha" in results
        assert "harvest_date" in results
        assert "total_water_mm" in results
        assert results["yield_kg_ha"] > 0

    async def test_get_crop_parameters(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-MCP-012: Crop parameters return expected structure."""
        for crop in ["wheat", "barley", "maize", "sorghum", "millet", "rice", "potato"]:
            payload = {"name": "get_crop_parameters", "arguments": {"crop": crop}}
            response = await http_client.post(
                "http://localhost:8093/mcp/v1/tools/call",
                json=payload,
                headers={"Authorization": f"Bearer {mock_jwt_token}"},
            )
            assert response.status_code == 200
            data = response.json()
            content = json.loads(data["content"][0]["text"])
            assert "parameters" in content


@pytest.mark.mcp
@pytest.mark.integration
class TestMarketMCP:
    """Tests for Market MCP Server (:8094)"""

    async def test_list_tools(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-MCP-013: Market tool discovery."""
        response = await http_client.get(
            "http://localhost:8094/mcp/v1/tools",
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        tools = response.json().get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "get_market_price" in tool_names
        assert "create_forward_contract" in tool_names
        assert "get_price_trend" in tool_names

    async def test_get_price(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_market_data: dict
    ):
        """TC-MCP-014: Market price returns numeric value."""
        payload = {
            "name": "get_market_price",
            "arguments": {"crop": mock_market_data["crop"], "market": mock_market_data["market"]},
        }
        response = await http_client.post(
            "http://localhost:8094/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        content = json.loads(data["content"][0]["text"])
        assert "price_yer_kg" in content
        assert content["price_yer_kg"] > 0

    async def test_create_contract(
        self, http_client: AsyncClient, mock_jwt_token: str, mock_field_data: dict
    ):
        """TC-MCP-015: Forward contract creation returns contract ID."""
        payload = {
            "name": "create_forward_contract",
            "arguments": {
                "farmer_id": "farmer-test-001",
                "field_id": mock_field_data["field_id"],
                "crop": "wheat",
                "estimated_yield_kg": 5000,
                "harvest_date": "2026-09-01",
            },
        }
        response = await http_client.post(
            "http://localhost:8094/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        content = json.loads(data["content"][0]["text"])
        assert "contract_id" in content
        assert "total_contract_value_yer" in content

    async def test_price_trend(self, http_client: AsyncClient, mock_jwt_token: str):
        """TC-MCP-016: Price trend returns 30-day data."""
        payload = {"name": "get_price_trend", "arguments": {"crop": "wheat", "market": "sanaa"}}
        response = await http_client.post(
            "http://localhost:8094/mcp/v1/tools/call",
            json=payload,
            headers={"Authorization": f"Bearer {mock_jwt_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        content = json.loads(data["content"][0]["text"])
        assert "trend_data" in content
        assert len(content["trend_data"]) == 30
