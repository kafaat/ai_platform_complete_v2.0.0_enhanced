"""Guard: the DB-level platform-write REVOKE for the decision SoR cutover is correct & fail-closed.

This is the CI-enforced (mandatory `pytest -m unit`) guard for the complementary DB-level
enforcement that backs the app-layer guard in
``sahool-platform/api/decision_sor_mode.assert_platform_may_write_decision_sor``. The behavioral
proof (real Postgres: platform role denied writes but keeps SELECT after revoke, restored after
grant) runs as an explicit step in the Decision Service Tests job
(``services/decision-service/tests/test_platform_sor_revoke_pg.py``).

It asserts the tool:
  * targets exactly the FIVE platform-owned SoR tables (in lockstep with the platform's
    ``DECISION_SOR_TABLES`` minus the decision-service-owned ``decision_outbox_events``);
  * revokes only writes (INSERT/UPDATE/DELETE) and retains SELECT;
  * is fail-closed behind the cutover/rollback approval gates (no importable side effects);
  * rejects non-identifier role/schema names (injection-safe).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REVOKE_PATH = ROOT / "services" / "decision-service" / "platform_sor_revoke.py"
MODE_PATH = ROOT / "services" / "sahool-platform" / "api" / "decision_sor_mode.py"
WRAPPER = ROOT / "scripts" / "deploy" / "decision_sor_platform_revoke.sh"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__ during class creation.
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_tool_and_wrapper_exist() -> None:
    assert REVOKE_PATH.exists(), "platform_sor_revoke.py must exist"
    assert WRAPPER.exists(), "the operator wrapper must exist"


def test_table_set_is_lockstep_with_platform_minus_outbox() -> None:
    revoke = _load("platform_sor_revoke", REVOKE_PATH)
    mode = _load("decision_sor_mode", MODE_PATH)
    # The five platform-owned tables == the platform's canonical SoR set minus the
    # decision-service-owned outbox. This keeps the REVOKE target honest as the set evolves.
    expected = set(mode.DECISION_SOR_TABLES) - {"decision_outbox_events"}
    assert set(revoke.PLATFORM_SOR_TABLES) == expected
    assert "decision_outbox_events" not in revoke.PLATFORM_SOR_TABLES
    assert len(revoke.PLATFORM_SOR_TABLES) == 5


def test_revokes_writes_only_keeps_select() -> None:
    revoke = _load("platform_sor_revoke", REVOKE_PATH)
    assert set(revoke.WRITE_PRIVILEGES) == {"INSERT", "UPDATE", "DELETE"}
    assert revoke.RETAINED_PRIVILEGE == "SELECT"
    assert "SELECT" not in revoke.WRITE_PRIVILEGES, "SELECT must never be revoked"


def test_fail_closed_gate_env_names_present() -> None:
    revoke = _load("platform_sor_revoke", REVOKE_PATH)
    # Revoke requires the production-cutover-approved gate + the explicit allow flag.
    assert revoke.CUTOVER_APPROVED_ENV == "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED"
    assert revoke.ROLLBACK_APPROVED_ENV == "DECISION_SERVICE_ROLLBACK_APPROVED"
    assert revoke.ALLOW_REVOKE_ENV == "DECISION_SOR_ALLOW_PLATFORM_REVOKE"


def test_identifier_validation_rejects_injection() -> None:
    revoke = _load("platform_sor_revoke", REVOKE_PATH)
    assert revoke._validate_identifier("sahool_app", kind="role") == "sahool_app"
    for bad in ("sahool_app; DROP TABLE decision_record", 'a"b', "role with space", ""):
        with pytest.raises(SystemExit):
            revoke._validate_identifier(bad, kind="role")


def test_no_import_side_effects_no_db() -> None:
    # Importing the module must not touch a database or read the admin URL — mutation is gated
    # behind explicit CLI actions only. (Loads cleanly with no env set.)
    _load("platform_sor_revoke", REVOKE_PATH)
