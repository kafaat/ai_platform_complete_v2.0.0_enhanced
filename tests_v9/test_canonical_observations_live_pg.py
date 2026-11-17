"""W1-11 (finding remote-1, owner decision 2026-11-16) — canonical observations as stored facts, live PG.

An NDVI observation existed only while raster-service answered: indicators-service recomputed it
from the latest COG on every read, so nothing could replay what a decision had seen. v286 adds
``canonical_observations`` (owner indicators-service, append-only, RLS FORCE) and
``raster_observation_outbox`` (owner raster-service, the durable delivery marker). Owner decision
of 2026-11-16 (pull form): indicators-service PULLS from raster's outbox over raster's internal
feed; raster-service never calls indicators-service (a push closed an architecture-graph cycle).
Measured on the migrated schema, with the real indicators-service drain and store, and the real
raster outbox and feed routes, all under the NOSUPERUSER / NOBYPASSRLS role:

1. a published observation is stored once: created, then the same content is a replay, and a
   re-written COG (delivery metadata only) is a replay that keeps the first delivery;
2. other content under the same stable id and product revision is a conflict and the row does
   not move;
3. a boundary edit (new geometry revision) or a reprocess (new algorithm version) of the same
   scene is a new revision: created, a second row, never a conflict (W1-11 review, HIGH);
4. the table refuses UPDATE, DELETE and TRUNCATE, for the restricted role and for the owner;
5. another tenant sees none of it, cannot insert under the first tenant, and its read is empty;
6. ``/observations`` serves the stored fact of the product raster-service serves now, twice
   identically, and after a boundary edit serves raster's current value, never the old polygon's;
   the season timeline serves a stored point only at raster's product revision, so a reprocess
   that is not stored yet keeps raster's value;
7. the pull end to end: raster's publish queues the entry; with the drain disabled nothing is
   stored and the entry stays pending (negative control); enabled, the drain reads the tenant's
   pending entries through raster's feed route, stores them, and acknowledges them delivered;
   other content is acknowledged as a conflict (terminal, never a success), an invalid payload as
   rejected, another tenant's entry is neither read nor settled, and an unavailable store leaves
   the entry pending for the next cycle;
8. raster's feed is tenant-bound and its acknowledgement idempotent: another tenant neither sees
   nor settles an entry, a repeated acknowledgement changes nothing, a wrong digest or another
   outcome is refused, and no entry is ever deleted;
9. v286 re-applies cleanly, and its down removes both tables (then it is applied again).

Run: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration <this file>``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_CERTIFICATION_REQUIRED = os.getenv("CANONICAL_OBSERVATIONS_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    import httpx
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")
    httpx = pytest.importorskip("httpx", reason="httpx is not installed")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "CANONICAL_OBSERVATIONS_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL and "
        "TEST_DATABASE_URL: the job claims a certification with no database to certify on."
    )
pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="needs TEST_DATABASE_ADMIN_URL and TEST_DATABASE_URL (live DB, restricted role)",
    )
)

_ROOT = Path(__file__).resolve().parents[1]
_INDICATORS = _ROOT / "services" / "indicators-service"
_RASTER = _ROOT / "services" / "raster-service"
_MIGRATION = _ROOT / "migrations" / "v286_canonical_observations.sql"
_DOWN = _ROOT / "migrations" / "v286_canonical_observations.down.sql"
_TOKEN = "live-mesh-token"


def _load_indicators():
    spec = importlib.util.spec_from_file_location(
        "indicators_service_main_live", _INDICATORS / "main.py"
    )
    assert spec and spec.loader, "indicators-service main.py must load"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_raster(monkeypatch):
    """raster-service's real outbox module and its real app (tenant middleware, auto-registered
    routers, including ``routers/observation_feed.py``) on the restricted role."""
    for path in (str(_ROOT), str(_RASTER)):
        if path not in sys.path:
            sys.path.append(path)
    import db_persist
    import observation_outbox
    import raster_settings
    from raster_app_factory import create_raster_app

    monkeypatch.setattr(db_persist, "DATABASE_URL", _APP_DSN)
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", _TOKEN)
    app = create_raster_app(title="raster-live", version="live", lifespan=None, cors_origins=[])
    return observation_outbox, app


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _APP_DSN)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _TOKEN)
    main = _load_indicators()
    from fastapi.testclient import TestClient

    return main, TestClient(main.app)


def _tenant() -> str:
    return str(uuid.uuid4())


def _payload(tenant: str, field: str, **overrides):
    body = {
        "schema_version": "sahool.published_observation/1",
        "tenant_id": tenant,
        "field_id": field,
        "indicator": "ndvi",
        "scene_id": "S2A_LIVE_SCENE",
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
        "product_identity_key": f"pik_{field}",
        "geometry_revision": 1,
        "data_available_at": "2026-10-15T09:00:00+00:00",
        "processing_job_id": "job_1",
        "cog_uri": "s3://bucket/x/ndvi_1.tif",
    }
    body.update(overrides)
    return body


def _store(main, body):
    """One observation through the store path the drain uses (``insert_observation``)."""
    store = main.observation_store
    record = store.PublishedObservationV1.model_validate(body)
    return asyncio.run(store.insert_observation(record))


async def _admin_fetch(sql: str, *args):
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


def _rows(tenant: str, field: str):
    return asyncio.run(
        _admin_fetch(
            "SELECT observation_id, payload, payload_sha256, mean FROM canonical_observations "
            "WHERE tenant_id = $1::uuid AND field_id = $2",
            tenant,
            field,
        )
    )


async def _as_app(tenant: str, sql: str, *args):
    conn = await asyncpg.connect(_APP_DSN)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            return await conn.fetch(sql, *args)
    finally:
        await conn.close()


def test_the_role_is_restricted():
    async def _flags():
        conn = await asyncpg.connect(_APP_DSN)
        try:
            return await conn.fetchrow(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        finally:
            await conn.close()

    flags = asyncio.run(_flags())
    assert not flags["rolsuper"] and not flags["rolbypassrls"], (
        "TEST_DATABASE_URL must be a NOSUPERUSER NOBYPASSRLS role or nothing here is measured"
    )


def test_indicators_startup_refuses_a_role_that_bypasses_row_security(svc, monkeypatch):
    """The lifespan's role check (``shared.db_role_guard``, as raster-service): the restricted
    role starts the service; the owner role (superuser) refuses startup."""
    main, _client = svc
    from fastapi.testclient import TestClient

    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_ENABLED", "false")
    monkeypatch.delenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE", raising=False)
    monkeypatch.delenv("SAHOOL_ENFORCE_RLS_ROLE", raising=False)
    with TestClient(main.app) as started:
        assert started.get("/healthz").status_code == 200
    monkeypatch.setenv("DATABASE_URL", _ADMIN_DSN)
    with pytest.raises(RuntimeError, match="superuser"), TestClient(main.app):
        pass


def test_store_once_replay_and_keep_the_first_delivery(svc):
    main, _client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    first = _store(main, _payload(tenant, field))
    assert first["status"] == "created", first
    again = _store(main, _payload(tenant, field))
    assert again["status"] == "replayed", again
    rerun = _store(
        main,
        _payload(
            tenant,
            field,
            data_available_at="2026-10-20T00:00:00+00:00",
            processing_job_id="job_2",
            cog_uri="s3://bucket/x/ndvi_2.tif",
        ),
    )
    assert rerun["status"] == "replayed", f"a re-written COG is a replay: {rerun}"
    rows = _rows(tenant, field)
    assert len(rows) == 1, f"exactly one stored observation, got {len(rows)}"
    assert rows[0]["observation_id"] == first["observation_id"], rows[0]
    assert '"job_1"' in rows[0]["payload"], "append-only: the first delivery is what is kept"
    assert str(rows[0]["mean"]) == "0.61", f"NUMERIC, never text-parsed: {rows[0]['mean']!r}"


def test_other_content_under_the_same_id_is_a_conflict_and_nothing_moves(svc):
    main, _client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _store(main, _payload(tenant, field))["status"] == "created", "seed"
    before = _rows(tenant, field)
    conflict = _store(main, _payload(tenant, field, stats={"mean": 0.7}))
    assert conflict["status"] == "conflict", conflict
    assert conflict["stored_payload_sha256"] != conflict["payload_sha256"], conflict
    after = _rows(tenant, field)
    assert [dict(r) for r in after] == [dict(r) for r in before], "the stored row is untouched"


def test_a_new_geometry_or_algorithm_is_a_new_revision_not_a_conflict(svc):
    main, _client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    first = _store(main, _payload(tenant, field))
    assert first["status"] == "created", first
    moved = _store(
        main,
        _payload(
            tenant,
            field,
            geometry_revision=2,
            product_identity_key=f"pik_{field}_r2",
            stats={"mean": 0.42},
        ),
    )
    assert moved["status"] == "created", f"a boundary edit is a new revision: {moved}"
    reprocessed = _store(
        main,
        _payload(
            tenant,
            field,
            algorithm_version="3.0.0",
            product_identity_key=f"pik_{field}_a3",
            stats={"mean": 0.6},
        ),
    )
    assert reprocessed["status"] == "created", f"a reprocess is a new revision: {reprocessed}"
    ids = {r["observation_id"] for r in (first, moved, reprocessed)}
    assert len(ids) == 1, f"one observation (the scene's asset), three revisions: {ids}"
    assert len(_rows(tenant, field)) == 3, "every revision is kept, append-only"


def test_the_table_is_append_only_for_everyone(svc):
    main, _client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _store(main, _payload(tenant, field))["status"] == "created", "seed"
    for sql in (
        "UPDATE canonical_observations SET mean = 0 WHERE field_id = $1",
        "DELETE FROM canonical_observations WHERE field_id = $1",
    ):
        with pytest.raises(asyncpg.PostgresError) as app_err:
            asyncio.run(_as_app(tenant, sql, field))
        assert app_err.value.sqlstate == "55000", f"restricted role: {sql} → {app_err.value}"
        with pytest.raises(asyncpg.PostgresError) as owner_err:
            asyncio.run(_admin_fetch(sql, field))
        assert owner_err.value.sqlstate == "55000", f"owner: {sql} → {owner_err.value}"
    with pytest.raises(asyncpg.PostgresError) as trunc:
        asyncio.run(_admin_fetch("TRUNCATE canonical_observations"))
    assert trunc.value.sqlstate == "55000", f"TRUNCATE must be refused: {trunc.value}"
    assert len(_rows(tenant, field)) == 1, "the row survived every attempt"


def test_another_tenant_sees_nothing_and_cannot_write_for_the_first(svc):
    main, _client = svc
    tenant, other, field = _tenant(), _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    created = _store(main, _payload(tenant, field))
    assert created["status"] == "created", "seed"
    seen = asyncio.run(
        _as_app(other, "SELECT 1 FROM canonical_observations WHERE field_id = $1", field)
    )
    assert seen == [], "RLS: another tenant reads nothing"
    with pytest.raises(asyncpg.PostgresError) as err:
        asyncio.run(
            _as_app(
                other,
                "INSERT INTO canonical_observations (tenant_id, observation_id, field_id, "
                "indicator_code, scene_id, acquired_at, mean, quality_gate_passed, payload, "
                "payload_sha256) VALUES ($1::uuid, 'ast_000000000000000000000000', $2, 'ndvi', "
                "'s', now(), 0.1, true, '{}'::jsonb, repeat('0', 64))",
                tenant,
                field,
            )
        )
    assert err.value.sqlstate == "42501", f"WITH CHECK must refuse: {err.value}"
    asset = created["observation_id"]
    mine = asyncio.run(
        main.observation_store.observations_for_assets(
            tenant_id=uuid.UUID(tenant), field_id=field, observation_ids=[asset]
        )
    )
    assert len(mine or []) == 1, f"the owner reads its row: {mine}"
    rows = asyncio.run(
        main.observation_store.observations_for_assets(
            tenant_id=uuid.UUID(other), field_id=field, observation_ids=[asset]
        )
    )
    assert rows == [], "the store's read is tenant-bound"


def _raster_bundle(field: str, *, mean: float, revision: int, acquisition: str):
    """What raster-service's ``/indicator-observation-bundle`` answers for its current product."""
    return {
        "field_id": field,
        "observations": {
            "ndvi": {
                "real_data": True,
                "date": acquisition[:10],
                "stats": {"mean": mean},
                "coverage_ratio": 0.94,
                "valid_pixel_ratio": 0.91,
                "cloud_pct": 4.0,
                "confidence": 0.89,
                "index_quality_flags": [],
                "grid_identity": {"geometry_revision": revision},
                "indicator_product": {
                    "source": "raster-service",
                    "estimated": False,
                    "quality_gate_passed": True,
                    "quality_score": 0.89,
                    "data_available_at": "2026-10-15T09:00:00+00:00",
                    "provenance": {
                        "scene_id": "S2A_LIVE_SCENE",
                        "qa_mask_version": "scl-v1",
                        "algorithm_version": "2.1.0",
                        "acquisition_datetime": acquisition,
                    },
                },
            }
        },
        "real_data": True,
        "bundle_consistency": True,
        "mixed_scene": False,
    }


def test_observations_serve_the_stored_fact_of_raster_s_current_product(svc, monkeypatch):
    main, client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    created = _store(main, _payload(tenant, field))
    assert created["status"] == "created", created
    current = {"bundle": _raster_bundle(field, mean=0.6, revision=1, acquisition="2026-10-15")}

    async def _raster(*, field_id, tenant_id, season_id, indicators):
        # raster-service after a restart: the layer carries its acquisition DATE only
        main.observation_runtime.LAST_BUNDLE.set(current["bundle"])
        return main.canonicalize_bundle(
            bundle=current["bundle"], tenant_id=tenant_id, season_id=season_id
        )

    monkeypatch.setattr(main, "fetch_canonical_observations", _raster)

    def _read():
        response = client.get(
            f"/v1/fields/{field}/observations",
            params={"season_id": "sea_live"},
            headers={"X-Tenant-Id": tenant, "X-Agent-Token": _TOKEN},
        )
        assert response.status_code == 200, response.text
        return response.json()

    first, second = _read(), _read()
    assert (first["observation_source"], first["store_status"]) == ("canonical_store", "served"), (
        first
    )
    [obs] = first["observations"]
    assert obs["asset_ref"] == f"urn:sahool:raster-asset:{created['observation_id']}", obs
    assert float(obs["summary"]["mean"]) == pytest.approx(0.61), "the stored published mean"
    assert first["observations"] == second["observations"], "a stored fact replays exactly"

    # The reviewer's live probe: the field boundary changes and raster serves revision 2.
    current["bundle"] = _raster_bundle(
        field, mean=0.42, revision=2, acquisition="2026-10-15T07:35:29+00:00"
    )
    moved = _read()
    assert moved["observation_source"] == "raster_computed_fallback", moved
    assert float(moved["observations"][0]["summary"]["mean"]) == pytest.approx(0.42), (
        "never the old polygon's stored 0.61"
    )
    stored = _store(
        main,
        _payload(
            tenant, field, geometry_revision=2, product_identity_key="pik_r2", stats={"mean": 0.43}
        ),
    )
    assert stored["status"] == "created", stored
    bound = _read()
    assert bound["observation_source"] == "canonical_store", bound
    assert float(bound["observations"][0]["summary"]["mean"]) == pytest.approx(0.43), bound


def test_the_timeline_serves_a_stored_point_only_at_raster_s_product_revision(svc):
    """W1-11 review (MEDIUM): the season timeline binds a raster point to the stored row the
    store's read returns for that day, at the same product revision (``match_bundle_item``).
    After a reprocess under a new algorithm that is not stored yet, raster's value is served."""
    main, _client = svc
    store = main.observation_store
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _store(main, _payload(tenant, field))["status"] == "created", "seed: algorithm 2.1.0"
    rows = asyncio.run(
        store.observations_between(
            tenant_id=uuid.UUID(tenant),
            field_id=field,
            indicator="ndvi",
            start=datetime(2026, 10, 1, tzinfo=UTC),
            end=datetime(2026, 11, 1, tzinfo=UTC),
        )
    )
    assert rows and rows[0]["acquisition_day_id"], f"the read carries the day id: {rows}"

    def _point(algorithm):
        return {
            "datetime": "2026-10-15",
            "mean": 0.42,
            "scene_id": "S2A_LIVE_SCENE",
            "geometry_revision": 1,
            "algorithm_version": algorithm,
            "qa_mask_version": "scl-v1",
        }

    def _merge(point):
        return store.merge_timeline_points(
            [point], rows, tenant_id=uuid.UUID(tenant), field_id=field, indicator="ndvi"
        )

    same, stored = _merge(_point("2.1.0"))
    assert stored == 1 and same[0]["mean"] == pytest.approx(0.61), "the stored fact"
    reprocessed = _point("3.0.0")
    assert _merge(reprocessed) == ([reprocessed], 0), "never the old algorithm's stored 0.61"


_RASTER_URL = "http://raster.test"


def _outbox(tenant: str):
    return asyncio.run(
        _admin_fetch(
            "SELECT id, status, attempts, last_error, delivered_at IS NOT NULL AS done, "
            "payload_sha256 FROM raster_observation_outbox WHERE tenant_id = $1::uuid ORDER BY id",
            tenant,
        )
    )


def _drain_env(monkeypatch, *tenants: str, enabled: bool = True) -> None:
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_TENANTS", ",".join(tenants))
    monkeypatch.setenv("RASTER_SERVICE_URL", _RASTER_URL)


def _cycle(main, raster_app):
    drain = main.observation_drain
    return asyncio.run(drain.run_cycle(transport=httpx.ASGITransport(app=raster_app)))


def test_the_pull_stores_what_raster_published_and_nothing_while_the_drain_is_off(svc, monkeypatch):
    """The owner's pull, end to end on the restricted role: raster's publish queues the entry,
    the drain reads it over raster's feed route, stores it and acknowledges it delivered."""
    main, _client = svc
    outbox, raster_app = _load_raster(monkeypatch)
    tenant, other, field = _tenant(), _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    payload = _payload(tenant, field)
    assert asyncio.run(outbox.publish(payload)) == "pending", "raster queues, calls no one"
    assert asyncio.run(outbox.publish(_payload(other, field))) == "pending"
    assert (
        asyncio.run(
            _as_app(
                other, "SELECT 1 FROM raster_observation_outbox WHERE tenant_id = $1::uuid", tenant
            )
        )
        == []
    ), "RLS: another tenant does not see the outbox row"

    # Negative control: the drain is off, so nothing is stored and the entry stays pending.
    _drain_env(monkeypatch, tenant, enabled=False)
    assert _cycle(main, raster_app) == {"skipped": "disabled"}
    assert _rows(tenant, field) == [], "drain off: nothing stored"
    assert [r["status"] for r in _outbox(tenant)] == ["pending"], "drain off: still pending"

    _drain_env(monkeypatch, tenant)
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    rows = _rows(tenant, field)
    assert len(rows) == 1, f"the pulled observation is stored once: {rows}"
    [entry] = _outbox(tenant)
    assert (entry["status"], entry["attempts"], entry["done"]) == ("delivered", 1, True), dict(
        entry
    )
    assert [r["status"] for r in _outbox(other)] == ["pending"], (
        "another tenant's entry is outside this partition: neither read nor settled"
    )
    assert _rows(other, field) == [], "and nothing of it was stored"

    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}, "nothing pending: no-op"
    assert len(_rows(tenant, field)) == 1 and _outbox(tenant)[0]["attempts"] == 1
    assert asyncio.run(outbox.publish(payload)) == "delivered", (
        "the same content is settled, not queued again"
    )


def test_a_conflict_or_an_invalid_payload_is_settled_terminal_never_as_success(svc, monkeypatch):
    main, _client = svc
    outbox, raster_app = _load_raster(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert asyncio.run(outbox.publish(_payload(tenant, field))) == "pending"
    assert asyncio.run(outbox.publish(_payload(tenant, field, stats={"mean": 0.7}))) == "pending"
    assert (
        asyncio.run(outbox.publish(_payload(tenant, field, scene_id="S2B", stats={"mean": "x"})))
        == "pending"
    )
    _drain_env(monkeypatch, tenant)
    before = main.observation_drain.state()["counters"]["conflict"]
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    entries = _outbox(tenant)
    assert [e["status"] for e in entries] == ["delivered", "conflict", "rejected"], [
        dict(e) for e in entries
    ]
    assert "observation_conflict" in entries[1]["last_error"], entries[1]["last_error"]
    assert not entries[1]["done"] and not entries[2]["done"], "neither counts as delivered"
    assert entries[2]["last_error"].startswith("invalid payload"), entries[2]["last_error"]
    rows = _rows(tenant, field)
    assert len(rows) == 1 and str(rows[0]["mean"]) == "0.61", "the first content stays stored"
    assert main.observation_drain.state()["counters"]["conflict"] == before + 1


def test_an_unavailable_store_leaves_the_entry_pending_for_the_next_cycle(svc, monkeypatch):
    main, _client = svc
    outbox, raster_app = _load_raster(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert asyncio.run(outbox.publish(_payload(tenant, field))) == "pending"
    _drain_env(monkeypatch, tenant)
    # A real refused connection: nothing listens on port 1.
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    before = main.observation_drain.state()["counters"]["store_unavailable"]
    assert _cycle(main, raster_app) == {"tenants": {tenant: False}}
    assert [e["status"] for e in _outbox(tenant)] == ["pending"], "not acknowledged"
    assert main.observation_drain.state()["counters"]["store_unavailable"] == before + 1
    assert main.observation_drain.state()["last_cycle_ok"] is False
    monkeypatch.setenv("DATABASE_URL", _APP_DSN)
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    assert [e["status"] for e in _outbox(tenant)] == ["delivered"], "the next cycle delivers it"
    assert len(_rows(tenant, field)) == 1


@pytest.mark.parametrize(
    ("override", "refusal"),
    [
        ({"geometry_revision": 2**31}, "DataError"),  # asyncpg: out of the INTEGER range
        ({"valid_pixel_ratio": 1.5}, "CheckViolationError"),  # the column's CHECK
    ],
)
def test_a_payload_the_database_refuses_is_store_rejected_not_unavailable(svc, override, refusal):
    """The real driver and server refusals, past the model (``model_construct``): permanent
    (``StoreRejected``, class and SQLSTATE only), never ``StoreUnavailable``; nothing stored."""
    main, _client = svc
    store = main.observation_store
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    valid = store.PublishedObservationV1.model_validate(_payload(tenant, field))
    record = valid.model_copy(update=override)
    with pytest.raises(store.StoreRejected, match=refusal) as caught:
        asyncio.run(store.insert_observation(record))
    assert "2147483648" not in str(caught.value), "the offered value stays out of the detail"
    assert _rows(tenant, field) == []


def test_a_refused_payload_is_rejected_and_the_next_entry_of_the_page_is_delivered(
    svc, monkeypatch
):
    """One payload the database refuses no longer holds the tenant's drain: it is settled
    ``rejected`` (inspectable, re-queueable) and the next entry on the same page is stored.
    The over-range value reaches the real INSERT the way the original gap let it through (the
    model then had no upper bound): the bad entry's validated record carries 2**31."""
    main, _client = svc
    outbox, raster_app = _load_raster(monkeypatch)
    store = main.observation_store
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    over_range = _payload(tenant, field, scene_id="S2B_BAD", geometry_revision=2**31)
    assert asyncio.run(outbox.publish(over_range)) == "pending"
    assert asyncio.run(outbox.publish(_payload(tenant, field))) == "pending"
    model = store.PublishedObservationV1
    real_validate = model.model_validate

    def _validate_as_before_the_bound(payload, *args, **kwargs):
        if isinstance(payload, dict) and payload.get("scene_id") == "S2B_BAD":
            fixed = real_validate({**payload, "geometry_revision": 1}, *args, **kwargs)
            return fixed.model_copy(update={"geometry_revision": payload["geometry_revision"]})
        return real_validate(payload, *args, **kwargs)

    monkeypatch.setattr(model, "model_validate", _validate_as_before_the_bound)
    _drain_env(monkeypatch, tenant)
    before = main.observation_drain.state()["counters"]
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    bad, good = _outbox(tenant)
    assert (bad["status"], good["status"]) == ("rejected", "delivered"), (dict(bad), dict(good))
    assert bad["last_error"].startswith("store refused the payload: DataError"), bad["last_error"]
    rows = _rows(tenant, field)
    assert len(rows) == 1 and str(rows[0]["mean"]) == "0.61", rows
    after = main.observation_drain.state()["counters"]
    assert after["store_unavailable"] == before["store_unavailable"], "never counted as down"

    # And with the bound in place, the same payload is refused by the model, still unstored.
    monkeypatch.setattr(model, "model_validate", real_validate)
    other = _tenant()
    assert asyncio.run(outbox.publish({**over_range, "tenant_id": other})) == "pending"
    _drain_env(monkeypatch, other)
    assert _cycle(main, raster_app) == {"tenants": {other: True}}
    [entry] = _outbox(other)
    assert entry["status"] == "rejected" and "geometry_revision" in entry["last_error"], dict(entry)


def test_the_feed_is_tenant_bound_and_its_acknowledgement_idempotent(svc, monkeypatch):
    """raster's feed routes on the real outbox: another tenant neither reads nor settles an
    entry; a repeated acknowledgement changes nothing; a wrong digest or another outcome is
    refused; nothing is deleted."""
    _main, _client = svc
    outbox, raster_app = _load_raster(monkeypatch)
    from fastapi.testclient import TestClient

    raster = TestClient(raster_app)
    tenant, other, field = _tenant(), _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert asyncio.run(outbox.publish(_payload(tenant, field))) == "pending"
    [entry] = _outbox(tenant)

    def _headers(who):
        return {"X-Agent-Token": _TOKEN, "X-Tenant-Id": who}

    def _ack(who, **overrides):
        body = {
            "id": entry["id"],
            "payload_sha256": entry["payload_sha256"],
            "outcome": "delivered",
        }
        body.update(overrides)
        response = raster.post(
            "/internal/v1/observation-outbox/acknowledgements",
            json={"entries": [body]},
            headers=_headers(who),
        )
        assert response.status_code == 200, response.text
        [result] = response.json()["results"]
        return result["result"]

    mine = raster.get("/internal/v1/observation-outbox", headers=_headers(tenant))
    assert mine.status_code == 200, mine.text
    assert [e["id"] for e in mine.json()["entries"]] == [entry["id"]]
    assert mine.json()["entries"][0]["payload"]["tenant_id"] == tenant
    theirs = raster.get("/internal/v1/observation-outbox", headers=_headers(other))
    assert theirs.status_code == 200 and theirs.json()["entries"] == [], "tenant-bound read"
    assert (
        raster.get("/internal/v1/observation-outbox", headers={"X-Tenant-Id": tenant}).status_code
        == 401
    ), "no service token, no feed"

    assert _ack(other) == "not_found", "another tenant cannot settle the entry"
    assert _ack(tenant, payload_sha256="0" * 64) == "payload_mismatch"
    assert [e["status"] for e in _outbox(tenant)] == ["pending"], "neither changed it"
    assert _ack(tenant) == "acknowledged"
    assert _ack(tenant) == "already_acknowledged", "idempotent"
    assert _ack(tenant, outcome="conflict") == "status_mismatch", "a settled entry stays settled"
    [after] = _outbox(tenant)
    assert (after["status"], after["attempts"]) == ("delivered", 1), dict(after)
    pending = raster.get("/internal/v1/observation-outbox", headers=_headers(tenant))
    assert pending.json()["entries"] == [], "settled entries leave the pending feed"
    assert len(_outbox(tenant)) == 1, "and are never deleted"


# ── W1-11 hardening (owner acceptance conditions, 2026-11-17): crash and fault cases ─────────
# Publication and the outbox write are two transactions (gap
# RASTER-OBSERVATION-PUBLISH-OUTBOX-NOT-ATOMIC-01, open). Each case below injects the fault at
# the exact step (a monkeypatched function that raises there), then proves the state the next
# cycle resumes from, on the migrated schema under the restricted role.
_OPERATOR = "live-operator-token"


def _raster_modules(monkeypatch):
    outbox, raster_app = _load_raster(monkeypatch)
    import observation_sweep
    from raster_asset_persistence import persist_raster_asset

    return outbox, raster_app, observation_sweep, persist_raster_asset


def _publish_asset(persist, tenant: str, field: str, *, scene: str = "S2A_SWEEP_SCENE") -> bool:
    """raster-service's real publish path (``persist_raster_asset``) on the live database: a
    local COG, so the asset is written ``ready`` (published) and then queued."""
    from raster_api_models import ProcessRequest

    req = ProcessRequest(
        field_id=field,
        tenant_id=tenant,
        scene_id=scene,
        capture_datetime="2026-09-01T10:15:00Z",
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider="cdse",
        raster_url="file:///scene.tif",
        precomputed_index=True,
    )
    return persist(
        req,
        f"file:///data/uploads/{field}_ndvi.tif",
        {"data_available_at": "2026-09-03T08:30:00+00:00"},
        [44, 15, 45, 16],
        {
            "valid_pixels": 9,
            "nodata_pixels": 1,
            "mean": 0.55,
            "median": 0.56,
            "min": 0.1,
            "max": 0.9,
            "std": 0.05,
        },
        job_id=f"job_{field}",
    )


def _assets(tenant: str, field: str):
    return asyncio.run(
        _admin_fetch(
            "SELECT asset_status, product_identity_key, "
            "provenance -> 'observation_payload' AS payload, "
            "provenance ->> 'observation_payload_sha256' AS digest "
            "FROM raster_assets WHERE tenant_id = $1::uuid AND field_id = $2",
            tenant,
            field,
        )
    )


def _crash_the_outbox_write(monkeypatch, outbox):
    calls: list = []

    async def _crash(payload, **_kw):
        calls.append(payload)
        raise RuntimeError("process died after publication, before the outbox write")

    monkeypatch.setattr(outbox, "publish", _crash)
    return calls


def _sweep_env(monkeypatch, *tenants: str, enabled: bool = True) -> None:
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_TENANTS", ",".join(tenants))


def test_case_a_crash_after_publish_before_the_outbox_write_is_swept_then_delivered_once(
    svc, monkeypatch
):
    main, _client = svc
    outbox, raster_app, sweep, persist = _raster_modules(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    crashed = _crash_the_outbox_write(monkeypatch, outbox)
    assert _publish_asset(persist, tenant, field) is True, "the asset is published"
    assert len(crashed) == 1, "the fault fired at the outbox write"
    [asset] = _assets(tenant, field)
    assert asset["asset_status"] == "ready", dict(asset)
    stored = json_loads(asset["payload"])
    assert stored["acquired_at"] == "2026-09-01T10:15:00+00:00", "the instant, not the DATE"
    assert stored["stats"]["median"] == 0.56, "what the row's columns do not keep"
    assert asset["digest"] == outbox.payload_sha256(crashed[0]), "the payload publish built"
    assert _outbox(tenant) == [], "no outbox row: the crash window"

    # Negative control: with the sweep off, the drain never sees it.
    _sweep_env(monkeypatch, tenant, enabled=False)
    assert asyncio.run(sweep.run_once()) == {"skipped": "disabled"}
    _drain_env(monkeypatch, tenant)
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    assert _outbox(tenant) == [] and _rows(tenant, field) == [], "sweep off: never delivered"

    _sweep_env(monkeypatch, tenant)
    first = asyncio.run(sweep.run_once())
    assert first["tenants"][tenant]["enqueued"] == 1, first
    again = asyncio.run(sweep.run_once())
    assert again["tenants"][tenant]["found"] == 0, f"idempotent: {again}"
    [entry] = _outbox(tenant)
    assert (entry["status"], entry["payload_sha256"]) == ("pending", asset["digest"]), dict(entry)

    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    rows = _rows(tenant, field)
    assert len(rows) == 1 and rows[0]["payload_sha256"], f"delivered once: {rows}"
    [entry] = _outbox(tenant)
    assert (entry["status"], entry["attempts"]) == ("delivered", 1), dict(entry)
    assert asyncio.run(sweep.run_once())["tenants"][tenant]["found"] == 0, "nothing left"


def json_loads(value):
    import json

    return json.loads(value) if isinstance(value, str) else value


def test_the_sweep_reaches_a_missing_asset_behind_a_full_batch_of_mismatched_rows(svc, monkeypatch):
    """A stored payload whose digest no longer matches never gets an outbox row, so it matches
    the sweep's query on every run. With a full batch of such rows at lower asset ids, the
    keyset cursor still reaches the genuinely missing asset after them, and the run that met
    them is reported not ok."""
    _main, _client = svc
    outbox, _raster_app, sweep, persist = _raster_modules(monkeypatch)
    tenant = _tenant()
    fields = [f"fld_{uuid.uuid4().hex[:10]}" for _ in range(3)]
    crashed = _crash_the_outbox_write(monkeypatch, outbox)
    for n, field in enumerate(fields):
        assert _publish_asset(persist, tenant, field, scene=f"S2A_SWEEP_SCENE_{n}") is True
    assert len(crashed) == 3 and _outbox(tenant) == [], "three published assets, no outbox row"
    tampered = asyncio.run(
        _admin_fetch(
            "UPDATE raster_assets SET provenance = jsonb_set(provenance, "
            "'{observation_payload_sha256}', to_jsonb(repeat('0', 64))) "
            "WHERE tenant_id = $1::uuid AND field_id = ANY($2::text[]) RETURNING id",
            tenant,
            fields[:2],
        )
    )
    assert len(tampered) == 2, tampered
    [missing] = _assets(tenant, fields[2])

    _sweep_env(monkeypatch, tenant)
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_BATCH", "2")
    runs = []
    for _ in range(3):
        runs.append(asyncio.run(sweep.run_once())["tenants"][tenant])
        if _outbox(tenant):
            break
    assert runs[0]["digest_mismatch"] == 2 and runs[0]["enqueued"] == 0, runs
    [entry] = _outbox(tenant)
    assert entry["payload_sha256"] == missing["digest"], (dict(entry), runs)
    assert len(runs) == 2, f"reached on the second run: {runs}"
    # The second pass was short, so the next one starts again from the first asset: the
    # tampered rows are met again and the run is still reported not ok.
    third = asyncio.run(sweep.run_once())["tenants"][tenant]
    assert third["digest_mismatch"] == 2 and third["enqueued"] == 0, third
    state = sweep.state()
    assert state["last_run_ok"] is False and state["last_run_mismatches"] == 2, state


def test_case_b_crash_after_the_outbox_write_before_the_drain_next_drain_delivers(svc, monkeypatch):
    main, _client = svc
    _outbox_module, raster_app, sweep, persist = _raster_modules(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _publish_asset(persist, tenant, field) is True
    assert [e["status"] for e in _outbox(tenant)] == ["pending"], "queued by the publish path"

    drain = main.observation_drain
    real_settle = drain.settle

    async def _crash(entry, who):
        raise RuntimeError("drain died after reading the entry, before storing it")

    monkeypatch.setattr(drain, "settle", _crash)
    _drain_env(monkeypatch, tenant)
    assert _cycle(main, raster_app) == {"tenants": {tenant: False}}
    assert _rows(tenant, field) == [] and [e["status"] for e in _outbox(tenant)] == ["pending"]
    _sweep_env(monkeypatch, tenant)
    assert asyncio.run(sweep.run_once())["tenants"][tenant]["found"] == 0, "no second row"

    monkeypatch.setattr(drain, "settle", real_settle)
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    assert len(_rows(tenant, field)) == 1
    [entry] = _outbox(tenant)
    assert (entry["status"], entry["attempts"]) == ("delivered", 1), dict(entry)


def test_case_c_crash_after_indicators_stored_before_ack_replays_without_a_duplicate(
    svc, monkeypatch
):
    main, _client = svc
    _outbox_module, raster_app, _sweep, persist = _raster_modules(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _publish_asset(persist, tenant, field) is True
    drain = main.observation_drain
    real_ack = drain._acknowledge

    async def _crash(*_a, **_kw):
        raise RuntimeError("drain died after storing, before the acknowledgement")

    monkeypatch.setattr(drain, "_acknowledge", _crash)
    _drain_env(monkeypatch, tenant)
    assert _cycle(main, raster_app) == {"tenants": {tenant: False}}
    assert len(_rows(tenant, field)) == 1, "stored"
    assert [e["status"] for e in _outbox(tenant)] == ["pending"], "but not acknowledged"

    monkeypatch.setattr(drain, "_acknowledge", real_ack)
    replayed = drain.state()["counters"]["replayed"]
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    assert drain.state()["counters"]["replayed"] == replayed + 1, "the next drain replays"
    assert len(_rows(tenant, field)) == 1, "no duplicate row"
    [entry] = _outbox(tenant)
    assert (entry["status"], entry["attempts"]) == ("delivered", 1), dict(entry)


def test_case_d_two_concurrent_drains_and_a_duplicate_ack_settle_once(svc, monkeypatch):
    main, _client = svc
    outbox, raster_app, _sweep, persist = _raster_modules(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _publish_asset(persist, tenant, field) is True
    [entry] = _outbox(tenant)
    drain = main.observation_drain
    real_settle = drain.settle
    _drain_env(monkeypatch, tenant)
    mismatch = drain.state()["counters"]["ack_mismatch"]

    async def _both():
        barrier = asyncio.Barrier(2)

        async def _settle(item, who):
            await barrier.wait()  # both drains hold the same pending entry before either stores
            return await real_settle(item, who)

        monkeypatch.setattr(drain, "settle", _settle)
        transport = httpx.ASGITransport(app=raster_app)
        async with (
            httpx.AsyncClient(transport=transport) as one,
            httpx.AsyncClient(transport=transport) as two,
        ):
            return await asyncio.gather(
                drain.drain_tenant(one, tenant), drain.drain_tenant(two, tenant)
            )

    assert asyncio.run(_both()) == [True, True], "neither drain errors"
    assert len(_rows(tenant, field)) == 1, "exactly one canonical row"
    [after] = _outbox(tenant)
    assert (after["status"], after["attempts"], after["done"]) == ("delivered", 1, True), dict(
        after
    )
    assert drain.state()["counters"]["ack_mismatch"] == mismatch, "no error state"

    again = asyncio.run(
        outbox.acknowledge(
            tenant,
            [
                {
                    "id": entry["id"],
                    "payload_sha256": entry["payload_sha256"],
                    "outcome": "delivered",
                }
            ],
        )
    )
    assert [r["result"] for r in again] == ["already_acknowledged"], again
    assert _outbox(tenant)[0]["attempts"] == 1, "a duplicate acknowledgement changes nothing"


def test_case_e_another_tenant_cannot_read_ack_requeue_or_sweep_the_first_tenants_outbox(
    svc, monkeypatch
):
    _main, _client = svc
    outbox, raster_app, sweep, persist = _raster_modules(monkeypatch)
    from fastapi.testclient import TestClient

    raster = TestClient(raster_app)
    tenant, other, field = _tenant(), _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _publish_asset(persist, tenant, field) is True
    [entry] = _outbox(tenant)
    monkeypatch.setenv("RASTER_OBSERVATION_OUTBOX_OPERATOR_TOKEN", _OPERATOR)
    headers = {"X-Agent-Token": _TOKEN, "X-Tenant-Id": other, "X-Operator-Token": _OPERATOR}
    for status in ("pending", "delivered", "conflict", "rejected"):
        seen = raster.get(
            "/internal/v1/observation-outbox", params={"status": status}, headers=headers
        )
        assert seen.status_code == 200 and seen.json()["entries"] == [], (status, seen.text)
    ack = raster.post(
        "/internal/v1/observation-outbox/acknowledgements",
        json={
            "entries": [
                {
                    "id": entry["id"],
                    "payload_sha256": entry["payload_sha256"],
                    "outcome": "delivered",
                }
            ]
        },
        headers=headers,
    )
    assert [r["result"] for r in ack.json()["results"]] == ["not_found"], ack.text
    requeue = raster.post(
        "/internal/v1/observation-outbox/requeue",
        json={
            "entries": [{"id": entry["id"], "payload_sha256": entry["payload_sha256"]}],
            "actor": "ops.mallory",
            "reason": "trying another tenant's entry",
        },
        headers=headers,
    )
    assert [r["result"] for r in requeue.json()["results"]] == ["not_found"], requeue.text
    # Directly on the restricted role: B's statements see and change none of A's rows.
    assert (
        asyncio.run(
            _as_app(other, "SELECT 1 FROM raster_observation_outbox WHERE id = $1", entry["id"])
        )
        == []
    )
    assert (
        asyncio.run(
            _as_app(
                other,
                "UPDATE raster_observation_outbox SET status = 'delivered' WHERE id = $1 RETURNING id",
                entry["id"],
            )
        )
        == []
    )
    # A's published asset with its outbox row removed (as if never written) is not B's to sweep.
    asyncio.run(_admin_fetch("DELETE FROM raster_observation_outbox WHERE id = $1", entry["id"]))
    _sweep_env(monkeypatch, other)
    assert asyncio.run(sweep.run_once())["tenants"][other]["found"] == 0
    assert _outbox(tenant) == [] and _outbox(other) == [], "B's sweep queued nothing of A's"
    _sweep_env(monkeypatch, tenant)
    assert asyncio.run(sweep.run_once())["tenants"][tenant]["enqueued"] == 1, "A's sweep does"


def test_a_drain_that_is_off_or_has_no_tenants_leaves_pending_entries_untouched(svc, monkeypatch):
    main, client = svc
    _outbox_module, raster_app, _sweep, persist = _raster_modules(monkeypatch)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _publish_asset(persist, tenant, field) is True
    before = [dict(e) for e in _outbox(tenant)]
    for enabled, tenants, reason in ((False, (tenant,), "disabled"), (True, (), "no_tenants")):
        _drain_env(monkeypatch, *tenants, enabled=enabled)
        assert _cycle(main, raster_app) == {"skipped": reason}
        ready = client.get("/readyz").json()
        assert ready["observation_delivery"] == "not_enabled", ready
        assert ready["observation_drain"]["ready_for_delivery"] is False
        assert [dict(e) for e in _outbox(tenant)] == before, "pending, untouched, not deleted"
    assert _rows(tenant, field) == []


def test_conflict_and_rejected_stay_inspectable_and_requeue_only_by_the_operator(svc, monkeypatch):
    main, _client = svc
    outbox, raster_app = _load_raster(monkeypatch)
    import observation_sweep
    from fastapi.testclient import TestClient

    raster = TestClient(raster_app)
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert asyncio.run(outbox.publish(_payload(tenant, field))) == "pending"
    assert asyncio.run(outbox.publish(_payload(tenant, field, stats={"mean": 0.7}))) == "pending"
    assert (
        asyncio.run(outbox.publish(_payload(tenant, field, scene_id="S2B", stats={"mean": "x"})))
        == "pending"
    )
    _drain_env(monkeypatch, tenant)
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    delivered, conflict, rejected = _outbox(tenant)
    assert [delivered["status"], conflict["status"], rejected["status"]] == [
        "delivered",
        "conflict",
        "rejected",
    ]
    service = {"X-Agent-Token": _TOKEN, "X-Tenant-Id": tenant}

    def _listed(status):
        response = raster.get(
            "/internal/v1/observation-outbox", params={"status": status}, headers=service
        )
        assert response.status_code == 200, response.text
        return response.json()["entries"]

    [seen] = _listed("conflict")
    assert seen["id"] == conflict["id"] and "observation_conflict" in seen["last_error"], seen
    assert seen["requeue_history"] == [] and seen["attempts"] == 1, seen
    assert [e["id"] for e in _listed("rejected")] == [rejected["id"]]
    assert _listed("pending") == [], "terminal entries are not what the drain reads"

    # Nothing re-queues them on its own: another drain cycle and a sweep leave them as they are.
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    _sweep_env(monkeypatch, tenant)
    asyncio.run(observation_sweep.run_once())
    assert [e["status"] for e in _outbox(tenant)] == ["delivered", "conflict", "rejected"]

    body = {
        "entries": [
            {"id": conflict["id"], "payload_sha256": conflict["payload_sha256"]},
            {"id": rejected["id"], "payload_sha256": rejected["payload_sha256"]},
            {"id": delivered["id"], "payload_sha256": delivered["payload_sha256"]},
        ],
        "actor": "ops.alice",
        "reason": "upstream store corrected; retry both",
    }
    path = "/internal/v1/observation-outbox/requeue"
    assert raster.post(path, json=body, headers=service).status_code == 503, "operator token unset"
    monkeypatch.setenv("RASTER_OBSERVATION_OUTBOX_OPERATOR_TOKEN", _OPERATOR)
    assert raster.post(path, json=body, headers=service).status_code == 403, "no operator token"
    assert (
        raster.post(path, json=body, headers={**service, "X-Operator-Token": "guess"}).status_code
        == 403
    )
    assert [e["status"] for e in _outbox(tenant)] == ["delivered", "conflict", "rejected"]

    done = raster.post(path, json=body, headers={**service, "X-Operator-Token": _OPERATOR})
    assert done.status_code == 200, done.text
    assert [r["result"] for r in done.json()["results"]] == [
        "requeued",
        "requeued",
        "status_mismatch",
    ], "a delivered entry is never re-queued"
    assert [e["status"] for e in _outbox(tenant)] == ["delivered", "pending", "pending"]
    history = asyncio.run(
        _admin_fetch(
            "SELECT requeue_history FROM raster_observation_outbox WHERE id = $1", conflict["id"]
        )
    )[0]["requeue_history"]
    [record] = json_loads(history)
    assert (record["by"], record["from_status"]) == ("ops.alice", "conflict"), record
    assert record["reason"].startswith("upstream store corrected") and record["at"], record
    assert "observation_conflict" in record["last_error"], "what it was is kept"

    # Re-queued, the drain reads them again; the content still conflicts / is invalid.
    assert _cycle(main, raster_app) == {"tenants": {tenant: True}}
    assert [e["status"] for e in _outbox(tenant)] == ["delivered", "conflict", "rejected"]
    assert len(_rows(tenant, field)) == 1, "the first content stays the stored one"
    assert len(json_loads(_listed("conflict")[0]["requeue_history"])) == 1, "history is kept"


# Last: the down drops both tables, and the re-apply does not restore the restricted role's
# grants (the bootstrap grants after the migrations), so nothing on the outbox may run after it.
def test_v286_reapplies_and_its_down_removes_both_tables():
    async def _run():
        conn = await asyncpg.connect(_ADMIN_DSN)
        try:
            await conn.execute(_MIGRATION.read_text(encoding="utf-8"))
            await conn.execute(_DOWN.read_text(encoding="utf-8"))
            gone = await conn.fetchval(
                "SELECT count(*) FROM pg_class WHERE relname IN "
                "('canonical_observations', 'raster_observation_outbox')"
            )
            await conn.execute(_MIGRATION.read_text(encoding="utf-8"))
            back = await conn.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'canonical_observations'"
            )
            return gone, back
        finally:
            await conn.close()

    gone, back = asyncio.run(_run())
    assert gone == 0, "the down removes both tables"
    assert back["relrowsecurity"] and back["relforcerowsecurity"], "re-applied with RLS FORCE"
