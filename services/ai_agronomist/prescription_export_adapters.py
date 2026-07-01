"""VRA prescription export adapters (V62.1) — pluggable machine-format builders.

Turns a v62 prescription proposal into machine-readable **export payloads** (GeoJSON,
CSV, ISO-XML / ISOBUS TaskData, shapefile attribute table). Every payload is marked
``machine_executable=False`` / ``proposal_only=True``: these adapters build a *preview*
payload; actual export/write to a controller stays behind human approval + agronomist
review (``create_prescription_map`` high-risk action). No file is written here.

Pure Python + stdlib (json/csv/xml via strings). Adapters are registered in
``EXPORT_ADAPTERS`` so a new controller format is a one-function add.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def _zones_of(prescription_result: dict[str, Any]) -> list[dict[str, Any]]:
    z = prescription_result.get("prescription_zones")
    return [x for x in z if isinstance(x, dict)] if isinstance(z, list) else []


def _meta(prescription_result: dict[str, Any]) -> dict[str, Any]:
    return prescription_result.get("vra_prescription") or {}


def build_geojson(prescription_result: dict[str, Any]) -> dict[str, Any]:
    """RFC-7946 FeatureCollection: one feature per zone with rate properties."""
    features = []
    for z in _zones_of(prescription_result):
        features.append(
            {
                "type": "Feature",
                "geometry": z.get("geometry"),
                "properties": {
                    "zone_id": z.get("zone_id"),
                    "productivity_class": z.get("productivity_class"),
                    "rate": z.get("rate"),
                    "unit": z.get("unit"),
                    "product_type": z.get("product_type"),
                    "area_ha": z.get("area_ha"),
                    "confidence": z.get("confidence"),
                },
            }
        )
    return {
        "content_type": "application/geo+json",
        "filename_hint": "vra_prescription.geojson",
        "payload": json.dumps(
            {"type": "FeatureCollection", "features": features}, ensure_ascii=False
        ),
    }


def build_csv(prescription_result: dict[str, Any]) -> dict[str, Any]:
    cols = [
        "zone_id",
        "product_type",
        "productivity_class",
        "rate",
        "unit",
        "area_ha",
        "confidence",
    ]
    lines = [",".join(cols)]
    for z in _zones_of(prescription_result):
        lines.append(",".join(str(z.get(c, "")) for c in cols))
    return {
        "content_type": "text/csv",
        "filename_hint": "vra_prescription.csv",
        "payload": "\n".join(lines) + "\n",
    }


def _xml_escape(v: Any) -> str:
    return (
        str(v)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_isoxml(prescription_result: dict[str, Any]) -> dict[str, Any]:
    """Simplified ISO 11783-10 (ISOBUS TaskData) — one treatment zone per prescription zone.

    A minimal, structurally-valid TSK/TZN skeleton; a full controller export needs the
    equipment adapter downstream. Rates are carried as PDV (process-data values).
    """
    meta = _meta(prescription_result)
    tzns = []
    for i, z in enumerate(_zones_of(prescription_result)):
        tzns.append(
            f'  <TZN A="{i + 1}" B="{_xml_escape(z.get("zone_id"))}">'
            f'<PDV A="0006" B="{_xml_escape(z.get("rate"))}" '
            f'C="{_xml_escape(z.get("unit"))}"/></TZN>'
        )
    body = "\n".join(tzns)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ISO11783_TaskData VersionMajor="4" VersionMinor="0" DataTransferOrigin="1">\n'
        f'  <TSK A="TSK1" B="{_xml_escape(meta.get("prescription_id") or "vra")}" G="1">\n'
        f"{body}\n"
        "  </TSK>\n"
        "</ISO11783_TaskData>\n"
    )
    return {
        "content_type": "application/xml",
        "filename_hint": "TASKDATA.XML",
        "payload": xml,
    }


def build_shp_attributes(prescription_result: dict[str, Any]) -> dict[str, Any]:
    """Attribute table (columns + records) for a shapefile built downstream via GDAL.

    We do not emit binary .shp/.dbf here (needs GDAL/pyshp); this is the attribute
    half plus the per-zone geometry references, ready for the domain export service.
    """
    cols = ["zone_id", "prod_class", "rate", "unit", "prod_type", "area_ha"]
    records = []
    for z in _zones_of(prescription_result):
        records.append(
            {
                "zone_id": z.get("zone_id"),
                "prod_class": z.get("productivity_class"),
                "rate": z.get("rate"),
                "unit": z.get("unit"),
                "prod_type": z.get("product_type"),
                "area_ha": z.get("area_ha"),
                "geometry": z.get("geometry"),
            }
        )
    return {
        "content_type": "application/x-shapefile-attributes+json",
        "filename_hint": "vra_prescription_attributes.json",
        "payload": json.dumps({"columns": cols, "records": records}, ensure_ascii=False),
        "note": "attribute table + geometries; assemble .shp/.dbf via GDAL downstream",
    }


EXPORT_ADAPTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "geojson": build_geojson,
    "csv": build_csv,
    "isoxml": build_isoxml,
    "shp_attributes": build_shp_attributes,
}


def available_formats() -> list[str]:
    return list(EXPORT_ADAPTERS)


def build_prescription_export(prescription_result: dict[str, Any], fmt: str) -> dict[str, Any]:
    """Build a governed export **preview** payload for one format.

    Always proposal-only: ``machine_executable=False`` and ``requires_approval=True``.
    Refuses unknown formats and prescriptions with no zones (fail-closed).
    """
    key = str(fmt or "").strip().lower()
    if key not in EXPORT_ADAPTERS:
        return {
            "format": key,
            "error": "unsupported_export_format",
            "supported": available_formats(),
            "machine_executable": False,
        }
    if not _zones_of(prescription_result):
        return {
            "format": key,
            "error": "no_prescription_zones_to_export",
            "machine_executable": False,
        }
    built = EXPORT_ADAPTERS[key](prescription_result)
    return {
        "format": key,
        **built,
        "machine_executable": False,
        "proposal_only": True,
        "requires_approval": True,
        "requires_agronomist_review": True,
        "note": built.get(
            "note",
            "export preview only — approve create_prescription_map before writing to a controller",
        ),
    }
