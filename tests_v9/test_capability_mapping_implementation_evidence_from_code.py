"""Routes, tables and events in the capability mapping come from code, never from documents.

`capability_mapping_engine` reads route, table and event strings from every file it maps
to a capability. Before this test it did so for plans and other documents too, so a plan
that named a schema id (`sahool.review-closure-register.v1`) next to `IRR-003` was counted
as irrigation event evidence. On main ee8c4c75 that gave 16 capabilities 103 events, 28
routes and 19 tables from non-code files (found by Devin on #1602).
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


def _engine():
    spec = importlib.util.spec_from_file_location("capability_mapping_engine", _ENGINE)
    assert spec is not None and spec.loader is not None, f"cannot load {_ENGINE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_code_kinds_supply_implementation_evidence():
    engine = _engine()
    kinds = engine.IMPLEMENTATION_KINDS
    for path in (
        "docs/plans/SAHOOL_UNIFIED_EXECUTION_PLAN_AR.md",
        "README.md",
        "sahool-brain/log.md",
    ):
        assert engine.classify(path) not in kinds, path
    assert engine.classify(".github/workflows/ci.yml") not in kinds
    for path in (
        "services/field-management-service/main.py",
        "frontend/src/pages/LoginPage.tsx",
        "mobile/lib/main.dart",
        "migrations/v289_scouting_verification_bridge.sql",
        "tests_v9/test_x.py",
    ):
        assert engine.classify(path) in kinds, path


def test_the_generated_mapping_has_no_route_table_or_event_from_a_document():
    engine = _engine()
    # The code kinds, spelled out so this test also reads a mapping generated before
    # IMPLEMENTATION_KINDS existed.
    code_kinds = {"backend", "web", "mobile", "database", "tests"}
    assert set(getattr(engine, "IMPLEMENTATION_KINDS", code_kinds)) == code_kinds
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    leaked = []
    for cap in data["capabilities"]:
        for dim in ("routes", "database", "events"):
            for item in cap.get(dim, []):
                value = item.get("value") if isinstance(item, dict) else None
                if not value or " @ " not in value:
                    continue
                rel = value.rsplit(" @ ", 1)[1].rsplit(":", 1)[0]
                if engine.classify(rel) not in code_kinds:
                    leaked.append(f"{cap['capability_id']} {dim}: {value}")
    assert leaked == [], leaked[:10]
