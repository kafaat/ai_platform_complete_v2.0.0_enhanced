"""W2-01 repo-side preparation for the staging decision-SoR cutover (owner decision 2026-11-16).

Pins what the operator relies on, without any database or network beyond localhost:

* the ``/readyz`` ``sor_capability`` block: booleans and identifiers only, gates identical to
  ``/v1/cutover/readiness``, ``review_available`` only when writes persist and the service is ready;
* ``scripts/deploy/decision_service_migrate.sh``: a pre-check that fails for any reason other than
  "pending" (exit 2) stops before ``--apply``; the review verifier uses the auditor connection;
* ``staging_probe.py`` sends the decision-service bearer, so it can pass against an authenticated
  staging service;
* the staging runbook keeps its order and names what closes each open gap.

The real-Postgres witnesses (migrate/certify/backfill against two roles) are recorded in the
runbook; ``backfill.verify_review`` under RLS is pinned in
``services/decision-service/tests/test_decision_sor_role_certify_pg.py``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "services" / "decision-service"
MIGRATE = ROOT / "scripts" / "deploy" / "decision_service_migrate.sh"
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_STAGING_CUTOVER_RUNBOOK.md"

GATE_ENVS = (
    "DECISION_SERVICE_MIGRATIONS_VERIFIED",
    "DECISION_SERVICE_BACKFILL_VERIFIED",
    "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
    "DECISION_SERVICE_OUTBOX_VERIFIED",
    "DECISION_SERVICE_STAGING_CUTOVER_APPROVED",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cutover(monkeypatch):
    for name in (
        "DATABASE_URL",
        "DECISION_SERVICE_SOR_ENABLED",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        *GATE_ENVS,
    ):
        monkeypatch.delenv(name, raising=False)
    return _load("decision_service_cutover_w201", DECISION / "cutover.py")


READY_DB = {
    "database_configured": True,
    "db_reachable": True,
    "migrations_current": True,
    "pending_migrations": [],
}


def test_capability_carries_no_secret_values(cutover, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://svc:pw-W201-SECRET@db.internal:5432/sahool")
    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", "tok-W201-SECRET")
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    signal = cutover.sor_capability_signal(READY_DB, sor_enabled=True, ready=True)
    text = json.dumps(signal)
    for leaked in ("pw-W201-SECRET", "tok-W201-SECRET", "db.internal", "postgresql://"):
        assert leaked not in text, f"capability block leaks {leaked!r}: {text}"
    scalars = [v for v in signal.values() if not isinstance(v, dict | list)]
    assert all(isinstance(v, bool | str) for v in scalars), f"non-identifier scalar: {signal}"
    assert all(isinstance(v, bool) for v in signal["gates"].values()), signal["gates"]


@pytest.mark.parametrize("sor_flag", [False, True])
@pytest.mark.parametrize("db_url", [False, True])
@pytest.mark.parametrize("gates_set", [0, 3, 5])
def test_capability_gates_match_the_cutover_readiness_endpoint(
    cutover, monkeypatch, sor_flag, db_url, gates_set
):
    if sor_flag:
        monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    if db_url:
        monkeypatch.setenv("DATABASE_URL", "postgresql://x@y/z")
    for name in GATE_ENVS[:gates_set]:
        monkeypatch.setenv(name, "true")
    readiness = cutover.readiness_from_env()
    signal = cutover.sor_capability_signal(READY_DB, sor_enabled=sor_flag and db_url, ready=True)
    assert signal["missing_gates"] == list(readiness.missing_gates), (signal, readiness)
    assert signal["can_enable_sor"] is readiness.can_enable_sor, (signal, readiness)
    assert signal["can_demote_platform"] is readiness.can_demote_platform, (signal, readiness)
    assert signal["cutover_mode"] == readiness.mode, (signal, readiness)
    assert set(signal["gates"]) == {"DATABASE_URL", *GATE_ENVS}, signal["gates"]
    assert signal["gates_complete"] is (not readiness.missing_gates), signal


def test_capability_modes_and_review_switch(cutover):
    mirror = cutover.sor_capability_signal(READY_DB, sor_enabled=False, ready=True)
    persisted = cutover.sor_capability_signal(READY_DB, sor_enabled=True, ready=True)
    degraded = cutover.sor_capability_signal(READY_DB, sor_enabled=True, ready=False)
    assert (mirror["mode"], mirror["persisted"]) == ("mirror", False), mirror
    assert mirror["review_available"] is False, "mirror mode must hide the review queue"
    assert (persisted["mode"], persisted["review_available"]) == ("persisted", True), persisted
    assert degraded["review_available"] is False, "a degraded SoR must not advertise review"
    assert persisted["persisted_without_verified_gates"] is True, (
        "the SoR flag without recorded gates must be visible"
    )


def test_capability_reports_the_migration_level(cutover):
    shipped = sorted(p.name for p in (DECISION / "migrations").glob("*.sql"))
    behind = dict(READY_DB, migrations_current=False, pending_migrations=[shipped[-1]])
    level = cutover.sor_capability_signal(behind, sor_enabled=True, ready=False)["migration_level"]
    assert level["code_head"] == shipped[-1], level
    assert level["applied_head"] == shipped[-2], level
    assert (level["pending_count"], level["current"]) == (1, False), level
    mirror = {"database_configured": False, "db_reachable": None, "migrations_current": None}
    unknown = cutover.sor_capability_signal(mirror, sor_enabled=False, ready=True)
    assert unknown["migration_level"]["applied_head"] is None, unknown["migration_level"]
    assert unknown["migration_level"]["pending_count"] is None, unknown["migration_level"]
    assert unknown["migration_level"]["code_head"] == shipped[-1], unknown["migration_level"]


def test_readyz_wires_the_capability_block():
    text = (DECISION / "main.py").read_text(encoding="utf-8")
    assert '"sor_capability": sor_capability_signal(db, sor_enabled=sor_on, ready=ready)' in text, (
        "/readyz must expose sor_capability built from the same db/ready values it reports"
    )


# --- scripts/deploy/decision_service_migrate.sh ------------------------------------------------

STUB = """#!/usr/bin/env python3
import os, sys
log = os.environ["W201_LOG"]
args = " ".join(sys.argv[1:])
with open(log, "a", encoding="utf-8") as fh:
    fh.write(f"{os.path.basename(sys.argv[1])} {' '.join(sys.argv[2:])} db={os.environ.get('DATABASE_URL')}\\n")
codes = os.environ.get("W201_CHECK_CODES", "0").split(",")
if sys.argv[-1] == "--check":
    n = sum(1 for line in open(log, encoding="utf-8") if line.split()[1:2] == ["--check"]) - 1
    sys.exit(int(codes[min(n, len(codes) - 1)]))
sys.exit(0)
"""


def _migrate(tmp_path: Path, check_codes: str, **extra: str):
    stub = tmp_path / "python_stub.py"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "calls.log"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHON": str(stub),
        "W201_LOG": str(log),
        "W201_CHECK_CODES": check_codes,
        "DATABASE_URL": "postgresql://owner@db/x",
        "DECISION_SERVICE_ALLOW_SCHEMA_CHANGE": "true",
        **extra,
    }
    proc = subprocess.run(
        ["bash", str(MIGRATE)],
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


def test_migrate_stops_before_apply_when_the_precheck_fails_for_another_reason(tmp_path):
    proc, calls = _migrate(tmp_path, "1")
    assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
    assert not any("--apply" in c for c in calls), f"apply ran after a broken pre-check: {calls}"
    assert "for a reason other than pending migrations" in proc.stderr, proc.stderr


def test_migrate_treats_exit_2_as_pending_and_audits_with_the_auditor_url(tmp_path):
    proc, calls = _migrate(
        tmp_path, "2,0", DECISION_SOR_AUDIT_DATABASE_URL="postgresql://auditor@db/x"
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "decision_service_migrate_ok" in proc.stdout, proc.stdout
    steps = [c.split(" db=")[0] for c in calls]
    assert steps == [
        "migration_runner.py --check",
        "migration_runner.py --apply",
        "migration_runner.py --check",
        "backfill.py --verify-review",
    ], calls
    assert calls[1].endswith("db=postgresql://owner@db/x"), f"apply must use the owner: {calls}"
    assert calls[-1].endswith("db=postgresql://auditor@db/x"), f"verifier must audit: {calls}"


def test_migrate_without_auditor_url_verifies_with_database_url(tmp_path):
    proc, calls = _migrate(tmp_path, "0")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert calls[-1] == "backfill.py --verify-review db=postgresql://owner@db/x", calls


def test_migrate_still_refuses_without_the_schema_change_flag(tmp_path):
    proc, calls = _migrate(tmp_path, "0", DECISION_SERVICE_ALLOW_SCHEMA_CHANGE="")
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert calls == [], f"nothing may run without the flag: {calls}"


# --- staging_probe.py bearer -------------------------------------------------------------------

TOKEN = "w201-probe-token"


class _ReadinessHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        if self.headers.get("authorization") != f"Bearer {TOKEN}":
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(
            {"can_enable_sor": True, "can_demote_platform": False, "missing_gates": []}
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


@pytest.fixture()
def readiness_server():
    server = HTTPServer(("127.0.0.1", 0), _ReadinessHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_staging_probe_readiness_sends_the_service_bearer(readiness_server, monkeypatch):
    probe = _load("decision_staging_probe_w201", DECISION / "staging_probe.py")
    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", TOKEN)
    step = probe._check_readiness(readiness_server)
    assert step.ok is True, f"authenticated staging readiness must pass: {step}"
    assert TOKEN not in step.detail, "the probe must never print the token"


def test_staging_probe_readiness_without_token_fails_closed(readiness_server, monkeypatch):
    probe = _load("decision_staging_probe_w201_anon", DECISION / "staging_probe.py")
    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    step = probe._check_readiness(readiness_server)
    assert step.ok is False, f"a 401 must fail the probe step: {step}"
    assert "401" in step.detail, step.detail


# --- staging runbook ---------------------------------------------------------------------------


def test_staging_runbook_sequences_the_cutover():
    text = RUNBOOK.read_text(encoding="utf-8")
    ordered = [
        "decision_sor_role_certify.py",
        "decision_service_migrate.sh",
        "backfill.py --verify-counts",
        "DECISION_SERVICE_SOR_ENABLED=true",
        "staging_probe.py --live",
        "/v1/decisions/review-queue",
        "rollback.py --live",
    ]
    # The order is checked in the step sections, after the at-a-glance table.
    body = text[text.index("## 1. Role certification") :]
    positions = [body.find(token) for token in ordered]
    assert all(p >= 0 for p in positions), dict(zip(ordered, positions, strict=True))
    assert positions == sorted(positions), dict(zip(ordered, positions, strict=True))
    for phrase in (
        "DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION",
        "DECISION-SOR-CUTOVER-WIRING-01",
        "2026-11-30",
        "Never set `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED` here",
        "DECISION_SOR_AUDIT_DATABASE_URL",
        "sor_capability",
        "platform_sequence_privilege_present:recommendation_outcomes_outcome_id_seq",
    ):
        assert phrase in text, f"staging runbook must state: {phrase}"
    for gate in GATE_ENVS:
        assert f"{gate}=true" in text, f"staging runbook must sequence gate {gate}"


def test_staging_runbook_proves_outbox_after_the_flag_never_before():
    """The outbox gate needs a persisted write, and a write persists only once the flag is set.

    The runbook must therefore set the flag with the outbox gate still missing (4b), prove one
    persisted write leaves its outbox row (4c) and only then set the outbox gate (4d). Any other
    order makes the operator record the gate as true without evidence.
    """
    text = RUNBOOK.read_text(encoding="utf-8")
    section = text[text.index("## 4. Gates and the SoR flag") : text.index("## 5. Staging probe")]
    ordered = [
        "**4a.",
        "Leave `DECISION_SERVICE_OUTBOX_VERIFIED` unset",
        "**4b.",
        "DECISION_SERVICE_SOR_ENABLED=true",
        "persisted_without_verified_gates: true",
        'missing_gates: ["DECISION_SERVICE_OUTBOX_VERIFIED"]',
        "**4c.",
        "FROM decision_outbox_events",
        "**4d.",
        "DECISION_SERVICE_OUTBOX_VERIFIED=true",
        "can_enable_sor: true",
    ]
    positions = [section.find(token) for token in ordered]
    assert all(p >= 0 for p in positions), dict(zip(ordered, positions, strict=True))
    assert positions == sorted(positions), dict(zip(ordered, positions, strict=True))
    first_outbox_gate = section.find("DECISION_SERVICE_OUTBOX_VERIFIED=true")
    assert first_outbox_gate > section.find("FROM decision_outbox_events"), (
        "the outbox gate must not be set anywhere in step 4 before its outbox-row proof"
    )
    gate_table = section[section.index("**4a.") : section.index("**4b.")]
    assert "DECISION_SERVICE_OUTBOX_VERIFIED=true" not in gate_table, (
        "step 4a must not list the outbox gate among the gates set before the flag"
    )


def test_staging_runbook_sql_recipe_uses_one_alter_table_per_statement():
    """PostgreSQL rejects ``ALTER TABLE a, b OWNER TO r``; the recipe must be pasteable."""
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("```sql\nCREATE ROLE")
    recipe = text[start : text.index("```", start + 6)]
    statements = [s.strip() for s in recipe.split(";")]
    alter_tables = [s for s in statements if "ALTER TABLE" in s]
    assert len(alter_tables) == 5, f"one ALTER TABLE per SoR table expected, got {alter_tables}"
    for stmt in alter_tables:
        head = stmt[stmt.index("ALTER TABLE") : stmt.index("OWNER TO")]
        assert "," not in head, f"multi-table ALTER TABLE is invalid PostgreSQL: {stmt!r}"


def test_staging_runbook_keeps_the_certification_gap_open_on_failed():
    """A FAILED certification never closes the role-certification gap on the operator's reading."""
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "stays open on a `FAILED` result" in text, (
        "the runbook must say the role-certification gap stays open on a FAILED run"
    )
    assert "classification: PASSED" in text, "closure must name a PASSED classification"
    assert "owner records a decision" in text, (
        "the only other closure path must be an owner decision, not the operator's reading"
    )
    gaps = text[text.index("## Open gaps and what closes them") :]
    assert "A `FAILED` run alone leaves it" in gaps, (
        "the open-gaps section must repeat that a FAILED run does not close the gap"
    )


def test_step_4b_window_matches_what_readyz_reports(cutover, monkeypatch):
    """The runbook's 4b expectation (flag set, outbox gate only missing) is what the code says."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x@y/z")
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    for name in GATE_ENVS:
        if name != "DECISION_SERVICE_OUTBOX_VERIFIED":
            monkeypatch.setenv(name, "true")
    signal = cutover.sor_capability_signal(READY_DB, sor_enabled=True, ready=True)
    assert signal["mode"] == "persisted", f"4b: writes must persist with the flag set: {signal}"
    assert signal["missing_gates"] == ["DECISION_SERVICE_OUTBOX_VERIFIED"], (
        f"4b: only the outbox gate may be missing: {signal}"
    )
    assert signal["persisted_without_verified_gates"] is True, (
        f"4b window must be visible: {signal}"
    )
    assert signal["cutover_mode"] == "sor-requested-but-not-ready", f"4b cutover_mode: {signal}"
    assert signal["can_enable_sor"] is False, f"4b: probe readiness must still fail: {signal}"
    text = RUNBOOK.read_text(encoding="utf-8")
    for expected in (
        "`cutover_mode: sor-requested-but-not-ready`",
        "`can_enable_sor: false`",
        "`persisted_without_verified_gates: true`",
    ):
        assert expected in text, f"runbook 4b must state {expected}"


def test_staging_runbook_recipe_grants_existing_sequences_and_interim_platform_dml():
    """Default privileges reach only future objects; the owner move drops the old owner's ACL.

    The live proof is ``tests_v9/test_decision_sor_staging_recipe_live_pg.py``; this pins the
    statements it depends on so a docs edit cannot drop them without a unit failure.
    """
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("```sql\nCREATE ROLE")
    recipe = text[start : text.index("\n```", start)]
    assert "GRANT USAGE, SELECT ON SEQUENCE %s TO decision_service_app, sahool_app" in recipe, (
        "sequences owned by the moved tables need explicit USAGE, SELECT for both writers"
    )
    assert "'recommendation_outcomes'" in recipe and "d.deptype IN ('a', 'i')" in recipe, recipe
    tables = (
        "decision_record, dispatch_decisions, outcome_record,\n"
        "      recommendation_outcomes, online_learning_updates"
    )
    for role in ("decision_service_app", "sahool_app"):
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO {role};" in recipe, role
    assert "Changing a table's owner keeps its existing grants" not in text, (
        "false when the platform role was the owner: ALTER OWNER drops the old owner's ACL"
    )


def test_review_available_is_documented_as_conservative_not_exact(cutover):
    """review-queue checks sor_enabled() alone; review_available also needs ready."""
    main = (DECISION / "main.py").read_text(encoding="utf-8")
    queue = main[main.index("async def review_queue(") :]
    queue = queue[: queue.index("\n@app.")]
    assert "if not sor_enabled():" in queue and "ready" not in queue.split('"""')[2], (
        "the wording below assumes the queue gates on the SoR flag only; update both together"
    )
    degraded = cutover.sor_capability_signal(READY_DB, sor_enabled=True, ready=False)
    assert degraded["review_available"] is False and degraded["persisted"] is True, degraded
    doc = cutover.sor_capability_signal.__doc__
    assert "exactly when" not in doc and "conservative" in doc, doc
    text = RUNBOOK.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `review_available` |"))
    assert "the condition under which the review queue answers 200" not in row, row
    assert "Conservative" in row, row
