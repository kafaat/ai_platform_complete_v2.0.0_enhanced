#!/usr/bin/env python3
"""Governed Step-4 runtime-verification promotion.

This tool never certifies production and never pushes to git.  It can prepare an
immutable candidate or apply an already approved candidate to a registry file.
The default and CI check modes are read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
IDENTITY_MAP = ROOT / "runtime-verification/service_identity_map.json"
BRIDGE = ROOT / "scripts/ci/runtime_identity_bridge.py"
TRUST = ROOT / "runtime-verification/trusted_environments.json"
PROBE_DIR = ROOT / "runtime-verification/functional_probes"
APPLY_TOOL = ROOT / "scripts/ci/runtime_verification_apply.py"
PROMOTION_WORKFLOW = ROOT / ".github/workflows/runtime-verification-promotion.yml"
PATH3_WORKFLOW = ROOT / ".github/workflows/path3-runtime-verification.yml"
LEDGER_DIR = ROOT / "runtime-verification/apply-ledger"
SCHEMA = "1.0"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def canonical(o: dict[str, Any]) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_obj(o: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(o)).hexdigest()


def aggregate_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: str(x.relative_to(ROOT))):
        rel = str(p.relative_to(ROOT)).encode()
        data = p.read_bytes()
        h.update(len(rel).to_bytes(4, "big"))
        h.update(rel)
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


def probe_plan_sha() -> str:
    return aggregate_files(list(PROBE_DIR.glob("*.json")))


def git_head() -> str:
    import subprocess

    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def parse_time(v: object) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(UTC) if d.tzinfo else None


def _bridge_module():
    from importlib.util import module_from_spec, spec_from_file_location

    s = spec_from_file_location("runtime_identity_bridge", BRIDGE)
    m = module_from_spec(s)
    s.loader.exec_module(m)
    return m


def evaluate(
    target_sha: str, receipt: Path, bundle: Path
) -> tuple[list[dict], dict[str, list[dict]]]:
    m = _bridge_module()
    b = load(IDENTITY_MAP)
    errors = m.validate_identity_map(b)
    by, le = m.load_committed_evidence()
    errors += le
    if not any(by.values()):
        errors.append("no_functional_evidence")
    errors += m._validate_external_provenance(str(receipt), target_sha, str(bundle), by)
    if errors:
        raise ValueError(";".join(errors))
    rows = m.evaluate_propagation(b, by, target_sha, datetime.now(UTC))
    return rows, by


def prepare(target_sha: str, receipt: Path, bundle: Path, out: Path, ttl_minutes: int = 60) -> dict:
    if not SHA40.fullmatch(target_sha):
        raise ValueError("target_sha must be full lowercase git SHA")
    rows, by = evaluate(target_sha, receipt, bundle)
    eligible = sorted(x["capability"] for x in rows if x.get("eligible"))
    if not eligible:
        raise ValueError("no capabilities eligible for promotion")
    envs = {str(ev.get("environment_id") or "") for xs in by.values() for ev in xs}
    if len(envs) != 1:
        raise ValueError("candidate evidence must use one environment")
    now = datetime.now(UTC)
    c = {
        "schema_version": SCHEMA,
        "kind": "runtime-verification-candidate",
        "target_sha": target_sha,
        "environment_id": next(iter(envs)),
        "evidence_bundle_sha256": sha(bundle),
        "provenance_receipt_sha256": sha(receipt),
        "registry_before_sha256": sha(REGISTRY),
        "identity_map_sha256": sha(IDENTITY_MAP),
        "bridge_sha256": sha(BRIDGE),
        "trusted_environments_sha256": sha(TRUST),
        "probe_plan_aggregate_sha256": probe_plan_sha(),
        "apply_tool_sha256": sha(APPLY_TOOL),
        "promotion_workflow_sha256": sha(PROMOTION_WORKFLOW),
        "path3_workflow_sha256": sha(PATH3_WORKFLOW),
        "capabilities": eligible,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        "requested_transition": "runtime_verified_false_to_true",
        "production_certified_must_remain_false": True,
    }
    c["candidate_id"] = digest_obj(c)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(c, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return c


def validate_candidate(c: Any, now: datetime | None = None) -> list[str]:
    e = []
    now = now or datetime.now(UTC)
    if not isinstance(c, dict):
        return ["candidate_not_object"]
    if c.get("schema_version") != SCHEMA:
        e.append("candidate_schema_version")
    if c.get("kind") != "runtime-verification-candidate":
        e.append("candidate_kind")
    if not SHA40.fullmatch(str(c.get("target_sha") or "")):
        e.append("candidate_target_sha")
    for k in (
        "evidence_bundle_sha256",
        "provenance_receipt_sha256",
        "registry_before_sha256",
        "identity_map_sha256",
        "bridge_sha256",
        "trusted_environments_sha256",
        "probe_plan_aggregate_sha256",
        "apply_tool_sha256",
        "promotion_workflow_sha256",
        "path3_workflow_sha256",
    ):
        if not HEX64.fullmatch(str(c.get(k) or "")):
            e.append("candidate_" + k)
    caps = c.get("capabilities")
    if (
        not isinstance(caps, list)
        or not caps
        or len(caps) != len(set(caps))
        or any(not isinstance(x, str) for x in caps)
    ):
        e.append("candidate_capabilities")
    exp = parse_time(c.get("expires_at"))
    created = parse_time(c.get("created_at"))
    if not created or not exp or exp <= created:
        e.append("candidate_time_window")
    elif now > exp:
        e.append("candidate_expired")
    if c.get("requested_transition") != "runtime_verified_false_to_true":
        e.append("candidate_transition")
    if c.get("production_certified_must_remain_false") is not True:
        e.append("candidate_production_guard")
    claimed = c.get("candidate_id")
    tmp = dict(c)
    tmp.pop("candidate_id", None)
    if claimed != digest_obj(tmp):
        e.append("candidate_id_mismatch")
    return e


def validate_approval(a: Any, c: dict) -> list[str]:
    e = []
    if not isinstance(a, dict):
        return ["approval_not_object"]
    if a.get("schema_version") != SCHEMA or a.get("kind") != "runtime-verification-approval":
        e.append("approval_contract")
    if a.get("decision") != "approved":
        e.append("approval_not_approved")
    if a.get("candidate_id") != c.get("candidate_id"):
        e.append("approval_candidate_mismatch")
    if a.get("candidate_sha256") != digest_obj(c):
        e.append("approval_candidate_digest_mismatch")
    if a.get("target_sha") != c.get("target_sha"):
        e.append("approval_target_sha_mismatch")
    if a.get("environment_id") != c.get("environment_id"):
        e.append("approval_environment_mismatch")
    if a.get("approval_environment") != "runtime-verification-approval":
        e.append("approval_environment_untrusted")
    if not str(a.get("approval_run_id") or ""):
        e.append("approval_run_id_missing")
    t = parse_time(a.get("approved_at"))
    if not t:
        e.append("approval_time_invalid")
    if a.get("production_certified_authorized") is not False:
        e.append("approval_must_forbid_production_certification")
    return e


def create_approval(candidate: Path, out: Path, run_id: str, actor: str) -> dict:
    c = load(candidate)
    e = validate_candidate(c)
    if e:
        raise ValueError(";".join(e))
    a = {
        "schema_version": SCHEMA,
        "kind": "runtime-verification-approval",
        "decision": "approved",
        "candidate_id": c["candidate_id"],
        "candidate_sha256": digest_obj(c),
        "target_sha": c["target_sha"],
        "environment_id": c["environment_id"],
        "approval_environment": "runtime-verification-approval",
        "approval_run_id": run_id,
        "approval_actor": actor,
        "approved_at": datetime.now(UTC).isoformat(),
        "production_certified_authorized": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(a, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return a


def _assert_policy_bindings(c: dict, current_head: str) -> None:
    if current_head != c["target_sha"]:
        raise ValueError(
            f"current HEAD {current_head} does not equal tested target SHA {c['target_sha']}"
        )
    checks = {
        "identity_map_sha256": sha(IDENTITY_MAP),
        "bridge_sha256": sha(BRIDGE),
        "trusted_environments_sha256": sha(TRUST),
        "probe_plan_aggregate_sha256": probe_plan_sha(),
        "apply_tool_sha256": sha(APPLY_TOOL),
        "promotion_workflow_sha256": sha(PROMOTION_WORKFLOW),
        "path3_workflow_sha256": sha(PATH3_WORKFLOW),
    }
    for key, actual in checks.items():
        if actual != c.get(key):
            raise ValueError(f"{key} changed since candidate evaluation")


def _attestation_chain(
    candidate_attestation: Path,
    approval_attestation: Path,
    verification_receipt: Path | None,
    c: dict,
    a: dict,
) -> dict:
    for p, label in (
        (candidate_attestation, "candidate attestation"),
        (approval_attestation, "approval attestation"),
    ):
        if not p.exists() or p.stat().st_size == 0:
            raise ValueError(label + " missing")
    chain = {
        "candidate_attestation_sha256": sha(candidate_attestation),
        "approval_attestation_sha256": sha(approval_attestation),
        "candidate_signer_workflow": ".github/workflows/path3-runtime-verification.yml",
        "approval_signer_workflow": ".github/workflows/runtime-verification-promotion.yml",
        "source_repository": os.environ.get("GITHUB_REPOSITORY", "unknown"),
        "source_sha": c["target_sha"],
        "source_ref": os.environ.get("GITHUB_REF", "unknown"),
        "candidate_run_id": os.environ.get("PATH3_RUN_ID", "unknown"),
        "approval_run_id": a["approval_run_id"],
        "promotion_run_id": os.environ.get("GITHUB_RUN_ID", "unknown"),
        "promotion_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "unknown"),
        "promotion_run_url": os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        + "/"
        + os.environ.get("GITHUB_REPOSITORY", "unknown")
        + "/actions/runs/"
        + os.environ.get("GITHUB_RUN_ID", "unknown"),
    }
    if verification_receipt:
        if not verification_receipt.exists() or verification_receipt.stat().st_size == 0:
            raise ValueError("verification receipt missing")
        chain["verification_receipt_sha256"] = sha(verification_receipt)
    return chain


def apply(
    candidate: Path,
    approval: Path,
    registry_in: Path,
    registry_out: Path,
    receipt_out: Path,
    confirm: str,
    current_head: str,
    candidate_attestation: Path,
    approval_attestation: Path,
    verification_receipt: Path | None = None,
) -> dict:
    if confirm != "RUNTIME_VERIFIED_ONLY":
        raise ValueError("explicit --confirm RUNTIME_VERIFIED_ONLY required")
    c = load(candidate)
    a = load(approval)
    e = validate_candidate(c) + validate_approval(a, c)
    if e:
        raise ValueError(";".join(e))
    _assert_policy_bindings(c, current_head)
    if sha(registry_in) != c["registry_before_sha256"]:
        raise ValueError("registry changed since candidate evaluation")
    provenance = _attestation_chain(
        candidate_attestation, approval_attestation, verification_receipt, c, a
    )
    data = load(registry_in)
    by = {x.get("id"): x for x in data.get("capabilities", []) if isinstance(x, dict)}
    unknown = [x for x in c["capabilities"] if x not in by]
    if unknown:
        raise ValueError("unknown capabilities:" + ",".join(unknown))
    application_id = hashlib.sha256(
        (c["candidate_id"] + ":" + a["approval_run_id"]).encode()
    ).hexdigest()
    ledger = LEDGER_DIR / f"{application_id}.json"
    if ledger.exists():
        raise ValueError("application replay detected")
    before_prod = {x: by[x].get("production_certified") for x in c["capabilities"]}
    before_status = {x: by[x].get("status") for x in c["capabilities"]}
    for cap in c["capabilities"]:
        row = by[cap]
        if row.get("production_certified") is not False:
            raise ValueError(f"{cap}: production_certified must already be false")
        if row.get("runtime_verified") is True:
            raise ValueError(f"{cap}: already runtime_verified")
        row["runtime_verified"] = True
        runtime = row.setdefault("runtime", {})
        receipts = runtime.setdefault("receipts", [])
        receipts.append(
            {
                "type": "attested-runtime-verification",
                "application_id": application_id,
                "candidate_id": c["candidate_id"],
                "target_sha": c["target_sha"],
                "environment_id": c["environment_id"],
                "evidence_bundle_sha256": c["evidence_bundle_sha256"],
                "approved_at": a["approved_at"],
                "approval_run_id": a["approval_run_id"],
                "provenance": provenance,
            }
        )
    if any(by[x].get("production_certified") != before_prod[x] for x in c["capabilities"]):
        raise ValueError("production certification mutation forbidden")
    if any(by[x].get("status") != before_status[x] for x in c["capabilities"]):
        raise ValueError("capability status taxonomy mutation forbidden")
    receipt = {
        "schema_version": SCHEMA,
        "kind": "runtime-verification-application",
        "application_id": application_id,
        "candidate_id": c["candidate_id"],
        "approval_run_id": a["approval_run_id"],
        "target_sha": c["target_sha"],
        "applied_to_head": current_head,
        "environment_id": c["environment_id"],
        "capabilities": c["capabilities"],
        "registry_before_sha256": sha(registry_in),
        "policy_bindings": {
            k: c[k]
            for k in (
                "identity_map_sha256",
                "bridge_sha256",
                "trusted_environments_sha256",
                "probe_plan_aggregate_sha256",
                "apply_tool_sha256",
                "promotion_workflow_sha256",
                "path3_workflow_sha256",
            )
        },
        "provenance": provenance,
        "applied_at": datetime.now(UTC).isoformat(),
        "runtime_verified_set_count": len(c["capabilities"]),
        "production_certified_changes": 0,
        "status_taxonomy_changes": 0,
        "write_scope": "pull-request-only",
    }
    registry_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(registry_out.parent)) as td:
        rp = Path(td) / "registry.json"
        ap = Path(td) / "receipt.json"
        rp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt["registry_after_sha256"] = sha(rp)
        ap.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(rp, registry_out)
        os.replace(ap, receipt_out)
    return receipt


def check() -> int:
    errors = []
    if not REGISTRY.exists():
        errors.append("capability registry missing")
    if not TRUST.exists():
        errors.append("trust registry missing")
    else:
        t = load(TRUST)
        env = next(
            (x for x in t.get("environments", []) if x.get("environment_id") == "staging-pg16"),
            None,
        )
        if (
            not env
            or env.get("required_promotion_workflow")
            != ".github/workflows/runtime-verification-promotion.yml"
        ):
            errors.append("promotion workflow not bound in trust registry")
        if not env or env.get("required_approval_environment") != "runtime-verification-approval":
            errors.append("approval environment not bound in trust registry")
        if not env or env.get("require_exact_target_sha_at_apply") is not True:
            errors.append("exact target SHA apply binding missing")
        if not env or env.get("require_policy_digest_revalidation") is not True:
            errors.append("policy digest revalidation missing")
        if not env or env.get("preserve_status_taxonomy") is not True:
            errors.append("status taxonomy preservation missing")
        if not env or env.get("require_repository_retained_attestation_chain") is not True:
            errors.append("repository attestation chain retention missing")
    if errors:
        print("runtime_verification_apply FAILED:")
        [print("  - " + x) for x in errors]
        return 1
    print("runtime_verification_apply_ok mode=governed-pr-only production_certification=forbidden")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    q = sub.add_parser("prepare")
    q.add_argument("--target-sha", required=True)
    q.add_argument("--provenance-receipt", required=True)
    q.add_argument("--evidence-bundle", required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--ttl-minutes", type=int, default=240)
    q = sub.add_parser("validate-candidate")
    q.add_argument("--candidate", required=True)
    q = sub.add_parser("create-approval")
    q.add_argument("--candidate", required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--run-id", required=True)
    q.add_argument("--actor", required=True)
    q = sub.add_parser("apply")
    q.add_argument("--candidate", required=True)
    q.add_argument("--approval", required=True)
    q.add_argument("--registry-in", default=str(REGISTRY))
    q.add_argument("--registry-out", required=True)
    q.add_argument("--receipt-out", required=True)
    q.add_argument("--confirm", required=True)
    q.add_argument("--current-head", required=True)
    q.add_argument("--candidate-attestation", required=True)
    q.add_argument("--approval-attestation", required=True)
    q.add_argument("--verification-receipt")
    a = p.parse_args(argv)
    try:
        if a.cmd == "check":
            return check()
        if a.cmd == "prepare":
            prepare(
                a.target_sha,
                Path(a.provenance_receipt),
                Path(a.evidence_bundle),
                Path(a.output),
                a.ttl_minutes,
            )
        elif a.cmd == "validate-candidate":
            e = validate_candidate(load(Path(a.candidate)))
            print("candidate_valid" if not e else "\n".join(e))
            return 1 if e else 0
        elif a.cmd == "create-approval":
            create_approval(Path(a.candidate), Path(a.output), a.run_id, a.actor)
        elif a.cmd == "apply":
            apply(
                Path(a.candidate),
                Path(a.approval),
                Path(a.registry_in),
                Path(a.registry_out),
                Path(a.receipt_out),
                a.confirm,
                a.current_head,
                Path(a.candidate_attestation),
                Path(a.approval_attestation),
                Path(a.verification_receipt) if a.verification_receipt else None,
            )
        return 0
    except Exception as ex:
        print(f"runtime_verification_apply: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
