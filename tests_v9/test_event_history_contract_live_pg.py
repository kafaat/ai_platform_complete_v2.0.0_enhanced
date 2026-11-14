"""Entity history, replay and producer dedup against a migrated Postgres (live PG).

Four event-contract defects were only visible against the real schema:

* C-13: the history query ordered ``occurred_at ASC, seq ASC`` with ``LIMIT 100``, so a
  stream longer than the limit returned its *oldest* events, and replay declared a full
  rebuild from a 10000-row read with no continuation.
* C-14: ``emit_event`` dedups on ``(tenant, type, entity, hash(payload), day)``; TASK_UPDATED
  carried only ``{status, field_id}``, so two real note edits on one day became one event.
* C-17: ``events.schema_version`` (INT) was not selected; replay assumed ``"1.0"``.
* C-18: the outbox worker read ``correlation_id`` only when ``payload`` was a dict, but
  asyncpg returns ``jsonb`` as text unless a codec is registered.

The routers run against the real schema through a pool that runs as a NOBYPASSRLS role, so
tenant isolation applies as in production. The outbox worker is cross-tenant by design and
uses the owner connection, as its production role (BYPASSRLS) does.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("events", "event_outbox", "field_tasks", "processed_events"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
        if not await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns"
            " WHERE table_name = 'events' AND column_name = 'seq')"
        ):
            return "schema not migrated (events.seq missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main

    return main


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{uuid.uuid4().hex[:8]}", tenant_id=tenant, role=UserRole.OWNER, name_ar="مالك"
    )


class Live:
    """Owner connection for setup + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        self.tenant = str(uuid.uuid4())
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"ev_rls_{uuid.uuid4().hex[:10]}"
            await self.owner.execute(
                f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
                f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
                f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{self.role}";'
            )
        role = self.role

        async def setup(conn):
            if role:
                await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, setup=setup)
        return self

    async def seed_events(
        self, entity_id: str, n: int, *, tie_pairs: bool = False, schema_version: int = 1
    ) -> None:
        """``n`` events on one entity, one second apart (pairs share a timestamp if asked)."""
        step = "(g / 2)" if tie_pairs else "g"
        await self.owner.execute(
            f"""INSERT INTO events (event_type, schema_version, entity_type, entity_id,
                                    tenant_id, payload, source, occurred_at)
                SELECT 'operation.irrigation.completed', $4, 'field', $1, $2::uuid,
                       jsonb_build_object('i', g), 'system',
                       $3::timestamptz + {step} * interval '1 second'
                FROM generate_series(1, $5) AS g""",
            entity_id,
            self.tenant,
            datetime(2026, 1, 1, tzinfo=UTC),
            schema_version,
            n,
        )

    async def __aexit__(self, *exc):
        o = self.owner
        try:
            # events is append-only (v9 trigger) and so is outbox_delivery_attempts (v140): the
            # rows stay behind under this test's own random tenant, which nothing else reads.
            await o.execute("DELETE FROM field_tasks WHERE tenant_id = $1::uuid", self.tenant)
            await o.execute("DELETE FROM irrigation_valves WHERE tenant_id = $1::uuid", self.tenant)
            await o.execute("DELETE FROM field_boundaries WHERE tenant_id = $1::uuid", self.tenant)
            await o.execute("DELETE FROM fields WHERE tenant_id = $1::uuid", self.tenant)
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()


def _run(monkeypatch, case):
    main = _platform()

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, main)

    asyncio.run(body())


# ── C-13 / C-21: keyset pages and the latest N ──────────────────────────────────────────


def test_latest_n_returns_the_newest_events_of_a_101_event_stream(monkeypatch):
    async def case(live, _main):
        from api.routers import events as events_router

        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        await live.seed_events(eid, 101)
        user = _user(live.tenant)
        page = await events_router.entity_events(
            "field", eid, limit=10, cursor=None, order="desc", user=user
        )
        got = [e["payload"]["i"] for e in page["events"]]
        assert got == list(range(101, 91, -1)), "latest-N must return the newest 10, newest first"
        assert page["next_cursor"] is not None

        # The default first page is still the oldest 100 and now says there is more.
        first = await events_router.entity_events(
            "field", eid, limit=100, cursor=None, order="asc", user=user
        )
        assert [e["payload"]["i"] for e in first["events"]] == list(range(1, 101))
        assert first["next_cursor"] is not None, "a truncated page must carry a cursor"
        rest = await events_router.entity_events(
            "field", eid, limit=100, cursor=first["next_cursor"], order="asc", user=user
        )
        assert [e["payload"]["i"] for e in rest["events"]] == [101]
        assert rest["next_cursor"] is None
        assert {e["schema_version"] for e in first["events"]} == {1}

    _run(monkeypatch, case)


def test_keyset_pages_cover_every_event_once_across_timestamp_ties(monkeypatch):
    async def case(live, _main):
        from api.routers import events as events_router

        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        await live.seed_events(eid, 101, tie_pairs=True)
        user = _user(live.tenant)
        for order in ("asc", "desc"):
            seen, cursor = [], None
            while True:
                page = await events_router.entity_events(
                    "field", eid, limit=7, cursor=cursor, order=order, user=user
                )
                seen.extend(e["payload"]["i"] for e in page["events"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            expected = list(range(1, 102))
            assert seen == (expected if order == "asc" else expected[::-1]), order

    _run(monkeypatch, case)


def test_malformed_or_cross_direction_cursor_is_422(monkeypatch):
    from fastapi import HTTPException

    async def case(live, _main):
        from api.routers import events as events_router

        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        await live.seed_events(eid, 3)
        user = _user(live.tenant)
        page = await events_router.entity_events(
            "field", eid, limit=1, cursor=None, order="asc", user=user
        )
        for bad, order in (("not-a-cursor", "asc"), (page["next_cursor"], "desc")):
            with pytest.raises(HTTPException) as caught:
                await events_router.entity_events(
                    "field", eid, limit=1, cursor=bad, order=order, user=user
                )
            assert caught.value.status_code == 422

    _run(monkeypatch, case)


def test_history_of_another_tenant_is_invisible(monkeypatch):
    async def case(live, _main):
        from api.routers import events as events_router

        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        await live.seed_events(eid, 5)
        page = await events_router.entity_events(
            "field", eid, limit=10, cursor=None, order="desc", user=_user(str(uuid.uuid4()))
        )
        assert page["events"] == [] and page["next_cursor"] is None

    _run(monkeypatch, case)


# ── C-13 / C-17: replay reads all pages or declares itself incomplete ───────────────────


def test_replay_of_10001_events_is_complete_over_all_pages_or_flagged(monkeypatch):
    async def case(live, main):
        from api.event_bus import EventBus
        from api.event_replay import REPLAY_MAX_EVENTS, EventReplay

        assert REPLAY_MAX_EVENTS == 10000
        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        await live.seed_events(eid, 10001)
        async with main.tenant_connection(_user(live.tenant)) as conn:
            replay = EventReplay(EventBus(live.pool, conn=conn))

            capped = await replay.reconstruct_state("field", eid)
            assert capped.complete is False
            assert capped.incomplete_reason.startswith("max_events_exceeded")
            assert capped.state.total_events == 10000

            full = await replay.reconstruct_state("field", eid, max_events=10001)
            assert full.complete is True and full.incomplete_reason is None
            assert full.events_read == 10001
            assert full.state.total_events == 10001
            assert full.state.irrigation_count == 10001

            snap = await replay.reconstruct_with_snapshot("field", eid, max_events=20000)
            assert snap.complete is True and snap.state.total_events == 10001

    _run(monkeypatch, case)


def test_replay_quarantines_an_unknown_schema_version(monkeypatch):
    async def case(live, main):
        from api.event_bus import EventBus
        from api.event_replay import EventReplay

        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        await live.seed_events(eid, 2)
        await live.seed_events(eid, 1, schema_version=7)
        async with main.tenant_connection(_user(live.tenant)) as conn:
            result = await EventReplay(EventBus(live.pool, conn=conn)).reconstruct_state(
                "field", eid
            )
        assert result.complete is False
        assert "unknown_schema_version" in result.incomplete_reason
        assert len(result.quarantined_event_ids) == 1
        assert result.state.total_events == 2, "an unknown version must not be replayed as 1.0"

    _run(monkeypatch, case)


# ── C-14: distinct same-day task edits are distinct events; a retry is not ──────────────


def test_two_same_day_task_note_edits_are_two_events_and_a_retry_is_one(monkeypatch):
    async def case(live, main):
        from api.routers import tasks

        field_id = f"ev-fb-{uuid.uuid4().hex[:10]}"
        task_id = str(uuid.uuid4())
        # v261: field_tasks.field_id references fields (the record the API writes), so the
        # task's field is seeded there.
        await live.owner.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, 'Event field', $2::uuid)",
            field_id,
            live.tenant,
        )
        await live.owner.execute(
            "INSERT INTO field_tasks (task_id, field_id, tenant_id, task_type, status)"
            " VALUES ($1::uuid, $2, $3::uuid, 'scouting', 'pending')",
            task_id,
            field_id,
            live.tenant,
        )
        user = _user(live.tenant)

        async def edit(notes):
            req = main.TaskUpdateRequest(notes=notes)
            return await tasks.update_task(task_id, req, idem=None, user=user)

        async def task_events():
            return await live.owner.fetch(
                "SELECT payload FROM events WHERE entity_type = 'task' AND entity_id = $1"
                " ORDER BY seq",
                task_id,
            )

        await edit("first look: aphids on the east edge")
        await edit("second look: aphids spreading")
        rows = await task_events()
        assert len(rows) == 2, "two real edits on one day must be two TASK_UPDATED events"
        payloads = [json.loads(r["payload"]) for r in rows]
        assert all(p["changed_fields"] == ["notes"] for p in payloads)
        assert payloads[0]["updated_at"] != payloads[1]["updated_at"]

        await edit("second look: aphids spreading")  # same command again, same row state
        assert len(await task_events()) == 2, "an idempotent retry must still dedup"

    _run(monkeypatch, case)


def test_valve_open_close_open_on_one_day_is_three_state_change_events(monkeypatch):
    """The critical actuator event had the same flaw: ``{"status": "open"}`` twice in a day."""

    async def case(live, _main):
        from api.irrigation_models import ValveStateRequest
        from api.routers import irrigation

        valve_id = f"ev-valve-{uuid.uuid4().hex[:10]}"
        await live.owner.execute(
            "INSERT INTO irrigation_valves (valve_id, tenant_id, name) VALUES ($1, $2::uuid, 'v')",
            valve_id,
            live.tenant,
        )
        user = _user(live.tenant)
        for status in ("open", "closed", "open"):
            await irrigation.set_valve_state(
                valve_id, ValveStateRequest(status=status), idem=None, user=user
            )
        n = await live.owner.fetchval(
            "SELECT COUNT(*) FROM events WHERE entity_type = 'irrigation_valve' AND entity_id = $1",
            valve_id,
        )
        assert n == 3, "a second real open on the same day must not be deduplicated away"

    _run(monkeypatch, case)


# ── C-18: correlation/causation survive the text-jsonb path through the outbox ──────────


def test_outbox_envelope_keeps_correlation_id_from_text_jsonb(monkeypatch):
    async def case(live, main):
        from api.event_bus import EventBus, EventSource, EventType, OutboxWorker

        corr, caus = str(uuid.uuid4()), str(uuid.uuid4())
        eid = f"ev-field-{uuid.uuid4().hex[:10]}"
        async with main.tenant_connection(_user(live.tenant)) as conn:
            emitted = await EventBus(live.pool, conn=conn).emit(
                EventType.FIELD_UPDATED,
                "field",
                eid,
                live.tenant,
                {"name_ar": "حقل", "correlation_id": corr, "causation_id": caus},
                source=EventSource.SYSTEM,
            )
        assert emitted.event_id is not None
        assert isinstance(
            await live.owner.fetchval(
                "SELECT payload FROM events WHERE event_id = $1::uuid", emitted.event_id
            ),
            str,
        ), "precondition: asyncpg returns jsonb as text here"

        published: dict[str, dict] = {}

        async def publish(_subject, data, msg_id=None):
            env = json.loads(data)
            published[env["event_id"]] = env

        owner_pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
        try:
            worker = OutboxWorker(owner_pool, publish, batch_size=500)
            for _ in range(20):
                if emitted.event_id in published or not await worker._process_batch():
                    break
        finally:
            await owner_pool.close()
        env = published[emitted.event_id]
        assert env["correlation_id"] == corr
        assert env["causation_id"] == caus
        assert env["payload"]["name_ar"] == "حقل"

    _run(monkeypatch, case)
