from __future__ import annotations

from copy import deepcopy

from api.machinery_export import generate_export_package
from core.machinery_as_applied import verify_machinery_as_applied
from core.yield_map_processing import process_yield_records


def _row(i, y, *, moisture=12.0, lon=44.0, lat=15.0):
    return {
        "record_id": f"r{i}",
        "source_record_id": f"s{i}",
        "longitude": lon + i * 0.0001,
        "latitude": lat + i * 0.0001,
        "yield_kg_ha": y,
        "moisture_pct": moisture,
        "harvested_at": f"2026-08-01T10:{i:02d}:00+00:00",
        "record_sha256": f"{i:064x}"[-64:],
    }


def test_yield_processing_is_non_destructive_deterministic_and_removes_extreme_outlier():
    rows = [_row(i, y) for i, y in enumerate([4000, 4100, 3900, 4050, 3950, 50000], start=1)]
    original = deepcopy(rows)
    a = process_yield_records(source_sha256="a" * 64, rows=rows, standard_moisture_pct=14.0)
    b = process_yield_records(source_sha256="a" * 64, rows=rows, standard_moisture_pct=14.0)
    assert rows == original
    assert a.processing_digest == b.processing_digest
    assert a.outlier_record_count == 1
    assert a.accepted_record_count == 5
    assert a.moisture_adjusted_count == 5
    assert {s.productivity_class for s in a.samples} <= {"low", "medium", "high"}


def test_yield_processing_deduplicates_only_projection_not_raw_evidence():
    a = _row(1, 4000)
    dup = dict(a, record_id="different-record-id", source_record_id="different-source")
    projection = process_yield_records(source_sha256="b" * 64, rows=[a, dup])
    assert projection.raw_record_count == 2
    assert projection.accepted_record_count == 1
    assert projection.duplicate_record_count == 1


def _profile():
    return {
        "profile_id": "mp1",
        "equipment_id": "eq1",
        "vendor": "generic_isobus",
        "controller_model": "TC",
        "task_controller_version": "4.3",
        "supported_units": ["kg/ha"],
        "supports_isoxml": True,
        "active": True,
    }


def _prescription():
    return {
        "prescription_id": "rx1",
        "field_id": "f1",
        "season_id": "s1",
        "name": "N plan",
        "product_type": "fertility",
        "zones": [
            {
                "zone_id": "mz-low",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[44, 15], [44.1, 15], [44.1, 15.1], [44, 15.1], [44, 15]]],
                },
                "rate": 100.0,
                "unit": "kg/ha",
                "source_lineage": {"yield_processing_digest": "c" * 64},
            },
            {
                "zone_id": "mz-high",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[44.1, 15], [44.2, 15], [44.2, 15.1], [44.1, 15.1], [44.1, 15]]
                    ],
                },
                "rate": 80.0,
                "unit": "kg/ha",
                "source_lineage": {"yield_processing_digest": "c" * 64},
            },
        ],
    }


def test_machine_artifact_freezes_prescription_and_zone_lineage():
    pkg = generate_export_package(
        _prescription(), _profile(), approved_recommendation_id="rx1", crop="wheat"
    )
    assert len(pkg.prescription_digest) == 64
    assert len(pkg.zone_lineage_digest) == 64
    xml = pkg.taskdata_xml.decode()
    assert "mz-low" in xml and "mz-high" in xml


def test_as_applied_verified_success_is_bound_to_artifact_and_prescription():
    pkg = generate_export_package(
        _prescription(), _profile(), approved_recommendation_id="rx1", crop="wheat"
    )
    receipt = {
        "receipt_id": "receipt-1",
        "observed_at": "2026-08-17T12:00:00Z",
        "device_id": "eq1",
        "device_identity_verified": True,
        "package_sha256": pkg.package_sha256,
        "prescription_digest": pkg.prescription_digest,
        "applied_zones": [
            {"zone_id": "mz-low", "actual_rate": 101, "unit": "kg/ha"},
            {"zone_id": "mz-high", "actual_rate": 79, "unit": "kg/ha"},
        ],
    }
    truth = verify_machinery_as_applied(
        artifact_id="artifact-1",
        expected_package_sha256=pkg.package_sha256,
        expected_prescription_digest=pkg.prescription_digest,
        expected_zones=_prescription()["zones"],
        receipt=receipt,
        allowed_rate_variance_pct=3.0,
    )
    assert truth.verification_state == "verified_success"
    assert truth.outcome_eligible is True
    assert len(truth.as_applied_digest) == 64


def test_as_applied_rate_deviation_is_verified_failure_but_still_outcome_evidence():
    pkg = generate_export_package(
        _prescription(), _profile(), approved_recommendation_id="rx1", crop="wheat"
    )
    receipt = {
        "receipt_id": "receipt-2",
        "observed_at": "2026-08-17T12:00:00Z",
        "device_id": "eq1",
        "device_identity_verified": True,
        "package_sha256": pkg.package_sha256,
        "prescription_digest": pkg.prescription_digest,
        "applied_zones": [
            {"zone_id": "mz-low", "actual_rate": 130, "unit": "kg/ha"},
            {"zone_id": "mz-high", "actual_rate": 80, "unit": "kg/ha"},
        ],
    }
    truth = verify_machinery_as_applied(
        artifact_id="artifact-1",
        expected_package_sha256=pkg.package_sha256,
        expected_prescription_digest=pkg.prescription_digest,
        expected_zones=_prescription()["zones"],
        receipt=receipt,
        allowed_rate_variance_pct=3.0,
    )
    assert truth.verification_state == "verified_failure"
    assert truth.outcome_eligible is True
    assert "zone_rate_variance_exceeded:mz-low" in truth.limitations


def test_as_applied_unverified_device_is_not_outcome_eligible():
    pkg = generate_export_package(
        _prescription(), _profile(), approved_recommendation_id="rx1", crop="wheat"
    )
    receipt = {
        "receipt_id": "receipt-3",
        "observed_at": "2026-08-17T12:00:00Z",
        "device_id": "eq1",
        "device_identity_verified": False,
        "package_sha256": pkg.package_sha256,
        "prescription_digest": pkg.prescription_digest,
        "applied_zones": [
            {"zone_id": "mz-low", "actual_rate": 100, "unit": "kg/ha"},
            {"zone_id": "mz-high", "actual_rate": 80, "unit": "kg/ha"},
        ],
    }
    truth = verify_machinery_as_applied(
        artifact_id="artifact-1",
        expected_package_sha256=pkg.package_sha256,
        expected_prescription_digest=pkg.prescription_digest,
        expected_zones=_prescription()["zones"],
        receipt=receipt,
        allowed_rate_variance_pct=3.0,
    )
    assert truth.verification_state == "unverified"
    assert truth.outcome_eligible is False


def test_prescription_boundary_canonicalizes_vra_aliases_for_machine_export():
    import importlib.util
    import sys
    from pathlib import Path

    # Avoid importing the full router application graph; execute the pydantic model
    # definitions through the normal module import used by product tests if available.
    from api.routers.prescriptions import PrescriptionCreateRequest

    req = PrescriptionCreateRequest(
        prescription_id="rx-vra",
        season_id="s1",
        name="N VRA",
        product_type="fertilizer",
        zones=[
            {
                "zone_id": "mz1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[44, 15], [44.1, 15], [44.1, 15.1], [44, 15.1], [44, 15]]],
                },
                "rate": 100,
                "unit": "kg_ha",
                "source_lineage": {"yield_processing_digest": "d" * 64},
            }
        ],
    )
    assert req.product_type == "fertility"
    assert req.zones[0].unit == "kg/ha"
    assert req.zones[0].source_lineage["yield_processing_digest"] == "d" * 64
