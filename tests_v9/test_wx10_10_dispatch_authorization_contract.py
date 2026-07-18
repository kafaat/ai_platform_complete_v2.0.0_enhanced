from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]


def test_migration_is_additive_append_only_and_non_executing():
    text = (
        ROOT / "services/decision-service/migrations/004_dispatch_authorization.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS decision_dispatch_authorizations" in text
    assert "BEFORE UPDATE OR DELETE" in text
    assert "status = 'authorized'" in text
    assert "INSERT INTO dispatch_decisions" not in text


def test_decision_service_owns_authorization_endpoint():
    text = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
    assert "/v1/execution-plans/{execution_plan_id}/authorize-dispatch" in text
    assert "X-Authorized-By is required" in text
    assert "not the system-of-record" in text


def test_persistence_emits_authorization_event_not_dispatch():
    text = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
    assert "DISPATCH_AUTHORIZATION_CREATED" in text
    assert "decision_dispatch_authorizations" in text
    body = text.split("async def authorize_dispatch", 1)[1]
    assert "persist_dispatch_decision(" not in body
    assert "create_task(" not in body
    assert "equipment_command" not in body


def test_bff_requires_dedicated_permission_and_authoritative_proof():
    text = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text(encoding="utf-8")
    assert "DECISION_DISPATCH_AUTHORIZE" in text
    assert 'result.get("authoritative") is True' in text
    assert 'result.get("persisted") is True' in text


def test_permission_is_dedicated_and_not_broadly_granted():
    text = (ROOT / "services/sahool-platform/core/authorization.py").read_text(encoding="utf-8")
    assert 'DECISION_DISPATCH_AUTHORIZE = "decision:dispatch-authorize"' in text
    # Owner + manager only in this increment.
    assert text.count("Permission.DECISION_DISPATCH_AUTHORIZE") == 2
