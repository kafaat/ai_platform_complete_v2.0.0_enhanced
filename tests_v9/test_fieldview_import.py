"""Synthetic documented-format exports, not customer or live vendor evidence."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.fieldview_import_preview import (
    export_fieldview_projection,
    preview_fieldview_planting,
)

pytestmark = pytest.mark.unit


def document():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]]],
                },
                "properties": {
                    "id": "synthetic-export-1",
                    "resourceOwner": {"id": "not-a-tenant", "email": "synthetic@example.invalid"},
                    "field": {"id": "vendor-field-1", "name": "Synthetic plot"},
                    "plantingActivity": {
                        "date": "2026-06-01",
                        "crop": "corn",
                        "area": {"q": 1.5, "u": "hectare"},
                    },
                },
            }
        ],
    }


def bindings(tenant="t1"):
    return {
        "vendor-field-1": {
            "tenant_id": tenant,
            "field_id": "internal-field",
            "season_id": "internal-season",
        }
    }


def preview(doc=None, mapping=None):
    return preview_fieldview_planting(
        document() if doc is None else doc,
        tenant_id="t1",
        field_bindings=bindings() if mapping is None else mapping,
    )


@pytest.mark.parametrize("value", [None, [], "FeatureCollection", 7, 1.5, True])
def test_non_object_document_is_rejected_with_validation_error(value):
    with pytest.raises(ValueError, match="FeatureCollection required"):
        preview_fieldview_planting(value, tenant_id="t1", field_bindings=bindings())


def test_documented_summary_reuses_ledger_without_claiming_persistence():
    result = preview()
    assert (
        result["row_count"] == 1 and result["persisted"] is False and result["erp_write"] is False
    )
    row = result["previews"][0]
    payload = row["ledger_payload"]
    assert payload["field_id"] == "internal-field" and payload["season_id"] == "internal-season"
    assert payload["operation_date"] == "2026-06-01" and payload["operation_type"] == "planting"
    assert payload["cost_amount"] is None and "water" not in payload and "inputs" not in payload
    assert payload["provenance"]["persisted"] is False
    assert row["area_ha"] == 1.5 and row["date_precision"] == "day"
    assert "resourceOwner" not in row["source_feature"]["properties"]
    assert "synthetic@example.invalid" not in json.dumps(result)


def test_supported_semantics_survive_round_trip_without_replacing_field_identity():
    first = preview()
    second = preview(export_fieldview_projection(first))
    assert first["previews"] == second["previews"]
    assert second["previews"][0]["source_feature"]["properties"]["field"]["id"] == "vendor-field-1"
    assert second["previews"][0]["ledger_payload"]["field_id"] == "internal-field"


@pytest.mark.parametrize("mapping", [{}, bindings("t2")])
def test_missing_or_cross_tenant_binding_rejected_even_with_resource_owner(mapping):
    with pytest.raises(PermissionError):
        preview(mapping=mapping)


def test_deduplication_and_conflict_are_separate():
    doc = document()
    doc["features"].append(copy.deepcopy(doc["features"][0]))
    result = preview(doc)
    assert result["row_count"] == 1 and result["duplicates_within_batch"] == 1
    doc["features"][1]["properties"]["plantingActivity"]["area"]["q"] = 2
    with pytest.raises(ValueError, match="conflicting"):
        preview(doc)


@pytest.mark.parametrize("value", [None, -1, 0, True, float("nan"), float("inf"), "1.5"])
def test_invalid_area_is_not_coerced(value):
    doc = document()
    doc["features"][0]["properties"]["plantingActivity"]["area"]["q"] = value
    with pytest.raises(ValueError, match="area"):
        preview(doc)


def test_unknown_unit_and_invalid_geometry_are_rejected():
    doc = document()
    doc["features"][0]["properties"]["plantingActivity"]["area"]["u"] = "local-unit"
    with pytest.raises(ValueError, match="hectare"):
        preview(doc)
    doc = document()
    doc["features"][0]["geometry"]["coordinates"][0][0][0] = [200, 15]
    with pytest.raises(ValueError, match="geometry"):
        preview(doc)


def _crs_target(doc, level):
    if level == "collection":
        return doc
    feature = doc["features"][0]
    return feature if level == "feature" else feature["geometry"]


@pytest.mark.parametrize("level", ["collection", "feature", "geometry"])
def test_explicit_coordinate_system_survives_projection_and_round_trip(level):
    doc = document()
    crs = {"type": "name", "properties": {"name": "EPSG:4326"}}
    _crs_target(doc, level)["crs"] = crs
    original = copy.deepcopy(doc)
    first = preview(doc)
    exported = export_fieldview_projection(first)
    assert exported["features"][0]["geometry"]["crs"] == crs
    assert preview(exported)["previews"] == first["previews"]
    assert doc == original


@pytest.mark.parametrize("level", ["collection", "feature", "geometry"])
@pytest.mark.parametrize("crs", [None, {"type": "name", "properties": {"name": "EPSG:3857"}}])
def test_unsupported_or_unknown_crs_at_any_level_is_rejected(level, crs):
    doc = document()
    # Small projected coordinates also fit degree ranges: range checks alone
    # must not establish the coordinate system.
    _crs_target(doc, level)["crs"] = crs
    with pytest.raises(ValueError, match="EPSG:4326"):
        preview(doc)


@pytest.mark.parametrize("level", ["collection", "feature"])
def test_valid_child_crs_does_not_hide_an_unsupported_parent(level):
    doc = document()
    _crs_target(doc, level)["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    doc["features"][0]["geometry"]["crs"] = {"type": "name", "properties": {"name": "EPSG:4326"}}
    with pytest.raises(ValueError, match="EPSG:4326"):
        preview(doc)


def test_empty_collection_cannot_bypass_crs_validation():
    doc = {"type": "FeatureCollection", "features": [], "crs": None}
    with pytest.raises(ValueError, match="EPSG:4326"):
        preview(doc)


def test_offline_cli_produces_reviewable_preview(tmp_path):
    source, mapping, output = (
        tmp_path / name for name in ("source.json", "map.json", "preview.json")
    )
    source.write_text(json.dumps(document()), encoding="utf-8")
    mapping.write_text(json.dumps(bindings()), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ops.fieldview_import_preview",
            "--input",
            str(source),
            "--bindings",
            str(mapping),
            "--tenant",
            "t1",
            "--output",
            str(output),
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "services/sahool-platform")},
        check=True,
        capture_output=True,
        timeout=20,
    )
    assert json.loads(output.read_text(encoding="utf-8"))["previews"] == preview()["previews"]
