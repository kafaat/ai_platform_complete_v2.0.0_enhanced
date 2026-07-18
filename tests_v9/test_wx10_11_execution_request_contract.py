from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]


def test_migration_and_endpoint_present():
    assert "decision_execution_requests" in (
        ROOT / "services/decision-service/migrations/005_execution_request.sql"
    ).read_text(encoding="utf-8")
    assert "/v1/dispatch-authorizations/{dispatch_authorization_id}/execute" in (
        ROOT / "services/decision-service/main.py"
    ).read_text(encoding="utf-8")


def test_fail_closed_and_no_direct_actuation():
    main = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
    assert "if not sor_enabled()" in main
    body = (
        (ROOT / "services/decision-service/persistence.py")
        .read_text(encoding="utf-8")
        .split("async def create_execution_request", 1)[1]
    )
    assert "EXECUTION_REQUEST_CREATED" in body
    assert "mqtt.publish" not in body and "actuator_runtime" not in body


def test_bff_permission_and_proof():
    auth = (ROOT / "services/sahool-platform/core/authorization.py").read_text(encoding="utf-8")
    router = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text(
        encoding="utf-8"
    )
    assert 'DECISION_EXECUTE = "decision:execute"' in auth
    assert "Permission.DECISION_EXECUTE" in router
    assert "did not prove an authoritative execution request" in router
