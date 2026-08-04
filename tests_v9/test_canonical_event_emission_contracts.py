"""What the canonical learning path writes must survive a real database.

Every defect pinned here was found by running the worker against PostgreSQL 16 with the
full 226-entry MANIFEST applied — never by a unit test, because the unit tests around
this path run against fake connections. A fake accepts any value: it enforces no CHECK
constraint, fires no trigger, and hands back Python objects where asyncpg hands back
strings. Three separate bugs lived behind that.

The tests below encode the properties the database actually enforces, so the next
regression is caught before someone stands up Postgres.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "sahool-platform"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# `source TEXT NOT NULL CHECK (source IN ('mobile', 'web', ...))`
_SOURCE_CHECK = re.compile(
    r"source\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*source\s+IN\s*\(([^)]*)\)", re.IGNORECASE
)


def _database_allowed_sources() -> set[str]:
    """The authority is the migration, not a list retyped into this test."""
    sql = (ROOT / "migrations/v11_events_bus.sql").read_text(encoding="utf-8")
    match = _SOURCE_CHECK.search(sql)
    assert match, "events.source CHECK constraint not found in v11_events_bus.sql"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_the_event_source_enum_matches_the_constraint_the_database_enforces():
    """A code enum that drifts from the CHECK is a green test and a rejected INSERT."""
    from api.event_bus import EventSource

    assert {member.value for member in EventSource} == _database_allowed_sources()


def test_the_projection_writer_emits_a_source_the_database_accepts():
    """The measured failure this pins.

    The projection SQL embedded ``'sahool-platform'`` — a service name, where the column
    takes a seven-value enum. Every canonical projection insert was rejected:

        asyncpg.exceptions.CheckViolationError: new row for relation "events"
        violates check constraint "events_source_check"

    Read off the imported module's SQL constant rather than grepped out of the file, so
    reformatting the query cannot turn a true property into a false alarm.
    """
    from api.event_bus import EventSource
    from api.persisted_canonical_repositories import _EMIT_PROJECTION_SQL

    literals = set(re.findall(r"'([^']*)'", _EMIT_PROJECTION_SQL))
    sources = literals & {member.value for member in EventSource}
    assert sources, (
        f"the projection emit SQL names no valid event source; literals present: {sorted(literals)}"
    )
    invalid = {lit for lit in literals if lit.startswith("sahool-")}
    assert not invalid, f"service names are not event sources: {sorted(invalid)}"


class _JsonbRow(dict):
    """A row that returns jsonb the way asyncpg really does: as ``str``.

    The fakes this path was tested against returned ``dict``/``list``, so
    ``dict(row["canonical_payload"])`` looked correct for as long as nobody ran it.
    Against a real connection it raised, and the worker's callback classifies that
    ValueError as permanent invalid input — so it called ``msg.term()`` and discarded a
    valid event, blaming the producer for a decoding bug of our own.
    """


def _worker():
    path = ROOT / "scripts/workers/canonical_execution_learning_worker.py"
    spec = importlib.util.spec_from_file_location("_canonical_learning_worker_jsonb", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeConn:
    def __init__(self, row):
        self._row = row
        self.executed: list[str] = []

    async def fetchrow(self, *_args, **_kwargs):
        return self._row

    async def execute(self, sql, *_args, **_kwargs):
        self.executed.append(sql)


def test_the_worker_decodes_jsonb_columns_that_arrive_as_strings():
    """asyncpg returns jsonb as ``str`` unless a codec is registered; this pool has none."""
    worker = _worker()
    row = _JsonbRow(
        {
            "status": "pending",
            "result_event_id": None,
            "projection_type": "unsupported-on-purpose",
            # exactly what asyncpg hands back
            "canonical_payload": '{"season_id": "s-1", "limitations": []}',
            "evidence_payload": "[]",
        }
    )
    conn = _FakeConn(row)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(worker._process_projection_request(conn, request_id="r-1"))

    # It must fail on the *unsupported projection type* — meaning decoding already
    # succeeded. Before the fix it died earlier, inside dict(), with
    # "dictionary update sequence element #0 has length 1; 2 is required".
    assert "UNSUPPORTED_PROJECTION_TYPE" in str(excinfo.value), (
        f"decoding failed before reaching the type switch: {excinfo.value}"
    )


def test_decoding_an_empty_jsonb_array_does_not_yield_two_bracket_characters():
    """``list("[]")`` is ``['[', ']']`` — a silent pair of bogus observations, not a raise."""
    from api.persisted_canonical_repositories import decode_jsonb

    assert list(decode_jsonb("[]", [])) == []
    assert list(decode_jsonb(None, [])) == []
    assert dict(decode_jsonb('{"a": 1}', {})) == {"a": 1}


def _append_only_tables() -> set[str]:
    """Tables whose migrations install a trigger refusing UPDATE/DELETE.

    Two construction shapes, and reading only the first is how this helper originally
    reported a clean sweep of 24 tables while missing ``events`` — the one that matters
    most here:

    * a literal ``CREATE TRIGGER trg_append_only_x BEFORE UPDATE OR DELETE ON x``
    * ``v9_append_only_enforcement.sql``, which builds the same triggers inside a
      ``DO`` block from ``tables TEXT[] := ARRAY[...]`` via ``EXECUTE format()``. No
      amount of CREATE TRIGGER matching sees those names; the array is the declaration.
    """
    found: set[str] = set()
    for path in (ROOT / "migrations").glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"CREATE\s+TRIGGER\s+\S*append_only\S*\s+BEFORE\s+([^\n]*?)\s+ON\s+(?:public\.)?(\w+)",
            text,
            re.IGNORECASE,
        ):
            if "delete" in match.group(1).lower():
                found.add(match.group(2))
        if "trg_append_only_%I" in text:
            array = re.search(r"tables\s+TEXT\[\]\s*:=\s*ARRAY\[(.*?)\]", text, re.DOTALL)
            if array:
                found.update(re.findall(r"'([^']+)'", array.group(1)))
    return found


def test_the_live_round_trip_never_deletes_from_an_append_only_table():
    """Its teardown deleted from two of them, so the gate could never exit zero.

    The round trip itself passed and then died cleaning up after itself — first on
    ``events`` (``trg_append_only_events``), then on ``canonical_salinity_states``
    (``canonical_salinity_states_append_only``). The repair is to leave the rows and
    disclose them, never to relax a trigger so a test can tidy up.
    """
    text = (ROOT / "scripts/e2e/canonical_projection_jetstream_roundtrip.py").read_text(
        encoding="utf-8"
    )
    append_only = _append_only_tables()
    assert {"events", "canonical_salinity_states"} <= append_only, (
        f"append-only discovery missed a known table; found {sorted(append_only)}"
    )

    deleted = {match.lower() for match in re.findall(r"DELETE\s+FROM\s+(\w+)", text, re.IGNORECASE)}
    offenders = sorted(deleted & {table.lower() for table in append_only})
    assert not offenders, f"teardown deletes from append-only tables: {offenders}"
    assert "residue" in text, "rows that cannot be removed must be disclosed, not left silent"


def test_the_live_gate_refuses_to_stamp_a_sha_for_a_dirty_tree():
    """A SHA names a tree. Evidence produced from uncommitted edits names the wrong one.

    Measured: this gate first went green with three production fixes still unstaged and
    stamped a SHA whose checkout could not have passed it.
    """
    text = (ROOT / "scripts/e2e/run_canonical_execution_learning_live_gate.sh").read_text(
        encoding="utf-8"
    )
    assert "git status --porcelain" in text
    assert "working tree is dirty" in text
