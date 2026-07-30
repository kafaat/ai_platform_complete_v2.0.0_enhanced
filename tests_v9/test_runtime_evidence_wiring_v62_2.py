"""تحقّق V62.2 — وصل الأدلّة الحيّة (NDVI/غيوم) + بوّابة VRA + نقطة معاينة التصدير.

- ``runtime_evidence``: اشتقاق cloud_risk (صريح/نسبة/جاهز-إجماليّ)، تمرير ndvi_grid.
- بوّابة VRA: مناطق مشتقّة من الهندسة فقط ⇒ ``zoning_evidence_backed=False`` + تحذير.
- تتبّع الكنتور (rasterio) خلف راية صريحة — الافتراضيّ حتميّ.
- نقطة ``/v1/prescription/export-preview`` تُرجع معاينة غير قابلة للتنفيذ (محروسة fastapi).

منطق صرف عدا نقطة الـHTTP (importorskip) — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import field_boundary_backends as B  # noqa: E402
from services.ai_agronomist import runtime_evidence as RE  # noqa: E402
from services.ai_agronomist import vra_prescription_engine as V  # noqa: E402

_GEOM = {
    "type": "Polygon",
    "coordinates": [[[44.0, 16.0], [44.1, 16.0], [44.1, 16.1], [44.0, 16.0]]],
}


# ── runtime evidence derivation ─────────────────────────────────────────────
def test_derive_cloud_risk_sources():
    assert RE.derive_cloud_risk({"imagery_timeline": {"cloud_risk": 0.4}}) == 0.4
    assert RE.derive_cloud_risk({"imagery_timeline": {"mean_cloud_pct": 90}}) == 0.9
    # 2 ready of 10 total ⇒ 0.8 cloud risk.
    assert RE.derive_cloud_risk({"imagery_timeline": {"total_dates": 10, "ready_dates": 2}}) == 0.8
    assert RE.derive_cloud_risk({"imagery_timeline": {}}) is None  # unknown


def test_boundary_imagery_context_injects_cloud():
    ctx = RE.boundary_imagery_context({"imagery_timeline": {"total_dates": 10, "ready_dates": 1}})
    assert ctx["cloud_risk"] == 0.9  # imagery present but very cloudy


def test_zoning_evidence_context_forwards_ndvi_grid():
    grid = [[0.1, 0.1], [0.8, 0.8]]
    ctx = RE.zoning_evidence_context({"ndvi_grid": grid, "imagery_timeline": {"total_dates": 5}})
    assert ctx["ndvi_grid"] == grid
    assert RE.zoning_evidence_context({"imagery_timeline": {}}).get("ndvi_grid") is None


# ── VRA readiness gate on geometry-seeded-only zones ────────────────────────
def test_vra_flags_geometry_seeded_only_zones():
    zones = [
        {
            "zone_id": "z1",
            "productivity_class": "high",
            "area_ha": 10,
            "geometry": _GEOM,
            "zoning_method": "geometry_seeded_zoning_fallback",
        },
    ]
    out = V.generate_vra_prescription(
        {"zones": zones, "product_type": "fertilizer", "allow_estimated": True}, field_id="f"
    )
    assert out["readiness_gate"]["zoning_evidence_backed"] is False
    assert any("الهندسة فقط" in w for w in out["warnings"])
    assert out["ready_for_machine_export"] is False


def test_vra_accepts_ndvi_backed_zones():
    zones = [
        {
            "zone_id": "z1",
            "productivity_class": "high",
            "area_ha": 10,
            "geometry": _GEOM,
            "zoning_method": "ndvi_kmeans_clustering",
        },
    ]
    out = V.generate_vra_prescription(
        {"zones": zones, "product_type": "fertilizer", "allow_estimated": True}, field_id="f"
    )
    assert out["readiness_gate"]["zoning_evidence_backed"] is True


# ── contour tracing is opt-in ───────────────────────────────────────────────
def test_contour_tracing_is_opt_in(monkeypatch):
    monkeypatch.delenv("SAHOOL_BOUNDARY_CONTOUR_TRACING", raising=False)
    polys = B.mask_to_polygons([[1] * 4 for _ in range(4)], [0.0, 0.0, 4.0, 4.0], min_area_px=1)
    # default (gated off) ⇒ deterministic full-bbox rectangle.
    assert polys[0]["coordinates"][0][:4] == [[0.0, 4.0], [4.0, 4.0], [4.0, 0.0], [0.0, 0.0]]


# ── export-preview endpoint (fastapi-guarded) ───────────────────────────────
def test_export_preview_endpoint_is_preview_only():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.ai_agronomist.main import app

    rx = {
        "vra_prescription": {"prescription_id": "vra-1"},
        "prescription_zones": [
            {
                "zone_id": "z1",
                "rate": 120,
                "unit": "kg_ha",
                "product_type": "fertilizer",
                "geometry": _GEOM,
            }
        ],
    }
    r = TestClient(app).post(
        "/v1/prescription/export-preview", json={"prescription": rx, "format": "geojson"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "geojson"
    assert body["machine_executable"] is False
    assert body["requires_approval"] is True
    assert body["executes_export"] is False
