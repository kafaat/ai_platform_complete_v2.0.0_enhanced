"""Actual authenticated HTTP projection; persistence mocked, no database claim."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytestmark = pytest.mark.unit


@pytest.mark.parametrize("correlation", ["76a90898-b083-48ae-a1bd-5650ceef0cbd", None])
@pytest.mark.parametrize("replay", [False, True])
def test_record_returns_stored_correlation_without_accepting_caller_identity(
    monkeypatch, correlation, replay
):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", "isolated-test-token")
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    monkeypatch.setattr(main, "agronomic_context_required", lambda: False)
    writer = AsyncMock(
        return_value={
            "correlation_id": correlation,
            "replayed": replay,
            "decision_value_digest": "stored-digest",
        }
    )
    monkeypatch.setattr(main, "persist_decision_record", writer)
    result = TestClient(main.app).post(
        "/v1/decisions/record",
        headers={
            "Authorization": "Bearer isolated-test-token",
            "X-Tenant-Id": "00000000-0000-0000-0000-000000001111",
        },
        json={
            "decision_id": "test-root",
            "decision_type": "recommendation",
            "stage": "candidate",
            "decision_value": {},
            "correlation_id": "caller-forged",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["correlation_id"] == correlation
    assert result.json()["replayed"] is replay
    assert not hasattr(writer.call_args.kwargs["payload"], "correlation_id")
