"""WX-10.9 execution-plan boundary: one canonical operation, timezone-aware windows.

* DECISION-MANUAL-PLAN-PADDED-OPERATION-BYPASS-01 — ``build_execution_plan`` validated
  ``operation_type.strip()`` but persisted the raw value, and ``create_execution_plan`` keyed the
  manual-irrigation binding on a literal ``== "manual_irrigation"``. ``" manual_irrigation "`` (or
  ``"Manual_Irrigation"``) skipped that binding, was stored unvalidated, and still matched the
  trimming comparison an execution request is checked against.
* DECISION-PLAN-MIXED-TIMEZONE-500-01 — ``planned_end <= planned_start`` with one naive and one
  aware datetime raised ``TypeError`` (HTTP 500); a naive window also reached persistence.

The persistence binding is checked through its pure helpers (no connection stand-in) and the
HTTP boundary through ``TestClient`` with persistence mocked — no Postgres.
"""

from __future__ import annotations

import inspect
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000001381"
TOKEN = "isolated-test-token"
SPELLINGS = [" manual_irrigation ", "manual_irrigation\n", "Manual_Irrigation", "MANUAL_IRRIGATION"]


# ── persistence: the manual-irrigation binding sees the canonical operation ──────────────────


def _plan_payload(operation_type: str) -> SimpleNamespace:
    return SimpleNamespace(
        operation_type=operation_type,
        planned_start=None,
        planned_end=None,
        target_zone_ids=["z1"],
        required_resources=[],
        constraints={"field_id": "field-1", "target_depth_mm": 20.0},
        safety_conditions={},
        weather_window_reference=None,
    )


NOT_IRRIGATION = {
    "tenant_id": TENANT,
    "field_id": "field-1",
    "decision_type": "crop_decision_candidate",
    "decision_value": json.dumps({"candidate_lineage_id": "lin_1"}),
    "approved_decision_value_digest": "a" * 64,
}


@pytest.mark.parametrize("operation_type", SPELLINGS, ids=repr)
def test_padded_or_case_variant_manual_irrigation_is_still_bound(operation_type):
    payload = _plan_payload(operation_type)
    assert (
        persistence._plan_operation_violation(NOT_IRRIGATION, operation_type, payload)
        == "manual_irrigation_requires_irrigation_decision"
    )


def test_other_operations_carry_no_manual_binding():
    assert persistence._plan_operation_violation(NOT_IRRIGATION, "irrigation", None) is None


def test_create_execution_plan_keys_the_binding_on_the_canonical_operation():
    source = inspect.getsource(persistence.create_execution_plan)
    assert "normalize_operation_type(payload.operation_type)" in source
    assert "_plan_operation_violation(source, operation_type, payload)" in source
    assert 'payload.operation_type == "manual_irrigation"' not in source


def test_request_hash_commits_to_the_canonical_operation():
    def digest(operation_type):
        return persistence._execution_plan_request_hash(
            decision_id="dec_1",
            review_id="rev_1",
            candidate_lineage_id="lin_1",
            payload=_plan_payload(operation_type),
            decision_value_digest="a" * 64,
        )

    assert {digest(s) for s in SPELLINGS} == {digest("manual_irrigation")}


def test_execution_request_match_is_not_loosened_on_case():
    plan = {"plan_operation_type": "manual_irrigation", "planned_end": None}
    request = SimpleNamespace(operation_type="Manual_Irrigation", command_payload={})
    reason = persistence._execution_request_plan_violation(plan, request, now=datetime.now(UTC))
    assert reason == "operation_type_mismatch"


# ── HTTP boundary ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    writer = AsyncMock(return_value={"status": "ok", "execution_plan_id": "xplan_1"})
    monkeypatch.setattr(main, "create_execution_plan", writer)
    return TestClient(main.app, raise_server_exceptions=False), writer


def _post(test_client, **body):
    payload = {
        "review_id": "rev_1",
        "candidate_lineage_id": "lin_1",
        "operation_type": "irrigation",
        "idempotency_key": "idem-1",
    }
    payload.update(body)
    return test_client.post(
        "/v1/decisions/dec_1/execution-plan",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Tenant-Id": TENANT,
            "X-Created-By": "planner",
        },
        json=payload,
    )


@pytest.mark.parametrize("operation_type", SPELLINGS, ids=repr)
def test_boundary_persists_the_operation_it_validated(client, operation_type):
    test_client, writer = client
    response = _post(test_client, operation_type=operation_type)
    assert response.status_code == 200, response.text
    assert writer.call_args.kwargs["payload"].operation_type == "manual_irrigation"


@pytest.mark.parametrize("operation_type", ["", "   ", "\t\n"], ids=repr)
def test_blank_operation_is_rejected(client, operation_type):
    test_client, writer = client
    response = _post(test_client, operation_type=operation_type)
    assert response.status_code == 422
    writer.assert_not_called()


AWARE = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("start", "end", "naive_field"),
    [
        (
            AWARE.isoformat(),
            (AWARE + timedelta(hours=2)).replace(tzinfo=None).isoformat(),
            "planned_end",
        ),
        (
            AWARE.replace(tzinfo=None).isoformat(),
            (AWARE + timedelta(hours=2)).isoformat(),
            "planned_start",
        ),
        (
            AWARE.replace(tzinfo=None).isoformat(),
            (AWARE + timedelta(hours=2)).replace(tzinfo=None).isoformat(),
            "planned_start",
        ),
        (None, (AWARE + timedelta(hours=2)).replace(tzinfo=None).isoformat(), "planned_end"),
    ],
    ids=["aware-start-naive-end", "naive-start-aware-end", "both-naive", "naive-end-only"],
)
def test_naive_plan_window_is_a_422_not_a_500(client, start, end, naive_field):
    test_client, writer = client
    response = _post(test_client, planned_start=start, planned_end=end)
    assert response.status_code == 422, response.text
    assert naive_field in response.json()["detail"]
    writer.assert_not_called()


def test_aware_ordered_window_is_accepted_and_inverted_window_refused(client):
    test_client, writer = client
    ok = _post(
        test_client,
        planned_start=AWARE.isoformat(),
        planned_end=(AWARE + timedelta(hours=2)).isoformat(),
    )
    assert ok.status_code == 200, ok.text
    inverted = _post(
        test_client,
        planned_start=(AWARE + timedelta(hours=2)).isoformat(),
        planned_end=AWARE.isoformat(),
    )
    assert inverted.status_code == 422
    assert writer.call_count == 1
