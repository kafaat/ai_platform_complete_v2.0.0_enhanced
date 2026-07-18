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
# Phase 3: the proven-shared machinery (build_sha / evidence admissibility / probe envelope / state
# machine) was extracted into this core AFTER two independent gates existed (PROD-07 honoured). The
# irr_f01-specific enforcement (a REFUSAL) stays in GATE; the machinery is asserted against CORE.
CORE = (ROOT / "services" / "decision-service" / "activation_gate_core.py").read_text(
    encoding="utf-8"
)
SAT_GATE = (ROOT / "services" / "decision-service" / "satellite_cdse_activation_gate.py").read_text(
    encoding="utf-8"
)
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
    # Server-derived, non-spoofable build_sha now lives in the shared core.
    assert "def deploy_build_sha" in CORE
    assert "DEPLOY_BUILD_SHA" in CORE
    assert "never supplied by a caller" in CORE
    # The gate wrapper still binds/exposes it (public API unchanged).
    assert "deploy_build_sha" in GATE and "build_sha = _CORE.build_sha" in GATE


def test_prod_06_no_parallel_readiness_consumes_evidence():
    # The gate CONSUMES evidence (never re-runs checks): the admissibility check in the core reads
    # these envelope fields.
    for field in ("producer", "check_name", "valid_until", "result", "environment_id"):
        assert field in CORE
    assert "_evidence_admissible" in CORE
    # The irr_f01 evidence config stays specific to the gate wrapper.
    assert "REQUIRED_CHECKS" in GATE
    # The full provenance envelope is the documented contract in the registry.
    for field in ("producer", "check_name", "observed_at", "valid_until", "result", "provenance"):
        assert field in REGISTRY


def test_prod_evidence_receipt_trust_root():
    # Gate-Trust-1: caller-supplied evidence was spoofable; the root of trust is now server-stored
    # producer-issued RECEIPTS. The caller submits references (evidence_refs), the gate resolves them
    # from its own store, re-verifies the stored HMAC signature, and raw caller evidence is forbidden.
    RECEIPT_MIGRATION = (
        ROOT
        / "services"
        / "decision-service"
        / "migrations"
        / "030_activation_evidence_receipts.sql"
    ).read_text(encoding="utf-8")
    assert "activation_evidence_receipts" in RECEIPT_MIGRATION
    assert "activation_evidence_receipts is append-only" in RECEIPT_MIGRATION
    # The revocation kill switch is a SEPARATE INSERT-only table (one revocation per receipt, itself
    # append-only) — it restores a selective kill switch without an UPDATE-able column on receipts.
    assert "activation_evidence_revocations" in RECEIPT_MIGRATION
    assert "evidence_id uuid NOT NULL UNIQUE" in RECEIPT_MIGRATION
    assert "activation_evidence_revocations is append-only" in RECEIPT_MIGRATION
    # The core resolves receipts server-side, re-verifies the stored signature, and drops any revoked
    # receipt inside the SAME resolve query (NOT EXISTS — no TOCTOU); complete takes references.
    assert "async def _resolve_evidence_refs" in CORE
    assert "evidence_signature_invalid" in CORE and "compare_digest" in CORE
    assert "NOT EXISTS" in CORE and "activation_evidence_revocations" in CORE
    assert (
        "evidence_refs" in CORE
        and "evidence: list[dict[str, Any]]"
        not in CORE.split("async def complete_evaluation")[1].split("async def")[0]
    )
    # Raw caller evidence is forbidden at the HTTP contract (extra=forbid) — a smuggled results
    # field is rejected, not silently ignored — and the ingest + revoke endpoints exist.
    assert 'ConfigDict(extra="forbid")' in MAIN
    assert "evidence-receipts" in MAIN  # the authenticated ingest endpoint
    assert "/revoke" in MAIN and "X-Requested-By is required" in MAIN  # actor-authed revoke


def test_prod_production_profile_fail_closed():
    # Gate-Trust-1: the trust root fails closed at READ. The deployed build identity is mandatory and
    # non-spoofable — deploy_build_sha() raises on an absent/malformed DEPLOY_BUILD_SHA, so no verdict
    # can bind to an unknown build. The evidence signing key is mandatory to ingest or resolve.
    assert "def deploy_build_sha" in CORE and "DEPLOY_BUILD_SHA" in CORE
    assert 'raise RuntimeError("ACTIVATION_EVIDENCE_SIGNING_KEY is required")' in CORE
    # Ingest fails closed without the signing key (503) and caps validity at 24h (defense-in-depth
    # alongside the revocation kill switch).
    assert "activation evidence signing unavailable" in MAIN
    assert "MAX_EVIDENCE_VALIDITY_SECONDS" in MAIN
    assert "MAX_EVIDENCE_VALIDITY_SECONDS = 24 * 60 * 60" in CORE


def test_prod_07_shared_core_extracted_after_two_gates():
    # Phase 3: the machinery is shared by exactly the two proven gates, each a thin wrapper that
    # instantiates the core with its own GateConfig. Neither re-implements the state machine.
    assert "class ActivationGateCore" in CORE
    for wrapper in (GATE, SAT_GATE):
        assert "ActivationGateCore(" in wrapper and "GateConfig(" in wrapper
    # The enforcement meaning stays per-gate: a refusal here, a source selection there.
    assert "async def enforce_enabled" in GATE
    assert "async def active_imagery_source" in SAT_GATE


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


def test_prod_probe_role_and_enforcement_wiring():
    assert 'PROBE_ROLE = "activation_probe"' in GATE
    # The probe envelope (role + HMAC signature) is in the shared core; the wrapper exposes it.
    assert "async def probe_state" in CORE
    assert "probe_state = _CORE.probe_state" in GATE
    # Enforcement is wired at the ingest point behind the opt-in flag, returning 403.
    assert "_enforce_reservation_activation()" in MAIN
    assert "activation_gate.enforce_enabled(_activation_environment())" in MAIN
    assert "IRR_F01_RESERVATION_ENFORCE_ACTIVATION" in MAIN
    # The probe endpoint requires the role + signature headers.
    assert "/v1/activation/irr_f01_reservation/probe" in MAIN
    assert "x_activation_probe_signature" in MAIN
