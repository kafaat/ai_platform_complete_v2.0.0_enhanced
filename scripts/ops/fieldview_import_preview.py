"""Operator CLI: preview FieldView's published 2020 planting-summary GeoJSON.

This is a file adapter, not a live FieldView connection. Bindings must come from
the authenticated caller's authorised field registry. No vendor identifier,
geometry or resourceOwner grants access or updates a SAHOOL field. Output uses
the existing farm-ledger preview contract; persistence and ERP remain separate.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from core.farm_closed_loop import OperationEvent, operation_event_to_ledger_payload

FORMAT = "fieldview.planting-summary.2020-01-16"
SOURCE = "https://dev.fieldview.com/export-format/"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: non-empty string required")
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _crs(value: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Validate every explicit legacy CRS declaration, including unknown null."""
    if "crs" not in value:
        return None
    crs = value["crs"]
    if crs != {"type": "name", "properties": {"name": "EPSG:4326"}}:
        raise ValueError(f"{name}: only EPSG:4326 is supported")
    return copy.deepcopy(crs)


def _geometry(value: Any, *, inherited_crs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the documented MultiPolygon shape without asserting land rights."""
    if not isinstance(value, dict) or value.get("type") != "MultiPolygon":
        raise ValueError("geometry: MultiPolygon required")
    crs = _crs(value, "geometry") or inherited_crs
    polygons = value.get("coordinates")
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("geometry: empty coordinates")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("geometry: empty polygon")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("geometry: closed ring with at least four positions required")
            for point in ring:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("geometry: two-dimensional longitude/latitude required")
                for coordinate, limit in zip(point, (180, 90), strict=True):
                    if (
                        isinstance(coordinate, bool)
                        or not isinstance(coordinate, (int, float))
                        or not math.isfinite(coordinate)
                        or not -limit <= coordinate <= limit
                    ):
                        raise ValueError("geometry: invalid EPSG:4326 coordinate")
    result = {"type": "MultiPolygon", "coordinates": copy.deepcopy(polygons)}
    if crs is not None:
        result["crs"] = copy.deepcopy(crs)
    return result


def preview_fieldview_planting(
    document: dict[str, Any], *, tenant_id: str, field_bindings: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Map a whole batch or reject it; repeats inside the batch are idempotent.

    A binding includes tenant_id, field_id and season_id from SAHOOL. An export
    date has day precision only. It is never converted to a fictitious timestamp.
    Only documented hectare units are accepted; local units need a reviewed map.
    """
    _text(tenant_id, "tenant_id")
    if not isinstance(document, dict):
        raise ValueError("FeatureCollection required (JSON object)")
    if document.get("type") != "FeatureCollection" or not isinstance(
        document.get("features"), list
    ):
        raise ValueError("FeatureCollection required")
    collection_crs = _crs(document, "collection")
    previews: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for feature in document["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Feature required")
        feature_crs = _crs(feature, "feature") or collection_crs
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("properties required")
        export_id = _text(properties.get("id"), "properties.id")
        field = properties.get("field")
        activity = properties.get("plantingActivity")
        if not isinstance(field, dict) or not isinstance(activity, dict):
            raise ValueError("field and plantingActivity required")
        external_field_id = _text(field.get("id"), "field.id")
        binding = field_bindings.get(external_field_id)
        if not isinstance(binding, dict) or binding.get("tenant_id") != tenant_id:
            raise PermissionError("field binding missing or tenant mismatch")
        field_id = _text(binding.get("field_id"), "binding.field_id")
        season_id = _text(binding.get("season_id"), "binding.season_id")
        day = _text(activity.get("date"), "plantingActivity.date")
        occurred_on = date.fromisoformat(day)
        if occurred_on.isoformat() != day:
            raise ValueError("date must have YYYY-MM-DD day precision")
        crop = _text(activity.get("crop"), "plantingActivity.crop")
        area = activity.get("area")
        if not isinstance(area, dict) or area.get("u") != "hectare":
            raise ValueError("only documented hectare area is supported")
        quantity = area.get("q")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or not math.isfinite(quantity)
            or quantity <= 0
        ):
            raise ValueError("planting area must be positive and finite")
        # Whitelist the supported projection. Do not copy resourceOwner/email.
        source_feature = {
            "type": "Feature",
            "geometry": _geometry(feature.get("geometry"), inherited_crs=feature_crs),
            "properties": {
                "id": export_id,
                "field": {"id": external_field_id, "name": _text(field.get("name"), "field.name")},
                "plantingActivity": {
                    "date": day,
                    "crop": crop,
                    "area": {"q": quantity, "u": "hectare"},
                },
            },
        }
        event_id = "fieldview_" + _hash([FORMAT, tenant_id, export_id])
        payload = operation_event_to_ledger_payload(
            OperationEvent(
                event_id=event_id,
                tenant_id=tenant_id,
                occurred_on=occurred_on,
                operation_type="planting",
                field_id=field_id,
                season_id=season_id,
                source=FORMAT,
            )
        )
        preview = {
            "tenant_id": tenant_id,
            "event_id": event_id,
            "ledger_payload": payload,
            "source_feature": source_feature,
            "source_projection_sha256": _hash(source_feature),
            "area_ha": quantity,
            "date_precision": "day",
            "requires_field_and_season_verification": True,
        }
        if event_id in previews:
            if previews[event_id] != preview:
                raise ValueError("conflicting content for the same FieldView export id")
            duplicates += 1
        else:
            previews[event_id] = preview
    return {
        "format": FORMAT,
        "source_specification": SOURCE,
        "persisted": False,
        "erp_write": False,
        "row_count": len(previews),
        "duplicates_within_batch": duplicates,
        "previews": list(previews.values()),
        "omitted": ["resourceOwner", "unsupported_properties"],
    }


def export_fieldview_projection(preview: dict[str, Any]) -> dict[str, Any]:
    """Round-trip the supported geometry/field/activity subset, not owner PII."""
    return {
        "type": "FeatureCollection",
        "features": [copy.deepcopy(row["source_feature"]) for row in preview["previews"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = preview_fieldview_planting(
        json.loads(args.input.read_text(encoding="utf-8")),
        tenant_id=args.tenant,
        field_bindings=json.loads(args.bindings.read_text(encoding="utf-8")),
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
