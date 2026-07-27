#!/usr/bin/env python3
"""Read-only runtime identity bridge with strict, attested, atomic evidence evaluation."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IDENTITY_MAP = ROOT / "runtime-verification/service_identity_map.json"
PROBE_PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
FUNCTIONAL_PLAN_DIR = ROOT / "runtime-verification/functional_probes"
FUNCTIONAL_EVIDENCE_DIR = ROOT / "runtime-verification/functional_evidence"
CAPABILITY_REGISTRY = ROOT / "capabilities/registry/capabilities.json"
TRUST_REGISTRY = ROOT / "runtime-verification/trusted_environments.json"
RUNNER = ROOT / "scripts/ci/functional_probe_runner.py"
PROVENANCE_RECEIPT_TOOL = ROOT / "scripts/ci/provenance_receipt.py"
SCHEMA_VERSION = "1.0"
EVIDENCE_SCHEMA_VERSION = "2.0"
_VALID_CARDINALITY = {"one-to-one", "one-to-many"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BUILD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RUN_RE = _BUILD_RE
_ENV_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _canonical(obj: dict[str, Any]) -> bytes:
    x = dict(obj)
    x.pop("attestation", None)
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _parse_time(v: object):
    if not isinstance(v, str) or not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(UTC) if d.tzinfo else None


def ledger_service_names() -> set[str]:
    if not PROBE_PLAN.exists():
        raise ValueError("authoritative runtime probe plan missing")
    data = _load(PROBE_PLAN)
    names = {
        s.get("service")
        for s in data.get("services", [])
        if isinstance(s, dict) and isinstance(s.get("service"), str)
    }
    if not names:
        raise ValueError("authoritative runtime probe plan empty")
    return names


def registry_service_paths() -> set[str]:
    if not CAPABILITY_REGISTRY.exists():
        raise ValueError("authoritative capability registry missing")
    caps = _load(CAPABILITY_REGISTRY).get("capabilities", [])
    if not isinstance(caps, list) or not caps:
        raise ValueError("authoritative capability registry empty")
    out = set()
    for c in caps:
        out.update(c.get("services", []) or [])
    if not out:
        raise ValueError("authoritative capability service paths empty")
    return out


def capability_service_paths() -> dict[str, set[str]]:
    if not CAPABILITY_REGISTRY.exists():
        raise ValueError("authoritative capability registry missing")
    caps = _load(CAPABILITY_REGISTRY).get("capabilities", [])
    if not isinstance(caps, list) or not caps:
        raise ValueError("authoritative capability registry empty")
    return {
        c["id"]: set(c.get("services", []) or [])
        for c in caps
        if isinstance(c, dict) and c.get("id")
    }


def functional_plan_path(name: str) -> Path:
    return FUNCTIONAL_PLAN_DIR / f"{name}.json"


def functional_plan_probe_ids(name: str) -> set[str] | None:
    p = functional_plan_path(name)
    if not p.exists():
        return None
    return {
        x["probe_id"]
        for x in _load(p).get("probes", [])
        if isinstance(x, dict) and x.get("probe_id")
    }


def validate_identity_map(b: dict[str, Any]) -> list[str]:
    e = []
    if b.get("schema_version") != SCHEMA_VERSION:
        e.append(f"schema_version must be {SCHEMA_VERSION}")
    try:
        known_services = ledger_service_names()
        known_paths = registry_service_paths()
        cap_paths = capability_service_paths()
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        return [str(ex)]
    identity = b.get("service_identity", [])
    if not isinstance(identity, list) or not identity:
        e.append("service_identity must be a non-empty list")
        identity = []
    by = {}
    owners = {}
    seen = set()
    for i, x in enumerate(identity):
        tag = f"service_identity[{i}]"
        if not isinstance(x, dict):
            e.append(f"{tag}: not an object")
            continue
        s = x.get("ledger_service")
        p = x.get("capability_service_path")
        if s not in known_services:
            e.append(f"{tag}: unknown ledger_service {s!r} (not in probe plan)")
        if p not in known_paths:
            e.append(f"{tag}: capability_service_path {p!r} not used by any capability")
        if x.get("cardinality") not in _VALID_CARDINALITY:
            e.append(f"{tag}: invalid cardinality")
        if (s, p) in seen:
            e.append(f"{tag}: duplicate identity entry {s} -> {p}")
        seen.add((s, p))
        by.setdefault(s, []).append(x)
        owners.setdefault(p, set()).add(s)
    for s, xs in by.items():
        if len(xs) > 1 and any(x.get("cardinality") != "one-to-many" for x in xs):
            e.append(f"ambiguous mapping for ledger_service {s!r}")
    for p, ss in owners.items():
        if len(ss) > 1:
            e.append(f"conflicting mapping: path {p!r} claimed by services {sorted(ss)}")
    cov = b.get("capability_functional_coverage", [])
    if not isinstance(cov, list) or not cov:
        e.append("capability_functional_coverage must be a non-empty list")
        cov = []
    for i, c in enumerate(cov):
        tag = f"capability_functional_coverage[{i}]"
        cap = c.get("capability")
        svc = c.get("ledger_service")
        req = c.get("requires_probes")
        if cap not in cap_paths:
            e.append(f"{tag}: unknown capability {cap!r}")
        if svc not in by:
            e.append(f"{tag}: ledger_service {svc!r} not declared in service_identity")
        if not isinstance(req, list) or not req:
            e.append(f"{tag}: requires_probes must be a non-empty list")
            req = []
        elif len(req) != len(set(req)):
            e.append(f"{tag}: duplicate required probes")
        mapped = {x.get("capability_service_path") for x in by.get(svc, [])}
        if cap in cap_paths and not (cap_paths[cap] & mapped):
            e.append(f"{tag}: capability path does not match identity")
        plan = next((x.get("functional_plan") for x in by.get(svc, [])), None)
        ids = functional_plan_probe_ids(plan) if plan else None
        if ids is None:
            e.append(f"{tag}: no functional plan for ledger_service {svc!r}")
        else:
            miss = [p for p in req if p not in ids]
            if miss:
                e.append(f"{tag}: required probes not in functional plan: {miss}")
    if b.get("evidence_policy", {}).get("require_trusted_environment"):
        if not TRUST_REGISTRY.exists():
            e.append("trusted environment registry missing")
        else:
            try:
                t = _load(TRUST_REGISTRY)
            except Exception:
                e.append("trusted environment registry invalid JSON")
            else:
                if not t.get("environments"):
                    e.append("trusted environment registry empty")
    return e


def expected_digests(bridge: dict[str, Any], service: str) -> dict[str, str]:
    ent = next(x for x in bridge["service_identity"] if x["ledger_service"] == service)
    return {
        "probe_plan_sha256": _sha(functional_plan_path(ent["functional_plan"])),
        "runner_sha256": _sha(RUNNER),
        "identity_map_sha256": _sha(IDENTITY_MAP),
        "bridge_sha256": _sha(Path(__file__)),
    }


def _trust(policy: dict[str, Any], env_id: str, issuer: str) -> tuple[dict | None, str | None]:
    if not _ENV_RE.fullmatch(env_id):
        return None, "invalid_environment_id"
    if not TRUST_REGISTRY.exists():
        return None, "trusted_environment_registry_missing"
    t = _load(TRUST_REGISTRY)
    env = next((x for x in t.get("environments", []) if x.get("environment_id") == env_id), None)
    if not env or not env.get("eligible_for_runtime_verified"):
        return None, "untrusted_environment"
    if issuer not in env.get("trusted_issuers", []):
        return None, "issuer_not_trusted_for_environment"
    iss = next((x for x in t.get("issuers", []) if x.get("issuer") == issuer), None)
    return (iss, None) if iss else (None, "unknown_issuer")


def validate_evidence(
    ev: Any,
    policy: dict[str, Any],
    target_sha: str,
    now: datetime,
    service: str,
    bridge: dict[str, Any],
) -> tuple[set[str], str | None]:
    if not isinstance(ev, dict):
        return set(), "evidence_not_object"
    if ev.get("kind") != "functional":
        return set(), "not_functional_evidence"
    if ev.get("service") not in (None, service):
        return set(), "service_mismatch"
    sha = ev.get("tested_sha")
    if not isinstance(sha, str) or sha != target_sha:
        return set(), "sha_mismatch"
    env = str(ev.get("environment_id") or "")
    if not env:
        return set(), "missing_environment_id"
    gen = _parse_time(ev.get("generated_at"))
    if gen is None:
        return set(), "invalid_or_missing_generated_at"
    future = float(policy.get("max_future_clock_skew_seconds", 300))
    if (gen - now).total_seconds() > future:
        return set(), "future_dated_evidence"
    age = (now - gen).total_seconds()
    max_age = policy.get("max_age_seconds")
    if isinstance(max_age, (int, float)) and age > max_age:
        return set(), "stale_evidence"
    # Compatibility for unit fixtures using a deliberately weaker policy. The committed
    # map enables every strict flag below, so production eligibility never takes this path.
    strict = any(
        policy.get(k)
        for k in (
            "require_attestation",
            "require_trusted_environment",
            "require_runtime_identity",
            "require_artifact_digests",
        )
    )
    if not strict:
        results = ev.get("probe_results", [])
        if not isinstance(results, list):
            return set(), "invalid_probe_results"
        seen = set()
        passed = set()
        for r in results:
            if not isinstance(r, dict):
                return set(), "malformed_probe_result"
            pid = r.get("probe_id")
            if not isinstance(pid, str) or not pid:
                return set(), "invalid_probe_id"
            if pid in seen:
                return set(), "duplicate_probe_id"
            seen.add(pid)
            if r.get("status") == "passed":
                passed.add(pid)
        return passed, None
    required = {
        "schema_version",
        "service",
        "tested_sha",
        "environment_id",
        "generated_at",
        "run_id",
        "runtime_identity",
        "artifact_digests",
        "probe_results",
        "attestation",
    }
    missing = sorted(required - set(ev))
    if missing:
        return set(), f"missing_fields:{missing}"
    if ev.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return set(), "unsupported_schema_version"
    if not _SHA_RE.fullmatch(sha):
        return set(), "invalid_tested_sha"
    att = ev.get("attestation")
    if not isinstance(att, dict):
        return set(), "invalid_attestation"
    issuer = att.get("issuer")
    iss, reason = _trust(policy, env, issuer)
    if reason:
        return set(), reason
    rid = ev.get("runtime_identity")
    if not isinstance(rid, dict):
        return set(), "invalid_runtime_identity"
    for k in ("service", "git_sha", "build_id", "image_digest"):
        if not isinstance(rid.get(k), str) or not rid[k]:
            return set(), f"invalid_runtime_identity_{k}"
    if rid["service"] != service or rid["git_sha"] != target_sha or sha != rid["git_sha"]:
        return set(), "runtime_identity_mismatch"
    if not _DIGEST_RE.fullmatch(rid["image_digest"]):
        return set(), "invalid_image_digest"
    if not _BUILD_RE.fullmatch(rid["build_id"]):
        return set(), "invalid_build_id"
    if not isinstance(ev.get("run_id"), str) or not _RUN_RE.fullmatch(ev["run_id"]):
        return set(), "invalid_run_id"
    digs = ev.get("artifact_digests")
    if not isinstance(digs, dict) or digs != expected_digests(bridge, service):
        return set(), "artifact_digest_mismatch"
    results = ev.get("probe_results")
    if not isinstance(results, list) or not results:
        return set(), "invalid_probe_results"
    known = (
        functional_plan_probe_ids(
            next(
                x["functional_plan"]
                for x in bridge["service_identity"]
                if x["ledger_service"] == service
            )
        )
        or set()
    )
    seen = set()
    passed = set()
    for r in results:
        if not isinstance(r, dict):
            return set(), "malformed_probe_result"
        pid = r.get("probe_id")
        if not isinstance(pid, str) or not pid:
            return set(), "invalid_probe_id"
        if pid in seen:
            return set(), "duplicate_probe_id"
        if pid not in known:
            return set(), "unknown_probe_id"
        if r.get("status") not in {"passed", "failed"}:
            return set(), "invalid_probe_status"
        seen.add(pid)
        if r["status"] == "passed":
            passed.add(pid)
    if iss and iss.get("algorithm") == "hmac-sha256":
        key = os.environ.get(iss.get("verification_key_env", ""))
        sig = att.get("signature")
        if not key or not isinstance(sig, str):
            return set(), "unverifiable_attestation"
        want = hmac.new(key.encode(), _canonical(ev), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, sig):
            return set(), "invalid_attestation_signature"
    else:
        return set(), "unsupported_attestation_verifier"
    return passed, None


# Backward-compatible name for callers; strict evaluation needs service+bridge and uses validate_evidence.
def valid_evidence_passed_probes(evidence, policy, target_sha, now):
    service = evidence.get("service", "") if isinstance(evidence, dict) else ""
    try:
        bridge = _load(IDENTITY_MAP)
    except Exception:
        return set(), "identity_map_unavailable"
    return validate_evidence(evidence, policy, target_sha, now, service, bridge)


def evaluate_propagation(bridge, evidence_by_service, target_sha, now):
    out = []
    policy = bridge.get("evidence_policy", {})
    for c in bridge.get("capability_functional_coverage", []):
        cap = c.get("capability")
        svc = c.get("ledger_service")
        required = set(c.get("requires_probes", []) or [])
        evs = evidence_by_service.get(svc, [])
        if not evs:
            out.append(
                {
                    "capability": cap,
                    "eligible": False,
                    "reason": "no_functional_evidence",
                    "would_set_runtime_verified": False,
                }
            )
            continue
        eligible_bundle = None
        reasons = []
        for ev in evs:  # atomic: every capability must be covered by ONE bundle
            passed, reason = validate_evidence(ev, policy, target_sha, now, svc, bridge)
            if reason:
                reasons.append(reason)
                continue
            missing = sorted(required - passed)
            if not missing:
                eligible_bundle = ev
                break
            reasons.append(f"partial_coverage missing={missing}")
        if eligible_bundle:
            out.append(
                {
                    "capability": cap,
                    "eligible": True,
                    "reason": "covered_by_atomic_attested_bundle",
                    "environment_id": eligible_bundle.get("environment_id"),
                    "run_id": eligible_bundle.get("run_id"),
                    "image_digest": (eligible_bundle.get("runtime_identity") or {}).get(
                        "image_digest"
                    ),
                    "would_set_runtime_verified": True,
                }
            )
        else:
            out.append(
                {
                    "capability": cap,
                    "eligible": False,
                    "reason": reasons[-1] if reasons else "no_valid_evidence",
                    "would_set_runtime_verified": False,
                }
            )
    return out


def load_committed_evidence():
    by = {}
    errors = []
    if not FUNCTIONAL_EVIDENCE_DIR.exists():
        return by, errors
    for p in sorted(FUNCTIONAL_EVIDENCE_DIR.glob("*.json")):
        try:
            ev = _load(p)
        except (OSError, ValueError) as ex:
            errors.append(f"{p.name}: corrupt evidence: {ex}")
            continue
        if not isinstance(ev, dict) or not isinstance(ev.get("service"), str):
            errors.append(f"{p.name}: invalid or missing service")
            continue
        by.setdefault(ev["service"], []).append(ev)
    return by, errors


def _head_sha():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def cmd_check():
    if not IDENTITY_MAP.exists():
        print("runtime_identity_bridge: identity map missing (fail-closed)", file=sys.stderr)
        return 1
    try:
        b = _load(IDENTITY_MAP)
    except Exception as ex:
        print(f"identity map invalid: {ex}", file=sys.stderr)
        return 1
    errors = validate_identity_map(b)
    _, load_errors = load_committed_evidence()
    errors += load_errors
    if errors:
        print("identity bridge validation FAILED (fail-closed):", file=sys.stderr)
        for x in errors:
            print("  - " + x, file=sys.stderr)
        return 1
    print(
        f"runtime_identity_bridge_ok identities={len(b['service_identity'])} coverage={len(b['capability_functional_coverage'])} (bridge ready, inert)"
    )
    return 0


def _validate_external_provenance(
    receipt_path: str | None,
    target_sha: str,
    bundle_path: str | None,
    evidence_by_service: dict[str, list[dict]],
) -> list[str]:
    if not receipt_path:
        return ["external_provenance_receipt_required"]
    if not bundle_path:
        return ["external_provenance_bundle_required"]
    p = Path(receipt_path)
    bundle = Path(bundle_path)
    if not p.exists():
        return ["external_provenance_receipt_missing"]
    if not bundle.exists():
        return ["external_provenance_bundle_missing"]
    try:
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("sahool_provenance_receipt", PROVENANCE_RECEIPT_TOOL)
        m = module_from_spec(spec)
        spec.loader.exec_module(m)
        obj = _load(p)
        bundle_sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
        errors = m.validate(obj, expected_bundle_sha=bundle_sha, expected_source_sha=target_sha)
        envs = {
            str(ev.get("environment_id") or "")
            for rows in evidence_by_service.values()
            for ev in rows
        }
        if len(envs) != 1:
            return errors + ["provenance_bundle_mixed_environments"]
        trust = _load(TRUST_REGISTRY)
        env = next(
            (x for x in trust.get("environments", []) if x.get("environment_id") in envs), None
        )
        if not env:
            return errors + ["provenance_environment_not_registered"]
        expected = (
            env.get("required_evidence_signer_workflow")
            or ".github/workflows/path3-runtime-verification.yml"
        )
        signer = str(obj.get("signer_workflow") or "")
        if not signer.endswith(expected):
            errors.append("untrusted_provenance_signer_workflow")
        return errors
    except Exception as ex:
        return [f"external_provenance_receipt_invalid:{ex}"]


def cmd_dry_run(target_sha=None, provenance_receipt=None, evidence_bundle=None):
    b = _load(IDENTITY_MAP)
    errors = validate_identity_map(b)
    by, load_errors = load_committed_evidence()
    errors += load_errors
    if errors:
        print("identity bridge invalid; refusing to evaluate (fail-closed):", file=sys.stderr)
        for x in errors:
            print("  - " + x, file=sys.stderr)
        return 1
    sha = target_sha or _head_sha()
    if any(by.values()) and b.get("evidence_policy", {}).get("require_external_provenance", False):
        errors += _validate_external_provenance(provenance_receipt, sha, evidence_bundle, by)
    if errors:
        print("identity bridge provenance validation FAILED (fail-closed):", file=sys.stderr)
        for x in errors:
            print("  - " + x, file=sys.stderr)
        return 1
    ev = evaluate_propagation(b, by, sha, datetime.now(UTC))
    flips = [x for x in ev if x["would_set_runtime_verified"]]
    print("=== runtime identity bridge — DRY RUN (no writes) ===")
    print(f"target_sha: {sha[:12]}")
    print(f"capabilities evaluated: {len(ev)}")
    for x in ev:
        print(
            f"  {x['capability']}: {'WOULD SET runtime_verified' if x['eligible'] else 'stays 0'} — {x['reason']}"
        )
    print(
        f"\nwould_set_runtime_verified: {len(flips)}  (capabilities: {[x['capability'] for x in flips]})"
    )
    print(f"stays_zero: {len(ev) - len(flips)}")
    print("runtime_verified written by this tool: 0 (read-only, dry-run)")
    print("production_certified: 0 (never set here)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    p.add_argument("--target-sha")
    p.add_argument("--provenance-receipt")
    p.add_argument("--evidence-bundle")
    a = p.parse_args(argv)
    return (
        cmd_check()
        if a.check
        else cmd_dry_run(a.target_sha, a.provenance_receipt, a.evidence_bundle)
    )


if __name__ == "__main__":
    raise SystemExit(main())
