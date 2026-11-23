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

No stand-in connection here (``FAKE-CONNECTION-ENFORCES-NOTHING-01``): a fake would answer the
role probe with whatever the test chose, which is exactly the claim under test. So this file
holds the pure state builder, the HTTP boundary with ``outbox_backlog`` itself replaced (it
never reaches a connection), and the shape of ``outbox_backlog`` read from its source. What the
probe answers on a real FORCE-RLS table, per role, is proven on PostgreSQL in
``test_outbox_backlog_live_pg.py``.
"""

from __future__ import annotations

import ast
import asyncio
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
RLS_REASON = "row_level_security_hides_other_tenants"
TENANT = "00000000-0000-0000-0000-00000000fd01"


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


def _function(path: Path, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path.name} no longer defines {name}")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _literal(node: ast.AST) -> str:
    """The string a call's first argument spells, with adjacent literals joined."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    return ""


def _awaited_calls(fn: ast.AST, method: str) -> list[tuple[ast.Call, str]]:
    """Every ``await <x>.<method>(sql, ...)`` in ``fn`` with its SQL text."""
    found = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == method
        ):
            args = node.value.args
            found.append((node.value, _flat(_literal(args[0])) if args else ""))
    return found


def _state_call_reason(node: ast.AST) -> str | None:
    """``outbox_state(reason="...")`` → the reason literal, else ``None``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "outbox_state"
    ):
        for kw in node.keywords:
            if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                return kw.value.value
    return None


PERSISTENCE = SERVICE_DIR / "persistence.py"
MAIN = SERVICE_DIR / "main.py"


# ── outbox_state: the block /readyz carries (pure) ────────────────────────────────────────────


def test_measured_state_reports_the_count_and_the_whole_seconds_of_the_oldest_row():
    state = persistence.outbox_state(
        measured=True, pending_count=4, oldest_pending_age_seconds=125.9
    )
    assert state == {
        "table": "decision_outbox_events",
        "relay_implemented": False,
        "delivery": "not_delivered",
        "measured": True,
        "pending_count": 4,
        "oldest_pending_age_seconds": 125,
        "reason": None,
    }


def test_measured_state_with_no_pending_row_reports_zero_and_no_age():
    state = persistence.outbox_state(measured=True, pending_count=0)
    measured = (state["measured"], state["pending_count"], state["oldest_pending_age_seconds"])
    assert measured == (True, 0, None)


@pytest.mark.parametrize("reason", sorted(persistence.OUTBOX_UNMEASURED_REASONS))
def test_every_unmeasured_state_reports_none_never_a_zero(reason):
    state = persistence.outbox_state(reason=reason)
    assert state["measured"] is False
    assert state["pending_count"] is None and state["oldest_pending_age_seconds"] is None
    assert state["reason"] == reason
    assert state["relay_implemented"] is False and state["delivery"] == "not_delivered"


def test_unmeasured_state_drops_counts_it_was_handed():
    """A caller cannot smuggle a count into an unmeasured state and have it read as a fact."""
    state = persistence.outbox_state(
        reason=RLS_REASON, pending_count=0, oldest_pending_age_seconds=0
    )
    assert state["pending_count"] is None and state["oldest_pending_age_seconds"] is None


def test_the_rls_reason_is_a_known_unmeasured_reason():
    assert RLS_REASON in persistence.OUTBOX_UNMEASURED_REASONS
    assert "query_failed" in persistence.OUTBOX_UNMEASURED_REASONS
    assert "database_unavailable" in persistence.OUTBOX_UNMEASURED_REASONS


def test_outbox_state_refuses_an_unknown_reason():
    with pytest.raises(ValueError):
        persistence.outbox_state(reason="all good, trust me")


def test_outbox_state_refuses_an_unmeasured_state_without_a_reason():
    with pytest.raises(ValueError):
        persistence.outbox_state()


def test_outbox_state_refuses_a_measured_state_without_a_count():
    with pytest.raises(ValueError):
        persistence.outbox_state(measured=True)


def test_outbox_state_refuses_a_measured_state_with_a_reason():
    with pytest.raises(ValueError):
        persistence.outbox_state(measured=True, pending_count=1, reason=RLS_REASON)


def test_outbox_state_carries_identifiers_and_integers_only():
    state = persistence.outbox_state(measured=True, pending_count=3, oldest_pending_age_seconds=5)
    for key, value in state.items():
        assert value is None or isinstance(value, bool | int | str), (key, value)
    assert TENANT not in json.dumps(state)


def test_the_relay_flag_is_false_in_both_modules():
    assert persistence.OUTBOX_RELAY_IMPLEMENTED is False
    assert cutover.OUTBOX_RELAY_IMPLEMENTED is False


# ── /readyz: the HTTP boundary, with outbox_backlog itself replaced (no connection) ───────────


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
        persistence.outbox_state(reason=RLS_REASON),
        persistence.outbox_state(reason="query_failed"),
    ):
        monkeypatch.setattr(main, "outbox_backlog", AsyncMock(return_value=state))
        response = test_client.get("/readyz")
        verdicts.append((response.status_code, response.json()["ready"]))
    assert verdicts == [(200, True)] * 4


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


# ── /readyz wiring, read from main.py ─────────────────────────────────────────────────────────


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def test_readyz_verdict_and_status_code_never_read_the_outbox():
    fn = _function(MAIN, "readyz")
    outbox_names = {"outbox", "outbox_backlog", "outbox_state"}
    verdict = [
        stmt
        for stmt in fn.body
        if isinstance(stmt, ast.Assign)
        and any(
            (isinstance(t, ast.Name) and t.id == "ready")
            or (isinstance(t, ast.Attribute) and t.attr == "status_code")
            for t in stmt.targets
        )
    ]
    assert len(verdict) == 2, "readyz must compute `ready` and set the status code once each"
    for stmt in verdict:
        assert not (_names(stmt.value) & outbox_names), ast.unparse(stmt)
    first_outbox = min(
        stmt.lineno for stmt in fn.body if _names(stmt) & {"outbox_backlog", "outbox_state"}
    )
    assert all(stmt.lineno < first_outbox for stmt in verdict), (
        "the outbox block must be computed after the verdict, never feed it"
    )


def test_readyz_reports_the_outbox_under_its_own_key_only():
    fn = _function(MAIN, "readyz")
    loads = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Name) and n.id == "outbox" and isinstance(n.ctx, ast.Load)
    ]
    assert len(loads) == 1, "`outbox` is read once: as the value of the response's outbox key"
    ret = next(s for s in fn.body if isinstance(s, ast.Return))
    assert isinstance(ret.value, ast.Dict)
    pairs = {
        k.value: v for k, v in zip(ret.value.keys, ret.value.values, strict=True) if k is not None
    }
    assert isinstance(pairs["outbox"], ast.Name) and pairs["outbox"].id == "outbox"
    assert isinstance(pairs["ready"], ast.Name) and pairs["ready"].id == "ready"


def test_readyz_queries_the_backlog_only_in_sor_mode_with_a_current_database():
    fn = _function(MAIN, "readyz")
    branch = next(
        s
        for s in fn.body
        if isinstance(s, ast.If) and _names(s) & {"outbox_backlog", "outbox_state"}
    )
    assert ast.unparse(branch.test) == "not sor_on"
    assert _state_call_reason(branch.body[0].value) == "not_system_of_record"
    (inner,) = branch.orelse
    assert isinstance(inner, ast.If)
    assert {"db_reachable", "migrations_current"} <= {
        n.value for n in ast.walk(inner.test) if isinstance(n, ast.Constant)
    }
    assert _state_call_reason(inner.body[0].value) == "database_not_ready"
    (query,) = inner.orelse
    assert ast.unparse(query) == "outbox = await outbox_backlog()"
    backlog_calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "outbox_backlog"
    ]
    assert len(backlog_calls) == 1


# ── outbox_backlog, read from persistence.py ──────────────────────────────────────────────────


def _role_probe(fn):
    probes = [(call, sql) for call, sql in _awaited_calls(fn, "fetchval") if "pg_roles" in sql]
    assert len(probes) == 1, "outbox_backlog must ask pg_roles once whether it sees every tenant"
    return probes[0]


def _aggregate(fn):
    aggregates = [
        (call, sql)
        for method in ("fetch", "fetchrow", "fetchval", "execute")
        for call, sql in _awaited_calls(fn, method)
        if "decision_outbox_events" in sql
    ]
    assert len(aggregates) == 1, "outbox_backlog must read decision_outbox_events exactly once"
    return aggregates[0]


def _readonly_transaction(fn) -> ast.AsyncWith:
    blocks = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "transaction"
            for item in node.items
        )
    ]
    assert len(blocks) == 1, "the probe must run inside one transaction"
    (item,) = blocks[0].items
    kwargs = {kw.arg: kw.value for kw in item.context_expr.keywords}
    assert isinstance(kwargs.get("readonly"), ast.Constant) and kwargs["readonly"].value is True, (
        "the probe must run in a read-only transaction"
    )
    return blocks[0]


def test_role_probe_asks_for_superuser_or_bypassrls_of_the_current_user():
    """Either attribute sees every tenant under FORCE RLS, and ``pg_roles`` does not set
    ``rolbypassrls`` for a superuser created without it: a check on one attribute alone
    misreports a role that holds only the other."""
    _, sql = _role_probe(_function(PERSISTENCE, "outbox_backlog"))
    assert re.search(r"\brolsuper\s+OR\s+rolbypassrls\b", sql, re.I), sql
    assert re.search(r"\bFROM\s+pg_roles\b", sql, re.I), sql
    assert re.search(r"\brolname\s*=\s*current_user\b", sql, re.I), sql


def test_a_role_that_cannot_see_every_tenant_returns_before_the_aggregate():
    """FORCE RLS hides every row from an unbound NOBYPASSRLS role: count(*) would say 0.

    The return on the RLS reason must be a statement of the transaction block, gated on the
    probe's answer and placed before the aggregate, so no path reaches the count with a role
    that sees a subset."""
    fn = _function(PERSISTENCE, "outbox_backlog")
    probe_call, _ = _role_probe(fn)
    aggregate_call, _ = _aggregate(fn)
    body = _readonly_transaction(fn).body

    def index_of(call: ast.Call) -> int:
        return next(i for i, stmt in enumerate(body) if call in set(ast.walk(stmt)))

    probe_at, aggregate_at = index_of(probe_call), index_of(aggregate_call)
    probe_stmt = body[probe_at]
    assert isinstance(probe_stmt, ast.Assign) and len(probe_stmt.targets) == 1
    answer = probe_stmt.targets[0]
    assert isinstance(answer, ast.Name)

    gates = [
        (i, stmt)
        for i, stmt in enumerate(body)
        if isinstance(stmt, ast.If)
        and isinstance(stmt.test, ast.UnaryOp)
        and isinstance(stmt.test.op, ast.Not)
        and isinstance(stmt.test.operand, ast.Name)
        and stmt.test.operand.id == answer.id
        and not stmt.orelse
        and len(stmt.body) == 1
        and isinstance(stmt.body[0], ast.Return)
        and _state_call_reason(stmt.body[0].value) == RLS_REASON
    ]
    assert len(gates) == 1, (
        f"outbox_backlog must return reason {RLS_REASON!r} when `{answer.id}` is false"
    )
    gate_at = gates[0][0]
    assert probe_at < gate_at < aggregate_at, (
        "order must be: role probe, RLS return, aggregate — the count never runs for a role "
        "that sees a subset of tenants"
    )


def test_aggregate_reads_counts_and_age_of_pending_rows_only():
    _, sql = _aggregate(_function(PERSISTENCE, "outbox_backlog"))
    assert re.search(r"\bcount\(\*\)", sql, re.I), sql
    assert re.search(r"\bmin\(created_at\)", sql, re.I), sql
    assert re.search(r"\bWHERE\s+status\s*=\s*'pending'", sql, re.I), sql
    for column in ("payload", "tenant_id", "event_id", "aggregate_id"):
        assert column not in sql, f"the probe must not read {column}: {sql}"


def test_probe_is_time_bounded_inside_its_transaction():
    fn = _function(PERSISTENCE, "outbox_backlog")
    body = _readonly_transaction(fn).body
    first = body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Await)
    sql = _flat(_literal(first.value.value.args[0]))
    assert re.fullmatch(r"SET LOCAL statement_timeout = '\d+s'", sql), sql


def test_probe_failures_are_unmeasured_and_carry_no_error_text():
    fn = _function(PERSISTENCE, "outbox_backlog")
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    reasons = set()
    for handler in handlers:
        assert handler.name is None, "an exception bound to a name can leak into the response"
        (ret,) = handler.body
        assert isinstance(ret, ast.Return)
        reasons.add(_state_call_reason(ret.value))
    assert reasons == {"database_unavailable", "query_failed"}


def test_probe_always_closes_its_connection():
    fn = _function(PERSISTENCE, "outbox_backlog")
    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try) and n.finalbody]
    assert len(tries) == 1
    assert [ast.unparse(s) for s in tries[0].finalbody] == ["await conn.close()"]


@pytest.mark.parametrize("dsn", ["postgresql://outbox_probe@127.0.0.1:1/outbox_probe"])
def test_unreachable_database_is_unmeasured_without_error_text(monkeypatch, dsn):
    """A real driver against a closed loopback port: no stand-in, no database needed."""
    monkeypatch.setenv("DATABASE_URL", dsn)

    async def _measure():
        try:
            return await persistence.outbox_backlog()
        finally:
            await persistence.close_pools()

    state = asyncio.run(_measure())
    assert state["measured"] is False and state["reason"] == "database_unavailable"
    assert state["pending_count"] is None and state["relay_implemented"] is False
    text = json.dumps(state)
    assert "127.0.0.1" not in text and "outbox_probe" not in text and "refused" not in text


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
            flat = _flat(literal)
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


def test_cutover_source_wires_the_gate_meaning_from_its_constant():
    fn = _function(SERVICE_DIR / "cutover.py", "readiness_from_env")
    kwargs = {
        kw.arg: ast.unparse(kw.value)
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CutoverReadiness"
        for kw in node.keywords
    }
    assert kwargs["outbox_gate_proves"] == "OUTBOX_GATE_PROVES"
    assert kwargs["outbox_relay_implemented"] == "OUTBOX_RELAY_IMPLEMENTED"
    assert cutover.OUTBOX_GATE_PROVES == GATE_MEANING
    assert "delivered" not in GATE_MEANING.replace("not delivered", "")


# ── the runbook describes no relay ─────────────────────────────────────────────────────────────


def test_staging_runbook_describes_no_relay():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "already relayed" not in text, "the runbook describes a relay that does not exist"
    section = text[text.index("**4c.") : text.index("**4d.")]
    assert "pending" in section and "not delivered" in section, section
    gate = text[text.index("**4d.") : text.index("### The capability signal on `/readyz`")]
    assert GATE_MEANING in gate, "4d must say what the outbox gate proves"
