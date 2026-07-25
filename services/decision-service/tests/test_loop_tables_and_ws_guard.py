"""Decision-service governance guards (open-ledger #2, slice 2): LOOP_TABLES drift + WebSocket auth.

Two static guards, no DB, no network:

1. LOOP_TABLES drift — every table named in ``main.LOOP_TABLES`` must be a REAL table created by a
   decision-service migration. This catches a renamed/dropped table left stale in the runtime list.

   Honest scope: LOOP_TABLES is a CURATED SUBSET of the decision tables (the closed-loop tables),
   so the reverse ("every decision table must be in LOOP_TABLES") is deliberately NOT enforced — it
   would drag non-loop tables (activation receipts, satellite_cdse, irr_f01 gate) into the list.

   Ownership cross-check (ledger #6, now WIRED): every LOOP_TABLES entry must be a table
   decision-service owns in docs/architecture/db_ownership.yml — either owner=decision-service, or
   (for the 5 interim-bridge SoR tables) mirror=decision-service until the SoR flip. The ownership
   baseline was populated (decision-service now owns the tables its migrations create) so this check
   holds without dragging non-loop tables into LOOP_TABLES.

2. WebSocket auth — a WebSocket route bypasses the HTTP ``_service_token_guard`` middleware entirely,
   so an unauthenticated WS endpoint would be a hole in the exact defense open-ledger #2 built. The
   service has NO WebSocket routes today; this guard fails the moment one is added, forcing a
   reviewer to confirm it authenticates before it can land.

3. Raw connection confinement (open-ledger #4) — production DB access should route through the
   pooled ``persistence.acquire_connection`` (asyncpg.create_pool). A raw ``asyncpg.connect(`` is
   confined to a fixed, reviewed allowlist of standalone/fallback modules; a NEW module opening a
   raw connection fails this guard, forcing a reviewer to use the pool (or justify the exception).
"""

from __future__ import annotations

import re
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
MAIN = (SERVICE_DIR / "main.py").read_text(encoding="utf-8")
MIGRATIONS = SERVICE_DIR / "migrations"
OWNERSHIP = SERVICE_DIR.parents[1] / "docs" / "architecture" / "db_ownership.yml"


def _decision_owned_or_mirrored() -> set[str]:
    """Tables decision-service owns, per db_ownership.yml — parsed without a YAML dependency.

    A loop table qualifies if decision-service is the ``owner`` OR its designated ``mirror``.
    The mirror clause covers the 5 interim-bridge SoR tables (decision_record, dispatch_decisions,
    outcome_record, recommendation_outcomes, online_learning_updates) which stay platform-owned
    with ``mirror: decision-service`` until the SoR flip (runbook ⑤) makes decision-service the
    owner outright. After that flip, those become owner=decision-service and the mirror clause is
    simply redundant — the check keeps passing without edits.
    """
    text = OWNERSHIP.read_text(encoding="utf-8")
    qualified: set[str] = set()
    cur: str | None = None
    for line in text.splitlines():
        m = re.match(r"^  ([a-z0-9_]+):\s*$", line)
        if m:
            cur = m.group(1)
            continue
        if cur and re.match(r"^    owner:\s*decision-service\s*$", line):
            qualified.add(cur)
        if cur and re.match(r"^    mirror:\s*decision-service\s*$", line):
            qualified.add(cur)
    return qualified


def _loop_tables() -> set[str]:
    block = re.search(r"LOOP_TABLES\s*=\s*\[(.*?)\]", MAIN, re.S)
    assert block, "LOOP_TABLES must be defined in main.py"
    return set(re.findall(r'"([a-z_]+)"', block.group(1)))


def _migration_tables() -> set[str]:
    tables: set[str] = set()
    for sql in MIGRATIONS.glob("*.sql"):
        tables |= set(
            re.findall(
                r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_]+)", sql.read_text(encoding="utf-8")
            )
        )
    return tables


def _service_modules():
    for path in SERVICE_DIR.rglob("*.py"):
        if path.name.startswith("test_") or "/tests/" in path.as_posix():
            continue
        yield path.name, path.read_text(encoding="utf-8")


_WS_MARKERS = ("@app.websocket", ".websocket(", "WebSocketRoute(")


# ---- LOOP_TABLES drift -----------------------------------------------------------------------
def test_loop_tables_have_no_phantom_entry():
    loop, migrated = _loop_tables(), _migration_tables()
    phantom = sorted(loop - migrated)
    assert not phantom, (
        f"LOOP_TABLES names tables no decision-service migration creates: {phantom}. "
        "A renamed/dropped table was left in the runtime list — fix LOOP_TABLES or add the migration."
    )


def test_loop_tables_gate_would_catch_a_phantom():
    # Negative proof: a synthetic loop list with a made-up table is caught by the set difference.
    migrated = _migration_tables()
    synthetic = {next(iter(migrated)), "decision_totally_made_up_table"}
    assert sorted(synthetic - migrated) == ["decision_totally_made_up_table"]


# ---- LOOP_TABLES ⊆ db_ownership[decision-service] (ledger #6, now wired) ----------------------
def test_every_loop_table_is_owned_by_decision_service():
    loop = _loop_tables()
    owned = _decision_owned_or_mirrored()
    orphan = sorted(loop - owned)
    assert not orphan, (
        f"LOOP_TABLES entries not registered as decision-service-owned (nor mirrored) in "
        f"docs/architecture/db_ownership.yml: {orphan}. A closed-loop table decision-service "
        "runs against must declare decision-service as its owner (or mirror during the SoR "
        "interim-bridge). Add the ownership entry, or fix LOOP_TABLES."
    )


def test_ownership_check_would_catch_an_unowned_loop_table():
    # Negative proof: a loop table absent from the ownership set is flagged by the set difference.
    owned = _decision_owned_or_mirrored()
    synthetic = {next(iter(owned)), "decision_unowned_loop_table"}
    assert sorted(synthetic - owned) == ["decision_unowned_loop_table"]


# ---- WebSocket auth ---------------------------------------------------------------------------
def test_no_websocket_route_bypasses_the_service_token_guard():
    offenders = sorted(
        name for name, src in _service_modules() if any(m in src for m in _WS_MARKERS)
    )
    assert not offenders, (
        f"WebSocket route(s) found in {offenders}: a WS endpoint bypasses the HTTP "
        "_service_token_guard middleware. Authenticate it explicitly (verify the service token in "
        "the WS handshake) and update this guard with justification."
    )


def test_ws_guard_would_catch_a_contrived_route():
    # Negative proof: the marker scan detects a synthetic WebSocket handler.
    contrived = "@app.websocket('/v1/stream')\nasync def stream(ws): ...\n"
    assert any(m in contrived for m in _WS_MARKERS)


# ---- Raw asyncpg.connect confinement (open-ledger #4) -----------------------------------------
# Modules permitted to open a RAW connection instead of the pooled acquire_connection(). Each is a
# standalone tool or a documented pooled-first fallback — reviewed on entry.
_RAW_CONNECT_ALLOWLIST = {
    "persistence.py",  # owns the pool (create_pool) + acquire_connection; the reference adapter
    "migration_runner.py",  # standalone schema-migration tool: a direct admin connection, not the pool
    "backfill.py",  # standalone backfill worker/CLI: runs outside the request path
    "activation_gate_core.py",  # pooled-FIRST; raw connect is a documented fallback for isolated tests/tools
    "platform_sor_revoke.py",  # standalone cutover REVOKE CLI: a privileged ADMIN connection (table owner/superuser), never the pooled app role
}


def test_raw_asyncpg_connect_is_confined_to_the_reviewed_allowlist():
    offenders = sorted(name for name, src in _service_modules() if "asyncpg.connect(" in src)
    unexpected = set(offenders) - _RAW_CONNECT_ALLOWLIST
    assert not unexpected, (
        f"Module(s) open a raw asyncpg connection instead of the pool: {sorted(unexpected)}. "
        "Route DB access through persistence.acquire_connection(), or add to "
        "_RAW_CONNECT_ALLOWLIST with a justification if a raw connection is genuinely required."
    )


def test_raw_connect_guard_would_catch_a_contrived_bypass():
    # Negative proof: a synthetic new module opening a raw connection is not in the allowlist.
    synthetic = {"persistence.py", "sneaky_direct_db.py"}
    assert synthetic - _RAW_CONNECT_ALLOWLIST == {"sneaky_direct_db.py"}
