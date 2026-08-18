from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
SHA = "7" * 40


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


collector = _load("decision_live_collector_test", "scripts/staging/decision_sor_live_closure_collector.py")
guard = _load("decision_live_receipt_guard_test", "scripts/architecture/s5_decision_live_closure_receipt_guard.py")


def _identity(service: str):
    return {
        "service": service,
        "git_sha": SHA,
        "build_id": "build-1",
        "metadata_source": "immutable-image-file",
    }


def _ready():
    return {
        "status": "ready",
        "ready": True,
        "service": "decision-service",
        "sor_enabled": True,
        "mode": "system-of-record",
        "db_readiness": {"db_reachable": True, "migrations_current": True},
    }


def _cutover():
    return {
        "requested_sor": True,
        "can_enable_sor": True,
        "production_approved": True,
        "can_demote_platform": True,
        "missing_gates": [],
    }


def _platform_ready():
    return {
        "decision_sor": {
            "requested_mode": "decision_service_sor",
            "effective_mode": "decision_service_sor",
            "platform_writes_required": False,
            "mirror_required": False,
            "strict_decision_service_required": True,
            "demotion_allowed": True,
            "missing_gates": [],
        }
    }


def _role():
    return {
        "classification": "PASSED",
        "cutover_preflight_safe": True,
        "role_separation_confirmed": True,
        "platform_role": "sahool_app",
        "decision_service_role": "decision_service",
        "blockers": [],
    }


def _privilege():
    state = {
        t: {"INSERT": False, "UPDATE": False, "DELETE": False, "SELECT": True}
        for t in collector.SOR_TABLES
    }
    return {"action": "check", "role": "sahool_app", "schema": "public", "after": state, "before": state}


def _evaluated():
    findings, evidence = collector.evaluate_evidence(
        subject_sha=SHA,
        decision_identity=_identity("decision-service"),
        platform_identity=_identity("sahool-platform"),
        decision_ready=_ready(),
        decision_cutover=_cutover(),
        platform_ready=_platform_ready(),
        role_certification=_role(),
        privilege_check=_privilege(),
    )
    assert findings == []
    return {
        "schema": collector.SCHEMA,
        "subject_sha": SHA,
        "observed_at": "2026-08-18T01:00:00+00:00",
        "classification": "PASSED",
        "read_only": True,
        "authority_promotion": False,
        "claims": {
            "post_cutover_platform_write_enforcement_proven": True,
            "historical_zero_platform_writes_measured": False,
        },
        "findings": [],
        "evidence": evidence,
    }


def test_subject_bound_post_cutover_receipt_accepts_only_full_live_closure():
    receipt = _evaluated()
    assert guard.findings_for(receipt, SHA) == []

    mutations = []
    x = copy.deepcopy(receipt); x["evidence"]["platform_runtime_identity"]["git_sha"] = "8" * 40; mutations.append(x)
    x = copy.deepcopy(receipt); x["evidence"]["platform_ready"]["decision_sor"]["platform_writes_required"] = True; mutations.append(x)
    x = copy.deepcopy(receipt); x["evidence"]["decision_ready"]["db_readiness"]["migrations_current"] = False; mutations.append(x)
    x = copy.deepcopy(receipt); x["evidence"]["role_certification"]["role_separation_confirmed"] = False; mutations.append(x)
    x = copy.deepcopy(receipt); x["evidence"]["platform_privilege_check"]["after"]["decision_record"]["UPDATE"] = True; mutations.append(x)
    x = copy.deepcopy(receipt); x["claims"]["historical_zero_platform_writes_measured"] = True; mutations.append(x)
    for broken in mutations:
        assert guard.findings_for(broken, SHA), broken


def test_collector_rejects_runtime_demotion_or_effective_privilege_drift():
    p = _platform_ready()
    p["decision_sor"]["effective_mode"] = "platform_sor"
    findings, _ = collector.evaluate_evidence(
        subject_sha=SHA,
        decision_identity=_identity("decision-service"),
        platform_identity=_identity("sahool-platform"),
        decision_ready=_ready(),
        decision_cutover=_cutover(),
        platform_ready=p,
        role_certification=_role(),
        privilege_check=_privilege(),
    )
    assert "platform_runtime_not_effectively_demoted" in findings

    priv = _privilege()
    priv["after"]["recommendation_outcomes"]["INSERT"] = True
    findings, _ = collector.evaluate_evidence(
        subject_sha=SHA,
        decision_identity=_identity("decision-service"),
        platform_identity=_identity("sahool-platform"),
        decision_ready=_ready(),
        decision_cutover=_cutover(),
        platform_ready=_platform_ready(),
        role_certification=_role(),
        privilege_check=priv,
    )
    assert "recommendation_outcomes:INSERT:effective_write_not_denied" in findings


def test_collector_is_read_only_and_uses_canonical_live_tools():
    src = (ROOT / "scripts/staging/decision_sor_live_closure_collector.py").read_text(encoding="utf-8")
    assert '"--check"' in src
    assert '"--revoke"' not in src
    assert '"--grant"' not in src
    assert "decision_sor_role_certify.py" in src
    assert "platform_sor_revoke.py" in src
    assert "/runtime-identity" in src
    assert "/v1/cutover/readiness" in src


def test_platform_readyz_exposes_mutable_mode_without_polluting_immutable_identity():
    src = (ROOT / "services/sahool-platform/api/routers/platform_health.py").read_text(encoding="utf-8")
    identity_body = src[src.index("def runtime_evidence_identity"):src.index("@router.get(\"/healthz\")")]
    ready_body = src[src.index("async def readyz") :]
    assert "get_platform_decision_sor_mode" not in identity_body
    assert "get_platform_decision_sor_mode" in ready_body
    assert 'body["decision_sor"]' in ready_body


def test_collector_rejects_platform_writes_required_true_even_if_other_mode_fields_look_closed():
    p = _platform_ready()
    p["decision_sor"]["platform_writes_required"] = True
    findings, _ = collector.evaluate_evidence(
        subject_sha=SHA,
        decision_identity=_identity("decision-service"),
        platform_identity=_identity("sahool-platform"),
        decision_ready=_ready(),
        decision_cutover=_cutover(),
        platform_ready=p,
        role_certification=_role(),
        privilege_check=_privilege(),
    )
    assert "platform_runtime_not_effectively_demoted" in findings
