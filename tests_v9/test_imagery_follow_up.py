"""Behavioral contract witnesses; database semantics live in the PG16 suite."""

from __future__ import annotations

import asyncio
import importlib.util
import secrets
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException

from shared.contracts.imagery_followup import (
    ImageryFollowUpRequest,
    request_digest,
    request_identity,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
TENANT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "services/raster-service"))
    import follow_up_runtime
    import follow_up_store
    import follow_up_worker

    spec = importlib.util.spec_from_file_location(
        "follow_up_router_witness", ROOT / "services/raster-service/routers/follow_up.py"
    )
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    return SimpleNamespace(
        runtime=follow_up_runtime, store=follow_up_store, worker=follow_up_worker, router=router
    )


@pytest.fixture
def bearer(monkeypatch):
    key = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET", key)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")

    def sign(tenant=TENANT, **extra):
        return "Bearer " + jwt.encode(
            {
                "sub": "witness",
                "tenant_id": tenant,
                "iss": "sahool-auth",
                "aud": "sahool",
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                **extra,
            },
            key,
            algorithm="HS256",
        )

    return sign


def body(**kwargs):
    return ImageryFollowUpRequest(season_id="season", execution_request_id="exec_1", **kwargs)


def row():
    now = datetime.now(UTC)
    return {
        "tenant_id": TENANT,
        "request_id": request_identity(TENANT, "field", "exec_1"),
        "field_id": "field",
        "request_hash": request_digest(body()),
        "attempts": 1,
        "status": "pending",
        "due_at": now + timedelta(days=5),
        "expires_at": now + timedelta(days=12),
        "request_payload": {"time_basis": "delivery_receipt_received_at", "receipt_id": "receipt"},
        "reason_code": None,
        "result_payload": None,
    }


def test_identity_is_stable_and_unambiguous():
    assert request_identity(TENANT, "field", "exec") == request_identity(TENANT, "field", "exec")
    assert request_identity(TENANT, "a|b", "c") != request_identity(TENANT, "a", "b|c")
    assert request_identity(TENANT, "field", "exec") != request_identity(OTHER, "field", "exec")
    assert request_digest(body(indicators=["NDMI", "ndvi"])) == request_digest(body())
    assert request_digest(body(days_after=6)) != request_digest(body())


@pytest.mark.parametrize("indicators", [[], ["vv"], ["ndvi", "ndmi", "ndvi"]])
def test_unsupported_products_rejected(indicators):
    with pytest.raises(ValueError):
        body(indicators=indicators)


def test_receipt_clock_and_scope(modules):
    anchor = datetime.now(UTC) - timedelta(days=1)
    ctx = {
        "tenant_id": TENANT,
        "field_id": "field",
        "season_id": "season",
        "execution_request_id": "exec_1",
        "time_basis": "delivery_receipt_received_at",
        "receipt_id": "receipt",
        "received_at": anchor.isoformat(),
    }
    due, end = modules.runtime.bind_receipt(TENANT, "field", body(), ctx)
    assert due == anchor + timedelta(days=5)
    assert end == due + timedelta(days=7)
    for key in ("tenant_id", "field_id", "season_id", "execution_request_id", "time_basis"):
        with pytest.raises(HTTPException) as exc:
            modules.runtime.bind_receipt(TENANT, "field", body(), {**ctx, key: "forged"})
        assert exc.value.status_code == 409
    with pytest.raises(HTTPException):
        modules.runtime.bind_receipt(
            TENANT, "field", body(), {**ctx, "received_at": "2026-01-01T00:00:00"}
        )


def test_scene_quality_time_and_provider_are_required(modules):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=7)
    valid = {
        "item_id": "s1",
        "provider": "cdse",
        "datetime": "2026-01-03T00:00:00Z",
        "cloud_cover_pct": 20,
        "cloud_cover_known": True,
    }
    invalid = [{**valid, "cloud_cover_pct": v} for v in (None, float("nan"), -1, 50)]
    invalid += [{**valid, "datetime": "2025-12-31T00:00:00Z"}, {**valid, "provider": "unknown"}]
    invalid += [{**valid, "cloud_cover_known": False, "cloud_cover_pct": 0}]
    assert modules.runtime.select_scene(invalid, start, end) is None
    assert modules.runtime.select_scene(invalid + [valid], start, end) == valid


@pytest.mark.asyncio
async def test_real_bridge_reaches_real_router_and_replays(monkeypatch, modules, bearer):
    app = FastAPI()
    app.include_router(modules.router.router)
    app.state.follow_up_ready = True
    monkeypatch.setenv("RASTER_FOLLOWUP_TENANTS", TENANT)
    stored = row()
    store = SimpleNamespace(
        get=AsyncMock(side_effect=[None, stored]), enqueue=AsyncMock(return_value=stored)
    )
    monkeypatch.setattr(modules.runtime, "store", store)
    admission = AsyncMock(
        return_value=(stored["request_payload"], stored["due_at"], stored["expires_at"])
    )
    monkeypatch.setattr(modules.runtime, "admission_payload", admission)
    spec = importlib.util.spec_from_file_location(
        "followup_bridge_witness",
        ROOT / "services/vegetation-analysis-service/post_execution_bridge.py",
    )
    bridge_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge_module)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        bridge_module.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.ASGITransport(app=app), **kw),
    )
    bridge = bridge_module.PostExecutionBridge()
    args = dict(
        field_id="field",
        season_id="season",
        execution_request_id="exec_1",
        tenant_id=TENANT,
        authorization=bearer(),
        days_after=5,
        indicators=["ndvi", "ndmi"],
    )
    first = await bridge.schedule_follow_up(**args)
    second = await bridge.schedule_follow_up(**args)
    assert first == second
    assert first["time_basis"] == "delivery_receipt_received_at"
    assert first["request"]["outcome_verified"] is False
    assert store.enqueue.await_count == admission.await_count == 1
    assert "Authorization" not in str(store.enqueue.call_args)


@pytest.mark.asyncio
async def test_api_auth_conflicts_failures_and_status_scope(monkeypatch, modules, bearer):
    app = FastAPI()
    app.include_router(modules.router.router)
    app.state.follow_up_ready = True
    monkeypatch.setenv("RASTER_FOLLOWUP_TENANTS", TENANT)
    store = SimpleNamespace(get=AsyncMock(return_value=row()))
    monkeypatch.setattr(modules.runtime, "store", store)
    url = "/v1/fields/field/imagery-ingestion-requests"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://witness"
    ) as client:
        for auth, header, expected in [
            ("Bearer forged", None, 401),
            (bearer(), OTHER, 403),
            (bearer(exp=datetime.now(UTC) - timedelta(minutes=1)), None, 401),
        ]:
            headers = {"Authorization": auth}
            if header:
                headers["X-Tenant-Id"] = header
            assert (
                await client.post(url, json=body().model_dump(), headers=headers)
            ).status_code == expected
        assert store.get.await_count == 0
        result = await client.post(
            url, json=body(days_after=6).model_dump(), headers={"Authorization": bearer()}
        )
        assert result.status_code == 409
        result = await client.get(
            url.replace("/field/", "/other/") + "/request", headers={"Authorization": bearer()}
        )
        assert result.status_code == 404
        store.get.side_effect = ConnectionError("must-not-leak-secret")
        result = await client.post(
            url, json=body().model_dump(), headers={"Authorization": bearer()}
        )
        assert result.status_code == 503 and "must-not-leak" not in result.text
        app.state.follow_up_ready = False
        assert (
            await client.post(url, json=body().model_dump(), headers={"Authorization": bearer()})
        ).status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,status,reason",
    [
        ("scene", "waiting_for_scene", "no_suitable_scene"),
        ("transient", "retry_wait", "catalog_unavailable"),
        ("permanent", "failed", "radiometry_unresolved"),
        ("timeout", "retry_wait", "upstream_timeout"),
        ("success", "dispatched", None),
    ],
)
async def test_worker_failure_policy(modules, kind, status, reason):
    store = SimpleNamespace(
        claim=AsyncMock(return_value=row()), settle=AsyncMock(return_value=True)
    )

    async def process(*args):
        if kind == "scene":
            raise modules.worker.RetryLater("no_suitable_scene", no_scene=True)
        if kind == "transient":
            raise modules.worker.RetryLater("catalog_unavailable")
        if kind == "permanent":
            raise modules.worker.PermanentFailure("radiometry_unresolved")
        if kind == "timeout":
            raise TimeoutError
        return {"jobs": [{"item_id": 1}]}

    assert await modules.worker.run_once(store, TENANT, process)
    values = store.settle.call_args.kwargs
    assert values["status"] == status and values.get("reason") == reason
    if kind == "scene":
        assert values["delay_seconds"] == 21600


@pytest.mark.asyncio
async def test_killed_worker_does_not_acknowledge(modules):
    store = SimpleNamespace(claim=AsyncMock(return_value=row()), settle=AsyncMock())

    async def process(*args):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await modules.worker.run_once(store, TENANT, process)
    store.settle.assert_not_awaited()


def test_retry_backoff_is_bounded(modules):
    for attempt in (1, 2, 10, 1000000):
        assert 1 <= modules.worker.retry_delay(attempt) <= 3600


@pytest.mark.asyncio
async def test_adapter_pins_scene_and_recovers_partial_handoff(monkeypatch, modules):
    import db_persist
    import stac_search

    now = datetime.now(UTC)
    claim = row()
    claim.update(due_at=now - timedelta(days=1), expires_at=now + timedelta(days=6))
    claim["request_payload"].update(
        processing_version=modules.runtime.canonical_processing_version(),
        geometry={"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]},
        geometry_revision=3,
        bbox=[44, 15, 45, 16],
        indicators=["ndmi", "ndvi"],
    )
    scene = {
        "item_id": "scene-1",
        "provider": "cdse",
        "datetime": now.isoformat(),
        "cloud_cover_pct": 10,
        "cloud_cover_known": True,
    }
    search = AsyncMock(return_value={"items": [scene]})
    monkeypatch.setattr(stac_search, "stac_search", search)
    calls = []

    async def enqueue(**kw):
        calls.append(kw)
        if len(calls) == 2:
            return None  # second product fails after first durable hand-off
        return {"status": "planned", "run_id": 1, "item_id": len(calls)}

    monkeypatch.setattr(db_persist, "enqueue_single_scene_process", enqueue)

    @asynccontextmanager
    async def tx(tenant):
        assert tenant == TENANT
        yield SimpleNamespace(fetchval=AsyncMock(return_value=1))

    progress = {}

    async def save(_row, value):
        import copy

        progress.clear()
        progress.update(copy.deepcopy(value))
        return True

    store = SimpleNamespace(transaction=tx, owns=AsyncMock(return_value=True), save_progress=save)
    with pytest.raises(modules.worker.RetryLater):
        await modules.runtime.process(claim, store)
    assert [j["indicator"] for j in progress["jobs"]] == ["ndmi"]
    claim["result_payload"] = progress.copy()
    result = await modules.runtime.process(claim, store)
    assert [c["index_name"] for c in calls] == ["ndmi", "ndvi", "ndvi"]
    assert search.await_count == 1  # retries never silently switch scene
    assert {j["indicator"] for j in result["jobs"]} == {"ndvi", "ndmi"}
    assert all(c["scene_id"] == "scene-1" and c["geometry_revision"] == 3 for c in calls)
    assert result["observation_verified"] is False


@pytest.mark.asyncio
async def test_adapter_cannot_emit_after_lease_loss(monkeypatch, modules):
    import db_persist

    claim = row()
    claim["request_payload"].update(
        processing_version=modules.runtime.canonical_processing_version(), indicators=["ndvi"]
    )
    claim["result_payload"] = {"scene": {"item_id": "scene"}, "jobs": []}

    @asynccontextmanager
    async def tx(_tenant):
        yield SimpleNamespace(fetchval=AsyncMock(return_value=1))

    store = SimpleNamespace(transaction=tx, owns=AsyncMock(return_value=False))
    enqueue = AsyncMock()
    monkeypatch.setattr(db_persist, "enqueue_single_scene_process", enqueue)
    with pytest.raises(modules.worker.PermanentFailure, match="lease_lost"):
        await modules.runtime.process(claim, store)
    enqueue.assert_not_awaited()
