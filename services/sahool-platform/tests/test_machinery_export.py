"""INT-004 live machinery integration — ISOXML TaskData export from a saved
prescription + operator controller profile. Pure logic (no DB): proves a real
machine-uploadable artifact is produced for compatible inputs and that every
incompatible/incomplete input fails closed (no partial TaskData)."""

from __future__ import annotations

from xml.etree.ElementTree import fromstring

import pytest

pytestmark = pytest.mark.unit

from api.machinery_export import (  # noqa: E402 — after pathed import in conftest
    MachineryExportError,
    build_prescription_isoxml,
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
