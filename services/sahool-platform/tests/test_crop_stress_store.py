from datetime import UTC, datetime
from uuid import UUID

import pytest
from api.crop_stress_store import (
    append_stress_event,
    load_stress_events,
    persist_stress_snapshot,
    validate_stress_event,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")


class FakeConn:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return self.row

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.rows


def test_event_validation_requires_truthful_source_and_time():
    with pytest.raises(ValueError):
        validate_stress_event(
            {"type": "heat", "severity": 0.5, "observed_at": "2026-07-11T00:00:00Z"}
        )
    with pytest.raises(ValueError):
        validate_stress_event(
            {
                "type": "heat",
                "severity": 1.2,
                "observed_at": "2026-07-11T00:00:00Z",
                "source_service": "weather-service",
            }
        )


def test_event_dedup_key_is_deterministic():
    event = {
        "type": "water",
        "severity": 0.7,
        "observed_at": "2026-07-11T00:00:00Z",
        "source_service": "vegetation-analysis-service",
    }
    assert validate_stress_event(event)["dedup_key"] == validate_stress_event(event)["dedup_key"]


@pytest.mark.asyncio
async def test_append_event_reports_insert_and_dedup():
    inserted = await append_stress_event(
        FakeConn(row={"event_id": "x"}),
        tenant_id=TENANT,
        field_id="f1",
        season_id="s1",
        event={
            "type": "heat",
            "severity": 0.5,
            "observed_at": "2026-07-11T00:00:00Z",
            "source_service": "weather-service",
        },
    )
    duplicate = await append_stress_event(
        FakeConn(row=None),
        tenant_id=TENANT,
        field_id="f1",
        season_id="s1",
        event={
            "type": "heat",
            "severity": 0.5,
            "observed_at": "2026-07-11T00:00:00Z",
            "source_service": "weather-service",
        },
    )
    assert inserted["persisted"] is True
    assert duplicate["deduplicated"] is True


@pytest.mark.asyncio
async def test_load_events_preserves_provenance():
    conn = FakeConn(
        rows=[
            {
                "stress_type": "heat",
                "severity": 0.4,
                "observed_at": datetime(2026, 7, 10, tzinfo=UTC),
                "evidence_id": "e1",
                "source_service": "weather-service",
                "source_product_id": "p1",
                "source_version": "1",
                "payload": {"quality": "validated"},
            }
        ]
    )
    out = await load_stress_events(
        conn,
        tenant_id=TENANT,
        field_id="f1",
        season_id="s1",
        since=datetime(2026, 7, 1, tzinfo=UTC),
        until=datetime(2026, 7, 11, tzinfo=UTC),
    )
    assert out[0]["source_service"] == "weather-service"
    assert out[0]["evidence_id"] == "e1"


@pytest.mark.asyncio
async def test_snapshot_is_idempotent_by_scope_version_and_evidence():
    snapshot = {
        "schema": "crop_stress_memory.v2",
        "product_version": "crop-stress-memory/2.0.0",
        "status": "available",
        "as_of": "2026-07-11T00:00:00Z",
        "overall_burden": 0.4,
        "recovery_state": "residual_stress",
        "observation_count": 2,
        "evidence_ids": ["e1", "e2"],
    }
    first = await persist_stress_snapshot(
        FakeConn(row={"snapshot_id": "s"}),
        tenant_id=TENANT,
        field_id="f1",
        season_id="s1",
        snapshot=snapshot,
    )
    second = await persist_stress_snapshot(
        FakeConn(row=None), tenant_id=TENANT, field_id="f1", season_id="s1", snapshot=snapshot
    )
    assert first["persisted"] is True
    assert second["deduplicated"] is True
    assert first["evidence_digest"] == second["evidence_digest"]
