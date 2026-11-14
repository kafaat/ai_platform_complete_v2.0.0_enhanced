"""The point-in-time endpoint answers a bad ``as_of`` with 422, never 500.

``build_point_in_time_snapshot`` rejects a naive or unparseable ``as_of`` with
``ValueError``; the route maps that to ``{"code": "invalid_as_of"}``. The route
does no persistence, so it is driven through the real router with no database.
"""

import os

import pytest
from api.phase10_continuous_learning import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")
URL = "/v1/phase10/learning/feature-store/point-in-time"
RECORDS = [
    {
        "tenant_id": "tenant-one",
        "source_version": "fixture-source-v1",
        "entity_type": "field",
        "entity_id": "field-a",
        "event_time": "2026-06-26T10:00:00+00:00",
        "available_at": "2026-06-26T10:05:00+00:00",
        "ingested_at": "2026-06-26T10:06:00+00:00",
        "prediction_at": "2026-06-26T10:07:00+00:00",
        "features": {"ndvi": 0.5},
    }
]


def _client():
    app = FastAPI()
    app.include_router(router)
    # raise_server_exceptions=False: an unmapped ValueError shows up as a 500
    # response instead of propagating into the test, so the control is honest.
    return TestClient(
        app,
        headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]},
        raise_server_exceptions=False,
    )


@pytest.mark.parametrize("as_of", ["2026-06-26T12:00:00", "not-a-time", ""])
def test_bad_as_of_is_422_with_stable_code(as_of):
    res = _client().post(URL, json={"records": RECORDS, "as_of": as_of})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_as_of"


def test_aware_as_of_keeps_the_snapshot_shape():
    # Negative control for the same payload: only the offset differs.
    res = _client().post(URL, json={"records": RECORDS, "as_of": "2026-06-26T12:00:00+00:00"})
    assert res.status_code == 200
    body = res.json()
    assert body["row_count"] == 1
    assert body["rows"][0]["entity_id"] == "field-a"
    assert body["as_of"] == "2026-06-26T12:00:00+00:00"
    assert body["missing_available_at_count"] == 0
