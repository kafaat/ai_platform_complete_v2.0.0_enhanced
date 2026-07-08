"""V62.3-C — real NDVI grid+quality plumbing pack → evidence → VRA.

Covers the acceptance points (pure/unit, no live services):
- ``test_pack_ndvi_grid_evidence_populated`` — a pack carrying a grid + quality yields a
  valid ``ndvi_grid_evidence`` contract object with the quality metrics populated.
- ``test_pack_ndvi_grid_evidence_none_without_grid`` — a pack with no grid ⇒ None, and
  zoning still falls back to geometry strips (unchanged).
- ``test_pack_ndvi_grid_evidence_feeds_vra_gate`` — the assembled evidence drives the VRA
  raster-quality machine-readiness verdict.
- raster indicator-grid extraction: real grid → grid+quality; synthetic/malformed ⇒ none.
- fetch helper degrades safely (simulated raster error ⇒ pack still built, no grid).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import runtime_evidence as RE  # noqa: E402
from services.ai_agronomist.evidence_contract import (  # noqa: E402
    evaluate_machine_readiness,
)

_CORE = str(ROOT / "services" / "sahool-platform")

_GRID = [[0.12, 0.14], [0.80, 0.83]]


def _pack_with_grid() -> dict:
    return {
        "field_id": "f-1",
        "tenant_id": "t-1",
        "imagery_timeline": {
            "ndvi_grid": _GRID,
            "ndvi_grid_quality": {
                "cloud_pct": 12,  # ratio derived as 0.12 by the assembler
                "valid_pixel_ratio": 0.91,
                "coverage_ratio": 0.86,
                "scene_id": "S2A_20260620",
                "source_resolution_m": 10,
                "asset_id": "asset-9",
                "acquisition_date": "2026-06-20",
            },
        },
    }


# 1 ── pack with grid+quality → valid contract object, quality populated ──────
def test_pack_ndvi_grid_evidence_populated():
    ev = RE.pack_ndvi_grid_evidence(_pack_with_grid())
    assert ev is not None
    assert ev["field_id"] == "f-1" and ev["tenant_id"] == "t-1"
    assert ev["source"] == "raster-service" and ev["index"] == "ndvi"
    assert ev["scene_id"] == "S2A_20260620"
    assert ev["acquisition_date"] == "2026-06-20"
    assert ev["grid"] == {"width": 2, "height": 2, "values": _GRID}
    q = ev["quality"]
    assert q["valid_pixel_ratio"] == 0.91
    assert q["coverage_ratio"] == 0.86
    assert q["cloud_cover"] == 0.12  # converted from cloud_pct=12
    assert q["source_resolution_m"] == 10.0
    assert ev["provenance"]["asset_id"] == "asset-9"
    assert ev["provenance"]["pipeline_version"] == "v62.3"


def test_pack_ndvi_grid_evidence_prefers_explicit_cloud_cover():
    pack = _pack_with_grid()
    pack["imagery_timeline"]["ndvi_grid_quality"]["cloud_cover"] = 0.05
    ev = RE.pack_ndvi_grid_evidence(pack)
    assert ev is not None and ev["quality"]["cloud_cover"] == 0.05  # ratio wins over pct


def test_pack_ndvi_grid_evidence_grid_without_quality():
    # grid present, no quality block ⇒ evidence still built; metrics stay None.
    pack = {"field_id": "f", "imagery_timeline": {"ndvi_grid": _GRID}}
    ev = RE.pack_ndvi_grid_evidence(pack)
    assert ev is not None
    assert ev["quality"]["valid_pixel_ratio"] is None
    assert ev["quality"]["coverage_ratio"] is None
    assert ev["quality"]["cloud_cover"] is None


# 2 ── pack with no grid → None, zoning still falls back to strips ────────────
def test_pack_ndvi_grid_evidence_none_without_grid():
    assert RE.pack_ndvi_grid_evidence({"imagery_timeline": {"total_dates": 3}}) is None
    assert RE.pack_ndvi_grid_evidence({}) is None
    assert RE.pack_ndvi_grid_evidence(None) is None
    # zoning context carries no grid ⇒ downstream k-means cannot fire (unchanged).
    ctx = RE.zoning_evidence_context({"imagery_timeline": {"total_dates": 3}})
    assert ctx.get("ndvi_grid") is None


# 3 ── assembled evidence drives the VRA raster-quality readiness verdict ─────
def test_pack_ndvi_grid_evidence_feeds_vra_gate():
    ev = RE.pack_ndvi_grid_evidence(_pack_with_grid())
    verdict = evaluate_machine_readiness(
        ev, zoning_method="ndvi_kmeans_clustering", now="2026-06-21"
    )
    assert verdict["machine_ready"] is True  # good ratios + fresh scene + real zoning

    # low valid-pixel ratio flips the gate to not-ready (fail-closed).
    poor = _pack_with_grid()
    poor["imagery_timeline"]["ndvi_grid_quality"]["valid_pixel_ratio"] = 0.4
    verdict_poor = evaluate_machine_readiness(
        RE.pack_ndvi_grid_evidence(poor),
        zoning_method="ndvi_kmeans_clustering",
        now="2026-06-21",
    )
    assert verdict_poor["machine_ready"] is False
    assert "valid_pixel_ratio_below_min" in verdict_poor["blocking_reasons"]


# 4 ── raster indicator-grid extraction (pure): real → grid+quality; else none ─
def test_ndvi_grid_from_raster_payload_real_and_synthetic():
    fac = _load_field_ai_context()
    real = {
        "field_id": "f",
        "index": "ndvi",
        "date": "2026-06-20",
        "grid": _GRID,
        "real_data": True,
        "cloud_pct": 8,
        "valid_pixel_ratio": 0.9,
        "coverage_ratio": 0.82,
    }
    grid, quality = fac._ndvi_grid_from_raster_payload(real)
    assert grid == _GRID
    assert quality["valid_pixel_ratio"] == 0.9
    assert quality["coverage_ratio"] == 0.82
    assert quality["cloud_pct"] == 8
    assert quality["acquisition_date"] == "2026-06-20"

    # synthetic (real_data=False) ⇒ never forwarded (no fabricated evidence).
    synth = {"grid": _GRID, "real_data": False, "source": "simulation"}
    assert fac._ndvi_grid_from_raster_payload(synth) == (None, None)
    # malformed payloads degrade to no grid.
    assert fac._ndvi_grid_from_raster_payload({"real_data": True, "grid": []}) == (None, None)
    assert fac._ndvi_grid_from_raster_payload({"real_data": True}) == (None, None)
    assert fac._ndvi_grid_from_raster_payload(None) == (None, None)


# 5 ── fetch helper degrades safely on raster error (pack still built, no grid) ─
def test_optional_ndvi_grid_degrades_on_raster_error(monkeypatch):
    fac = _load_field_ai_context()
    import asyncio

    # P2.2 raster facade: _optional_ndvi_grid reads the grid through get_indicator_grid
    # (raster_service_client) instead of an injected httpx client. Patch the facade to
    # raise; the fail-safe degrade (no grid + warning) behaviour is unchanged.
    async def _boom(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("raster down")

    monkeypatch.setattr(fac, "get_indicator_grid", _boom)

    grid, quality, warn = asyncio.run(fac._optional_ndvi_grid("f-1", "t-1"))
    assert grid is None and quality is None
    assert warn is not None and "ndvi_grid" in warn


def _load_field_ai_context():
    """Import the platform router (adds the service root to path); skip if the platform
    app is not importable in this environment (keeps the ai_agronomist tests running)."""
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    pytest.importorskip("fastapi")
    try:
        from api.routers import field_ai_context  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"platform app not importable in unit tier: {exc}")
    return field_ai_context


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
