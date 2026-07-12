from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import raster_batch_job_store as store
import raster_job_orchestration as orchestration
from routers import processing


def test_lease_heartbeat_runs_during_long_indicator_and_fences_on_loss(monkeypatch):
    calls = []
    responses = iter([True, True, False])

    def heartbeat_sync(**kwargs):
        calls.append(kwargs)
        return next(responses, False)

    monkeypatch.setattr(store, "heartbeat_sync", heartbeat_sync)
    hb = orchestration._LeaseHeartbeat(
        claim_key="rib_claim",
        tenant_id="00000000-0000-0000-0000-000000000001",
        lease_token="secret",
        logger=SimpleNamespace(warning=lambda *a, **k: None),
    )
    hb.interval = 0.01
    assert hb.start()
    deadline = time.time() + 1
    while not hb.lost and time.time() < deadline:
        time.sleep(0.01)
    hb.stop()

    assert hb.lost
    assert len(calls) >= 3
    assert all(call["lease_token"] == "secret" for call in calls)


def test_completed_durable_job_is_returned_after_process_restart(monkeypatch):
    async def claim_or_recover(**kwargs):
        return store.DurableClaim(
            available=True,
            acquired=False,
            job_id="batch_existing",
            status="completed",
            result_payload={"batch_results": {"ndvi": "layer_1"}},
        )

    monkeypatch.setattr(processing.raster_batch_job_store, "claim_or_recover", claim_or_recover)
    monkeypatch.setattr(
        processing.indicator_batch_claim, "batch_claim_key", lambda req: "rib_existing"
    )
    monkeypatch.setattr(
        processing.raster_security_context, "require_service_token", lambda token: None
    )
    monkeypatch.setattr(processing.raster_runtime_state.JOBS, "get", lambda job_id: None)

    req = SimpleNamespace(
        raster_url="/tmp/scene.tif",
        indicators=[SimpleNamespace(value="ndvi")],
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld_1",
    )
    response = asyncio.run(
        processing.process_batch(req, SimpleNamespace(add_task=lambda *a, **k: None), "token")
    )

    assert response["status"] == "completed"
    assert response["deduplicated"] is True
    assert response["result"]["batch_results"]["ndvi"] == "layer_1"


def test_failed_durable_job_exposes_stable_error_after_restart(monkeypatch):
    async def claim_or_recover(**kwargs):
        return store.DurableClaim(
            available=True,
            acquired=False,
            job_id="batch_failed",
            status="failed",
            error_code="batch_no_products_completed",
        )

    monkeypatch.setattr(processing.raster_batch_job_store, "claim_or_recover", claim_or_recover)
    monkeypatch.setattr(
        processing.indicator_batch_claim, "batch_claim_key", lambda req: "rib_failed"
    )
    monkeypatch.setattr(
        processing.raster_security_context, "require_service_token", lambda token: None
    )
    monkeypatch.setattr(processing.raster_runtime_state.JOBS, "get", lambda job_id: None)

    req = SimpleNamespace(
        raster_url="/tmp/scene.tif",
        indicators=[SimpleNamespace(value="ndvi")],
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld_1",
    )
    response = asyncio.run(
        processing.process_batch(req, SimpleNamespace(add_task=lambda *a, **k: None), "token")
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "batch_no_products_completed"
