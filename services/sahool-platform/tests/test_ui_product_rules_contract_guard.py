from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT / "docs" / "ui" / "SAHOOL_UI_PRODUCT_RULES.md"
MODES = ROOT / "docs" / "ui" / "SAHOOL_PRODUCT_MODES_AND_FIELD_OPERATING_CONTRACT.md"
FRONTEND_CONTRACT = ROOT / "frontend" / "src" / "lib" / "fieldOperatingContract.ts"
DEGRADED_STATE = ROOT / "frontend" / "src" / "components" / "product" / "DegradedState.tsx"


def test_ui_product_rules_document_exists_and_contains_non_breakable_rules():
    src = RULES.read_text(encoding="utf-8")
    required_rules = [
        "Product Operating Contract",
        "field_id",
        "season_id",
        "active_valid_boundary",
        "evidence_snapshot_id",
        "confidence_budget",
        "outcome_recorded",
        "Layer Manager",
        "operation_id",
        "sync_status",
        "No Wide Rewrite Rule",
        "Product Mode Rule",
        "Field Readiness Score",
        "Map Clutter Control",
        "Action from Map",
        "Unified Field Timeline",
        "Design QA Gate Rule",
    ]
    for phrase in required_rules:
        assert phrase in src


def test_product_modes_and_field_operating_contract_are_documented():
    src = MODES.read_text(encoding="utf-8")
    for mode in ["basic_farm", "precision", "enterprise", "government_ngo", "demo"]:
        assert mode in src
    for role in ["Owner", "Manager", "Agronomist", "Worker", "Government/NGO supervisor"]:
        assert role in src
    for contract in [
        "Field Readiness Score",
        "Data Completeness Panel",
        "Confidence Budget",
        "Operational Priority Queue",
        "Map Clutter Control",
        "Unified Field Timeline",
        "Action from Map",
    ]:
        assert contract in src


def test_frontend_field_operating_contract_exports_state_machines_and_contract_types():
    src = FRONTEND_CONTRACT.read_text(encoding="utf-8")
    for symbol in [
        "ProductMode",
        "SahoolRole",
        "FieldState",
        "SeasonState",
        "TaskState",
        "RecommendationState",
        "SyncStatus",
        "ProductOperatingContract",
        "LayerContract",
        "ConfidenceBudget",
        "calculateFieldReadiness",
        "buildConfidenceBudget",
        "canRunFieldAnalytics",
        "MAP_CLUTTER_RULES",
        "MAP_LAYER_PRESETS",
        "UNIFIED_FIELD_TIMELINE_EVENTS",
    ]:
        assert symbol in src
    assert "boundary_validated" in src
    assert "outcome_recorded" in src
    assert "local_pending" in src
    assert "degraded_state" in src


def test_degraded_state_component_exists_for_runtime_partial_failure():
    src = DEGRADED_STATE.read_text(encoding="utf-8")
    assert "DegradedState" in src
    assert 'role="status"' in src
    assert "availableActions" in src
    assert "إعادة المحاولة" in src
