"""Dashboard reads cross a DB boundary only after cutover."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import api.main
import pytest
from api.routers import learning_summary as dashboard
from fastapi import HTTPException

TENANT = "2c5ba219-e9ce-48b0-977b-f3810327696d"
USER = SimpleNamespace(tenant_id=TENANT)
pytestmark = pytest.mark.unit


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setenv("FEATURE_LEARNING_DASHBOARD", "true")
    monkeypatch.setattr(
        dashboard,
        "get_platform_decision_sor_mode",
        lambda: SimpleNamespace(strict_decision_service_required=True),
    )


async def test_strict_uses_owner_for_counts_and_platform_only_for_field_region(strict, monkeypatch):
    stamp = "2026-11-12T09:30:00Z"
    reply = {
        "tenant_id": TENANT,
        "authoritative": True,
        "decisions": [{"tenant_id": TENANT, "region": "jawf", "created_at": stamp}],
        "outcomes": [
            {
                "tenant_id": TENANT,
                "outcome_id": "o",
                "decision_id": "d",
                "region": "jawf",
                "field_id": "pivot",
                "success": True,
                "created_at": stamp,
            }
        ],
        "recommendations": [
            {
                "tenant_id": TENANT,
                "outcome_id": 1,
                "recommendation_id": "r",
                "decision_id": "d",
                "field_id": "pivot",
                "season_id": "wheat",
                "farm_id": None,
                "crop": "wheat",
                "accepted": True,
                "matured_within_lag": False,
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": 5.1,
                "issued_at": stamp,
                "outcome_recorded_at": None,
            }
        ],
        "dispatch_links": {"r": "other"},
    }
    owner = AsyncMock(return_value=reply)
    monkeypatch.setattr(dashboard, "decision_get_json", owner)
    fetch = AsyncMock(return_value=[{"field_id": "pivot", "region": "jawf"}])

    @asynccontextmanager
    async def platform(user):
        assert user == USER
        yield SimpleNamespace(fetch=fetch)

    monkeypatch.setattr(dashboard, "tenant_connection", platform)
    result = await dashboard.get_learning_summary(USER)
    owner.assert_awaited_once_with(
        "/v1/learning/summary", tenant_id=TENANT, params={"dashboard_inputs": "true"}
    )
    sql, tenant, fields = fetch.await_args.args
    assert "FROM fields WHERE tenant_id=" in sql and (tenant, fields) == (TENANT, ["pivot"])
    assert result["overall"]["decision_count"] == 1
    assert result["regions"][0]["outcomes_pending"] == 1
    assert result["outcome_reconciliation"]["independent_case_count"] == 1
    assert result["overall"]["success_rate"] == 1.0


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"tenant_id": "other"}, 503),
        ({"authoritative": False}, 503),
        ({"outcomes": [{"tenant_id": "other"}]}, 502),
        ({"dispatch_links": []}, 502),
        ({"decisions": [{}]}, 502),
    ],
)
async def test_wrong_or_incomplete_source_never_falls_back(strict, monkeypatch, change, expected):
    empty = {
        "tenant_id": TENANT,
        "authoritative": True,
        "decisions": [],
        "outcomes": [],
        "recommendations": [],
        "dispatch_links": {},
    }
    monkeypatch.setattr(dashboard, "decision_get_json", AsyncMock(return_value={**empty, **change}))
    monkeypatch.setattr(dashboard, "tenant_connection", lambda *_: pytest.fail("wrong DB"))
    with pytest.raises(HTTPException) as caught:
        await dashboard.get_learning_summary(USER)
    assert caught.value.status_code == expected
