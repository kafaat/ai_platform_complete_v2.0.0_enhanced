"""Pure contract of entity history paging, replay completeness and schema-version mapping.

The database behaviour (keyset over ``(occurred_at, seq)``, RLS, dedup, text jsonb) is
proved in ``test_event_history_contract_live_pg.py``. This file pins what needs no
database: the router's ``limit``/``cursor``/``order`` bounds (C-21), the opaque cursor,
the INT → upcaster version mapping (C-17), and how replay reads pages and reports itself
incomplete (C-13), using a history source that serves pre-built pages.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"


def _platform_path():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))


# ── C-21: the router bounds limit and cursor before touching a connection ───────────────


@pytest.fixture()
def client():
    _platform_path()
    import api.main as main
    from api.routers import events
    from core.canonical_schemas import UserRole, UserSchema
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(events.router)
    app.dependency_overrides[main.get_current_user] = lambda: UserSchema(
        user_id="u1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=UserRole.OWNER,
        name_ar="مالك",
    )
    return TestClient(app)


@pytest.mark.parametrize(
    "query",
    [
        "limit=-1",
        "limit=0",
        "limit=1001",
        "limit=abc",
        "order=sideways",
        "cursor=" + "x" * 513,
    ],
)
def test_out_of_bounds_query_is_422_before_any_database_access(client, query):
    resp = client.get(f"/api/v1/events/field/f-1?{query}")
    assert resp.status_code == 422, resp.text


def test_the_cap_is_shared_by_router_and_bus():
    _platform_path()
    from api.event_bus import HISTORY_PAGE_MAX, EventBus

    assert HISTORY_PAGE_MAX == 1000
    bus = EventBus(pool=None)
    for bad in (0, -5, HISTORY_PAGE_MAX + 1, True, 2.5):
        with pytest.raises(ValueError):
            asyncio.run(bus.query_entity_history_page("field", "f-1", limit=bad))
    with pytest.raises(ValueError):
        asyncio.run(bus.query_entity_history_page("field", "f-1", order="random"))


# ── the opaque cursor ───────────────────────────────────────────────────────────────────


def test_cursor_round_trips_microseconds_and_is_bound_to_its_direction():
    _platform_path()
    from api.event_bus import InvalidHistoryCursor, decode_history_cursor, encode_history_cursor

    ts = datetime(2026, 3, 1, 12, 30, 15, 123456, tzinfo=UTC)
    cur = encode_history_cursor(ts, 42, "desc")
    assert "=" not in cur and "42" not in cur  # opaque, URL-safe
    assert decode_history_cursor(cur, "desc") == (ts, 42)
    with pytest.raises(InvalidHistoryCursor):
        decode_history_cursor(cur, "asc")
    for bad in ("", "!!!", "eyJ2IjoyfQ", encode_history_cursor(ts, 1, "asc")[:-3]):
        with pytest.raises(InvalidHistoryCursor):
            decode_history_cursor(bad, "asc")


def test_naive_timestamp_in_a_cursor_is_rejected():
    _platform_path()
    import base64
    import json

    from api.event_bus import InvalidHistoryCursor, decode_history_cursor

    raw = json.dumps({"v": 1, "o": "asc", "t": "2026-01-01T00:00:00", "s": 1}).encode()
    with pytest.raises(InvalidHistoryCursor):
        decode_history_cursor(base64.urlsafe_b64encode(raw).decode(), "asc")


# ── C-17: INT schema_version → upcaster version, never a silent 1.0 ─────────────────────


def test_schema_version_mapping_is_explicit():
    _platform_path()
    from api.event_upcasting import (
        SCHEMA_VERSION_LABELS,
        UnknownSchemaVersion,
        schema_version_label,
    )

    assert SCHEMA_VERSION_LABELS == {1: "1.0"}
    assert schema_version_label(1) == "1.0"
    assert schema_version_label("1") == "1.0"
    for bad in (None, 0, 2, 7, True, 1.0, "1.0", "x", ""):
        with pytest.raises(UnknownSchemaVersion):
            schema_version_label(bad)


def test_prepare_replay_events_quarantines_unknown_and_missing_versions():
    _platform_path()
    from api.event_replay import prepare_replay_events

    events = [
        {"event_id": "a", "event_type": "field.created", "schema_version": 1, "payload": {}},
        {"event_id": "b", "event_type": "field.created", "schema_version": 2, "payload": {}},
        {"event_id": "c", "event_type": "field.created", "payload": {}},
    ]
    accepted, quarantined = prepare_replay_events(events)
    assert [e["event_id"] for e in accepted] == ["a"]
    assert accepted[0]["schema_version"] == "1.0"
    assert [q["event_id"] for q in quarantined] == ["b", "c"]
    assert all(q["quarantine_reason"] for q in quarantined)


# ── C-13: replay reads every page, or says it did not ──────────────────────────────────


class PagedHistory:
    """Serves ``n`` ordered events in pages, as ``EventBus.query_entity_history_page`` does."""

    def __init__(self, n: int, bad_versions: frozenset[int] = frozenset()):
        self.events = [
            {
                "event_id": f"e{i}",
                "event_type": "operation.irrigation.completed",
                "schema_version": 9 if i in bad_versions else 1,
                "payload": {},
                "source": "system",
                "actor_id": None,
                "command_id": None,
                "occurred_at": f"2026-01-01T00:00:{i:05d}",
                "seq": i,
            }
            for i in range(1, n + 1)
        ]
        self.calls: list[tuple[int, str | None]] = []

    async def query_entity_history_page(
        self, entity_type, entity_id, *, limit, cursor=None, order="asc"
    ):
        assert order == "asc"
        self.calls.append((limit, cursor))
        start = int(cursor) if cursor else 0
        page = self.events[start : start + limit]
        more = start + limit < len(self.events)
        return {"events": page, "next_cursor": str(start + limit) if more else None, "order": order}


def _replay(history):
    _platform_path()
    from api.event_replay import EventReplay

    return EventReplay(history)


def test_replay_reads_all_pages_and_is_complete_when_under_the_cap():
    history = PagedHistory(25)
    result = asyncio.run(_replay(history).reconstruct_state("field", "f", max_events=100))
    assert result.complete is True and result.incomplete_reason is None
    assert result.state.total_events == 25 and result.events_read == 25
    assert len(history.calls) == 1


def test_replay_pages_through_with_the_cursor():
    _platform_path()
    import api.event_replay as er

    history = PagedHistory(25)
    read = asyncio.run(
        _replay(history).read_full_history("field", "f", max_events=100, page_size=10)
    )
    assert read.complete is True and len(read.events) == 25
    assert history.calls == [(10, None), (10, "10"), (10, "20")]
    assert er.REPLAY_MAX_EVENTS == 10000


def test_replay_exactly_at_the_cap_is_complete():
    result = asyncio.run(_replay(PagedHistory(30)).reconstruct_state("field", "f", max_events=30))
    assert result.complete is True and result.state.total_events == 30


def test_replay_beyond_the_cap_declares_itself_incomplete():
    result = asyncio.run(_replay(PagedHistory(31)).reconstruct_state("field", "f", max_events=30))
    assert result.complete is False
    assert result.incomplete_reason.startswith("max_events_exceeded")
    assert result.state.total_events == 30


def test_replay_with_an_unknown_version_is_incomplete_and_skips_that_event():
    history = PagedHistory(5, bad_versions=frozenset({3}))
    result = asyncio.run(_replay(history).reconstruct_state("field", "f", max_events=100))
    assert result.complete is False and "unknown_schema_version" in result.incomplete_reason
    assert result.quarantined_event_ids == ["e3"]
    assert result.state.total_events == 4 and result.events_read == 5


def test_timeline_page_carries_the_next_cursor():
    page = asyncio.run(_replay(PagedHistory(5)).get_timeline("field", "f", limit=2))
    assert [e.event_id for e in page.entries] == ["e1", "e2"]
    assert page.next_cursor == "2" and page.quarantined_event_ids == []
