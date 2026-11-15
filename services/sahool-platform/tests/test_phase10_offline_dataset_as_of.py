"""The offline-dataset endpoint judges point-in-time safety at a capped as-of time.

Driven through the real router with no database: the route does no persistence.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from api.phase10_continuous_learning import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")
URL = "/v1/phase10/learning/feature-store/offline-dataset"


def _row(available: datetime) -> dict:
    event = available - timedelta(minutes=5)
    return {
        "tenant_id": "tenant-one",
        "source_version": "fixture-source-v1",
        "entity_type": "field",
        "entity_id": "field-a",
        "event_time": event.isoformat(),
        "available_at": available.isoformat(),
        "ingested_at": (available + timedelta(minutes=1)).isoformat(),
        "prediction_at": (available + timedelta(minutes=2)).isoformat(),
        "features": {"ndvi": 0.5},
    }


def _post(records, **extra):
    client = TestClient(FastAPI(), headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})
    client.app.include_router(router)
    res = client.post(URL, json={"records": records, **extra})
    assert res.status_code == 200
    return res.json()


def test_lineage_rows_are_safe_without_a_client_as_of():
    # Before: the endpoint passed no as_of, so no request could ever be safe.
    past = datetime(2026, 6, 26, 10, tzinfo=UTC)
    body = _post([_row(past)])
    assert body["point_in_time_safe"] is True
    assert body["as_of"] == (past + timedelta(minutes=2)).isoformat()


def test_a_future_client_as_of_is_capped_at_now():
    future = datetime.now(UTC) + timedelta(days=365)
    body = _post([_row(future)], as_of=(future + timedelta(days=1)).isoformat())
    assert body["point_in_time_safe"] is False
    assert body["future_available_count"] == 1
    # Negative control: the same as_of on rows published in the past is accepted.
    past = datetime(2026, 6, 26, 10, tzinfo=UTC)
    assert _post([_row(past)], as_of=(future + timedelta(days=1)).isoformat())["point_in_time_safe"]


def test_a_naive_client_as_of_is_reported_not_guessed():
    past = datetime(2026, 6, 26, 10, tzinfo=UTC)
    body = _post([_row(past)], as_of="2026-06-27T00:00:00")
    assert body["point_in_time_safe"] is False
    assert body["pit_unsafe_reasons"] == ["as_of_naive"]
