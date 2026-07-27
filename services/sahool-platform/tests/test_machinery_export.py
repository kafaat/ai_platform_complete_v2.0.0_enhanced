"""INT-004 live machinery integration — ISOXML TaskData export from a saved
prescription + operator controller profile. Pure logic (no DB): proves a real
machine-uploadable artifact is produced for compatible inputs and that every
incompatible/incomplete input fails closed (no partial TaskData)."""

from __future__ import annotations

import hashlib
import io
import zipfile
from xml.etree.ElementTree import fromstring

import pytest

pytestmark = pytest.mark.unit

from api.machinery_export import (  # noqa: E402 — after pathed import in conftest
    MachineryExportError,
    build_prescription_isoxml,
    generate_export_package,
    package_taskdata,
    resolve_persisted_profile,
)

_POLY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def _rx(product_type="fertility", unit="kg/ha", zones=2):
    return {
        "prescription_id": "rx-1",
        "field_id": "F1",
        "name": "north block",
        "product_type": product_type,
        "zones": [{"geometry": _POLY, "rate": 100.0 + i, "unit": unit} for i in range(zones)],
    }


def _machine(units=("kg/ha", "seeds/ha", "l/ha", "mm")):
    return {
        "vendor": "John Deere",
        "controller": "Gen4",
        "task_controller_version": "4",
        "supported_units": ",".join(units),
    }


def test_fertility_prescription_exports_real_isoxml_taskdata():
    xml = build_prescription_isoxml(_rx(), _machine(), approved_recommendation_id="rx-1")
    root = fromstring(xml)  # noqa: S314 — first-party deterministic serializer, not untrusted input
    assert root.tag == "ISO11783_TaskData"
    # product carries the (kg/ha) unit; exactly one TSK; one TZN per zone.
    assert root.find("PDT").get("C") == "kg/ha"
    assert len(root.findall(".//TSK")) == 1
    assert len(root.findall(".//TZN")) == 2


def test_seed_prescription_maps_and_exports():
    xml = build_prescription_isoxml(
        _rx(product_type="seed", unit="seeds/ha"), _machine(), approved_recommendation_id="rx-1"
    )
    assert fromstring(xml).find("PDT").get("C") == "seeds/ha"


def test_incompatible_controller_fails_closed():
    # controller supports only l/ha, prescription is kg/ha -> no partial file.
    with pytest.raises(MachineryExportError, match="unit"):
        build_prescription_isoxml(
            _rx(), _machine(units=("l/ha",)), approved_recommendation_id="rx-1"
        )


def test_incomplete_machine_profile_fails_closed():
    with pytest.raises(MachineryExportError, match="incomplete"):
        build_prescription_isoxml(
            _rx(), {"vendor": "John Deere"}, approved_recommendation_id="rx-1"
        )


def test_zero_zones_fails_closed():
    with pytest.raises(MachineryExportError, match="no zones"):
        build_prescription_isoxml(_rx(zones=0), _machine(), approved_recommendation_id="rx-1")


def test_mixed_zone_units_fail_closed():
    rx = _rx()
    rx["zones"][1]["unit"] = "lb/ac"
    with pytest.raises(MachineryExportError, match="one non-empty unit"):
        build_prescription_isoxml(rx, _machine(), approved_recommendation_id="rx-1")


def test_unsupported_product_type_fails_closed():
    with pytest.raises(MachineryExportError, match="product_type"):
        build_prescription_isoxml(
            _rx(product_type="irrigation"), _machine(), approved_recommendation_id="rx-1"
        )


def test_missing_approved_recommendation_id_fails_closed():
    with pytest.raises(MachineryExportError, match="approved recommendation"):
        build_prescription_isoxml(_rx(), _machine(), approved_recommendation_id="")


# ── persisted-profile adapter (v216 machine_control_profiles row shape) ──────


def _profile_row(active=True, supports_isoxml=True):
    # mirrors a machine_control_profiles row; note controller_model (not controller).
    return {
        "profile_id": "P1",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "equipment_id": "EQ1",
        "vendor": "John Deere",
        "controller_model": "Gen4",
        "task_controller_version": "4",
        "firmware_version": "1.2",
        "unit_system": "metric",
        "supported_units": ["kg/ha", "seeds/ha", "l/ha", "mm"],
        "supports_isoxml": supports_isoxml,
        "active": active,
    }


def test_generate_package_produces_deterministic_checksummed_artifact():
    pkg = generate_export_package(_rx(), _profile_row(), approved_recommendation_id="rx-1")
    # a real machine-uploadable ZIP carrying TASKDATA.XML
    root = fromstring(pkg.taskdata_xml)  # noqa: S314 — first-party serializer
    assert root.tag == "ISO11783_TaskData"
    with zipfile.ZipFile(io.BytesIO(pkg.package_bytes)) as zf:
        assert zf.namelist() == ["TASKDATA.XML"]
        assert zf.read("TASKDATA.XML") == pkg.taskdata_xml
    # checksum matches the packaged bytes and is a 64-char lowercase hex digest
    assert pkg.package_sha256 == hashlib.sha256(pkg.package_bytes).hexdigest()
    assert len(pkg.package_sha256) == 64 and pkg.package_sha256.islower()
    assert pkg.zone_count == 2
    # immutable snapshot freezes the resolved profile identity
    assert pkg.profile_snapshot["profile_id"] == "P1"
    assert pkg.profile_snapshot["controller_model"] == "Gen4"
    assert pkg.profile_snapshot["supported_units"] == sorted(
        pkg.profile_snapshot["supported_units"]
    )


def test_packaging_is_byte_reproducible():
    # same inputs -> byte-identical package -> identical checksum (provenance).
    a = generate_export_package(_rx(), _profile_row(), approved_recommendation_id="rx-1")
    b = generate_export_package(_rx(), _profile_row(), approved_recommendation_id="rx-1")
    assert a.package_bytes == b.package_bytes
    assert a.package_sha256 == b.package_sha256


def test_package_taskdata_is_deterministic_zip():
    xml = b"<ISO11783_TaskData/>"
    assert package_taskdata(xml) == package_taskdata(xml)


def test_inactive_profile_fails_closed():
    with pytest.raises(MachineryExportError, match="inactive"):
        generate_export_package(
            _rx(), _profile_row(active=False), approved_recommendation_id="rx-1"
        )


def test_profile_without_isoxml_support_fails_closed():
    with pytest.raises(MachineryExportError, match="ISOXML"):
        resolve_persisted_profile(_profile_row(supports_isoxml=False))


def test_missing_profile_row_fails_closed():
    # an RLS-scoped lookup miss (wrong tenant / no such id) surfaces as None.
    with pytest.raises(MachineryExportError, match="not found or not authorized"):
        generate_export_package(_rx(), None, approved_recommendation_id="rx-1")


def test_persisted_incompatible_controller_units_fail_closed():
    row = _profile_row()
    row["supported_units"] = ["l/ha"]  # cannot carry the kg/ha prescription
    with pytest.raises(MachineryExportError, match="unit"):
        generate_export_package(_rx(), row, approved_recommendation_id="rx-1")
