"""W1-11 — indicators-service owns the canonical observation store (owner decision 2026-11-16).

Unit level: the ingest route's service-token and tenant assertion, its idempotency contract
(201 created, 200 replay, 409 conflict, 503 when the store cannot answer), the payload's stable
id (the asset reference the canonical contract already derives), numbers that are never decimal
text, and the two read routes serving stored rows with the computed path as declared fallback.
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


def _post(body, **headers):
    base = {"X-Tenant-Id": TENANT, "X-Agent-Token": TOKEN}
    base.update(headers)
    return client.post("/internal/v1/observations", json=body, headers=base)


@pytest.fixture
def store(monkeypatch):
    """Stand in for ``observation_store.insert_observation`` and record what reached it."""
    state = {"calls": [], "result": "created", "raise": None}

    async def _insert(record):
        state["calls"].append(record)
        if state["raise"] is not None:
            raise state["raise"]
        digest = record.content_sha256()
        stored = digest if state["result"] != "conflict" else "f" * 64
        return {
            "status": state["result"],
            "observation_id": record.observation_id(),
            "payload_sha256": digest,
            "stored_payload_sha256": stored,
            "published_at": PUBLISHED,
        }

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(main.observation_store, "insert_observation", _insert)
    return state


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
    assert record.observation_id() == observation_runtime._stable_id(
        "ast", TENANT, "fld_a", "S2A_TEST_SCENE", "ndvi", "2026-10-15T07:35:29+00:00"
    ), "observation_id must be observation_runtime._stable_id over the asset identity"


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
def test_an_invalid_payload_is_refused_before_the_store(store, overrides):
    response = _post(_payload(**overrides))
    assert response.status_code == 422, f"{overrides} must be refused, got {response.status_code}"
    assert store["calls"] == [], "nothing may reach the store"


def test_a_non_finite_number_is_refused():
    with pytest.raises(ValueError):
        observation_store.PublishedObservationV1.model_validate(
            _payload(stats={"mean": float("nan")})
        )


# ── the route: who may write, and the idempotency contract ─────────────────────────────────
def test_ingest_requires_the_service_token(store):
    assert _post(_payload(), **{"X-Agent-Token": "guessed"}).status_code == 401, (
        "a wrong token is refused"
    )
    response = client.post(
        "/internal/v1/observations", json=_payload(), headers={"X-Tenant-Id": TENANT}
    )
    assert response.status_code == 401, "a missing token is refused"
    assert store["calls"] == [], "nothing reaches the store without the service token"


def test_ingest_fails_closed_without_a_configured_token(store, monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "")
    assert _post(_payload(), **{"X-Agent-Token": ""}).status_code == 503, (
        "an unconfigured service token is 503, never an open door"
    )
    assert store["calls"] == [], "nothing reaches the store"


def test_ingest_refuses_a_body_for_another_tenant(store):
    response = _post(_payload(tenant_id=OTHER))
    assert response.status_code == 403, "the asserted tenant must match the body"
    assert _post(_payload(), **{"X-Tenant-Id": "not-a-uuid"}).status_code == 400, (
        "a malformed tenant assertion is refused"
    )
    assert store["calls"] == [], "nothing reaches the store"


def test_a_new_observation_is_created(store):
    response = _post(_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    record = store["calls"][0]
    assert body["status"] == "created", body
    assert body["observation_id"] == record.observation_id(), body
    assert body["asset_ref"] == f"urn:sahool:raster-asset:{record.observation_id()}", body


def test_the_same_content_again_is_a_replay(store):
    store["result"] = "replayed"
    response = _post(_payload())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "replayed", response.json()


def test_other_content_under_the_same_id_is_409(store):
    store["result"] = "conflict"
    response = _post(_payload())
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "observation_conflict", detail
    assert detail["stored_payload_sha256"] != detail["offered_payload_sha256"], detail


def test_an_unavailable_store_is_503_never_a_claimed_write(store):
    store["raise"] = observation_store.StoreUnavailable("down")
    assert _post(_payload()).status_code == 503, "the raster outbox must see a retryable status"


def test_without_a_database_the_store_refuses_to_write(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    record = observation_store.PublishedObservationV1.model_validate(_payload())
    import asyncio

    with pytest.raises(observation_store.StoreUnavailable):
        asyncio.run(observation_store.insert_observation(record))


# ── the read routes: stored rows first, computed path as declared fallback ──────────────────
def _row(indicator="ndvi", scene="S2A_TEST_SCENE", acquired="2026-10-15T07:35:29+00:00", **kw):
    record = observation_store.PublishedObservationV1.model_validate(
        _payload(indicator=indicator, scene_id=scene, acquired_at=acquired, **kw)
    )
    return {
        "observation_id": record.observation_id(),
        "indicator_code": indicator,
        "scene_id": scene,
        "acquired_at": record.acquired_at,
        "payload": record.stored_payload(),
        "published_at": PUBLISHED,
    }


@pytest.fixture
def reads(monkeypatch):
    state = {"latest": [], "computed": [], "between": {}}

    async def _latest(*, tenant_id, field_id, indicators):
        state["latest_args"] = (str(tenant_id), field_id, list(indicators))
        return state["latest"]

    async def _fetch(*, field_id, tenant_id, season_id, indicators):
        state["computed"].append(indicators)
        return []

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(main.observation_store, "configured", lambda: True)
    monkeypatch.setattr(main.observation_store, "latest_observations", _latest)
    monkeypatch.setattr(main, "fetch_canonical_observations", _fetch)
    return state


def _observations(indicators="ndvi"):
    return client.get(
        "/v1/fields/fld_a/observations",
        params={"season_id": "sea_2026", "indicators": indicators},
        headers={"X-Tenant-Id": TENANT, "X-Agent-Token": TOKEN},
    )


def test_observations_are_served_from_the_store_without_calling_raster(reads):
    row = _row()
    reads["latest"] = [row]
    response = _observations()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["observation_source"] == "canonical_store", body
    assert reads["computed"] == [], "a stored observation must not recompute from raster-service"
    [obs] = body["observations"]
    assert obs["asset_ref"] == f"urn:sahool:raster-asset:{row['observation_id']}", obs
    assert obs["published_at"].startswith("2026-10-16T09:00:00"), (
        "the stored publication time, not the time of the read"
    )
    assert obs["lineage"]["raster_provenance"]["scene_id"] == "S2A_TEST_SCENE", obs["lineage"]
    assert float(obs["summary"]["mean"]) == pytest.approx(0.61), obs["summary"]
    assert reads["latest_args"] == (TENANT, "fld_a", ["ndvi"]), reads["latest_args"]


def test_two_reads_of_a_stored_observation_are_identical(reads):
    reads["latest"] = [_row()]
    first, second = _observations().json(), _observations().json()
    assert first["observations"] == second["observations"], "a stored fact replays exactly"


@pytest.mark.parametrize(
    ("rows", "indicators", "status"),
    [
        ([], "ndvi", "incomplete"),
        ([_row("ndvi")], "ndvi,ndmi", "incomplete"),
        ([_row("ndvi"), _row("ndmi", scene="S2B_OTHER_SCENE")], "ndvi,ndmi", "mixed_scene"),
        (None, "ndvi", "unavailable"),
    ],
)
def test_the_computed_path_is_the_declared_fallback(reads, rows, indicators, status):
    reads["latest"] = rows
    response = _observations(indicators)
    # the stub computed path returns nothing, so the route answers its existing 424
    assert response.status_code == 424, response.text
    assert reads["computed"], f"{status}: the computed raster path must be used"


def test_the_fallback_says_why_it_was_used(reads, monkeypatch):
    async def _fetch(*, field_id, tenant_id, season_id, indicators):
        reads["computed"].append(indicators)
        return observation_runtime.canonicalize_bundle(
            bundle={
                "field_id": "fld_a",
                "observations": {"ndvi": observation_store.bundle_item(_row())},
            },
            tenant_id=tenant_id,
            season_id=season_id,
        )

    monkeypatch.setattr(main, "fetch_canonical_observations", _fetch)
    monkeypatch.setattr(main.observation_store, "configured", lambda: False)
    body = _observations().json()
    assert body["observation_source"] == "raster_computed_fallback", body
    assert body["store_status"] == "not_configured", body


def test_the_timeline_reads_stored_points_and_skips_raster(monkeypatch):
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
        return httpx.Response(500)

    real = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real(*args, **kwargs)

    windows = []

    async def _between(*, tenant_id, field_id, indicator, start, end):
        windows.append((start, end))
        return [
            _row(acquired="2026-10-01T07:35:29+00:00", stats={"mean": 0.5}),
            _row(acquired="2026-10-15T07:35:29+00:00"),
        ]

    monkeypatch.setattr(observation_timeline, "RASTER_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(main.httpx, "AsyncClient", _client)
    monkeypatch.setattr(main.observation_store, "observations_between", _between)
    response = client.get(
        "/v1/fields/fld_a/observation-timeline",
        params={"season_id": "sea_2026"},
        headers={"X-Tenant-Id": TENANT, "Authorization": "Bearer t"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["observation_sources"] == {"ndvi": "canonical_store"}, body
    assert not [p for p in seen if p.endswith("/timeseries")], "raster must not be called"
    assert len(body["entries"]) == 2, body["entries"]
    assert body["entries"][0]["publication_status"] == "published", body["entries"][0]
    assert windows == [(datetime(2026, 9, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))], (
        "the season window is inclusive by calendar day"
    )
