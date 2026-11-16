"""W1-11 — raster-service pushes each published asset to the canonical observation store.

Owner decision of 2026-11-16: the push is HTTP to indicators-service, idempotent there on the
asset stable id, and never silently lost: an outbox row is written first and a failed push stays
pending for the cache invalidation worker. Unit level: the payload built from a published asset,
the classification of each answer, the outbox bookkeeping (stubbed at its function level), and
the publication path that calls it only after the asset is published.
``tests_v9/test_canonical_observations_live_pg.py`` drains a real outbox on PostgreSQL.
"""

from __future__ import annotations

import asyncio

import db_persist
import httpx
import observation_outbox
import pytest

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000000001"


def _build(**overrides):
    kwargs = {
        "tenant_id": TENANT,
        "field_id": "fld_pubgate",
        "indicator": "NDVI",
        "scene_id": "scene_1",
        "capture_datetime": "2026-09-01",
        "stats": {"mean": 0.55, "min": 0.1, "max": 0.9, "std": 0.05, "cloud_pct": 3.0},
        "quality": {"valid_pixel_ratio": 0.9, "coverage_ratio": 1.0, "index_quality_flags": []},
        "algorithm_version": "raster-quality-2.0.0",
        "qa_mask_version": None,
        "product_identity_key": "pik_1",
        "geometry_revision": 2,
        "data_available_at": "2026-09-03T08:30:00Z",
        "processing_job_id": "job_1",
        "cog_uri": "s3://bucket/fld_pubgate/ndvi_x.tif",
    }
    kwargs.update(overrides)
    return observation_outbox.build_payload(**kwargs)


# ── the payload ───────────────────────────────────────────────────────────────────────────
def test_a_published_asset_becomes_a_published_observation_payload():
    payload = _build()
    assert payload is not None, "a published asset with a finite mean is an observation"
    assert payload["schema_version"] == "sahool.published_observation/1", payload
    assert payload["indicator"] == "ndvi", "indicator codes are lower case"
    assert payload["acquired_at"] == "2026-09-01T00:00:00+00:00", "UTC, timezone explicit"
    assert payload["data_available_at"] == "2026-09-03T08:30:00+00:00", payload
    assert payload["stats"] == {"mean": 0.55, "min": 0.1, "max": 0.9, "std": 0.05}, payload
    assert payload["cloud_pct"] == 3.0, payload
    assert payload["quality_gate_passed"] is True, "measured positive valid ratio passes"


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenant_id": None},
        {"scene_id": None},
        {"scene_id": "  "},
        {"capture_datetime": None},
        {"capture_datetime": "not-a-date"},
        {"stats": {"mean": None}},
        {"stats": {"mean": float("nan")}},
        {"stats": {"mean": "0.55"}},
    ],
)
def test_an_asset_without_identity_or_a_finite_mean_is_not_an_observation(overrides):
    assert _build(**overrides) is None, f"{overrides} must not produce an observation"


def test_unmeasured_quality_never_passes_the_gate_and_bad_numbers_are_dropped():
    payload = _build(
        quality={"valid_pixel_ratio": None, "coverage_ratio": 7},
        stats={"mean": 0.4, "min": float("inf"), "cloud_pct": 140.0},
    )
    assert payload["quality_gate_passed"] is False, "no measured ratio, no passed gate"
    assert payload["coverage_ratio"] is None, "an out-of-range ratio is unknown, not clipped"
    assert payload["cloud_pct"] is None, "an out-of-range cloud percentage is unknown"
    assert payload["stats"] == {"mean": 0.4}, "a non-finite statistic is dropped"


def test_the_payload_hash_is_stable_and_content_bound():
    a, b = _build(), _build()
    assert observation_outbox.payload_sha256(a) == observation_outbox.payload_sha256(b), (
        "the same asset must hash the same"
    )
    other = _build(stats={"mean": 0.56})
    assert observation_outbox.payload_sha256(a) != observation_outbox.payload_sha256(other), (
        "another mean is another outbox row"
    )


# ── the push and its classification ───────────────────────────────────────────────────────
def _transport(status: int, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"status": "x"})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (201, "delivered"),
        (200, "delivered"),
        (409, "conflict"),
        (422, "rejected"),
        (403, "rejected"),
        (400, "rejected"),
        (401, "pending"),
        (503, "pending"),
        (500, "pending"),
    ],
)
def test_each_answer_is_classified(monkeypatch, status, outcome):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "tok")
    monkeypatch.setenv("INDICATORS_SERVICE_URL", "http://indicators.test")
    seen: list = []
    out = asyncio.run(observation_outbox.push(_build(), transport=_transport(status, seen)))
    assert out.status == outcome, f"{status} must be {outcome}, got {out}"
    [request] = seen
    assert str(request.url) == "http://indicators.test/internal/v1/observations", request.url
    assert request.headers["X-Agent-Token"] == "tok", "the service token is sent"
    assert request.headers["X-Tenant-Id"] == TENANT, "the tenant is asserted in the header"


def test_a_transport_failure_stays_pending(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "tok")

    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    out = asyncio.run(observation_outbox.push(_build(), transport=httpx.MockTransport(boom)))
    assert out.status == "pending", "a network error is retried, never dropped"


def test_no_token_means_no_request_and_pending(monkeypatch):
    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    seen: list = []
    out = asyncio.run(observation_outbox.push(_build(), transport=_transport(201, seen)))
    assert out.status == "pending" and seen == [], "unconfigured: nothing sent, retried later"


def test_backoff_grows_and_is_capped():
    steps = [observation_outbox.backoff_seconds(n) for n in (1, 2, 3, 30)]
    assert steps[0] < steps[1] < steps[2], f"backoff must grow: {steps}"
    assert steps[3] == observation_outbox.BACKOFF_MAX_S, f"backoff must be capped: {steps}"


# ── publish: outbox first, then one push, then the outcome on the row ──────────────────────
@pytest.fixture
def outbox(monkeypatch):
    state = {"queued": (7, "pending"), "recorded": [], "record_ok": True}

    async def _enqueue(payload):
        state["enqueued"] = payload
        return state["queued"]

    async def _record(tenant_id, row_id, attempts, out):
        state["recorded"].append((tenant_id, row_id, attempts, out.status))
        return state["record_ok"]

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "tok")
    monkeypatch.setattr(observation_outbox, "enqueue", _enqueue)
    monkeypatch.setattr(observation_outbox, "record_outcome", _record)
    return state


def test_publish_writes_the_outbox_then_records_a_delivery(outbox):
    seen: list = []
    status = asyncio.run(observation_outbox.publish(_build(), transport=_transport(201, seen)))
    assert status == "delivered", status
    assert outbox["enqueued"]["field_id"] == "fld_pubgate", "the outbox row comes first"
    assert outbox["recorded"] == [(TENANT, 7, 0, "delivered")], outbox["recorded"]


def test_a_failed_push_stays_pending_on_its_outbox_row(outbox):
    status = asyncio.run(observation_outbox.publish(_build(), transport=_transport(503, [])))
    assert status == "pending", status
    assert outbox["recorded"] == [(TENANT, 7, 0, "pending")], "the row stays pending for the worker"


def test_settled_content_is_not_sent_again(outbox):
    outbox["queued"] = (7, "delivered")
    seen: list = []
    status = asyncio.run(observation_outbox.publish(_build(), transport=_transport(201, seen)))
    assert status == "delivered" and seen == [], "the same content is not re-pushed"


def test_an_unrecorded_outcome_is_reported_pending(outbox):
    outbox["record_ok"] = False
    status = asyncio.run(observation_outbox.publish(_build(), transport=_transport(201, [])))
    assert status == "pending", "the worker will replay it; indicators-service answers 200"


def test_without_a_database_the_outbox_is_not_claimed(monkeypatch):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    assert asyncio.run(observation_outbox.enqueue(_build())) is None, (
        "no database: no retry marker, and the caller logs that"
    )


# ── the publication path calls it only after the asset is published ────────────────────────
def _patch_db(monkeypatch, *, registry=True, promote=True):
    async def insert_asset(**kwargs):
        return True

    async def insert_registry(**kwargs):
        return registry

    async def set_status(**kwargs):
        return promote if kwargs["status"] == "ready" else True

    published: list = []

    async def publish(payload, **_kw):
        published.append(payload)
        return "delivered"

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert_asset)
    monkeypatch.setattr(db_persist, "insert_raster_registry_entry", insert_registry)
    monkeypatch.setattr(db_persist, "set_raster_asset_status", set_status, raising=False)
    monkeypatch.setattr(observation_outbox, "publish", publish)
    return published


def _persist(cog_url="s3://bucket/fld_pubgate/ndvi_x.tif", stats=None):
    from raster_api_models import ProcessRequest
    from raster_asset_persistence import persist_raster_asset

    req = ProcessRequest(
        field_id="fld_pubgate",
        tenant_id=TENANT,
        scene_id="scene_1",
        capture_datetime="2026-09-01",
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider="cdse",
        raster_url="file:///scene.tif",
        precomputed_index=True,
    )
    return persist_raster_asset(
        req,
        cog_url,
        {"data_available_at": "2026-09-03T08:30:00+00:00"},
        [44, 15, 45, 16],
        stats or {"valid_pixels": 4, "nodata_pixels": 0, "mean": 0.55, "min": 0.1, "max": 0.9},
        job_id="job_1",
    )


def test_a_published_asset_is_pushed_once(monkeypatch):
    published = _patch_db(monkeypatch)
    assert _persist() is True, "the asset is published"
    [payload] = published
    assert payload["scene_id"] == "scene_1" and payload["stats"]["mean"] == 0.55, payload
    assert payload["tenant_id"] == TENANT and payload["processing_job_id"] == "job_1", payload
    assert payload["product_identity_key"], "the product identity travels with the payload"


def test_a_local_file_publication_is_pushed_too(monkeypatch):
    published = _patch_db(monkeypatch)
    assert _persist("file:///data/uploads/ndvi_x.tif") is True, "file:// asset is the publication"
    assert len(published) == 1, published


@pytest.mark.parametrize(("registry", "promote"), [(False, True), (True, False)])
def test_an_unpublished_asset_is_never_pushed(monkeypatch, registry, promote):
    published = _patch_db(monkeypatch, registry=registry, promote=promote)
    assert _persist() is False, "the asset is not published"
    assert published == [], "only a published asset becomes a canonical observation"


def test_an_all_masked_asset_is_never_pushed(monkeypatch):
    published = _patch_db(monkeypatch)
    assert _persist(stats={"valid_pixels": 0, "nodata_pixels": 4, "mean": 0.1}) is False, (
        "an all-masked product is not published"
    )
    assert published == [], "and is never an observation"


def test_a_push_failure_never_changes_the_publication(monkeypatch):
    _patch_db(monkeypatch)

    async def explode(payload, **_kw):
        raise RuntimeError("indicators down")

    monkeypatch.setattr(observation_outbox, "publish", explode)
    assert _persist() is True, "publication stands; the outbox or the worker retries the push"


# ── the drain: independent of invalidation, bounded per cycle (W1-11 review) ───────────────
def _worker():
    import cache_invalidation_worker

    return cache_invalidation_worker


@pytest.mark.parametrize(
    ("flag", "token", "expected"),
    [
        (None, "tok", True),
        ("true", "tok", True),
        ("false", "tok", False),
        (None, "", False),
    ],
)
def test_the_drain_is_on_by_default_and_needs_only_its_token(monkeypatch, flag, token, expected):
    worker = _worker()
    monkeypatch.setenv("RASTER_CACHE_INVALIDATION_ENABLED", "false")
    if flag is None:
        monkeypatch.delenv("RASTER_OBSERVATION_OUTBOX_DRAIN_ENABLED", raising=False)
    else:
        monkeypatch.setenv("RASTER_OBSERVATION_OUTBOX_DRAIN_ENABLED", flag)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", token)
    on, reason = worker._outbox_drain_configured()
    assert on is expected, f"flag={flag} token={bool(token)}: {reason}"
    assert on or reason, "an off drain must say why"


def test_a_drain_that_is_off_warns_the_operator_once(monkeypatch, caplog):
    worker = _worker()
    monkeypatch.setenv("RASTER_OBSERVATION_OUTBOX_DRAIN_ENABLED", "false")
    monkeypatch.setattr(worker, "_outbox_drain_warned", False)
    with caplog.at_level("WARNING", logger=worker.logger.name):
        assert asyncio.run(worker._drain_cycle(None)) is None, "no pool is opened"
        asyncio.run(worker._drain_cycle(None))
    warned = [r for r in caplog.records if "not retried" in r.getMessage()]
    assert len(warned) == 1, f"one warning, not one per cycle: {[r.getMessage() for r in warned]}"


def test_the_drain_runs_when_invalidation_is_disabled_or_failed(monkeypatch):
    worker = _worker()
    drained: list = []

    async def _drain(pool):
        drained.append(pool)
        return 0

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "tok")
    monkeypatch.delenv("RASTER_OBSERVATION_OUTBOX_DRAIN_ENABLED", raising=False)
    monkeypatch.setattr(worker, "_drain_observation_outbox", _drain)
    held = "the-loop-pool"
    assert asyncio.run(worker._drain_cycle(held)) == held, "the loop keeps its pool"
    assert drained == [held], drained
    import inspect

    src = inspect.getsource(worker.loop_worker)
    assert src.count("_drain_cycle(pool)") == 2, (
        "the loop must drain both in the disabled branch and after every invalidation cycle"
    )
    assert "await _drain_observation_outbox(pool)\n        except" not in src, (
        "the drain must not sit inside the invalidation try (a failed run_once would skip it)"
    )
    assert "pool = await _connect()" in inspect.getsource(worker._drain_cycle), (
        "with invalidation off the drain opens its own pool"
    )


def test_the_drain_budget_is_spent_on_a_clock():
    ticks = iter([0.0, 10.0, 31.0])
    clock = lambda: next(ticks)  # noqa: E731
    started = clock()
    assert observation_outbox.within_budget(started, 30, clock=clock), "10s of 30s: send"
    assert not observation_outbox.within_budget(started, 30, clock=clock), "31s of 30s: stop"
    assert observation_outbox.DRAIN_BUDGET_S < 120, (
        "a drain must end well inside the worker heartbeat max-age (120 s)"
    )
