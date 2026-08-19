"""api/machinery_export.py — INT-004 platform-side machinery-integration adapter.

Turns a **saved** manual VRT prescription + a **persisted** controller profile
(the ``machine_control_profiles`` system of record, v216) into a **machine-
uploadable ISOXML package**: a deterministic ZIP carrying ``TASKDATA.XML``, a
content checksum, and an **immutable snapshot** of the resolved profile so a
later profile edit can never change the meaning of an already-produced export.

Honest boundary (INT-004A, artifact adapter slice). This produces and can
persist the machine-uploadable artifact at the platform edge. It does NOT:
connect to a controller, transmit over CAN/ISOBUS, start an implement, or claim
a machine consumed/executed the task. Device delivery / consumption / physical
execution / runtime remain **out of scope** and unverified by this module.

Fail-closed everywhere: an unknown product type, zero zones, mixed/unsupported
units, an incomplete or inactive profile, or an incompatible controller raise
:class:`MachineryExportError` — no partial or invalid TaskData is ever emitted.
The persisted profile is the canonical production path; an inline request-body
profile is a clearly-marked dev/privileged compatibility path only.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass

from core.isoxml_vrt import (
    ISOXMLTask,
    MachineProfile,
    ProductProfile,
    VRTZone,
    export_taskdata_xml,
)
from core.machinery_artifact_identity import (
    prescription_content_digest,
    zone_lineage_digest,
)

# Saved-prescription product_type -> ISOXML prescription kind. The saved model
# (routers/prescriptions.py) is deliberately narrow: {seed, fertility}.
_KIND_MAP = {"seed": "seed", "fertility": "fertilizer"}
MACHINE_REQUIRED = ("vendor", "controller", "task_controller_version")

# The archive member name inside the machine-uploadable package. ISO 11783-10
# names the task description file TASKDATA.XML at the root of the dataset.
_TASKDATA_ARCNAME = "TASKDATA.XML"
# A fixed ZIP member timestamp so the same inputs always package to identical
# bytes (hence an identical checksum). Provenance must be reproducible.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


class MachineryExportError(ValueError):
    """A saved prescription could not be turned into a valid machine task."""


def build_machine_profile(machine: dict) -> MachineProfile:
    """Build a controller profile from a plain dict, fail-closed on gaps.

    Accepts both the inline request shape (``controller``) and the persisted
    ``machine_control_profiles`` row shape (``controller_model``) so the same
    validation guards both the canonical and the dev/privileged path.
    """
    controller = machine.get("controller") or machine.get("controller_model")
    normalized = {
        "vendor": machine.get("vendor"),
        "controller": controller,
        "task_controller_version": machine.get("task_controller_version"),
    }
    missing = [k for k in MACHINE_REQUIRED if not str(normalized.get(k, "") or "").strip()]
    if missing:
        raise MachineryExportError(f"machine profile is incomplete: missing {', '.join(missing)}")
    units = machine.get("supported_units") or []
    if isinstance(units, str):
        units = [u.strip() for u in units.split(",") if u.strip()]
    return MachineProfile(
        vendor=str(normalized["vendor"]).strip(),
        controller=str(normalized["controller"]).strip(),
        task_controller_version=str(normalized["task_controller_version"]).strip(),
        supported_units={str(u).strip() for u in units if str(u).strip()},
        supports_isoxml=bool(machine.get("supports_isoxml", True)),
    )


def resolve_persisted_profile(row: dict) -> MachineProfile:
    """Resolve a controller profile from a persisted ``machine_control_profiles``
    row, fail-closed. The row is the system of record; a missing/inactive/
    tenant-mismatched row is refused **before** this call (by the RLS-scoped
    lookup that returns ``None``). Here we refuse an *inactive* or profile that
    does not support ISOXML — a package must never be built from a profile the
    operator has retired or that cannot consume the format.
    """
    if row is None:
        raise MachineryExportError("machine profile not found or not authorized for this tenant")
    if not bool(row.get("active", True)):
        raise MachineryExportError("machine profile is inactive")
    if not bool(row.get("supports_isoxml", True)):
        raise MachineryExportError("machine profile does not support ISOXML")
    return build_machine_profile(row)


def build_profile_snapshot(row: dict, resolved: MachineProfile) -> dict:
    """An immutable snapshot of the resolved profile, embedded in the artifact
    metadata. Later edits to the mutable ``machine_control_profiles`` SoR must
    not change the meaning of an already-produced export, so we freeze exactly
    what was used at generation time (sorted units for determinism)."""
    return {
        "profile_id": str(row.get("profile_id") or ""),
        "equipment_id": (str(row["equipment_id"]) if row.get("equipment_id") else None),
        "vendor": resolved.vendor,
        "controller_model": resolved.controller,
        "task_controller_version": resolved.task_controller_version,
        "firmware_version": (str(row["firmware_version"]) if row.get("firmware_version") else None),
        "unit_system": str(row.get("unit_system") or "metric"),
        "supported_units": sorted(resolved.supported_units),
        "supports_isoxml": bool(resolved.supports_isoxml),
    }


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
                zone_id=str(z.get("zone_id") or f"ZN{i + 1}"),
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


def package_taskdata(taskdata_xml: bytes) -> bytes:
    """Package ``TASKDATA.XML`` into a **deterministic** ISOXML ZIP.

    Determinism (fixed member name, fixed timestamp, fixed order) means the same
    task always yields byte-identical package bytes and therefore an identical
    checksum — the package is provenance, so it must be reproducible."""
    buf = io.BytesIO()
    info = zipfile.ZipInfo(_TASKDATA_ARCNAME, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(info, taskdata_xml)
    return buf.getvalue()


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 — the artifact checksum stored alongside bytes."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ExportPackage:
    """The machine-uploadable artifact + its provenance. Immutable once built:
    correcting an export means producing a NEW package, never mutating one."""

    taskdata_xml: bytes
    package_bytes: bytes
    package_sha256: str
    profile_snapshot: dict
    zone_count: int
    prescription_digest: str
    zone_lineage_digest: str


def generate_export_package(
    prescription: dict,
    profile_row: dict,
    *,
    approved_recommendation_id: str,
    crop: str = "",
) -> ExportPackage:
    """End-to-end adapter core: resolve the persisted profile, validate + build
    the ISOXML TaskData, package it deterministically, checksum it, and freeze
    an immutable profile snapshot. Pure (no DB/IO) so it is unit-testable; the
    router supplies the RLS-scoped ``profile_row`` and persists the result.

    Fail-closed: any incompatibility raises :class:`MachineryExportError` and no
    package is produced. No device delivery or execution is implied.
    """
    resolved = resolve_persisted_profile(profile_row)
    snapshot = build_profile_snapshot(profile_row, resolved)
    machine = {
        "vendor": resolved.vendor,
        "controller": resolved.controller,
        "task_controller_version": resolved.task_controller_version,
        "supported_units": sorted(resolved.supported_units),
        "supports_isoxml": resolved.supports_isoxml,
    }
    taskdata_xml = build_prescription_isoxml(
        prescription, machine, approved_recommendation_id=approved_recommendation_id, crop=crop
    )
    package_bytes = package_taskdata(taskdata_xml)
    return ExportPackage(
        taskdata_xml=taskdata_xml,
        package_bytes=package_bytes,
        package_sha256=sha256_hex(package_bytes),
        profile_snapshot=snapshot,
        zone_count=len(prescription.get("zones") or []),
        prescription_digest=prescription_content_digest(prescription),
        zone_lineage_digest=zone_lineage_digest(prescription),
    )
