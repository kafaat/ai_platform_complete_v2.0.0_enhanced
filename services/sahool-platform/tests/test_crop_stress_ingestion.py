from uuid import UUID

import pytest
from api.crop_stress_ingestion import ingest_stress_product, normalize_stress_product

TENANT = UUID("11111111-1111-1111-1111-111111111111")


class FakeConn:
    def __init__(self):
        self.calls = 0

    async def fetchrow(self, query, *args):
        self.calls += 1
        return {"event_id": f"e{self.calls}"}


def _product():
    return {
        "schema": "weather_stress_product.v1",
        "source_service": "weather-service",
        "product_id": "wx-1",
        "product_version": "weather-stress/1.0.0",
        "observed_at": "2026-07-11T00:00:00Z",
        "quality_status": "validated",
        "stress_signals": [
            {"type": "heat", "severity": 0.8, "evidence_id": "wx:heat:1"},
            {"type": "cold", "severity": 0.1},
        ],
    }


def test_normalize_requires_explicit_numeric_severity():
    product = _product()
    product["stress_signals"] = [{"type": "heat", "severity": True}]
    with pytest.raises(ValueError):
        normalize_stress_product(product)


def test_normalize_preserves_product_provenance():
    events = normalize_stress_product(_product())
    assert len(events) == 2
    assert events[0]["source_service"] == "weather-service"
    assert events[0]["source_product_id"] == "wx-1"
    assert events[0]["payload"]["quality_status"] == "validated"


@pytest.mark.asyncio
async def test_ingest_persists_each_explicit_signal():
    conn = FakeConn()
    out = await ingest_stress_product(
        conn,
        tenant_id=TENANT,
        field_id="f1",
        season_id="s1",
        product=_product(),
    )
    assert out["accepted_signals"] == 2
    assert out["persisted"] == 2
    assert out["deduplicated"] == 0
    assert conn.calls == 2
