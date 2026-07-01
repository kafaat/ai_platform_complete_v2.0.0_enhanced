"""تحقّق V62.1 — محوّلات تصدير الوصفة (geojson/csv/isoxml/shp) — معاينة محكومة فقط.

- كلّ محوّل يبني حمولة صحيحة من وصفة v62.
- كلّ حمولة ``machine_executable=False`` و``requires_approval=True`` (لا تصدير آليّ).
- صيغة مجهولة ⇒ خطأ؛ وصفة بلا مناطق ⇒ خطأ (fail-closed).
- محرّك v62 يُعلن الصيغ المتاحة دون قلب ``ready_for_machine_export``.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import prescription_export_adapters as E  # noqa: E402
from services.ai_agronomist import vra_prescription_engine as V  # noqa: E402

_GEOM = {
    "type": "Polygon",
    "coordinates": [[[44.0, 16.0], [44.1, 16.0], [44.1, 16.1], [44.0, 16.0]]],
}
_RX = {
    "vra_prescription": {"prescription_id": "vra-1", "product_type": "fertilizer", "unit": "kg_ha"},
    "prescription_zones": [
        {
            "zone_id": "z1",
            "productivity_class": "high",
            "rate": 120.0,
            "unit": "kg_ha",
            "product_type": "fertilizer",
            "area_ha": 12.5,
            "confidence": 0.8,
            "geometry": _GEOM,
        },
        {
            "zone_id": "z2",
            "productivity_class": "low",
            "rate": 139.2,
            "unit": "kg_ha",
            "product_type": "fertilizer",
            "area_ha": 8.0,
            "confidence": 0.8,
            "geometry": _GEOM,
        },
    ],
}


def test_registry_lists_four_formats():
    assert set(E.available_formats()) == {"geojson", "csv", "isoxml", "shp_attributes"}


@pytest.mark.parametrize("fmt", ["geojson", "csv", "isoxml", "shp_attributes"])
def test_every_export_is_proposal_only(fmt):
    out = E.build_prescription_export(_RX, fmt)
    assert out["machine_executable"] is False
    assert out["requires_approval"] is True
    assert out["requires_agronomist_review"] is True
    assert out.get("payload")


def test_geojson_is_valid_featurecollection_with_rates():
    out = E.build_prescription_export(_RX, "geojson")
    fc = json.loads(out["payload"])
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    assert fc["features"][0]["properties"]["rate"] == 120.0
    assert fc["features"][0]["geometry"]["type"] == "Polygon"


def test_csv_has_header_and_rows():
    out = E.build_prescription_export(_RX, "csv")
    lines = out["payload"].strip().splitlines()
    assert lines[0].startswith("zone_id,product_type")
    assert len(lines) == 3  # header + 2 zones
    assert "z1" in lines[1] and "120.0" in lines[1]


def test_isoxml_has_taskdata_and_zones():
    out = E.build_prescription_export(_RX, "isoxml")
    xml = out["payload"]
    assert "<ISO11783_TaskData" in xml and "</ISO11783_TaskData>" in xml
    assert xml.count("<TZN") == 2


def test_shp_attributes_has_columns_and_records():
    out = E.build_prescription_export(_RX, "shp_attributes")
    data = json.loads(out["payload"])
    assert "zone_id" in data["columns"]
    assert len(data["records"]) == 2 and data["records"][0]["rate"] == 120.0


def test_unknown_format_and_empty_prescription_fail_closed():
    bad = E.build_prescription_export(_RX, "dwg")
    assert bad["error"] == "unsupported_export_format" and bad["machine_executable"] is False
    empty = E.build_prescription_export({"prescription_zones": []}, "geojson")
    assert empty["error"] == "no_prescription_zones_to_export"


def test_engine_advertises_formats_without_enabling_export():
    out = V.generate_vra_prescription(
        {
            "zones": [
                {"zone_id": "z1", "productivity_class": "high", "area_ha": 10, "geometry": _GEOM}
            ],
            "product_type": "fertilizer",
            "allow_estimated": True,
        },
        field_id="f",
    )
    assert set(out["vra_prescription"]["machine_export_formats"]) == {
        "geojson",
        "csv",
        "isoxml",
        "shp_attributes",
    }
    assert out["ready_for_machine_export"] is False  # advertising ≠ enabling
