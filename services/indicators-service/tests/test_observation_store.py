"""W1-11 — indicators-service owns the canonical observation store (owner decision 2026-11-16).

Unit level: the payload's stable id (the asset reference the canonical contract already
derives), its validation, numbers that are never decimal text, and the two read routes serving
stored rows with the computed path as declared fallback. The pull that fills the store (owner
decision 2026-11-16, pull form) is ``test_observation_drain.py``; there is no ingest route.
The store is stubbed at its function level; ``tests_v9/test_canonical_observations_live_pg.py``
measures the same contract on PostgreSQL under a restricted role.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

MODULE_PATH = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location("indicators_service_main_w1_11", MODULE_PATH)
assert spec and spec.loader, "indicators-service main.py must be importable"
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
client = TestClient(main.app)

import observation_runtime  # noqa: E402  (main.py put the service dir on sys.path)
import observation_store  # noqa: E402
import observation_timeline  # noqa: E402

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TOKEN = "test-mesh-token"
PUBLISHED = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _payload(**overrides):
    body = {
        "schema_version": "sahool.published_observation/1",
        "tenant_id": TENANT,
        "field_id": "fld_a",
        "indicator": "ndvi",
        "scene_id": "S2A_TEST_SCENE",
        "acquired_at": "2026-10-15T07:35:29+00:00",
        "stats": {"mean": 0.61, "min": 0.2, "max": 0.8, "std": 0.1},
        "valid_pixel_ratio": 0.91,
        "coverage_ratio": 0.94,
        "cloud_pct": 4.0,
        "quality_score": 0.89,
        "quality_gate_passed": True,
        "index_quality_flags": [],
        "algorithm_version": "2.1.0",
        "qa_mask_version": "scl-v1",
        "product_identity_key": "pik_1",
        "geometry_revision": 3,
        "data_available_at": "2026-10-15T09:00:00+00:00",
        "processing_job_id": "job_1",
        "cog_uri": "s3://bucket/fld_a/ndvi_1.tif",
    }
    body.update(overrides)
    return body


# ── the payload: stable id, content hash, numbers ─────────────────────────────────────────
def test_the_stored_id_is_the_asset_ref_the_canonical_contract_derives():
    record = observation_store.PublishedObservationV1.model_validate(_payload())
    item = observation_store.bundle_item(
        {"payload": record.stored_payload(), "published_at": PUBLISHED}
    )
    [canonical] = observation_runtime.canonicalize_bundle(
        bundle={"field_id": "fld_a", "observations": {"ndvi": item}},
        tenant_id=UUID(TENANT),
        season_id="sea_2026",
    )
    assert canonical.asset_ref == f"urn:sahool:raster-asset:{record.observation_id()}", (
        "the store must be keyed on the same stable id the canonical observation carries"
    )
    assert record.observation_id() == observation_runtime.asset_stable_id(
        TENANT, "fld_a", "S2A_TEST_SCENE", "ndvi", record.acquired_at
    ), "observation_id must be observation_runtime.asset_stable_id over the asset identity"


@pytest.mark.parametrize(
    ("served_acquisition", "id_kind"),
    [
        ("2026-10-15T07:35:29+00:00", "observation_id"),  # a layer raster holds in memory
        ("2026-10-15T07:35:29Z", "observation_id"),
        ("2026-10-15", "acquisition_day_id"),  # rehydrated from raster_assets (DATE column)
    ],
)
def test_the_stored_row_carries_both_ids_raster_gives_one_asset(served_acquisition, id_kind):
    """W1-11 review (MEDIUM): raster's computed path names one asset by its capture instant
    while the layer is in memory and by its DATE after a restart. The asset reference stays the
    frozen wire id; the stored row carries both, so a ref a decision recorded joins to it."""
    record = observation_store.PublishedObservationV1.model_validate(_payload())
    [computed] = observation_runtime.canonicalize_bundle(
        bundle={
            "field_id": "fld_a",
            "observations": {"ndvi": _raster_item(acquisition=served_acquisition)},
        },
        tenant_id=UUID(TENANT),
        season_id="sea_2026",
    )
    expected = getattr(record, id_kind)()
    assert computed.asset_ref == f"urn:sahool:raster-asset:{expected}", (
        f"raster serving {served_acquisition!r} must name the stored row by its {id_kind}"
    )
    assert record.observation_id() != record.acquisition_day_id(), "two ids for one asset"


def test_a_new_geometry_or_algorithm_is_a_new_revision_of_the_same_observation():
    """W1-11 review (HIGH): a boundary edit or a reprocess must not collide with the old row."""
    base = observation_store.PublishedObservationV1.model_validate(_payload())
    moved = observation_store.PublishedObservationV1.model_validate(
        _payload(geometry_revision=4, product_identity_key="pik_2")
    )
    reprocessed = observation_store.PublishedObservationV1.model_validate(
        _payload(algorithm_version="3.0.0", product_identity_key="pik_3")
    )
    rerun = observation_store.PublishedObservationV1.model_validate(
        _payload(processing_job_id="job_9", cog_uri="s3://bucket/fld_a/ndvi_9.tif")
    )
    assert base.observation_id() == moved.observation_id() == reprocessed.observation_id(), (
        "the scene's asset stable id does not change with the revision"
    )
    keys = {base.revision_key(), moved.revision_key(), reprocessed.revision_key()}
    assert len(keys) == 3, "each geometry revision and algorithm version is its own revision"
    assert rerun.revision_key() == base.revision_key(), "a re-written COG is the same revision"


def test_the_same_instant_in_another_zone_is_the_same_observation():
    a = observation_store.PublishedObservationV1.model_validate(_payload())
    b = observation_store.PublishedObservationV1.model_validate(
        _payload(acquired_at="2026-10-15T10:35:29+03:00")
    )
    assert a.observation_id() == b.observation_id(), "acquisition is normalised to UTC"
    assert a.content_sha256() == b.content_sha256(), "the content hash sees the same instant"


def test_delivery_metadata_is_outside_the_content_hash_but_observed_values_are_not():
    base = observation_store.PublishedObservationV1.model_validate(_payload())
    rerun = observation_store.PublishedObservationV1.model_validate(
        _payload(
            data_available_at="2026-10-20T00:00:00+00:00",
            processing_job_id="job_2",
            cog_uri="s3://bucket/fld_a/ndvi_2.tif",
        )
    )
    changed = observation_store.PublishedObservationV1.model_validate(
        _payload(stats={"mean": 0.62, "min": 0.2, "max": 0.8, "std": 0.1})
    )
    assert base.content_sha256() == rerun.content_sha256(), (
        "re-writing the same COG must replay, not conflict"
    )
    assert base.observation_id() == changed.observation_id(), "same asset, same id"
    assert base.content_sha256() != changed.content_sha256(), "another mean is other content"


def test_a_stored_payload_carries_numbers_never_decimal_text():
    record = observation_store.PublishedObservationV1.model_validate(_payload())
    stored = record.stored_payload()
    assert isinstance(stored["stats"]["mean"], float), "mean must be a JSON number"
    assert isinstance(stored["valid_pixel_ratio"], float), "ratios must be JSON numbers"


@pytest.mark.parametrize(
    "overrides",
    [
        {"stats": {"mean": "0.61"}},  # decimal text (gap CANONICAL-DECIMAL-ARRIVES-AS-TEXT…)
        {"valid_pixel_ratio": "0.9"},
        {"valid_pixel_ratio": 1.5},
        {"cloud_pct": 101.0},
        {"acquired_at": "2026-10-15T07:35:29"},  # no timezone
        {"scene_id": "   "},
        {"quality_gate_passed": "true"},
        {"unexpected": 1},
    ],
)
def test_an_invalid_payload_is_refused_by_the_store_model(overrides):
    """The drain stores nothing it cannot validate (``observation_drain.settle`` rejects it)."""
    with pytest.raises(ValueError):
        observation_store.PublishedObservationV1.model_validate(_payload(**overrides))


def test_a_non_finite_number_is_refused():
    with pytest.raises(ValueError):
        observation_store.PublishedObservationV1.model_validate(
            _payload(stats={"mean": float("nan")})
        )


def test_without_a_database_the_store_refuses_to_write(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    record = observation_store.PublishedObservationV1.model_validate(_payload())
    import asyncio

    with pytest.raises(observation_store.StoreUnavailable):
        asyncio.run(observation_store.insert_observation(record))


def test_the_geometry_revision_is_bounded_by_its_integer_column():
    """``canonical_observations.geometry_revision`` is an INTEGER: a value above its range
    would pass ``ge=0`` and then overflow the column on every retry."""
    model = observation_store.PublishedObservationV1
    assert model.model_validate(_payload(geometry_revision=2**31 - 1)).geometry_revision
    with pytest.raises(ValueError):
        model.model_validate(_payload(geometry_revision=2**31))


class _RefusingConnection:
    """A connection whose INSERT fails with ``error`` (the store's write path up to the driver)."""

    def __init__(self, error):
        self.error = error
        self.closed = False

    def transaction(self):
        import contextlib

        @contextlib.asynccontextmanager
        async def _tx():
            yield

        return _tx()

    async def execute(self, *_args):
        return None

    async def fetchrow(self, *_args):
        raise self.error

    async def close(self):
        self.closed = True


def _write_failure(monkeypatch, error):
    import asyncio

    conn = _RefusingConnection(error)

    async def _connect():
        return conn

    monkeypatch.setattr(observation_store, "_connect", _connect)
    record = observation_store.PublishedObservationV1.model_validate(_payload())
    try:
        asyncio.run(observation_store.insert_observation(record))
    finally:
        assert conn.closed, "the connection is closed either way"


def _asyncpg_errors():
    import asyncpg.exceptions as pg
    from asyncpg.exceptions import _base as pg_base

    permanent = [
        pg_base.DataError("invalid input for query argument $12: 2147483648 (out of int32 range)"),
        pg.NumericValueOutOfRangeError("integer out of range"),
        pg.CharacterNotInRepertoireError("invalid byte sequence"),
        pg.CheckViolationError("new row violates check constraint"),
        pg.NotNullViolationError("null value"),
    ]
    transient = [
        pg.UniqueViolationError("duplicate key"),
        pg.ConnectionDoesNotExistError("connection was closed"),
        pg.InsufficientPrivilegeError("permission denied"),
        pg.SerializationError("could not serialize"),
        OSError("network down"),
        TimeoutError(),
    ]
    return permanent, transient


@pytest.mark.parametrize("index", range(len(_asyncpg_errors()[0])))
def test_a_payload_the_database_refuses_is_a_permanent_rejection(monkeypatch, index):
    error = _asyncpg_errors()[0][index]
    with pytest.raises(observation_store.StoreRejected) as caught:
        _write_failure(monkeypatch, error)
    detail = str(caught.value)
    assert detail.startswith("store refused the payload: ") and type(error).__name__ in detail
    assert "2147483648" not in detail, "the offered values stay out of the detail"


@pytest.mark.parametrize("index", range(len(_asyncpg_errors()[1])))
def test_an_unavailable_store_stays_transient(monkeypatch, index):
    error = _asyncpg_errors()[1][index]
    with pytest.raises(observation_store.StoreUnavailable):
        _write_failure(monkeypatch, error)


# ── the read routes: raster says which product is current, the store serves its fact ────────
def _raster_item(
    *,
    mean=0.6,
    acquisition="2026-10-15T07:35:29+00:00",
    scene="S2A_TEST_SCENE",
    revision=3,
    algorithm="2.1.0",
    qa="scl-v1",
):
    """One raster ``/indicator-observation-bundle`` item as layer_lookup builds it."""
    return {
        "real_data": True,
        "date": acquisition[:10],
        "stats": {"mean": mean, "min": 0.2, "max": 0.8, "std": 0.1},
        "coverage_ratio": 0.94,
        "valid_pixel_ratio": 0.91,
        "cloud_pct": 4.0,
        "confidence": 0.89,
        "index_quality_flags": [],
        "grid_identity": None if revision is None else {"geometry_revision": revision},
        "indicator_product": {
            "source": "raster-service",
            "estimated": False,
            "real_data": True,
            "quality_gate_passed": True,
            "quality_score": 0.89,
            "valid_pixel_ratio": 0.91,
            "data_available_at": "2026-10-15T09:00:00+00:00",
            "provenance": {
                "scene_id": scene,
                "qa_mask_version": qa,
                "algorithm_version": algorithm,
                "acquisition_datetime": acquisition,
            },
        },
    }


def _row(indicator="ndvi", scene="S2A_TEST_SCENE", acquired="2026-10-15T07:35:29+00:00", **kw):
    record = observation_store.PublishedObservationV1.model_validate(
        _payload(indicator=indicator, scene_id=scene, acquired_at=acquired, **kw)
    )
    return {
        "observation_id": record.observation_id(),
        "acquisition_day_id": record.acquisition_day_id(),
        "indicator_code": indicator,
        "scene_id": scene,
        "acquired_at": record.acquired_at,
        "geometry_revision": record.geometry_revision,
        "algorithm_version": record.algorithm_version,
        "qa_mask_version": record.qa_mask_version,
        "payload": record.stored_payload(),
        "published_at": PUBLISHED,
    }


@pytest.fixture
def reads(monkeypatch):
    """raster-service's bundle (``items``) and the store's rows (``rows``), stubbed at the
    function boundary: ``fetch_canonical_observations`` and ``observations_for_assets``."""
    state = {"items": {"ndvi": _raster_item()}, "rows": [], "store_calls": [], "raster": 0}

    async def _fetch(*, field_id, tenant_id, season_id, indicators):
        state["raster"] += 1
        bundle = {"field_id": field_id, "observations": dict(state["items"])}
        observation_runtime.LAST_BUNDLE.set(bundle)
        return observation_runtime.canonicalize_bundle(
            bundle=bundle, tenant_id=tenant_id, season_id=season_id
        )

    async def _for_assets(*, tenant_id, field_id, observation_ids):
        state["store_calls"].append((str(tenant_id), field_id, list(observation_ids)))
        return state["rows"]

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(main.observation_store, "configured", lambda: True)
    monkeypatch.setattr(main.observation_store, "observations_for_assets", _for_assets)
    monkeypatch.setattr(main, "fetch_canonical_observations", _fetch)
    return state


def _observations(indicators="ndvi"):
    return client.get(
        "/v1/fields/fld_a/observations",
        params={"season_id": "sea_2026", "indicators": indicators},
        headers={"X-Tenant-Id": TENANT, "X-Agent-Token": TOKEN},
    )


def test_the_stored_fact_of_the_current_product_is_served(reads):
    row = _row()
    reads["rows"] = [row]
    response = _observations()
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["observation_source"], body["store_status"]) == ("canonical_store", "served"), body
    [obs] = body["observations"]
    assert obs["asset_ref"] == f"urn:sahool:raster-asset:{row['observation_id']}", obs
    assert obs["published_at"].startswith("2026-10-16T09:00:00"), (
        "the stored publication time, not the time of the read"
    )
    assert float(obs["summary"]["mean"]) == pytest.approx(0.61), "the stored published mean"
    assert reads["store_calls"] == [(TENANT, "fld_a", [row["observation_id"]])], reads


def test_two_reads_of_a_stored_observation_are_identical(reads):
    reads["rows"] = [_row()]
    first, second = _observations().json(), _observations().json()
    assert first["observations"] == second["observations"], "a stored fact replays exactly"


def test_after_a_boundary_edit_the_old_polygon_row_is_never_served(reads):
    """W1-11 review (HIGH), reproduced: revision 1 stored (0.61); raster now serves revision 2."""
    reads["items"] = {"ndvi": _raster_item(mean=0.42, revision=2)}
    reads["rows"] = [_row(geometry_revision=1, product_identity_key="pik_r1")]
    body = _observations().json()
    assert body["observation_source"] == "raster_computed_fallback", body
    assert body["store_status"] == "not_stored", body
    assert float(body["observations"][0]["summary"]["mean"]) == pytest.approx(0.42), (
        "the current geometry's value, never the old polygon's"
    )
    revised = {"stats": {"mean": 0.43, "min": 0.2, "max": 0.8, "std": 0.1}}
    reads["rows"].append(_row(geometry_revision=2, product_identity_key="pik_r2", **revised))
    body = _observations().json()
    assert body["observation_source"] == "canonical_store", body
    assert float(body["observations"][0]["summary"]["mean"]) == pytest.approx(0.43), (
        "the stored revision-2 fact once it is pushed"
    )


def test_a_reprocess_under_a_new_algorithm_is_not_served_from_the_old_row(reads):
    reads["items"] = {"ndvi": _raster_item(algorithm="3.0.0")}
    reads["rows"] = [_row()]
    body = _observations().json()
    assert body["observation_source"] == "raster_computed_fallback", body


def test_a_raster_item_with_no_algorithm_version_matches_nothing(reads):
    reads["items"] = {"ndvi": _raster_item(algorithm=None)}
    reads["rows"] = [_row(algorithm_version=None)]
    assert _observations().json()["observation_source"] == "raster_computed_fallback", (
        "an unknown producer is not proof of the same product"
    )


def test_a_stale_product_is_not_served_from_the_store(reads):
    """raster-service dropped the asset (stale after a boundary edit): nothing is current."""
    reads["items"] = {}
    reads["rows"] = [_row()]
    response = _observations()
    assert response.status_code == 424, response.text
    assert reads["store_calls"] == [], "the store is never asked to stand in for currency"


def test_after_a_raster_restart_the_rehydrated_layer_binds_to_its_stored_row(reads):
    reads["items"] = {"ndvi": _raster_item(acquisition="2026-10-15")}
    reads["rows"] = [_row()]
    body = _observations().json()
    assert body["observation_source"] == "canonical_store", body


@pytest.mark.parametrize(
    ("configured", "rows", "status"),
    [(False, [], "not_configured"), (True, None, "unavailable"), (True, [], "not_stored")],
)
def test_the_computed_path_is_the_declared_fallback(reads, monkeypatch, configured, rows, status):
    monkeypatch.setattr(main.observation_store, "configured", lambda: configured)
    reads["rows"] = rows
    response = _observations()
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["observation_source"], body["store_status"]) == (
        "raster_computed_fallback",
        status,
    ), body
    assert float(body["observations"][0]["summary"]["mean"]) == pytest.approx(0.6), body


def test_a_stand_in_for_raster_without_a_bundle_is_unbound(reads, monkeypatch):
    async def _fetch(*, field_id, tenant_id, season_id, indicators):
        return observation_runtime.canonicalize_bundle(
            bundle={"field_id": field_id, "observations": {"ndvi": _raster_item()}},
            tenant_id=tenant_id,
            season_id=season_id,
        )

    monkeypatch.setattr(main, "fetch_canonical_observations", _fetch)
    reads["rows"] = [_row()]
    body = _observations().json()
    assert (body["observation_source"], body["store_status"]) == (
        "raster_computed_fallback",
        "unbound",
    ), body


def test_some_indicators_stored_and_some_computed_says_so(reads):
    reads["items"] = {"ndvi": _raster_item(), "ndmi": _raster_item(mean=0.2)}
    reads["rows"] = [_row("ndvi")]
    body = _observations("ndvi,ndmi").json()
    assert body["observation_source"] == "canonical_store_with_raster_computed", body
    assert body["store_status"] == "partial", body
    assert len(body["observations"]) == 2, body


# ── the timeline: every raster point stays, each stored product replaces its point ──────────
def _season_client(monkeypatch, points, *, raster_status=200):
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/seasons"):
            return httpx.Response(
                200,
                json=[
                    {
                        "season_id": "sea_2026",
                        "field_id": "fld_a",
                        "sowing_date": "2026-09-01",
                        "season_end": "2026-12-31",
                    }
                ],
            )
        if raster_status != 200:
            return httpx.Response(raster_status)
        return httpx.Response(
            200, json={"available": True, "real_data": True, "points": list(points)}
        )

    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(observation_timeline, "RASTER_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(main.httpx, "AsyncClient", _client)
    monkeypatch.setattr(main.observation_store, "configured", lambda: True)
    return seen


def _raster_point(day, mean, scene=None, revision=3, algorithm="2.1.0", qa="scl-v1"):
    """One raster ``/timeseries`` point as ``raster_field_runtime._timeseries_point`` builds it."""
    return {
        "datetime": day,
        "mean": mean,
        "valid_pixel_ratio": 0.9,
        "coverage_ratio": 0.95,
        "cloud_pct": 3.0,
        "scene_id": scene or f"S2A_{day}",
        "geometry_revision": revision,
        "source_uri": f"s3://bucket/fld_a/ndvi_{day}.tif",
        "algorithm_version": algorithm,
        "qa_mask_version": qa,
    }


def _timeline():
    return client.get(
        "/v1/fields/fld_a/observation-timeline",
        params={"season_id": "sea_2026"},
        headers={"X-Tenant-Id": TENANT, "Authorization": "Bearer t"},
    )


EIGHT_DAYS = [f"2026-10-{d:02d}" for d in (1, 3, 5, 7, 9, 11, 13, 15)]


def test_one_stored_scene_does_not_truncate_the_season(monkeypatch):
    """W1-11 review (MEDIUM): 8 raster points, 1 pushed after deploy ⇒ still 8 entries."""
    points = [_raster_point(day, 0.4 + i / 100) for i, day in enumerate(EIGHT_DAYS)]
    seen = _season_client(monkeypatch, points)
    windows = []

    async def _between(*, tenant_id, field_id, indicator, start, end):
        windows.append((start, end))
        return [
            _row(
                scene="S2A_2026-10-15",
                acquired="2026-10-15T07:35:29+00:00",
                stats={"mean": 0.55, "min": 0.2, "max": 0.8, "std": 0.1},
            )
        ]

    monkeypatch.setattr(main.observation_store, "observations_between", _between)
    response = _timeline()
    assert response.status_code == 200, response.text
    body = response.json()
    entries = body["entries"]
    assert len(entries) == 8, f"no history dropped: {len(entries)} entries"
    assert [p for p in seen if p.endswith("/timeseries")], "raster is still the currency source"
    assert body["observation_sources"] == {"ndvi": "canonical_store_with_raster_computed"}, body
    assert entries[0]["publication_status"] == "published", entries[0]
    assert {e["publication_status"] for e in entries[1:]} == {"superseded"}, entries[1:]
    assert float(entries[0]["summary"]["mean"]) == pytest.approx(0.55), "the stored fact"
    assert windows == [(datetime(2026, 9, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))], (
        "the season window is inclusive by calendar day"
    )


def test_stored_and_computed_points_have_the_same_refs(monkeypatch):
    points = [_raster_point("2026-10-15", 0.5, scene="S2A_TEST_SCENE")]
    _season_client(monkeypatch, points)

    async def _none(**_kw):
        return []

    monkeypatch.setattr(main.observation_store, "observations_between", _none)
    computed = _timeline().json()["entries"][0]

    async def _stored(**_kw):
        return [_row()]

    monkeypatch.setattr(main.observation_store, "observations_between", _stored)
    body = _timeline().json()
    assert body["observation_sources"] == {"ndvi": "canonical_store"}, body
    stored = body["entries"][0]
    assert (stored["observation_ref"], stored["asset_ref"]) == (
        computed["observation_ref"],
        computed["asset_ref"],
    ), "which source served a point must not change its references"


def test_a_stored_row_of_an_old_geometry_or_an_unlisted_day_is_not_served(monkeypatch):
    points = [_raster_point("2026-10-15", 0.42, scene="S2A_TEST_SCENE", revision=4)]
    _season_client(monkeypatch, points)

    async def _between(**_kw):
        return [
            _row(geometry_revision=3),  # the old boundary of the same scene
            _row(scene="S2A_GONE", acquired="2026-10-20T07:00:00+00:00"),  # raster dropped it
        ]

    monkeypatch.setattr(main.observation_store, "observations_between", _between)
    body = _timeline().json()
    assert body["observation_sources"] == {"ndvi": "raster_computed_fallback"}, body
    assert len(body["entries"]) == 1, body["entries"]
    assert float(body["entries"][0]["summary"]["mean"]) == pytest.approx(0.42), body["entries"]


def test_the_timeline_still_fails_when_raster_cannot_answer(monkeypatch):
    _season_client(monkeypatch, [], raster_status=500)

    async def _between(**_kw):
        return [_row()]

    monkeypatch.setattr(main.observation_store, "observations_between", _between)
    assert _timeline().status_code == 424, "no silent store-only history when raster is down"


def _merge(points, rows):
    return observation_store.merge_timeline_points(
        points, rows, tenant_id=UUID(TENANT), field_id="fld_a", indicator="ndvi"
    )


def test_a_raster_point_without_a_scene_is_left_as_computed():
    point = {"datetime": "2026-10-15", "mean": 0.5, "scene_id": None, "geometry_revision": 3}
    merged, stored = _merge([point], [_row()])
    assert (merged, stored) == ([point], 0), "an unnamed scene cannot prove the same product"


def test_a_reprocessed_scene_serves_raster_current_value_not_the_old_stored_row(monkeypatch):
    """W1-11 review (MEDIUM): the same scene and geometry revision reprocessed under a new
    algorithm. The new revision's push has not reached the store (still pending in the raster
    outbox, or refused), so the store holds only the old algorithm's row. The timeline must serve
    raster's current value, as /observations does (``match_bundle_item``), not the old fact."""
    points = [_raster_point("2026-10-15", 0.42, scene="S2A_TEST_SCENE", algorithm="2.2.0")]
    _season_client(monkeypatch, points)
    rows = [_row(algorithm_version="2.1.0")]  # mean 0.61, the superseded revision

    async def _between(**_kw):
        return rows

    monkeypatch.setattr(main.observation_store, "observations_between", _between)
    body = _timeline().json()
    assert body["observation_sources"] == {"ndvi": "raster_computed_fallback"}, body
    [entry] = body["entries"]
    assert float(entry["summary"]["mean"]) == pytest.approx(0.42), (
        "raster's current product, not the stored value of the older algorithm"
    )


@pytest.mark.parametrize(
    "point_overrides",
    [
        {"algorithm": "2.2.0"},
        {"qa": "scl-v2"},
        {"revision": 4},
        {"algorithm": None},
    ],
    ids=["other_algorithm", "other_qa_mask", "other_geometry", "unreported_algorithm"],
)
def test_the_timeline_matches_the_full_product_revision(point_overrides):
    point = _raster_point("2026-10-15", 0.42, scene="S2A_TEST_SCENE", **point_overrides)
    merged, stored = _merge([point], [_row()])
    assert (merged, stored) == ([point], 0), "a row of another revision is never served"


def test_the_timeline_and_observations_share_one_matching_rule():
    point = _raster_point("2026-10-15", 0.42, scene="S2A_TEST_SCENE")
    row = _row()
    merged, stored = _merge([point], [row])
    assert stored == 1 and merged[0]["mean"] == pytest.approx(0.61), merged
    assert (
        observation_store.match_bundle_item(
            [row],
            observation_id=row["acquisition_day_id"],
            identity=observation_store.timeline_point_identity(point),
        )
        is row
    )


def test_there_is_no_ingest_route_raster_could_push_to():
    """Owner decision 2026-11-16 (pull form): raster-service never calls this service, so the
    push target ``POST /internal/v1/observations`` is gone, not kept as dead surface."""
    paths = {(m, r.path) for r in main.app.routes for m in getattr(r, "methods", ()) or ()}
    assert ("POST", "/internal/v1/observations") not in paths, paths
    assert "/internal/v1/observations" not in main.app.openapi()["paths"]
