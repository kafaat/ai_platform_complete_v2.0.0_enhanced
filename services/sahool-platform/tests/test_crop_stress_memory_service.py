from datetime import UTC, datetime
from uuid import UUID

import pytest
from api.crop_stress_memory_service import rebuild_stress_memory_snapshot

TENANT = UUID("11111111-1111-1111-1111-111111111111")


class FakeConn:
    def __init__(self):
        self.fetch_calls = []
        self.fetchrow_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return [
            {
                "stress_type": "heat",
                "severity": 0.9,
                "observed_at": datetime(2026, 7, 9, tzinfo=UTC),
                "evidence_id": "e1",
                "source_service": "weather-service",
                "source_product_id": "p1",
                "source_version": "1",
                "payload": {},
            },
            {
                "stress_type": "heat",
                "severity": 0.1,
                "observed_at": datetime(2026, 7, 10, tzinfo=UTC),
                "evidence_id": "e2",
                "source_service": "weather-service",
                "source_product_id": "p2",
                "source_version": "1",
                "payload": {},
            },
        ]

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return {"snapshot_id": "snap-1"}


@pytest.mark.asyncio
async def test_rebuild_loads_raw_events_and_persists_snapshot():
    conn = FakeConn()
    out = await rebuild_stress_memory_snapshot(
        conn,
        tenant_id=TENANT,
        field_id="f1",
        season_id="s1",
        as_of="2026-07-11T00:00:00Z",
        half_life_days=7,
        max_age_days=45,
    )
    assert out["status"] == "snapshot_ready"
    assert out["event_count"] == 2
    assert out["snapshot"]["schema"] == "crop_stress_memory.v2"
    assert out["snapshot"]["evidence_ids"] == ["e1", "e2"]
    assert out["persistence"]["persisted"] is True
    assert len(conn.fetch_calls) == 1
    assert len(conn.fetchrow_calls) == 1
