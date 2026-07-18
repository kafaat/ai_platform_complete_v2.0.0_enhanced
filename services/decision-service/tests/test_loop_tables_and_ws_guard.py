"""Decision-service governance guards (open-ledger #2, slice 2): LOOP_TABLES drift + WebSocket auth.

Two static guards, no DB, no network:

1. LOOP_TABLES drift — every table named in ``main.LOOP_TABLES`` must be a REAL table created by a
   decision-service migration. This catches a renamed/dropped table left stale in the runtime list.

   Honest scope: LOOP_TABLES is a CURATED SUBSET of the decision tables (the closed-loop tables),
   so the reverse ("every decision table must be in LOOP_TABLES") is deliberately NOT enforced — it
   would drag non-loop tables (activation receipts, satellite_cdse, irr_f01 gate) into the list.
   The ownership cross-check (LOOP_TABLES ⊆ db_ownership.yml[decision-service]) is a documented
   FOLLOW-UP: docs/architecture/db_ownership.yml currently registers only 4 decision tables, so
   wiring that check requires first populating the ownership baseline — a separate governance change.

2. WebSocket auth — a WebSocket route bypasses the HTTP ``_service_token_guard`` middleware entirely,
   so an unauthenticated WS endpoint would be a hole in the exact defense open-ledger #2 built. The
   service has NO WebSocket routes today; this guard fails the moment one is added, forcing a
   reviewer to confirm it authenticates before it can land.
"""

from __future__ import annotations

import re
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
MAIN = (SERVICE_DIR / "main.py").read_text(encoding="utf-8")
MIGRATIONS = SERVICE_DIR / "migrations"


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
