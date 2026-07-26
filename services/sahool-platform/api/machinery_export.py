"""api/machinery_export.py — INT-004 live external-machinery integration.

Turns a **saved** manual VRT prescription + an operator-supplied controller
profile into an ISOXML TaskData artifact the equipment can import. This is the
live consumer that wires the ``core/isoxml_vrt`` export contract (previously
groundwork with no caller) into a real request path.

Honesty: this invents nothing. Every zone/rate/unit/geometry comes from the
stored prescription; the machine capabilities come from the request. An unknown
product type, zero zones, mixed/unsupported units, an incomplete profile, or an
incompatible controller **fail closed** — no partial or invalid TaskData is ever
emitted. It produces the machine-uploadable file at the platform boundary; it
does not itself drive a physical controller (that remains an operator upload
step — so this is not an end-to-end runtime claim).
"""

from __future__ import annotations

from core.isoxml_vrt import (
    ISOXMLTask,
    MachineProfile,
    ProductProfile,
    VRTZone,
    export_taskdata_xml,
)

# Saved-prescription product_type -> ISOXML prescription kind. The saved model
# (routers/prescriptions.py) is deliberately narrow: {seed, fertility}.
_KIND_MAP = {"seed": "seed", "fertility": "fertilizer"}
MACHINE_REQUIRED = ("vendor", "controller", "task_controller_version")


class MachineryExportError(ValueError):
    """A saved prescription could not be turned into a valid machine task."""


def build_machine_profile(machine: dict) -> MachineProfile:
    """Build a controller profile from request fields, fail-closed on gaps."""
    missing = [k for k in MACHINE_REQUIRED if not str(machine.get(k, "") or "").strip()]
    if missing:
        raise MachineryExportError(f"machine profile is incomplete: missing {', '.join(missing)}")
    units = machine.get("supported_units") or []
    if isinstance(units, str):
        units = [u.strip() for u in units.split(",") if u.strip()]
    return MachineProfile(
        vendor=str(machine["vendor"]).strip(),
        controller=str(machine["controller"]).strip(),
        task_controller_version=str(machine["task_controller_version"]).strip(),
        supported_units={str(u).strip() for u in units if str(u).strip()},
        supports_isoxml=bool(machine.get("supports_isoxml", True)),
    )


def build_prescription_isoxml(
    prescription: dict,
    machine: dict,
    *,
    approved_recommendation_id: str,
    crop: str = "",
) -> bytes:
    """ISOXML TaskData bytes for a saved prescription + machine profile.

    ``approved_recommendation_id`` is the reviewed artifact being exported (the
    saved prescription id) — required by the ISOXML contract so an exported task
    always traces to an approved source.
    """
    product_type = str(prescription.get("product_type", "") or "").strip()
    kind = _KIND_MAP.get(product_type)
    if kind is None:
        raise MachineryExportError(f"unsupported prescription product_type {product_type!r}")
    raw_zones = prescription.get("zones") or []
    if not isinstance(raw_zones, list) or not raw_zones:
        raise MachineryExportError("prescription has no zones to export")
    units = {str(z.get("unit", "") or "").strip() for z in raw_zones}
    if len(units) != 1 or "" in units:
        raise MachineryExportError("all prescription zones must share one non-empty unit")
    unit = units.pop()
    if not str(approved_recommendation_id or "").strip():
        raise MachineryExportError("approved recommendation id is required")
    machine_profile = build_machine_profile(machine)
    try:
        product = ProductProfile(
            name=str(prescription.get("name") or kind), product_type=kind, unit=unit
        )
        zones = [
            VRTZone(
                zone_id=f"ZN{i + 1}",
                rate=float(z["rate"]),
                unit=str(z["unit"]).strip(),
                geometry=z["geometry"],
            )
            for i, z in enumerate(raw_zones)
        ]
        task = ISOXMLTask(
            task_id=str(prescription.get("prescription_id") or approved_recommendation_id),
            field_id=str(prescription.get("field_id") or ""),
            crop=str(crop or ""),
            prescription_kind=kind,
            approved_recommendation_id=str(approved_recommendation_id).strip(),
            product=product,
            machine=machine_profile,
            zones=zones,
        )
    except (ValueError, KeyError, TypeError) as exc:
        # ProductProfile/VRTZone/ISOXMLTask enforce unit/geometry/controller
        # compatibility; surface any breach as a fail-closed export error.
        raise MachineryExportError(str(exc)) from exc
    return export_taskdata_xml(task)
