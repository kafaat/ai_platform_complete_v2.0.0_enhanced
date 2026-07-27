from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "scripts/ci/runtime_verification_apply.py"
s = importlib.util.spec_from_file_location("rv_apply", P)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def candidate(regsha="a" * 64, target="a" * 40):
    now = datetime.now(UTC)
    c = {
        "schema_version": "1.0",
        "kind": "runtime-verification-candidate",
        "target_sha": target,
        "environment_id": "staging-pg16",
        "evidence_bundle_sha256": "b" * 64,
        "provenance_receipt_sha256": "c" * 64,
        "registry_before_sha256": regsha,
        "identity_map_sha256": m.sha(m.IDENTITY_MAP),
        "bridge_sha256": m.sha(m.BRIDGE),
        "trusted_environments_sha256": m.sha(m.TRUST),
        "probe_plan_aggregate_sha256": m.probe_plan_sha(),
        "apply_tool_sha256": m.sha(m.APPLY_TOOL),
        "promotion_workflow_sha256": m.sha(m.PROMOTION_WORKFLOW),
        "path3_workflow_sha256": m.sha(m.PATH3_WORKFLOW),
        "capabilities": ["WX-004"],
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "requested_transition": "runtime_verified_false_to_true",
        "production_certified_must_remain_false": True,
    }
    c["candidate_id"] = m.digest_obj(c)
    return c


def approval(c):
    return {
        "schema_version": "1.0",
        "kind": "runtime-verification-approval",
        "decision": "approved",
        "candidate_id": c["candidate_id"],
        "candidate_sha256": m.digest_obj(c),
        "target_sha": c["target_sha"],
        "environment_id": c["environment_id"],
        "approval_environment": "runtime-verification-approval",
        "approval_run_id": "123-1",
        "approval_actor": "reviewer",
        "approved_at": datetime.now(UTC).isoformat(),
        "production_certified_authorized": False,
    }


def artifacts(tmp_path):
    ca = tmp_path / "candidate-attestation.json"
    aa = tmp_path / "approval-attestation.json"
    vr = tmp_path / "verification.json"
    ca.write_text('{"verified":true}')
    aa.write_text('{"verified":true}')
    vr.write_text('{"verified":true}')
    return ca, aa, vr


def invoke_apply(tmp_path, c, reg, status="analytical_partial", head=None):
    ri = tmp_path / "in.json"
    ri.write_text(json.dumps(reg))
    c["registry_before_sha256"] = m.sha(ri)
    c["candidate_id"] = m.digest_obj({k: v for k, v in c.items() if k != "candidate_id"})
    a = approval(c)
    cp = tmp_path / "c.json"
    ap = tmp_path / "a.json"
    cp.write_text(json.dumps(c))
    ap.write_text(json.dumps(a))
    ca, aa, vr = artifacts(tmp_path)
    m.LEDGER_DIR = tmp_path / "ledger"
    m.LEDGER_DIR.mkdir(exist_ok=True)
    ro = tmp_path / "out.json"
    rr = tmp_path / "receipt.json"
    r = m.apply(cp, ap, ri, ro, rr, "RUNTIME_VERIFIED_ONLY", head or c["target_sha"], ca, aa, vr)
    return r, json.loads(ro.read_text()), json.loads(rr.read_text())


def test_candidate_valid():
    assert m.validate_candidate(candidate()) == []


def test_candidate_expired_rejected():
    c = candidate()
    c["created_at"] = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    c["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    tmp = dict(c)
    tmp.pop("candidate_id")
    c["candidate_id"] = m.digest_obj(tmp)
    assert "candidate_expired" in m.validate_candidate(c)


def test_candidate_tamper_rejected():
    c = candidate()
    c["capabilities"].append("WX-006")
    assert "candidate_id_mismatch" in m.validate_candidate(c)


def test_approval_candidate_mismatch():
    c = candidate()
    a = approval(c)
    a["candidate_id"] = "x"
    assert "approval_candidate_mismatch" in m.validate_approval(a, c)


def test_approval_cannot_authorize_production():
    c = candidate()
    a = approval(c)
    a["production_certified_authorized"] = True
    assert "approval_must_forbid_production_certification" in m.validate_approval(a, c)


def test_apply_runtime_only_preserves_status_and_provenance(tmp_path, monkeypatch):
    reg = {
        "schema_version": "1",
        "capabilities": [
            {
                "id": "WX-004",
                "status": "analytical_partial",
                "runtime_verified": False,
                "production_certified": False,
                "runtime": {"receipts": []},
            }
        ],
    }
    c = candidate()
    r, out, receipt = invoke_apply(tmp_path, c, reg)
    row = out["capabilities"][0]
    assert row["runtime_verified"] is True
    assert row["production_certified"] is False
    assert row["status"] == "analytical_partial"
    assert r["production_certified_changes"] == 0 and r["status_taxonomy_changes"] == 0
    assert (
        receipt["provenance"]["candidate_attestation_sha256"]
        and row["runtime"]["receipts"][0]["provenance"]["approval_attestation_sha256"]
    )


def test_apply_registry_drift_rejected(tmp_path):
    reg = {
        "capabilities": [{"id": "WX-004", "runtime_verified": False, "production_certified": False}]
    }
    ri = tmp_path / "in"
    ri.write_text(json.dumps(reg))
    c = candidate("a" * 64)
    a = approval(c)
    cp = tmp_path / "c"
    ap = tmp_path / "a"
    cp.write_text(json.dumps(c))
    ap.write_text(json.dumps(a))
    ca, aa, vr = artifacts(tmp_path)
    with pytest.raises(ValueError, match="registry changed"):
        m.apply(
            cp,
            ap,
            ri,
            tmp_path / "o",
            tmp_path / "r",
            "RUNTIME_VERIFIED_ONLY",
            c["target_sha"],
            ca,
            aa,
            vr,
        )


def test_apply_requires_explicit_confirmation(tmp_path):
    c = candidate()
    a = approval(c)
    cp = tmp_path / "c"
    ap = tmp_path / "a"
    ri = tmp_path / "i"
    cp.write_text(json.dumps(c))
    ap.write_text(json.dumps(a))
    ri.write_text("{}")
    ca, aa, vr = artifacts(tmp_path)
    with pytest.raises(ValueError, match="explicit"):
        m.apply(cp, ap, ri, tmp_path / "o", tmp_path / "r", "NO", c["target_sha"], ca, aa, vr)


def test_apply_rejects_unchanged_registry_but_changed_head(tmp_path):
    reg = {
        "capabilities": [
            {
                "id": "WX-004",
                "status": "runtime_unverified",
                "runtime_verified": False,
                "production_certified": False,
            }
        ]
    }
    ri = tmp_path / "in"
    ri.write_text(json.dumps(reg))
    c = candidate(m.sha(ri), "a" * 40)
    a = approval(c)
    cp = tmp_path / "c"
    ap = tmp_path / "a"
    cp.write_text(json.dumps(c))
    ap.write_text(json.dumps(a))
    ca, aa, vr = artifacts(tmp_path)
    with pytest.raises(ValueError, match="does not equal tested target SHA"):
        m.apply(
            cp,
            ap,
            ri,
            tmp_path / "o",
            tmp_path / "r",
            "RUNTIME_VERIFIED_ONLY",
            "b" * 40,
            ca,
            aa,
            vr,
        )


def test_apply_rejects_policy_digest_change(tmp_path, monkeypatch):
    reg = {
        "capabilities": [
            {
                "id": "WX-004",
                "status": "runtime_unverified",
                "runtime_verified": False,
                "production_certified": False,
            }
        ]
    }
    ri = tmp_path / "in"
    ri.write_text(json.dumps(reg))
    c = candidate(m.sha(ri))
    c["bridge_sha256"] = "f" * 64
    c["candidate_id"] = m.digest_obj({k: v for k, v in c.items() if k != "candidate_id"})
    a = approval(c)
    cp = tmp_path / "c"
    ap = tmp_path / "a"
    cp.write_text(json.dumps(c))
    ap.write_text(json.dumps(a))
    ca, aa, vr = artifacts(tmp_path)
    with pytest.raises(ValueError, match="bridge_sha256 changed"):
        m.apply(
            cp,
            ap,
            ri,
            tmp_path / "o",
            tmp_path / "r",
            "RUNTIME_VERIFIED_ONLY",
            c["target_sha"],
            ca,
            aa,
            vr,
        )


def test_apply_requires_attestation_chain(tmp_path):
    reg = {
        "capabilities": [
            {
                "id": "WX-004",
                "status": "runtime_unverified",
                "runtime_verified": False,
                "production_certified": False,
            }
        ]
    }
    ri = tmp_path / "in"
    ri.write_text(json.dumps(reg))
    c = candidate(m.sha(ri))
    a = approval(c)
    cp = tmp_path / "c"
    ap = tmp_path / "a"
    cp.write_text(json.dumps(c))
    ap.write_text(json.dumps(a))
    with pytest.raises(ValueError, match="candidate attestation missing"):
        m.apply(
            cp,
            ap,
            ri,
            tmp_path / "o",
            tmp_path / "r",
            "RUNTIME_VERIFIED_ONLY",
            c["target_sha"],
            tmp_path / "missing",
            tmp_path / "missing2",
        )
