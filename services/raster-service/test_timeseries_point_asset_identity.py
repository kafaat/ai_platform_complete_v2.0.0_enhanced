"""S4-a — نقطة ``/v1/fields/{id}/timeseries`` تحمل هويّة الأصل لا الرقم وحده.

المستهلك (محاكاة الموسم التاريخيّ في المنصّة) يبني بصمة المدخلات من صفوف هذه النقاط.
نقطةٌ تحمل ``scene_id`` وحده لا تُميّز COG أُعيد حسابه على **حدٍّ أحدث** للحقل لنفس
التاريخ والمشهد: الرقم نفسه، الهويّة مختلفة. فنُحمّل النقطة ما تحمله الشبكة فعلاً —
``geometry_revision`` من هويّة الشبكة و``source_uri`` (الأصل المقروء) من نَسَب المنتج —
و``None`` حين يغيب، بلا تلفيق.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from raster_indicator_product import from_grid_response  # noqa: E402
from raster_validated_product import ProvenanceRecord  # noqa: E402
from routers import fields  # noqa: E402


def _grid(*, revision, source_uri, scene_id="S2A_T38PNA_20250110"):
    payload = {
        "field_id": "field-1",
        "index": "ndvi",
        "real_data": True,
        "date": "2025-01-10",
        "stats": {"mean": 0.5},
        "valid_pixel_ratio": 0.9,
        "coverage_ratio": 0.95,
        "cloud_pct": 10.0,
        "grid_identity": (
            {"crs": "EPSG:4326", "transform": [1, 0, 0, 0, -1, 0], "geometry_revision": revision}
            if revision is not None
            else None
        ),
    }
    provenance = (
        ProvenanceRecord(scene_id=scene_id, source_uri=source_uri)
        if source_uri is not None
        else None
    )
    payload["indicator_product"] = from_grid_response(payload, provenance=provenance)
    return payload


async def _points(monkeypatch, grid_payload):
    async def allow_field(field_id: str, **kwargs):
        return None

    async def real_grid(field_id, index, date, grid):
        return grid_payload

    monkeypatch.setattr(fields, "_require_field_tenant", allow_field)
    monkeypatch.setattr(fields, "_real_field_grid", real_grid)
    out = await fields.field_timeseries("field-1", index="ndvi", dates="2025-01-10", grid=16)
    return out["points"]


@pytest.mark.asyncio
async def test_point_carries_geometry_revision_and_source_asset(monkeypatch):
    (point,) = await _points(
        monkeypatch, _grid(revision=3, source_uri="s3://rasters/field-1/ndvi/r3.tif")
    )
    assert point["scene_id"] == "S2A_T38PNA_20250110"
    assert point["geometry_revision"] == 3
    assert point["source_uri"] == "s3://rasters/field-1/ndvi/r3.tif"


@pytest.mark.asyncio
async def test_same_scene_on_new_boundary_is_a_distinct_point(monkeypatch):
    """نفس المشهد والرقم، حدٌّ أحدث ⇒ نقطتان مختلفتان (لا هويّةٌ واحدةٌ لأصلين)."""
    (old,) = await _points(monkeypatch, _grid(revision=1, source_uri="s3://r/f/ndvi/r1.tif"))
    (new,) = await _points(monkeypatch, _grid(revision=2, source_uri="s3://r/f/ndvi/r2.tif"))
    assert old["mean"] == new["mean"] and old["scene_id"] == new["scene_id"]
    assert old != new


@pytest.mark.asyncio
async def test_unknown_identity_stays_none_not_fabricated(monkeypatch):
    (point,) = await _points(monkeypatch, _grid(revision=None, source_uri=None))
    assert point["geometry_revision"] is None
    assert point["source_uri"] is None
    assert point["scene_id"] is None
