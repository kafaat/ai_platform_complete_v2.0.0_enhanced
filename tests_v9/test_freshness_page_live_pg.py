"""Compare batched freshness signals and the per-field reads on the migrated tenant schema."""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "sahool-platform"))

pytestmark = pytest.mark.integration


async def _seed(conn, tenant, other, prefix):
    await conn.execute(
        """INSERT INTO fields (field_id, name, tenant_id)
           SELECT $1 || lpad(n::text, 3, '0'), 'test ' || n::text, $2::uuid
           FROM generate_series(1, 205) n ORDER BY n DESC""",
        prefix,
        tenant,
    )
    await conn.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, 'foreign', $2)",
        prefix + "foreign",
        other,
    )
    await conn.executemany(
        """INSERT INTO imagery_automation_fields
           (field_id, tenant_id, bbox_west, bbox_south, bbox_east, bbox_north, last_ndvi_date)
           VALUES ($1, $2, 0, 0, 1, 1, '2025-01-01')""",
        [(prefix + "001", tenant), (prefix + "002", other)],
    )
    for key, field_id, lat, fetched in (
        ("old", "001", 1, "2025-01-01T20:00:00+03"),
        ("undated", "001", 2, None),
        ("new", "001", 3, "2025-01-02T01:00:00+03"),
        ("unknown", "002", 4, None),
        ("other-tenant", "foreign", 5, "2025-01-09T00:00:00+00"),
    ):
        await conn.execute(
            "INSERT INTO weather_automation_locations (location_key, lat, lon, field_id) "
            "VALUES ($1, $3, 1, $2)",
            prefix + key,
            prefix + field_id,
            lat,
        )
        await conn.execute(
            "INSERT INTO weather_automation_cache (location_key, data_json, fetched_at) "
            "VALUES ($1, $3::jsonb, $2::text::timestamptz)",
            prefix + key,
            fetched,
            json.dumps({"location": key}),
        )

    # First field has newer invalid/non-sensor/rejected/foreign measurements. In the second
    # field the 50 newest eligible candidates are invalid, so even its older valid row is hidden.
    insert_soil = """
        INSERT INTO soil_observations (
            observation_id, idempotency_key, contract_version, tenant_id, field_id, property,
            value_json, unit, depth_from_cm, depth_to_cm, observed_at, received_at,
            source_type, quality_status, confidence
        ) VALUES (
            $1, $1, 'soil-observation.v1', $2, $3, $4, $5::jsonb, $6, 0, 10,
            '2025-01-01 00:00:00+00'::timestamptz + $7::int * interval '1 hour', now(),
            $8, $9, 1
        )
    """
    observations = [
        (tenant, "001", "soil_moisture", "0.42", "m3/m3", 1, "sensor", "accepted"),
        (tenant, "001", "soil_moisture", "2", "m3/m3", 2, "sensor", "accepted"),
        (tenant, "001", "soil_moisture", "45", "%", 3, "lab", "accepted"),
        (tenant, "001", "soil_moisture", "45", "%", 4, "sensor", "rejected"),
        (tenant, "001", "soil_temperature", "45", "%", 5, "sensor", "accepted"),
        (other, "001", "soil_moisture", "45", "%", 6, "sensor", "accepted"),
        (tenant, "002", "soil_moisture", "44", "%", 1, "sensor", "accepted"),
    ]
    observations.extend(
        (tenant, "002", "soil_moisture", "101", "%", hour, "sensor", "accepted")
        for hour in range(2, 52)
    )
    await conn.executemany(
        insert_soil,
        [
            (prefix + str(index), tid, prefix + field, prop, value, unit, hour, source, quality)
            for index, (tid, field, prop, value, unit, hour, source, quality) in enumerate(
                observations
            )
        ],
    )


async def _per_field_rows(conn, tenant):
    from api.field_context import _latest_soil_moisture

    fields = await conn.fetch(
        "SELECT field_id FROM fields WHERE tenant_id=$1 ORDER BY field_id", tenant
    )
    rows = []
    for field in fields:
        field_id = field["field_id"]
        ndvi = await conn.fetchval(
            "SELECT extract(epoch FROM last_ndvi_date::timestamptz) "
            "FROM imagery_automation_fields WHERE field_id=$1",
            field_id,
        )
        soil = await _latest_soil_moisture(conn, field_id)
        weather = await conn.fetchval(
            "SELECT extract(epoch FROM max(c.fetched_at)) FROM weather_automation_cache c "
            "JOIN weather_automation_locations l USING (location_key) WHERE l.field_id=$1",
            field_id,
        )
        rows.append(
            (
                field_id,
                float(ndvi) if ndvi is not None else None,
                soil.recorded_at.timestamp() if soil else None,
                float(weather) if weather is not None else None,
            )
        )
    return rows


@pytest.fixture
def database_urls():
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL")
    app_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not app_url:
        reason = "requires migrated PostgreSQL and both admin and restricted application URLs"
        if os.getenv("FRESHNESS_CERTIFICATION_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    return admin_url, app_url


@pytest.fixture
async def weather_rows(database_urls):
    import asyncpg

    admin_url, app_url = database_urls
    app = await asyncpg.connect(app_url)
    try:
        role = await app.fetchval(
            "SELECT quote_ident(rolname) FROM pg_roles "
            "WHERE rolname = current_user AND NOT (rolsuper OR rolbypassrls)"
        )
        assert role, "the freshness comparison requires a restricted application role"
    finally:
        await app.close()

    conn = await asyncpg.connect(admin_url)
    transaction = conn.transaction()
    await transaction.start()
    try:
        tenant, other = uuid4(), uuid4()
        prefix = uuid4().hex[:16]
        await _seed(conn, tenant, other, prefix)
        yield conn, tenant, prefix, role
    finally:
        await transaction.rollback()
        await conn.close()


async def test_batch_matches_scoped_per_field_reads_with_two_queries_per_page(weather_rows):
    from api.freshness_store import PAGE_SIZE, read_freshness_page

    conn, tenant, prefix, role = weather_rows
    # Explicit tenant predicates also protect inputs when the connection can see every row.
    privileged = await read_freshness_page(conn, tenant, None)
    assert privileged[0][2] == datetime(2025, 1, 1, 1, tzinfo=UTC).timestamp()
    assert privileged[1][1:] == (None, None, None)

    # Same transaction keeps both tenants' data private to this test, including on failure.
    await conn.execute(f"SET LOCAL ROLE {role}")
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
    await conn.execute("SET LOCAL TIME ZONE 'Asia/Riyadh'")
    old_queries, page_queries, empty_queries = [], [], []
    with conn.query_logger(old_queries.append):
        baseline = await _per_field_rows(conn, tenant)
    rows, sizes = [], []
    with conn.query_logger(page_queries.append):
        while True:
            page = await read_freshness_page(conn, tenant, rows[-1][0] if rows else None)
            rows.extend(page)
            sizes.append(len(page))
            if len(page) < PAGE_SIZE:
                break
    with conn.query_logger(empty_queries.append):
        assert await read_freshness_page(conn, tenant, rows[-1][0]) == []
    await asyncio.sleep(0)  # asyncpg schedules synchronous query loggers with call_soon.

    assert sizes == [100, 100, 5]
    assert len(old_queries) == 616  # One field list + three reads per field.
    assert len(page_queries) == 6
    assert len(empty_queries) == 1
    assert rows == baseline
    assert [row[0] for row in rows] == [prefix + f"{i:03}" for i in range(1, 206)]
    assert rows[0][1:] == (
        datetime(2024, 12, 31, 21, tzinfo=UTC).timestamp(),  # midnight in session time zone
        datetime(2025, 1, 1, 1, tzinfo=UTC).timestamp(),
        datetime(2025, 1, 1, 22, tzinfo=UTC).timestamp(),
    )
    assert all(row[1:] == (None, None, None) for row in rows[1:])


async def test_projection_uses_only_dated_weather_for_age_and_et0(weather_rows, monkeypatch):
    from api import field_state_projection

    conn, tenant, prefix, role = weather_rows
    payloads = []

    async def capture_et0(payload, *args, **kwargs):
        payloads.append(json.loads(payload)["location"])
        return None

    monkeypatch.setattr(field_state_projection, "_et0_from_weather_payload", capture_et0)
    await conn.execute(f"SET LOCAL ROLE {role}")
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
    now = await conn.fetchval("SELECT now()")
    latest = datetime(2025, 1, 1, 22, tzinfo=UTC)
    ages = []
    for field in ("001", "002", "foreign"):
        result = await field_state_projection.recompute_field_state(conn, prefix + field)
        ages.append(result["state"]["inputs"]["weather_age_hours"])
    assert (ages, payloads) == (
        [pytest.approx((now - latest).total_seconds() / 3600), None, None],
        ["new"],
    )


async def test_cache_restart_restores_dated_locations_and_keeps_undated_tracked(
    weather_rows, caplog
):
    from api.weather_automation import WeatherAutomation

    conn, tenant, _, role = weather_rows
    await conn.execute(f"SET LOCAL ROLE {role}")
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    weather = WeatherAutomation()
    weather.set_pool(pool)
    with caplog.at_level(logging.WARNING, logger="sahool.weather_automation"):
        await weather.load_from_db()

    assert caplog.messages == []
    assert weather.registered_count() == 4
    assert weather.get_cached(1, 1).data == {"location": "old"}
    assert weather.get_cached(3, 1).data == {"location": "new"}
    assert weather.get_cached(3, 1).fetched_at == datetime(2025, 1, 1, 22, tzinfo=UTC).timestamp()
    assert weather.get_cached(2, 1) is None
    assert weather.get_cached(4, 1) is None
    assert weather.get_cached(5, 1) is None


async def test_scheduler_records_partial_run_and_resumes_with_next_tenant(
    database_urls, monkeypatch, caplog
):
    import asyncpg
    from api import freshness_store, main, scheduler
    from core import automation_ledger

    _, app_url = database_urls
    tenants = [str(uuid4()), str(uuid4())]
    calls = []
    tasks = {}
    ledger = automation_ledger.RunLedger()

    async def list_tenants(_pool, *, sweep):
        return tenants

    async def read_page(conn, tenant, after):
        actual_tenant = await conn.fetchval("SELECT current_setting('app.current_tenant')")
        assert actual_tenant == tenant
        calls.append((tenant, after))
        if tenant == tenants[0]:
            # Abort the first transaction on the server; the pool must recover for tenant two.
            await conn.fetchval("SELECT 1 / 0")
        if after is None:
            return [(f"f{i:03}", None, None, None) for i in range(freshness_store.PAGE_SIZE)]
        return [("f100", 1.0, None, 1.0)]

    monkeypatch.setattr(automation_ledger, "LEDGER", ledger)
    monkeypatch.setattr(scheduler, "list_sweep_tenant_ids", list_tenants)
    monkeypatch.setattr(
        scheduler, "register_default_tasks", lambda **registered: tasks.update(registered)
    )
    monkeypatch.setattr(scheduler, "cluster_singleton", lambda callback, **_kwargs: callback)
    monkeypatch.setattr(scheduler.scheduler, "start", lambda: None)
    monkeypatch.setattr(freshness_store, "read_freshness_page", read_page)
    monkeypatch.setattr(main, "_DB_POOL", None)
    await main._start_scheduler()
    async with asyncpg.create_pool(app_url, min_size=1, max_size=1) as pool:
        monkeypatch.setattr(main, "_DB_POOL", pool)
        with caplog.at_level(logging.WARNING):
            await tasks["check_decision_freshness"]()

    assert calls == [(tenants[0], None), (tenants[1], None), (tenants[1], "f099")]
    record = ledger.recent()[0]
    assert record["status"] == "partial"
    assert record["fields_total"] == record["evaluated"] == 101
    assert record["errored"] == 0
    assert record["errors"] == [{"tenant_id": tenants[0], "error": "division by zero"}]
    assert any("f100" in line and "stale_ndvi, stale_weather" in line for line in caplog.messages)
