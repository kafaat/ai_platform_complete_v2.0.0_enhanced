"""W1-11 — raster-service queues each published asset for the canonical observation store.

Owner decision of 2026-11-16 (pull form): raster-service writes each published asset to its
outbox and never calls indicators-service; indicators-service drains the outbox over raster's
internal feed (``routers/observation_feed.py``, tested in ``test_observation_feed.py``). Unit
level: the payload built from a published asset, ``publish`` (outbox write only, stubbed at its
function level), the hold when the outbox cannot be written, the publication path that queues
only after the asset is published, and the fact that this module calls no other service.
``tests_v9/test_canonical_observations_live_pg.py`` drains a real outbox on PostgreSQL.
"""

from __future__ import annotations

import asyncio

import db_persist
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


# ── publish: the outbox row, nothing else ─────────────────────────────────────────────────
@pytest.fixture
def outbox(monkeypatch):
    state = {"queued": (7, "pending"), "enqueued": []}

    async def _enqueue(payload):
        state["enqueued"].append(payload)
        return state["queued"]

    monkeypatch.setattr(observation_outbox, "enqueue", _enqueue)
    monkeypatch.setattr(observation_outbox, "_UNQUEUED", {}, raising=False)
    return state


def test_publish_writes_the_outbox_row_and_reports_it_pending(outbox):
    status = asyncio.run(observation_outbox.publish(_build()))
    assert status == "pending", status
    [queued] = outbox["enqueued"]
    assert queued["field_id"] == "fld_pubgate", "the payload is what reaches the outbox"


def test_settled_content_reports_its_settled_status(outbox):
    outbox["queued"] = (7, "delivered")
    assert asyncio.run(observation_outbox.publish(_build())) == "delivered", (
        "the same content already drained is not queued again (raster_observation_outbox_once)"
    )


def test_without_a_database_the_outbox_is_not_written(monkeypatch):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    assert asyncio.run(observation_outbox.enqueue(_build())) is None, (
        "no database: no outbox row, and the caller holds the payload as unqueued"
    )


def test_raster_never_calls_indicators_service():
    """Owner decision 2026-11-16: the direction is pull. A push client here closed the cycle
    [indicators-service, raster-service] in the architecture graph (architecture:no_cycles)."""
    import inspect
    import re

    source = inspect.getsource(observation_outbox)
    assert not re.search(r"\b[A-Z][A-Z0-9_]*INDICATORS[A-Z0-9_]*_(URL|HOST)\b", source), (
        "no indicators-service address in raster's outbox"
    )
    assert "httpx" not in source, "the outbox module makes no HTTP call"
    assert not hasattr(observation_outbox, "push") and not hasattr(observation_outbox, "drain_once")
    import cache_invalidation_worker

    worker = inspect.getsource(cache_invalidation_worker)
    assert "observation_outbox" not in worker, "the invalidation worker no longer sends anything"


# ── the publication path queues only after the asset is published ────────────────────────
def _patch_db(monkeypatch, *, registry=True, promote=True, assets=None):
    async def insert_asset(**kwargs):
        if assets is not None:
            assets.append(kwargs)
        return True

    async def insert_registry(**kwargs):
        return registry

    async def set_status(**kwargs):
        return promote if kwargs["status"] == "ready" else True

    published: list = []

    async def publish(payload, **_kw):
        published.append(payload)
        return "pending"

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


def test_a_published_asset_is_queued_once(monkeypatch):
    published = _patch_db(monkeypatch)
    assert _persist() is True, "the asset is published"
    [payload] = published
    assert payload["scene_id"] == "scene_1" and payload["stats"]["mean"] == 0.55, payload
    assert payload["tenant_id"] == TENANT and payload["processing_job_id"] == "job_1", payload
    assert payload["product_identity_key"], "the product identity travels with the payload"


def test_the_asset_row_stores_the_exact_payload_the_outbox_receives(monkeypatch):
    """W1-11 hardening: the sweep's source. Publication and the outbox write are two
    transactions, so the payload is stored with the asset (same statement) with its digest."""
    assets: list = []
    published = _patch_db(monkeypatch, assets=assets)
    assert _persist() is True
    [asset] = assets
    [payload] = published
    provenance = asset["provenance"]
    assert provenance[observation_outbox.PROVENANCE_PAYLOAD_KEY] == payload, provenance
    assert provenance[observation_outbox.PROVENANCE_DIGEST_KEY] == (
        observation_outbox.payload_sha256(payload)
    )
    assert payload["product_identity_key"] == asset["product_identity_key"]


def test_an_asset_that_is_no_observation_stores_no_payload(monkeypatch):
    assets: list = []
    published = _patch_db(monkeypatch, assets=assets)
    assert _persist(stats={"valid_pixels": 4, "nodata_pixels": 0, "mean": None}) is True
    assert observation_outbox.PROVENANCE_PAYLOAD_KEY not in assets[0]["provenance"]
    assert published == []


def test_a_local_file_publication_is_queued_too(monkeypatch):
    published = _patch_db(monkeypatch)
    assert _persist("file:///data/uploads/ndvi_x.tif") is True, "file:// asset is the publication"
    assert len(published) == 1, published


@pytest.mark.parametrize(("registry", "promote"), [(False, True), (True, False)])
def test_an_unpublished_asset_is_never_queued(monkeypatch, registry, promote):
    published = _patch_db(monkeypatch, registry=registry, promote=promote)
    assert _persist() is False, "the asset is not published"
    assert published == [], "only a published asset becomes a canonical observation"


def test_an_all_masked_asset_is_never_queued(monkeypatch):
    published = _patch_db(monkeypatch)
    assert _persist(stats={"valid_pixels": 0, "nodata_pixels": 4, "mean": 0.1}) is False, (
        "an all-masked product is not published"
    )
    assert published == [], "and is never an observation"


def test_a_queueing_failure_never_changes_the_publication(monkeypatch):
    _patch_db(monkeypatch)

    async def explode(payload, **_kw):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(observation_outbox, "publish", explode)
    assert _persist() is True, "publication stands; queueing runs after it"


# ── an outbox that cannot be written: held, counted, queued by the next publish ─────────────
@pytest.fixture
def no_outbox(monkeypatch):
    """The outbox write fails until ``state["db"]`` is set; the held set starts empty."""
    import raster_batch_observability

    state = {"db": False, "enqueued": []}

    async def _enqueue(payload):
        if not state["db"]:
            return None
        state["enqueued"].append(payload)
        return (len(state["enqueued"]), "pending")

    monkeypatch.setattr(observation_outbox, "enqueue", _enqueue)
    monkeypatch.setattr(observation_outbox, "_UNQUEUED", {}, raising=False)
    raster_batch_observability.reset()
    yield state
    raster_batch_observability.reset()


def test_an_unwritable_outbox_holds_counts_and_queues_later(no_outbox):
    """W1-11 review (LOW): the outbox write failed. The payload must not be lost: it is a
    counted, retryable state that the next publish writes to the outbox, where
    indicators-service's drain finds it."""
    import raster_batch_observability

    first = _build()
    status = asyncio.run(observation_outbox.publish(first))
    assert status == "unqueued", status
    assert observation_outbox.unqueued_count() == 1, "held for retry, not only logged"
    assert raster_batch_observability.snapshot().get("observation_outbox_unqueued_total") == 1

    no_outbox["db"] = True  # the database is back
    second = _build(scene_id="scene_2")
    status = asyncio.run(observation_outbox.publish(second))
    assert status == "pending", status
    assert [p["scene_id"] for p in no_outbox["enqueued"]] == [first["scene_id"], "scene_2"], (
        "the held payload reaches the outbox first, then the new one"
    )
    assert observation_outbox.unqueued_count() == 0
    assert raster_batch_observability.snapshot().get("observation_outbox_requeued_total") == 1


def test_the_unqueued_hold_is_bounded_and_counts_what_it_drops(no_outbox, monkeypatch):
    import raster_batch_observability

    monkeypatch.setattr(observation_outbox, "UNQUEUED_LIMIT", 2)
    for n in range(3):
        asyncio.run(observation_outbox.publish(_build(scene_id=f"s{n}")))
    assert observation_outbox.unqueued_count() == 2
    counters = raster_batch_observability.snapshot()
    assert counters.get("observation_outbox_unqueued_total") == 3, counters
    assert counters.get("observation_outbox_unqueued_dropped_total") == 1, counters
