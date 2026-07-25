"""Unit + static guard: NDVI reads route through the canonical raster-service facade.

The historical-season simulation (``api/routers/seasons.py``) and the agronomic
replay (``api/routers/agronomic_replay.py``) previously read NDVI from the legacy
``ndvi_timeseries`` table (seed-only, no live writer). They now read the canonical
scalar per-date index mean from raster-service ``GET /v1/fields/{id}/timeseries``
through the allowlisted ``api.raster_service_client`` HTTP facade.

These tests pin:
  1. the pure point→vegetation-row mapping (no fabrication; None cloud stays None);
  2. the facade's fail-soft contract (any raster failure ⇒ empty list, never raises);
  3. a static guard that neither router SELECTs from ``ndvi_timeseries`` anymore and
     both call the facade helper — so a regression to the dead table is caught.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api import raster_service_client as rsc  # noqa: E402

_PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"


@pytest.mark.unit
def test_point_maps_to_canonical_vegetation_row():
    """datetime→acquisition_date, mean→ndvi_mean, quality keys pass through verbatim."""
    point = {
        "datetime": "2026-05-01",
        "mean": 0.62,
        "cloud_pct": 12.5,
        "valid_pixel_ratio": 0.98,
        "coverage_ratio": 0.99,
    }
    row = rsc.timeseries_point_to_vegetation_row(point, field_id="F-1")

    assert row["acquisition_date"] == "2026-05-01"
    assert row["id"] == "2026-05-01"  # stable per-date id for deterministic sort
    assert row["field_id"] == "F-1"
    assert row["ndvi_mean"] == 0.62
    assert row["cloud_pct"] == 12.5
    assert row["valid_pixel_ratio"] == 0.98
    assert row["coverage_ratio"] == 0.99


@pytest.mark.unit
def test_point_missing_cloud_stays_none_not_fabricated():
    """A legacy layer without measured cloud yields cloud_pct=None (unqualified),
    so the composer's ``cloud_pct_required<=30`` rule drops it — no invented cloud."""
    row = rsc.timeseries_point_to_vegetation_row(
        {"datetime": "2026-05-02", "mean": 0.5}, field_id="F"
    )
    assert row["cloud_pct"] is None
    assert row["ndvi_mean"] == 0.5


@pytest.mark.unit
async def test_get_field_timeseries_returns_points(monkeypatch):
    """Happy path: facade returns the raw per-date points list from raster-service."""

    async def _fake_get_json(path, *, tenant_id=None, params=None, timeout_s=15.0):
        assert path == "/v1/fields/F-9/timeseries"
        assert params == {"index": "ndvi"}
        assert tenant_id == "t-1"
        return {
            "available": True,
            "points": [
                {"datetime": "2026-04-01", "mean": 0.4, "cloud_pct": 8.0},
                "not-a-dict",  # defensive: non-dict entries are dropped
                {"datetime": "2026-04-15", "mean": 0.55, "cloud_pct": 5.0},
            ],
        }

    monkeypatch.setattr(rsc, "raster_get_json", _fake_get_json)
    points = await rsc.get_field_timeseries("F-9", tenant_id="t-1", index="ndvi")

    assert [p["datetime"] for p in points] == ["2026-04-01", "2026-04-15"]


@pytest.mark.unit
async def test_get_field_timeseries_fail_soft_returns_empty(monkeypatch):
    """Any raster failure degrades to an empty list — the read never breaks the caller."""

    async def _boom(*args, **kwargs):
        raise RuntimeError("raster-service unavailable")

    monkeypatch.setattr(rsc, "raster_get_json", _boom)
    assert await rsc.get_field_timeseries("F", tenant_id="t") == []


@pytest.mark.unit
async def test_get_field_timeseries_missing_points_key_returns_empty(monkeypatch):
    """A response with no points list (available=False) yields []."""

    async def _empty(*args, **kwargs):
        return {"available": False, "points": None}

    monkeypatch.setattr(rsc, "raster_get_json", _empty)
    assert await rsc.get_field_timeseries("F", tenant_id="t") == []


@pytest.mark.unit
@pytest.mark.parametrize("router", ["seasons.py", "agronomic_replay.py"])
def test_router_no_longer_selects_from_ndvi_timeseries(router):
    """Static guard: neither NDVI-reading router SELECTs the dead ``ndvi_timeseries``
    table; both must go through the canonical facade helper."""
    text = (_PLATFORM / "api" / "routers" / router).read_text(encoding="utf-8")

    # No SQL read of the legacy table (comments may still mention it by name).
    assert "FROM ndvi_timeseries" not in text, (
        f"{router} must not read the dead ndvi_timeseries table — use the raster-service facade"
    )
    # Canonical path: the allowlisted facade helper is imported and used.
    assert "get_field_timeseries" in text
    assert "timeseries_point_to_vegetation_row" in text
