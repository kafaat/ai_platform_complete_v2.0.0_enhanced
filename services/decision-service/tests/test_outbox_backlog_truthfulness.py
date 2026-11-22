"""F-D01: ``decision_outbox_events`` is written and never relayed — say so, and measure it.

The decision-service inserts a ``pending`` row into ``decision_outbox_events`` for every
authoritative write (``persistence.emit_outbox_event``). Nothing in the tree reads that table
back, sets ``published_at`` or moves a row out of ``pending``: there is no relay. The repo's
own ownership survey lists the table under ``written_never_read``.

This file pins the truthful state instead of a relay (a relay is an owner decision):

* ``/readyz`` reports the backlog as ``relay_implemented: false`` / ``delivery: not_delivered``
  with the pending count and the age of the oldest pending row — aggregates only, no payloads,
  no tenant ids — and never as part of the readiness verdict;
* under FORCE ROW LEVEL SECURITY (migrations 033/034) a role without BYPASSRLS sees no row
  unless a tenant is bound, so an unbound count would read ``0`` and look healthy. The probe
  reports ``measured: false`` with the reason instead of that false zero;
* the cutover gate ``DECISION_SERVICE_OUTBOX_VERIFIED`` states what it proves: a pending row
  was recorded, not that it was delivered;
* the staging runbook no longer describes a relay that does not exist.

HTTP boundary through ``TestClient`` with persistence mocked, no Postgres.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import cutover  # noqa: E402
import persistence  # noqa: E402

pytestmark = pytest.mark.unit

ROOT = SERVICE_DIR.parents[1]
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_STAGING_CUTOVER_RUNBOOK.md"
GATE_MEANING = "pending row recorded, not delivered"
TENANT = "00000000-0000-0000-0000-00000000fd01"


class _Tx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    """Records SQL; answers the role probe and the backlog aggregate."""

    def __init__(self, *, sees_all: bool, pending: int = 0, oldest: float | None = None):
        self.sees_all = sees_all
        self.pending = pending
        self.oldest = oldest
        self.sql: list[str] = []
        self.readonly: list[bool] = []
        self.closed = False

    def transaction(self, *, readonly: bool = False):
        self.readonly.append(readonly)
        return _Tx(self)

    async def execute(self, sql, *args):
        self.sql.append(sql)

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        return self.sees_all

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        return {"pending": self.pending, "oldest_age_seconds": self.oldest}

    async def close(self):
        self.closed = True


@pytest.fixture()
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("DECISION_REQUIRE_AUTH_TOKEN", raising=False)
    return main, TestClient(main.app, raise_server_exceptions=False)


def _ready_db():
    return {
        "database_configured": True,
        "db_reachable": True,
        "migrations_current": True,
        "pending_migrations": [],
    }


def _sor_ready(main, monkeypatch, db=None):
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    monkeypatch.setattr(main, "sor_requested_without_db", lambda: False)
    monkeypatch.setattr(main, "_db_readiness", AsyncMock(return_value=db or _ready_db()))


# ── /readyz ────────────────────────────────────────────────────────────────────────────────


def test_readyz_reports_the_outbox_as_pending_and_undelivered(client, monkeypatch):
    main, test_client = client
    _sor_ready(main, monkeypatch)
    backlog = AsyncMock(
        return_value=persistence.outbox_state(
            measured=True, pending_count=7, oldest_pending_age_seconds=3600
        )
    )
    monkeypatch.setattr(main, "outbox_backlog", backlog)
    outbox = test_client.get("/readyz").json()["outbox"]
    assert outbox["table"] == "decision_outbox_events"
    assert outbox["relay_implemented"] is False
    assert outbox["delivery"] == "not_delivered"
    assert outbox["pending_count"] == 7
    assert outbox["oldest_pending_age_seconds"] == 3600
    assert outbox["measured"] is True
    backlog.assert_awaited_once()


def test_readyz_never_reports_a_published_or_delivered_row(client, monkeypatch):
    main, test_client = client
    _sor_ready(main, monkeypatch)
    monkeypatch.setattr(
        main,
        "outbox_backlog",
        AsyncMock(return_value=persistence.outbox_state(measured=True, pending_count=1)),
    )
    outbox = test_client.get("/readyz").json()["outbox"]
    keys = " ".join(outbox).lower()
    assert "published" not in keys and "relayed" not in keys and "delivered_count" not in keys
    assert outbox["delivery"] != "delivered"


def test_backlog_is_reported_never_part_of_the_readiness_verdict(client, monkeypatch):
    main, test_client = client
    _sor_ready(main, monkeypatch)
    verdicts = []
    for state in (
        persistence.outbox_state(measured=True, pending_count=0),
        persistence.outbox_state(measured=True, pending_count=10**6, oldest_pending_age_seconds=9),
        persistence.outbox_state(reason="query_failed"),
    ):
        monkeypatch.setattr(main, "outbox_backlog", AsyncMock(return_value=state))
        response = test_client.get("/readyz")
        verdicts.append((response.status_code, response.json()["ready"]))
    assert verdicts == [(200, True)] * 3


def test_readyz_does_not_query_the_outbox_in_mirror_mode(client, monkeypatch):
    main, test_client = client
    monkeypatch.setattr(main, "sor_enabled", lambda: False)
    monkeypatch.setattr(main, "sor_requested_without_db", lambda: False)
    backlog = AsyncMock()
    monkeypatch.setattr(main, "outbox_backlog", backlog)
    outbox = test_client.get("/readyz").json()["outbox"]
    backlog.assert_not_awaited()
    assert outbox["measured"] is False
    assert outbox["pending_count"] is None
    assert outbox["reason"] == "not_system_of_record"
    assert outbox["relay_implemented"] is False


def test_readyz_does_not_query_the_outbox_before_migrations_are_current(client, monkeypatch):
    main, test_client = client
    _sor_ready(main, monkeypatch, db={**_ready_db(), "migrations_current": False})
    backlog = AsyncMock()
    monkeypatch.setattr(main, "outbox_backlog", backlog)
    outbox = test_client.get("/readyz").json()["outbox"]
    backlog.assert_not_awaited()
    assert outbox["measured"] is False
    assert outbox["reason"] == "database_not_ready"


# ── persistence.outbox_backlog ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backlog_aggregate_for_a_role_that_sees_every_tenant(monkeypatch):
    conn = _FakeConn(sees_all=True, pending=4, oldest=125.9)
    monkeypatch.setattr(persistence, "_connect", AsyncMock(return_value=conn))
    state = await persistence.outbox_backlog()
    assert state["measured"] is True
    assert state["pending_count"] == 4
    assert state["oldest_pending_age_seconds"] == 125
    assert state["reason"] is None
    assert conn.readonly == [True], "the probe must run in a read-only transaction"
    assert conn.closed
    aggregate = [s for s in conn.sql if "decision_outbox_events" in s]
    assert len(aggregate) == 1
    assert "payload" not in aggregate[0] and "tenant_id" not in aggregate[0]
    assert "count(*)" in aggregate[0] and "min(created_at)" in aggregate[0]
    assert any("statement_timeout" in s for s in conn.sql), "a probe must be time-bounded"


@pytest.mark.asyncio
async def test_backlog_with_no_pending_row_reports_zero_and_no_age(monkeypatch):
    conn = _FakeConn(sees_all=True, pending=0, oldest=None)
    monkeypatch.setattr(persistence, "_connect", AsyncMock(return_value=conn))
    state = await persistence.outbox_backlog()
    measured = (state["measured"], state["pending_count"], state["oldest_pending_age_seconds"])
    assert measured == (True, 0, None)


@pytest.mark.asyncio
async def test_rls_restricted_role_is_unmeasured_not_a_false_zero(monkeypatch):
    """FORCE RLS hides every row from an unbound NOBYPASSRLS role: count(*) would say 0."""
    conn = _FakeConn(sees_all=False, pending=0)
    monkeypatch.setattr(persistence, "_connect", AsyncMock(return_value=conn))
    state = await persistence.outbox_backlog()
    assert state["measured"] is False
    assert state["pending_count"] is None and state["oldest_pending_age_seconds"] is None
    assert state["reason"] == "row_level_security_hides_other_tenants"
    assert not [s for s in conn.sql if "decision_outbox_events" in s], (
        "the aggregate must not run when its answer would be a false zero"
    )
    assert conn.closed


@pytest.mark.asyncio
async def test_backlog_failure_is_unmeasured_and_carries_no_error_text(monkeypatch):
    class _Broken(_FakeConn):
        async def fetchrow(self, sql, *args):
            raise RuntimeError("password=secret host=db.internal")

    conn = _Broken(sees_all=True)
    monkeypatch.setattr(persistence, "_connect", AsyncMock(return_value=conn))
    state = await persistence.outbox_backlog()
    assert state["measured"] is False and state["reason"] == "query_failed"
    text = json.dumps(state)
    assert "secret" not in text and "db.internal" not in text
    assert conn.closed


@pytest.mark.asyncio
async def test_backlog_connect_failure_is_unmeasured(monkeypatch):
    monkeypatch.setattr(persistence, "_connect", AsyncMock(side_effect=OSError("refused")))
    state = await persistence.outbox_backlog()
    assert state["measured"] is False and state["reason"] == "database_unavailable"
    assert state["relay_implemented"] is False


def test_outbox_state_refuses_an_unknown_reason():
    with pytest.raises(ValueError):
        persistence.outbox_state(reason="all good, trust me")


def test_outbox_state_refuses_a_measured_state_without_a_count():
    with pytest.raises(ValueError):
        persistence.outbox_state(measured=True)


def test_outbox_state_carries_identifiers_and_integers_only():
    state = persistence.outbox_state(measured=True, pending_count=3, oldest_pending_age_seconds=5)
    for key, value in state.items():
        assert value is None or isinstance(value, bool | int | str), (key, value)
    assert TENANT not in json.dumps(state)


# ── no relay exists: pin it so a future relay has to update this file on purpose ─────────────


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_service_code_marks_an_outbox_row_published():
    offenders = []
    for path in sorted(SERVICE_DIR.glob("*.py")):
        for literal in _string_literals(path):
            flat = " ".join(literal.split())
            if re.search(r"UPDATE\s+decision_outbox_events", flat, re.IGNORECASE):
                offenders.append(f"{path.name}: {flat[:120]}")
            if re.search(r"published_at\s*=", flat, re.IGNORECASE):
                offenders.append(f"{path.name}: {flat[:120]}")
    assert offenders == [], (
        "a relay now exists: update F-D01 (readiness `relay_implemented`, the cutover gate "
        f"meaning and the staging runbook) in the same change: {offenders}"
    )


# ── the cutover gate says what it proves ──────────────────────────────────────────────────────


def test_cutover_readiness_says_the_outbox_gate_proves_a_pending_row_only(monkeypatch):
    monkeypatch.setenv("DECISION_SERVICE_OUTBOX_VERIFIED", "true")
    data = cutover.readiness_from_env().as_dict()
    assert data["outbox_verified"] is True
    assert data["outbox_gate_proves"] == GATE_MEANING
    assert data["outbox_relay_implemented"] is False


def test_sor_capability_carries_the_same_gate_meaning():
    signal = cutover.sor_capability_signal(_ready_db(), sor_enabled=True, ready=True)
    assert signal["outbox_gate_proves"] == GATE_MEANING
    assert signal["outbox_relay_implemented"] is False


# ── the runbook describes no relay ─────────────────────────────────────────────────────────────


def test_staging_runbook_describes_no_relay():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "already relayed" not in text, "the runbook describes a relay that does not exist"
    section = text[text.index("**4c.") : text.index("**4d.")]
    assert "pending" in section and "not delivered" in section, section
    gate = text[text.index("**4d.") : text.index("### The capability signal on `/readyz`")]
    assert GATE_MEANING in gate, "4d must say what the outbox gate proves"
