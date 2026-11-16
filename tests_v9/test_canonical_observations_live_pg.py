"""W1-11 (finding remote-1, owner decision 2026-11-16) — canonical observations as stored facts, live PG.

An NDVI observation existed only while raster-service answered: indicators-service recomputed it
from the latest COG on every read, so nothing could replay what a decision had seen. v286 adds
``canonical_observations`` (owner indicators-service, append-only, RLS FORCE) and
``raster_observation_outbox`` (owner raster-service, the push's durable retry marker). Measured on
the migrated schema, with the real indicators-service route and store under the NOSUPERUSER /
NOBYPASSRLS role and the real raster outbox drained on the owner connection:

1. a published observation is stored once: 201, then the same content is a 200 replay, and a
   re-written COG (delivery metadata only) is a replay that keeps the first delivery;
2. other content under the same stable id and product revision is 409 and the row does not move;
3. a boundary edit (new geometry revision) or a reprocess (new algorithm version) of the same
   scene is a new revision: 201, a second row, never a 409 (W1-11 review, HIGH);
4. the table refuses UPDATE, DELETE and TRUNCATE, for the restricted role and for the owner;
5. another tenant sees none of it, cannot insert under the first tenant, and its read is empty;
6. ``/observations`` serves the stored fact of the product raster-service serves now, twice
   identically, and after a boundary edit serves raster's current value, never the old polygon's;
   the season timeline serves a stored point only at raster's product revision, so a reprocess
   whose push is not stored keeps raster's value;
7. a push that failed stays pending in the outbox and the worker's drain delivers it later;
8. v286 re-applies cleanly, and its down removes both tables (then it is applied again).

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


def _load_outbox():
    if str(_RASTER) not in sys.path:
        sys.path.append(str(_RASTER))
    import db_persist
    import observation_outbox

    return observation_outbox, db_persist


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


def _post(client, body, tenant=None):
    return client.post(
        "/internal/v1/observations",
        json=body,
        headers={"X-Agent-Token": _TOKEN, "X-Tenant-Id": tenant or body["tenant_id"]},
    )


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


def test_store_once_replay_and_keep_the_first_delivery(svc):
    _main, client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    first = _post(client, _payload(tenant, field))
    assert first.status_code == 201, first.text
    again = _post(client, _payload(tenant, field))
    assert again.status_code == 200 and again.json()["status"] == "replayed", again.text
    rerun = _post(
        client,
        _payload(
            tenant,
            field,
            data_available_at="2026-10-20T00:00:00+00:00",
            processing_job_id="job_2",
            cog_uri="s3://bucket/x/ndvi_2.tif",
        ),
    )
    assert rerun.status_code == 200, f"a re-written COG is a replay: {rerun.text}"
    rows = _rows(tenant, field)
    assert len(rows) == 1, f"exactly one stored observation, got {len(rows)}"
    assert rows[0]["observation_id"] == first.json()["observation_id"], rows[0]
    assert '"job_1"' in rows[0]["payload"], "append-only: the first delivery is what is kept"
    assert str(rows[0]["mean"]) == "0.61", f"NUMERIC, never text-parsed: {rows[0]['mean']!r}"


def test_other_content_under_the_same_id_is_409_and_nothing_moves(svc):
    _main, client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _post(client, _payload(tenant, field)).status_code == 201, "seed"
    before = _rows(tenant, field)
    conflict = _post(client, _payload(tenant, field, stats={"mean": 0.7}))
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "observation_conflict", conflict.json()
    after = _rows(tenant, field)
    assert [dict(r) for r in after] == [dict(r) for r in before], "the stored row is untouched"


def test_a_new_geometry_or_algorithm_is_a_new_revision_not_a_conflict(svc):
    _main, client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    first = _post(client, _payload(tenant, field))
    assert first.status_code == 201, first.text
    moved = _post(
        client,
        _payload(
            tenant,
            field,
            geometry_revision=2,
            product_identity_key=f"pik_{field}_r2",
            stats={"mean": 0.42},
        ),
    )
    assert moved.status_code == 201, f"a boundary edit is a new revision: {moved.text}"
    reprocessed = _post(
        client,
        _payload(
            tenant,
            field,
            algorithm_version="3.0.0",
            product_identity_key=f"pik_{field}_a3",
            stats={"mean": 0.6},
        ),
    )
    assert reprocessed.status_code == 201, f"a reprocess is a new revision: {reprocessed.text}"
    ids = {r.json()["observation_id"] for r in (first, moved, reprocessed)}
    assert len(ids) == 1, f"one observation (the scene's asset), three revisions: {ids}"
    assert len(_rows(tenant, field)) == 3, "every revision is kept, append-only"


def test_the_table_is_append_only_for_everyone(svc):
    _main, client = svc
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _post(client, _payload(tenant, field)).status_code == 201, "seed"
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
    main, client = svc
    tenant, other, field = _tenant(), _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _post(client, _payload(tenant, field)).status_code == 201, "seed"
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
    assert _post(client, _payload(tenant, field), tenant=other).status_code == 403, (
        "the route refuses a body for another tenant"
    )
    asset = _post(client, _payload(tenant, field)).json()["observation_id"]
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
    created = _post(client, _payload(tenant, field))
    assert created.status_code == 201, created.text
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
    assert obs["asset_ref"] == created.json()["asset_ref"], obs
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
    pushed = _post(
        client,
        _payload(
            tenant, field, geometry_revision=2, product_identity_key="pik_r2", stats={"mean": 0.43}
        ),
    )
    assert pushed.status_code == 201, pushed.text
    bound = _read()
    assert bound["observation_source"] == "canonical_store", bound
    assert float(bound["observations"][0]["summary"]["mean"]) == pytest.approx(0.43), bound


def test_the_timeline_serves_a_stored_point_only_at_raster_s_product_revision(svc):
    """W1-11 review (MEDIUM): the season timeline binds a raster point to the stored row the
    store's read returns for that day, at the same product revision (``match_bundle_item``).
    After a reprocess under a new algorithm whose push is not stored, raster's value is served."""
    main, client = svc
    store = main.observation_store
    tenant, field = _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    assert _post(client, _payload(tenant, field)).status_code == 201, "seed: algorithm 2.1.0"
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


def test_a_failed_push_stays_pending_and_the_drain_delivers_it(svc, monkeypatch):
    main, _client = svc
    outbox, db_persist = _load_outbox()
    monkeypatch.setattr(db_persist, "DATABASE_URL", _APP_DSN)
    tenant, other, field = _tenant(), _tenant(), f"fld_{uuid.uuid4().hex[:10]}"
    payload = _payload(tenant, field)

    def _down(request):
        return httpx.Response(503, json={"detail": "store unavailable"})

    status = asyncio.run(outbox.publish(payload, transport=httpx.MockTransport(_down)))
    assert status == "pending", status
    [row] = asyncio.run(
        _admin_fetch(
            "SELECT id, status, attempts, next_attempt_at > now() AS later "
            "FROM raster_observation_outbox WHERE tenant_id = $1::uuid",
            tenant,
        )
    )
    assert (row["status"], row["attempts"], row["later"]) == ("pending", 1, True), dict(row)
    assert (
        asyncio.run(
            _as_app(other, "SELECT 1 FROM raster_observation_outbox WHERE field_id = $1", field)
        )
        == []
    ), "RLS: another tenant does not see the outbox row"
    assert _rows(tenant, field) == [], "nothing was stored by the failed push"

    asyncio.run(
        _admin_fetch(
            "UPDATE raster_observation_outbox SET next_attempt_at = now() WHERE id = $1",
            row["id"],
        )
    )

    async def _drain():
        pool = await asyncpg.create_pool(_ADMIN_DSN, min_size=1, max_size=2)
        try:
            transport = httpx.ASGITransport(app=main.app)
            delivered = await outbox.drain_once(pool, transport=transport)
            again = await outbox.drain_once(pool, transport=transport)
            return delivered, again
        finally:
            await pool.close()

    monkeypatch.setenv("INDICATORS_SERVICE_URL", "http://indicators.test")
    delivered, again = asyncio.run(_drain())
    assert (delivered, again) == (1, 0), f"one delivery, then nothing pending: {delivered, again}"
    [after] = asyncio.run(
        _admin_fetch(
            "SELECT status, attempts, delivered_at IS NOT NULL AS done "
            "FROM raster_observation_outbox WHERE id = $1",
            row["id"],
        )
    )
    assert (after["status"], after["attempts"], after["done"]) == ("delivered", 2, True), dict(
        after
    )
    assert len(_rows(tenant, field)) == 1, "the drained push stored the observation"
    replay = asyncio.run(outbox.publish(payload))
    assert replay == "delivered", "the same content is settled, not re-queued"


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
