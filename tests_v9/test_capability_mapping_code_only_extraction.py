"""Routes, tables and events in the capability mapping come from code, never from documents.

`capability_mapping_engine` reads route, table and event strings from every file it maps
to a capability. Before this test it did so for plans, docs, certification evidence and CI
gates too, so a plan that named a schema id next to a capability id was counted as that
capability's event evidence (found by Devin on #1602). Runtime code outside services/
(agents/, shared/, sentinel_hub/, top-level contracts) keeps its evidence.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_ENGINE = _ROOT / "scripts" / "ci" / "capability_mapping_engine.py"
_MAPPING = (
    _ROOT / "docs" / "capability-registry" / "generated" / "mapping" / "capability_mapping.json"
)

_DOCUMENTS = (
    "docs/plans/SAHOOL_UNIFIED_EXECUTION_PLAN_AR.md",
    "docs/architecture/helm_compose_workload_ledger.json",
    "certification/evidence/soil_ingest_native_postgres_20261003.json",
    "runtime-verification/functional_probes/sahool-platform.json",
    "scripts/ci/weather_service_real_contract_gate.py",
    "skills/sahool-gis/NDVI_TIMELINE.md",
    "sahool-brain/log.md",
    "README.md",
    ".github/workflows/ci.yml",
)
_CODE = (
    "services/field-management-service/main.py",
    "frontend/src/pages/LoginPage.tsx",
    "mobile/lib/main.dart",
    "migrations/v289_scouting_verification_bridge.sql",
    "tests_v9/test_x.py",
    "agents/notification/agent.py",
    "shared/nats_stream_contract.py",
    "sentinel_hub/vegetation_real.py",
    "event_publish_contracts.yaml",
)


def _engine():
    spec = importlib.util.spec_from_file_location("capability_mapping_engine", _ENGINE)
    assert spec is not None and spec.loader is not None, f"cannot load {_ENGINE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_documents_supply_no_implementation_evidence_and_code_does():
    engine = _engine()
    for path in _DOCUMENTS:
        assert not engine.supplies_implementation_evidence(path), path
    for path in _CODE:
        assert engine.supplies_implementation_evidence(path), path


def _source(value: str) -> str:
    return value.rsplit(" @ ", 1)[1].rsplit(":", 1)[0]


def test_the_generated_mapping_has_no_route_table_or_event_from_a_document():
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    sources = set()
    for cap in data["capabilities"]:
        for dim in ("routes", "database", "events"):
            for item in cap.get(dim, []):
                value = item.get("value") if isinstance(item, dict) else None
                if value and " @ " in value:
                    sources.add(_source(value))
    leaked = sorted(
        s
        for s in sources
        if s.lower().startswith(("docs/", "certification/", "sahool-brain/", "scripts/", "skills/"))
        or s.lower().endswith(".md")
    )
    assert leaked == [], leaked[:10]
    # Runtime code outside services/ is still read.
    assert "agents/notification/agent.py" in sources
    assert "event_publish_contracts.yaml" in sources
