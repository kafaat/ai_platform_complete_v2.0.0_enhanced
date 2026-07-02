"""V62.3 — NDVI-grid evidence contract + machine-readiness gate.

Covers the five acceptance points:
- ``test_ndvi_grid_evidence_contract`` — canonical object shape, no fabrication.
- ``test_vra_rejects_low_completeness`` — low valid-pixel/coverage ⇒ raster_quality not
  machine-ready (VRA surfaces the blocking verdict + an Arabic warning).
- ``test_vra_warns_stale_scene`` — old scene with good ratios ⇒ stale warning (advisory).
- ``test_productivity_zones_use_ndvi_grid_when_available`` — the pack→evidence plumbing makes
  the k-means path fire (not geometry strips).
- ``test_no_machine_export_from_geometry_fallback`` — geometry-only zoning can never anchor
  machine export.
Pure/unit (no DB, no services).
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
    build_ndvi_grid_evidence,
    evaluate_machine_readiness,
)
from services.ai_agronomist.productivity_zones import propose_productivity_zones  # noqa: E402
from services.ai_agronomist.vra_prescription_engine import (  # noqa: E402
    generate_vra_prescription,
)

_BBOX = [44.0, 16.0, 44.4, 16.4]


# 1 ── contract shape + no fabrication ───────────────────────────────────────
def test_ndvi_grid_evidence_contract():
    ev = build_ndvi_grid_evidence(
        field_id=7,
        tenant_id="t-1",
        source="raster-service",
        scene_id="S2A_20260620",
        acquisition_date="2026-06-20",
        grid=[[0.1, 0.2], [0.3, 0.4]],
        cloud_cover=0.12,
        valid_pixel_ratio=0.91,
        coverage_ratio=0.87,
        source_resolution_m=10,
        quality_flags=["partial_cloud"],
        asset_id="asset-9",
        computed_at="2026-06-21T00:00:00Z",
    )
    assert ev["field_id"] == "7" and ev["tenant_id"] == "t-1"
    assert ev["source"] == "raster-service" and ev["index"] == "ndvi"
    assert ev["grid"] == {"width": 2, "height": 2, "values": [[0.1, 0.2], [0.3, 0.4]]}
    q = ev["quality"]
    assert q["valid_pixel_ratio"] == 0.91 and q["coverage_ratio"] == 0.87
    assert q["cloud_cover"] == 0.12 and q["source_resolution_m"] == 10.0
    assert q["quality_flags"] == ["partial_cloud"]
    assert ev["provenance"] == {
        "asset_id": "asset-9",
        "pipeline_version": "v62.3",
        "computed_at": "2026-06-21T00:00:00Z",
    }

    # no fabrication: unknown metrics stay None / [] (distinguishable from measured zeros).
    empty = build_ndvi_grid_evidence(field_id="f")
    assert empty["grid"] is None
    assert empty["quality"]["valid_pixel_ratio"] is None
    assert empty["quality"]["coverage_ratio"] is None
    assert empty["quality"]["quality_flags"] == []
    assert empty["scene_id"] is None and empty["acquisition_date"] is None


def _lab_zones_params():
    return {
        "product_type": "fertilizer",
        "crop": "wheat",
        "lab_results": [{"n": 12, "p": 8, "k": 20}],
        "zones": [
            {
                "zone_id": "z1",
                "productivity_class": "high",
                "area_ha": 2.0,
                "zoning_method": "ndvi_kmeans_clustering",
                "geometry": {"type": "Polygon", "coordinates": [[[44.0, 16.0]]]},
            }
        ],
    }


# 2 ── VRA fail-closed on low valid-pixel/coverage ───────────────────────────
def test_vra_rejects_low_completeness():
    evidence = build_ndvi_grid_evidence(
        field_id="f",
        acquisition_date="2026-06-25",
        valid_pixel_ratio=0.5,  # < 0.7 ⇒ blocking
        coverage_ratio=0.9,
    )
    out = generate_vra_prescription(
        _lab_zones_params(),
        field_id="f",
        evidence_context={"ndvi_grid_evidence": evidence},
    )
    rq = out["readiness_gate"]["raster_quality"]
    assert rq is not None
    assert rq["machine_ready"] is False
    assert "valid_pixel_ratio_below_min" in rq["blocking_reasons"]
    assert out["ready_for_machine_export"] is False
    assert any("جودة الصور دون عتبة" in w for w in out["warnings"])


# 3 ── VRA advisory stale-scene warning (good ratios ⇒ still machine-ready) ───
def test_vra_warns_stale_scene():
    evidence = build_ndvi_grid_evidence(
        field_id="f",
        acquisition_date="2000-01-01",  # far past ⇒ stale regardless of today
        valid_pixel_ratio=0.92,
        coverage_ratio=0.88,
        cloud_cover=0.1,
    )
    out = generate_vra_prescription(
        _lab_zones_params(),
        field_id="f",
        evidence_context={"ndvi_grid_evidence": evidence},
    )
    rq = out["readiness_gate"]["raster_quality"]
    assert rq["machine_ready"] is True  # ratios pass; staleness is advisory only
    assert "stale_scene" in rq["warnings"]
    assert any("قديم" in w for w in out["warnings"])


# 4 ── pack→evidence plumbing makes k-means fire (not strips) ─────────────────
def test_productivity_zones_use_ndvi_grid_when_available():
    grid = [[0.15, 0.15]] * 2 + [[0.82, 0.82]] * 2
    pack = {"imagery_timeline": {"ndvi_grid": grid}}
    ctx = RE.zoning_evidence_context(pack)  # forwards the grid from the pack
    assert ctx.get("ndvi_grid") == grid
    out = propose_productivity_zones({"bbox": _BBOX, "zone_count": 2, **ctx}, field_id="f")
    assert out["method"] == "ndvi_kmeans_clustering"
    assert RE.zoning_is_evidence_backed(out["method"]) is True


# 5 ── geometry-only zoning can never anchor machine export ───────────────────
def test_no_machine_export_from_geometry_fallback():
    good = build_ndvi_grid_evidence(
        field_id="f",
        acquisition_date="2026-06-25",
        valid_pixel_ratio=0.95,
        coverage_ratio=0.9,
    )
    verdict = evaluate_machine_readiness(
        good, zoning_method="geometry_seeded_zoning_fallback", now="2026-06-26"
    )
    assert verdict["machine_ready"] is False
    assert "geometry_fallback_zoning_not_machine_exportable" in verdict["blocking_reasons"]
    # same evidence with an evidence-backed zoning method is machine-ready.
    ok = evaluate_machine_readiness(good, zoning_method="ndvi_kmeans_clustering", now="2026-06-26")
    assert ok["machine_ready"] is True


# extra ── fail-closed on missing metrics (never assume unseen quality) ───────
def test_missing_quality_metrics_block():
    verdict = evaluate_machine_readiness(build_ndvi_grid_evidence(field_id="f"), now="2026-06-26")
    assert verdict["machine_ready"] is False
    assert "missing_valid_pixel_ratio" in verdict["blocking_reasons"]
    assert "missing_coverage_ratio" in verdict["blocking_reasons"]
    assert "unknown_scene_age" in verdict["warnings"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
