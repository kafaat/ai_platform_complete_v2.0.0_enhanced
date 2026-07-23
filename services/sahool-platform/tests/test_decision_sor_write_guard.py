"""DECISION-SOR-CUTOVER-WIRING-01 slice 1 — the decision-SoR write guard.

Verifies (a) the guard is a strict no-op while the platform is the authoritative
writer (default `platform_sor` and `shadow`), (b) it fails closed once the platform
is demoted to `decision_service_sor`, and (c) the guard is actually WIRED before the
platform's decision-SoR-row-creation writes in the HTTP router paths — so the
contract is no longer orphaned.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api.decision_sor_mode import (
    DECISION_SOR_TABLES,
    PlatformDecisionWriteForbidden,
    assert_platform_may_write_decision_sor,
)

ROOT = Path(__file__).resolve().parents[3]
ROUTERS = ROOT / "services/sahool-platform/api/routers"

_CUTOVER_GATES = (
    "DECISION_SERVICE_SOR_ENABLED",
    "DECISION_SERVICE_MIGRATIONS_VERIFIED",
    "DECISION_SERVICE_BACKFILL_VERIFIED",
    "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
    "DECISION_SERVICE_OUTBOX_VERIFIED",
    "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
)


def _clear_mode_env(monkeypatch) -> None:
    monkeypatch.delenv("SAHOOL_DECISION_WRITE_MODE", raising=False)
    for gate in _CUTOVER_GATES:
        monkeypatch.delenv(gate, raising=False)


def test_guard_is_noop_in_default_platform_sor(monkeypatch):
    _clear_mode_env(monkeypatch)
    # Default (no env) → platform_sor → platform is authoritative → no raise.
    assert assert_platform_may_write_decision_sor("decision_record") is None


def test_guard_is_noop_in_shadow_mode(monkeypatch):
    _clear_mode_env(monkeypatch)
    monkeypatch.setenv("SAHOOL_DECISION_WRITE_MODE", "shadow")
    # Shadow still requires platform writes (+ mirror) → no raise.
    assert assert_platform_may_write_decision_sor("outcome_record") is None


def test_guard_fails_closed_once_platform_is_demoted(monkeypatch):
    _clear_mode_env(monkeypatch)
    monkeypatch.setenv("SAHOOL_DECISION_WRITE_MODE", "decision_service_sor")
    for gate in _CUTOVER_GATES:
        monkeypatch.setenv(gate, "true")
    with pytest.raises(PlatformDecisionWriteForbidden) as exc:
        assert_platform_may_write_decision_sor("decision_record")
    assert exc.value.table == "decision_record"
    assert exc.value.effective_mode == "decision_service_sor"


def test_demotion_needs_all_gates_so_a_missing_gate_keeps_the_guard_open(monkeypatch):
    _clear_mode_env(monkeypatch)
    monkeypatch.setenv("SAHOOL_DECISION_WRITE_MODE", "decision_service_sor")
    for gate in _CUTOVER_GATES[:-1]:  # one gate missing
        monkeypatch.setenv(gate, "true")
    # Incomplete cutover → falls back to platform_sor → guard stays a no-op.
    assert assert_platform_may_write_decision_sor("decision_record") is None


def test_sor_table_set_matches_decision_service_cutover_contract():
    cutover = (ROOT / "services/decision-service/cutover.py").read_text(encoding="utf-8")
    for table in DECISION_SOR_TABLES:
        assert f'"{table}"' in cutover, f"{table} missing from decision-service cutover contract"


# --- Wiring: the SoR-row-creation writes in the router paths must be guarded. ---

_GUARDED_ROUTER_WRITES = {
    "decision_record.py": [("decision_record", 2), ("outcome_record", 1)],
    "decision_dispatch.py": [("dispatch_decisions", 1)],
    "recommendations.py": [("recommendation_outcomes", 1)],
    "weather.py": [("decision_record", 1)],
}


@pytest.mark.parametrize("filename,expected", sorted(_GUARDED_ROUTER_WRITES.items()))
def test_router_sor_writes_are_preceded_by_the_guard(filename, expected):
    src = (ROUTERS / filename).read_text(encoding="utf-8")
    for table, count in expected:
        # The guard call for this table appears at least as many times as the
        # INSERT INTO <table> creation sites we wired in this slice.
        assert src.count(f'assert_platform_may_write_decision_sor("{table}")') >= count
