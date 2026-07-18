"""IRR-F01 Phase 1 — anti-deletion + contract guard for the irr_f01_reservation activation gate.

Locks the ACTIVATION-GATE-PROD-01..07 invariants (the ratified architecture) in the gap registry
AND in code, so none can be silently removed or shortcut without an explicit architectural
decision. Runs via the irrigation-convergence workflow (no infra).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = (ROOT / "sahool-brain" / "gaps" / "registry.md").read_text(encoding="utf-8")
GATE = (ROOT / "services" / "decision-service" / "activation_gate.py").read_text(encoding="utf-8")
MIGRATION = (
    ROOT
    / "services"
    / "decision-service"
    / "migrations"
    / "028_irr_f01_reservation_activation_gate.sql"
).read_text(encoding="utf-8")
MAIN = (ROOT / "services" / "decision-service" / "main.py").read_text(encoding="utf-8")


def test_prod_01_to_07_recorded_in_registry():
    for n in range(1, 8):
        assert f"ACTIVATION-GATE-PROD-0{n}" in REGISTRY, f"PROD-0{n} must stay recorded"
    # PROD-07 must remain the deferred anti-abstraction ratchet.
    assert "Anti-premature abstraction" in REGISTRY


def test_prod_01_state_machine_present():
    for state in ("disabled", "evaluating", "enabled", "degraded", "revoked"):
        assert f"'{state}'" in MIGRATION
    assert "ck_irr_act_state" in MIGRATION


def test_prod_02_cas_generation_guard():
    assert "irr_f01_reservation_activation_guard" in MIGRATION
    assert "generation must advance by exactly 1 (CAS)" in MIGRATION
    assert "environment_id is immutable" in MIGRATION


def test_prod_03_append_only_evidence_log():
    assert "irr_f01_reservation_activation_events_immutable" in MIGRATION
    assert "is append-only" in MIGRATION


def test_prod_04_ttl_and_fresh_enforcement():
    assert "state_expires_at" in MIGRATION and "ck_irr_act_ttl" in MIGRATION
    assert "async def enforce_enabled" in GATE
    assert "never the cache" in GATE  # enforcement reads fresh, not the cache


def test_prod_05_non_spoofable_build_sha():
    assert "def deploy_build_sha" in GATE
    assert "DEPLOY_BUILD_SHA" in GATE
    assert "never supplied by a caller" in GATE


def test_prod_06_no_parallel_readiness_consumes_evidence():
    # The gate CONSUMES evidence (never re-runs checks): it reads these envelope fields.
    for field in ("producer", "check_name", "valid_until", "result", "environment_id"):
        assert field in GATE
    assert "REQUIRED_CHECKS" in GATE and "_evidence_admissible" in GATE
    # The full provenance envelope is the documented contract in the registry.
    for field in ("producer", "check_name", "observed_at", "valid_until", "result", "provenance"):
        assert field in REGISTRY


def test_prod_schema_scope_and_operational_role_contract():
    # Closure of the schema/RLS/operational-role criterion: the gate is ENVIRONMENT-scoped, not
    # tenant-scoped, so tenant-RLS is inapplicable by design — the schema carries no tenant_id and
    # keys on environment_id. Access control is the operational role/token contract instead.
    assert "environment_id text PRIMARY KEY" in MIGRATION
    assert "tenant_id" not in MIGRATION
    # Operator transitions require an actor (X-Requested-By) and the system-of-record.
    assert "_activation_actor(x_requested_by)" in MAIN
    assert MAIN.count("activation gate requires the system-of-record") >= 5
    # A shared service token guards every non-probe request when configured (production).
    assert "_service_token_guard" in MAIN


def test_prod_07_probe_role_and_enforcement_wiring():
    assert 'PROBE_ROLE = "activation_probe"' in GATE
    assert "def probe_state" in GATE
    # Enforcement is wired at the ingest point behind the opt-in flag, returning 403.
    assert "_enforce_reservation_activation()" in MAIN
    assert "activation_gate.enforce_enabled(_activation_environment())" in MAIN
    assert "IRR_F01_RESERVATION_ENFORCE_ACTIVATION" in MAIN
    # The probe endpoint requires the role + signature headers.
    assert "/v1/activation/irr_f01_reservation/probe" in MAIN
    assert "x_activation_probe_signature" in MAIN
