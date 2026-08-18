from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_yield_qc_is_projection_not_raw_mutation():
    src = text("services/sahool-platform/core/yield_map_processing.py")
    assert "never edits or replaces" in src
    assert "yield_map_processing.v1" in src


def test_existing_yield_route_hosts_processing_without_new_route():
    src = text("services/sahool-platform/api/routers/yield_map_ingestion.py")
    assert "process_yield_records" in src
    assert src.count('@router.get("/api/v1/fields/{field_id}/yield-map-records")') == 1


def test_vra_and_saved_prescription_preserve_source_lineage():
    engine = text("services/ai_agronomist/vra_prescription_engine.py")
    router = text("services/sahool-platform/api/routers/prescriptions.py")
    assert '"source_lineage": _zone_source_lineage(zone, ctx)' in engine
    assert "source_lineage: dict" in router


def test_machine_export_remains_artifact_boundary_only():
    src = text("services/sahool-platform/api/machinery_export.py")
    assert "does NOT:" in src
    assert "physical\nexecution" in src or "physical execution" in src
    assert "prescription_digest" in src
    assert "zone_lineage_digest" in src


def test_as_applied_contract_has_no_transport_or_database_side_effect():
    src = text("services/sahool-platform/core/machinery_as_applied.py")
    assert "does not claim a controller transport exists" in src
    assert "asyncpg" not in src
    assert "httpx" not in src
    assert "INSERT INTO" not in src
