"""Phase 2 P2-c — REAL end-to-end: the raster-service consumer against the live satellite_cdse gate.

Not a mock. The raster-service restricted adapter (``imagery_source_gate.resolve_active_source``)
talks to the actual decision-service FastAPI app over an ASGI transport, and the gate's state is
persisted in real Postgres. This proves the operator's closure conditions end to end:

  #1 changing the gate state changes the imagery source the consumer selects (disabled→enabled→cdse)
  #2 a revoke immediately blocks a NEW CDSE selection (revoked → element84)
  #3 degraded (incomplete evidence) uses Element84 without pretending the gate is enabled
  #4 a generation change between two resolves is observable (the race signal)

Runs in the Decision Service Tests job (real Postgres, SoR on).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

DECISION_DIR = Path(__file__).resolve().parents[1]
RASTER_DIR = DECISION_DIR.parents[0] / "raster-service"
for p in (str(DECISION_DIR), str(RASTER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")


def _evidence(env: str, *, complete: bool = True) -> list[dict]:
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    items = [
        {
            "producer": "raster-service",
            "check_name": "cdse_credentials_present",
            "observed_at": future,
            "valid_until": future,
            "result": "pass",
            "provenance": "raster-service/cdse_client",
            "environment_id": env,
        },
        {
            "producer": "raster-service",
            "check_name": "cdse_live_probe",
            "observed_at": future,
            "valid_until": future,
            "result": "pass",
            "provenance": "raster-service/stac_search",
            "environment_id": env,
        },
    ]
    return items if complete else items[:1]


async def _decision_client(monkeypatch, env: str):
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("ACTIVATION_ENVIRONMENT_ID", env)
    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("RASTER_ACTIVATION_GATE_ENFORCE", "1")
    import main  # decision-service app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://ds")


async def _operate(ds: httpx.AsyncClient, path: str, **json):
    return await ds.post(
        f"/v1/activation/satellite_cdse/{path}",
        headers={"X-Requested-By": "operator"},
        json=json or None,
    )


async def _ingest_refs(ds: httpx.AsyncClient, env: str, *, complete: bool = True) -> list[str]:
    """Producers issue receipts over the ingest endpoint; the operator references them by id."""
    ids = []
    for item in _evidence(env, complete=complete):
        r = await ds.post(
            "/v1/activation/satellite_cdse/evidence-receipts",
            headers={"X-Requested-By": "producer"},
            json={
                "producer": item["producer"],
                "check_name": item["check_name"],
                "result": item["result"],
                "observed_at": item["observed_at"],
                "valid_until": item["valid_until"],
                "provenance": item.get("provenance"),
            },
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["receipt_id"])
    return ids


async def test_gate_state_changes_flip_the_consumer_source(monkeypatch):
    import imagery_source_gate as consumer

    env = "env-" + uuid4().hex[:10]
    ds = await _decision_client(monkeypatch, env)
    try:
        # disabled ⇒ consumer selects the safe fallback
        d0 = await consumer.resolve_active_source(env=env, client=ds)
        assert d0.provider == "element84" and d0.use_cdse is False

        # operator enables ⇒ consumer now selects CDSE, bound to the live generation
        began = await _operate(ds, "begin")
        gen = began.json()["generation"]
        await _operate(
            ds,
            "complete",
            expected_generation=gen,
            evidence_refs=await _ingest_refs(ds, env),
            ttl_seconds=3600,
        )
        d1 = await consumer.resolve_active_source(env=env, client=ds)
        assert d1.use_cdse is True and d1.provider == "cdse"
        assert d1.gate_state == "enabled" and isinstance(d1.generation, int)

        # revoke ⇒ a NEW selection is immediately blocked (proof #2) and generation advanced (proof #4)
        await _operate(ds, "revoke", reason="incident")
        d2 = await consumer.resolve_active_source(env=env, client=ds)
        assert d2.use_cdse is False and d2.provider == "element84"
        assert d2.generation != d1.generation
    finally:
        await ds.aclose()


async def test_degraded_evidence_stays_on_fallback(monkeypatch):
    import imagery_source_gate as consumer

    env = "env-" + uuid4().hex[:10]
    ds = await _decision_client(monkeypatch, env)
    try:
        began = await _operate(ds, "begin")
        gen = began.json()["generation"]
        # incomplete evidence ⇒ gate degraded ⇒ consumer must NOT treat it as enabled (proof #3)
        done = await _operate(
            ds,
            "complete",
            expected_generation=gen,
            evidence_refs=await _ingest_refs(ds, env, complete=False),
            ttl_seconds=3600,
        )
        assert done.json()["status"] == "degraded"
        d = await consumer.resolve_active_source(env=env, client=ds)
        assert d.use_cdse is False and d.provider == "element84"
    finally:
        await ds.aclose()
