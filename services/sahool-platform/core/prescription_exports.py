"""VRT prescription exporters.

Exporters are deterministic and require an approved recommendation upstream.
They do not calculate agronomic rates; they serialize already-approved zones.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from xml.etree.ElementTree import Element, SubElement, tostring


@dataclass(frozen=True)
class PrescriptionZoneRate:
    zone_id: str
    rate: float
    unit: str
    geometry: dict

    def __post_init__(self) -> None:
        if self.rate < 0:
            raise ValueError("Prescription rate must be non-negative")
        if not self.unit:
            raise ValueError("Prescription unit is required")


@dataclass(frozen=True)
class MachineProfile:
    vendor: str
    controller: str
    supports_isoxml: bool = False


def export_geojson(zones: list[PrescriptionZoneRate]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": z.geometry,
                "properties": {"zone_id": z.zone_id, "rate": z.rate, "unit": z.unit},
            }
            for z in zones
        ],
    }


def export_isoxml(
    prescription_id: str,
    zones: list[PrescriptionZoneRate],
    machine: MachineProfile | None,
) -> bytes:
    """Serialize a minimal ISOXML-like task data document.

    This is an interoperability skeleton. It fails closed without an ISOXML-capable
    machine profile so the platform does not claim controller compatibility blindly.
    """
    if machine is None or not machine.supports_isoxml:
        raise ValueError("ISOXML export requires an ISOXML-capable machine profile")
    root = Element("ISO11783_TaskData", Version="4", ManagementSoftwareManufacturer="SAHOOL")
    task = SubElement(root, "TSK", A=prescription_id)
    SubElement(root, "DVC", A=machine.vendor, B=machine.controller)
    for zone in zones:
        part = SubElement(task, "PFD", A=zone.zone_id, B=str(zone.rate), C=zone.unit)
        part.text = json.dumps(zone.geometry, ensure_ascii=False)
    return tostring(root, encoding="utf-8", xml_declaration=True)
