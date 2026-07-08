from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
CLIENT = PLATFORM / "api" / "decision_service_client.py"
CONTRACT = ROOT / "docs" / "architecture" / "DECISION_SERVICE_BOUNDARY_CONTRACT.md"
DB_OWNERSHIP = ROOT / "docs" / "architecture" / "db_ownership.yml"
SERVICE_MAIN = ROOT / "services" / "decision-service" / "main.py"
BASELINE = ROOT / "docs" / "architecture" / "platform_python_module_baseline.json"

LOOP_TABLES = [
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
]


def test_p4_decision_service_runtime_exists_and_names_owned_tables():
    text = SERVICE_MAIN.read_text(encoding="utf-8", errors="ignore")
    for token in [
        "FastAPI",
        "/v1/decisions/record",
        "/v1/outcomes/record",
        "/v1/learning/updates",
        "rejected_untraceable",
    ]:
        assert token in text
    for table in LOOP_TABLES:
        assert table in text


def test_p4_platform_decision_client_is_the_transport_boundary():
    text = CLIENT.read_text(encoding="utf-8", errors="ignore")
    required = [
        "DEFAULT_DECISION_SERVICE_URL",
        "decision_get_json",
        "decision_post_json",
        "X-Agent-Token",
        "X-Tenant-Id",
        "/v1/decisions/record",
        "/v1/outcomes/record",
        "/v1/learning/updates",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, repr(missing)


def test_p4_loop_tables_are_platform_sor_with_decision_service_mirror_interim():
    """INTERIM: loop tables are the platform's temporary Source of Record, mirrored to
    decision-service.  Ownership honestly reflects the authoritative writer (sahool-platform)
    and marks decision-service as the not-yet-SoR mirror — not the sole writer any more."""
    text = DB_OWNERSHIP.read_text(encoding="utf-8", errors="ignore")
    violations = []
    for table in LOOP_TABLES:
        pattern = (
            rf"  {table}:\n    owner: sahool-platform\n    writers: \[sahool-platform\]\n"
            rf"    mirror: decision-service\n    status: interim-bridge"
        )
        if not re.search(pattern, text):
            violations.append(table)
    assert not violations, repr(violations)


def test_p4_contract_documents_boundary_and_legacy_status():
    text = CONTRACT.read_text(encoding="utf-8", errors="ignore")
    assert "P4.1" in text
    assert "P4.4" in text
    assert "decision-service" in text
    assert "rejected_untraceable" in text
    # INTERIM bridge must be documented honestly.
    assert "Source of Record" in text
    assert "mirror" in text


def test_p4_platform_baseline_tracks_single_facade_module():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert "api/decision_service_client.py" in data["modules"]
    assert "p4_note" in data
