"""حراس Landsat thermal-only.

القرار: لا نستخدم Landsat لتكرار NDVI/NDMI/MSI/SAVI من Sentinel-2؛ نسحب منه فقط
LST كراستر مباشر، ونترك CWSI/TVDI/TCI/VHI كمشتقات محلية من LST + الطقس/NDVI.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_landsat_unique_sets_do_not_include_sentinel_duplicate_indices():
    duplicates = {"ndvi", "ndmi", "msi", "ndwi", "savi", "evi", "gndvi", "ndre"}
    assert main.LANDSAT_UNIQUE_INDICES.isdisjoint(duplicates)
    assert "lst" in main.LANDSAT_DIRECT_RASTER_INDICES
    assert main.LANDSAT_DIRECT_RASTER_INDICES <= main.LANDSAT_UNIQUE_INDICES
    assert main.LANDSAT_DERIVED_INDICES <= main.LANDSAT_UNIQUE_INDICES


def test_landsat_payload_keeps_only_thermal_urls_and_excludes_optical_bands():
    feat = {
        "id": "LC08_thermal_demo",
        "bbox": [44, 16, 45, 17],
        "properties": {"datetime": "2026-07-01T08:00:00Z", "eo:cloud_cover": 7.0},
        "assets": {
            "red": {"href": "https://example.test/red.tif"},
            "nir08": {"href": "https://example.test/nir.tif"},
            "swir16": {"href": "https://example.test/swir.tif"},
            "lwir11": {"href": "https://example.test/lst.tif", "title": "Surface Temperature"},
        },
    }
    item = main._landsat_unique_payload(feat)
    assert item is not None
    assert item["thermal_urls"] == {"lst": "https://example.test/lst.tif"}
    assert "bands_urls" not in item
    assert "ndvi" in item["excluded_duplicate_sentinel_indices"]
    assert item["direct_indices"] == ["lst"]


def test_landsat_payload_without_thermal_asset_is_dropped():
    feat = {
        "id": "LC08_optical_only_demo",
        "properties": {"datetime": "2026-07-01T08:00:00Z"},
        "assets": {"red": {"href": "https://example.test/red.tif"}},
    }
    assert main._landsat_unique_payload(feat) is None


def test_backfill_endpoint_static_rejects_landsat_duplicate_indices():
    src = (ROOT / "routers" / "fields.py").read_text(encoding="utf-8")
    assert "is_landsat_thermal" in src
    assert "LANDSAT_UNIQUE_INDICES" in src
    assert "المؤشرات المكررة مع Sentinel-2 مرفوضة" in src
    assert "_stac_search_landsat_unique" in src
    assert "IndicatorKind.lst" in src
