from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Import router through the normal package-less service layout (needs sys.path above).
import routers.fields as fields  # noqa: E402


@pytest.mark.asyncio
async def test_indicator_grid_missing_real_product_fails_424(monkeypatch):
    async def allow(*args, **kwargs):
        return None

    async def no_layer(*args, **kwargs):
        return None

    monkeypatch.setattr(fields, "_require_field_tenant", allow)
    monkeypatch.setattr(fields, "_resolve_field_layer", no_layer)
    with pytest.raises(HTTPException) as exc:
        await fields.field_indicator_grid("fld-1", index="ndvi", date="latest", grid=16)
    assert exc.value.status_code == 424
    assert exc.value.detail["code"] == "RASTER_INDICATOR_PRODUCT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_prescription_missing_real_product_fails_424(monkeypatch):
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)

    async def no_layer(*args, **kwargs):
        return None

    monkeypatch.setattr(fields, "_resolve_field_layer", no_layer)
    req = SimpleNamespace(
        index="ndvi", date="latest", grid=16, n_zones=3, base_rate=None, strategy="quantile"
    )
    with pytest.raises(HTTPException) as exc:
        await fields.field_prescription("fld-1", req, x_agent_token="ok")
    assert exc.value.status_code == 424
    assert exc.value.detail["code"] == "RASTER_INDICATOR_PRODUCT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_prescription_rejects_unqualified_product(monkeypatch):
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)

    async def layer(*args, **kwargs):
        return {"cog_url": "x"}

    monkeypatch.setattr(fields, "_resolve_field_layer", layer)
    monkeypatch.setattr(
        fields,
        "_grid_from_cog",
        lambda *a, **k: {
            "grid": [[0.4]],
            "real_data": True,
            "indicator_product": {
                "source": "raster-service",
                "estimated": False,
                "quality_gate_passed": False,
                "provenance": None,
            },
        },
    )
    req = SimpleNamespace(
        index="ndvi", date="latest", grid=16, n_zones=3, base_rate=None, strategy="quantile"
    )
    with pytest.raises(HTTPException) as exc:
        await fields.field_prescription("fld-1", req, x_agent_token="ok")
    assert exc.value.status_code == 424
    assert exc.value.detail["code"] == "RASTER_PRODUCT_NOT_DECISION_ELIGIBLE"
