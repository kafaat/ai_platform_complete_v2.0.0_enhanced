"""ISOXML/VRT export contracts for real machinery workflows.

This module deliberately serializes only *approved* prescription zones and fails
closed when a machine/controller profile is incomplete.  It does not calculate
agronomic rates and it does not bypass the Recommendation Engine.  The output is
an ISOXML-compatible TaskData skeleton with deterministic identifiers, product
metadata, controller capability checks, and per-zone Treatment Zone entries that
can be transformed by an equipment-specific adapter before field upload.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Literal
from xml.etree.ElementTree import Element, SubElement, tostring

PrescriptionKind = Literal["fertilizer", "seed", "irrigation", "spray"]

_ALLOWED_UNITS = {
    "fertilizer": {"kg/ha", "lb/ac"},
    "seed": {"seeds/ha", "seeds/m2"},
    "irrigation": {"mm", "m3/ha"},
    "spray": {"l/ha", "gal/ac"},
}

_VENDOR_UNITS = {
    "john_deere": {"kg/ha", "seeds/ha", "l/ha", "mm"},
    "trimble": {"kg/ha", "seeds/ha", "l/ha", "m3/ha"},
    "agleader": {"kg/ha", "seeds/ha", "l/ha"},
    "cnh": {"kg/ha", "seeds/ha", "l/ha"},
    "generic_isobus": {"kg/ha", "lb/ac", "seeds/ha", "seeds/m2", "l/ha", "gal/ac", "mm", "m3/ha"},
}


def _safe_id(value: str, prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or prefix
    digest = sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{cleaned[:32]}_{digest}"


@dataclass(frozen=True)
class MachineProfile:
    """Controller capability profile.

    A machine profile is required because ISOXML compatibility is not one flag;
    controller families differ in accepted units, products, and import tooling.
    """

    vendor: str
    controller: str
    task_controller_version: str
    supported_units: set[str] = field(default_factory=set)
    supports_isoxml: bool = True

    def normalized_vendor(self) -> str:
        return self.vendor.lower().replace(" ", "_").replace("-", "_")

    def effective_units(self) -> set[str]:
        base = set(_VENDOR_UNITS.get(self.normalized_vendor(), _VENDOR_UNITS["generic_isobus"]))
        return base & self.supported_units if self.supported_units else base


@dataclass(frozen=True)
class ProductProfile:
    name: str
    product_type: PrescriptionKind
    unit: str
    product_id: str | None = None

    def __post_init__(self) -> None:
        if self.unit not in _ALLOWED_UNITS[self.product_type]:
            raise ValueError(f"unit {self.unit!r} is not valid for {self.product_type}")


@dataclass(frozen=True)
class VRTZone:
    zone_id: str
    rate: float
    unit: str
    geometry: dict

    def __post_init__(self) -> None:
        if self.rate < 0:
            raise ValueError("zone rate must be non-negative")
        if not self.unit:
            raise ValueError("zone unit is required")
        if not isinstance(self.geometry, dict) or self.geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError("zone geometry must be Polygon or MultiPolygon GeoJSON")


@dataclass(frozen=True)
class ISOXMLTask:
    task_id: str
    field_id: str
    crop: str
    prescription_kind: PrescriptionKind
    approved_recommendation_id: str
    product: ProductProfile
    machine: MachineProfile
    zones: list[VRTZone]

    def __post_init__(self) -> None:
        if not self.zones:
            raise ValueError("ISOXML task requires at least one VRT zone")
        if not self.approved_recommendation_id:
            raise ValueError("approved recommendation id is required")
        if self.product.product_type != self.prescription_kind:
            raise ValueError("product type must match prescription kind")
        if not self.machine.supports_isoxml:
            raise ValueError("machine profile does not support ISOXML")
        if self.product.unit not in self.machine.effective_units():
            raise ValueError(f"machine profile does not support unit {self.product.unit}")
        for zone in self.zones:
            if zone.unit != self.product.unit:
                raise ValueError("all zone units must match product unit")


def export_taskdata_xml(task: ISOXMLTask) -> bytes:
    """Export deterministic TaskData XML for an approved VRT prescription.

    The XML contains enough structure for downstream equipment adapters while
    staying conservative: geometry is embedded as a vendor-neutral GeoJSON note,
    and controller-specific binary/shape packaging is intentionally left to the
    adapter layer.
    """

    root = Element(
        "ISO11783_TaskData",
        VersionMajor="4",
        VersionMinor="3",
        ManagementSoftwareManufacturer="SAHOOL",
        ManagementSoftwareVersion="v13",
    )
    SubElement(root, "CCT", A="CCT_SAHOOL", B="SAHOOL")
    device = SubElement(
        root,
        "DVC",
        A=_safe_id(task.machine.vendor, "DVC"),
        B=task.machine.vendor,
        C=task.machine.controller,
        D=task.machine.task_controller_version,
    )
    product_id = task.product.product_id or _safe_id(task.product.name, "PDT")
    SubElement(root, "PDT", A=product_id, B=task.product.name, C=task.product.unit)
    tsk = SubElement(
        root,
        "TSK",
        A=_safe_id(task.task_id, "TSK"),
        B=task.field_id,
        C=task.crop,
        D=task.prescription_kind,
        E=task.approved_recommendation_id,
    )
    SubElement(tsk, "DVCRef", A=device.attrib["A"])
    SubElement(tsk, "PDTRef", A=product_id)
    for idx, zone in enumerate(task.zones, start=1):
        tzn = SubElement(
            tsk,
            "TZN",
            A=_safe_id(zone.zone_id, "TZN"),
            B=str(idx),
            C=zone.zone_id,
        )
        SubElement(tzn, "VPN", A=product_id, B=f"{zone.rate:.6g}", C=zone.unit)
        geom = SubElement(tzn, "GEOM", A="geojson")
        geom.text = _compact_geojson(zone.geometry)
    return tostring(root, encoding="utf-8", xml_declaration=True)


def _compact_geojson(geometry: dict) -> str:
    import json

    return json.dumps(geometry, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def validate_machine_task(task: ISOXMLTask) -> dict[str, object]:
    """Return a machine-readiness report without producing a file."""

    return {
        "ready": True,
        "vendor": task.machine.normalized_vendor(),
        "controller": task.machine.controller,
        "unit": task.product.unit,
        "zones": len(task.zones),
        "requires_adapter_packaging": True,
        "approved_recommendation_id": task.approved_recommendation_id,
    }
