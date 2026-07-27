#!/usr/bin/env python3
"""Runtime identity bridge — governance-only, evidence-gated, and inert by design.

Two independent registries describe the same services with different keys:
  * the runtime evidence ledger keys by NAME   ("weather-service")
  * the capability registry keys by PATH        ("services/weather-service/main.py")

Without an explicit, reviewed bridge a live-verified service can never be tied to
its capabilities, so runtime_verified could never move honestly. This tool supplies
that bridge — and nothing more. It is READ-ONLY: it never writes runtime_verified or
production_certified anywhere. Its whole job is to (a) validate the declared bridge
fail-closed, and (b) show, as a dry run, exactly which capabilities WOULD become
eligible if valid Step-3 functional evidence existed — and which stay zero, and why.

Hard rules (all fail-closed):
  * Identity is matched by EXPLICIT declared pairs only — never approximate name or
    substring matching.
  * Each ledger service maps one-to-one, or one-to-many only when every entry for it
    declares cardinality "one-to-many". Ambiguous or conflicting duplicates are rejected.
  * A capability becomes eligible only when VALID functional evidence covers THAT
    capability's declared required probes — not merely because a service "passed".
  * Evidence is valid only if it is kind=functional (liveness-only is rejected), its
    tested_sha matches the target SHA, it carries an environment_id, and it is not
    stale. Missing identity or missing/insufficient evidence => not eligible.
  * The existence of this bridge, by itself, changes nothing. Flipping runtime_verified
    remains a separate, reviewed step gated on this evaluation returning eligible caps.

The bridge is "ready" while every eligibility check honestly returns zero until real
Step-3 evidence is produced in a blessed environment (that evidence is gitignored and
never committed, so the repository cannot bake in a claim).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IDENTITY_MAP = ROOT / "runtime-verification" / "service_identity_map.json"
PROBE_PLAN = ROOT / "runtime-verification" / "generated" / "runtime_probe_plan.json"
FUNCTIONAL_PLAN_DIR = ROOT / "runtime-verification" / "functional_probes"
FUNCTIONAL_EVIDENCE_DIR = ROOT / "runtime-verification" / "functional_evidence"
CAPABILITY_REGISTRY = ROOT / "capabilities" / "registry" / "capabilities.json"
SCHEMA_VERSION = "1.0"
_VALID_CARDINALITY = {"one-to-one", "one-to-many"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ledger_service_names() -> set[str]:
    if not PROBE_PLAN.exists():
        return set()
    return {s["service"] for s in _load(PROBE_PLAN).get("services", [])}


def registry_service_paths() -> set[str]:
    if not CAPABILITY_REGISTRY.exists():
        return set()
    paths: set[str] = set()
    for cap in _load(CAPABILITY_REGISTRY).get("capabilities", []):
        paths.update(cap.get("services", []) or [])
    return paths


def capability_service_paths() -> dict[str, set[str]]:
    if not CAPABILITY_REGISTRY.exists():
        return {}
    return {
        cap["id"]: set(cap.get("services", []) or [])
        for cap in _load(CAPABILITY_REGISTRY).get("capabilities", [])
    }


def functional_plan_probe_ids(plan_name: str) -> set[str] | None:
    path = FUNCTIONAL_PLAN_DIR / f"{plan_name}.json"
    if not path.exists():
        return None
    return {p["probe_id"] for p in _load(path).get("probes", [])}


def validate_identity_map(bridge: dict[str, Any]) -> list[str]:
    """Fail-closed structural + referential validation of the bridge. No network,
    no evidence, no mutation. Returns human-readable errors (empty == valid)."""
    errors: list[str] = []
    if bridge.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    known_services = ledger_service_names()
    known_paths = registry_service_paths()
    cap_paths = capability_service_paths()

    identity = bridge.get("service_identity", [])
    if not isinstance(identity, list) or not identity:
        errors.append("service_identity must be a non-empty list")
        identity = []

    by_service: dict[str, list[dict]] = {}
    path_to_services: dict[str, set[str]] = {}
    seen_exact: set[tuple[str, str]] = set()
    for i, e in enumerate(identity):
        tag = f"service_identity[{i}]"
        svc, path = e.get("ledger_service"), e.get("capability_service_path")
        if not isinstance(svc, str) or not svc:
            errors.append(f"{tag}: missing ledger_service")
            continue
        if known_services and svc not in known_services:
            errors.append(f"{tag}: unknown ledger_service {svc!r} (not in probe plan)")
        if not isinstance(path, str) or not path:
            errors.append(f"{tag}: missing capability_service_path")
            continue
        if known_paths and path not in known_paths:
            errors.append(f"{tag}: capability_service_path {path!r} not used by any capability")
        if e.get("cardinality") not in _VALID_CARDINALITY:
            errors.append(f"{tag}: cardinality must be one of {sorted(_VALID_CARDINALITY)}")
        if (svc, path) in seen_exact:
            errors.append(f"{tag}: duplicate identity entry {svc} -> {path}")
        seen_exact.add((svc, path))
        by_service.setdefault(svc, []).append(e)
        path_to_services.setdefault(path, set()).add(svc)

    # Ambiguity: a service with multiple targets must declare one-to-many on every entry.
    for svc, entries in by_service.items():
        if len(entries) > 1 and any(e.get("cardinality") != "one-to-many" for e in entries):
            errors.append(
                f"ambiguous mapping for ledger_service {svc!r}: multiple targets "
                "without a consistent one-to-many declaration"
            )
    # Conflict: one path must not be owned by more than one ledger service.
    for path, svcs in path_to_services.items():
        if len(svcs) > 1:
            errors.append(f"conflicting mapping: path {path!r} claimed by services {sorted(svcs)}")

    coverage = bridge.get("capability_functional_coverage", [])
    if not isinstance(coverage, list) or not coverage:
        errors.append("capability_functional_coverage must be a non-empty list")
        coverage = []
    for i, c in enumerate(coverage):
        tag = f"capability_functional_coverage[{i}]"
        cap = c.get("capability")
        svc = c.get("ledger_service")
        req = c.get("requires_probes")
        if cap not in cap_paths:
            errors.append(f"{tag}: unknown capability {cap!r}")
        if svc not in by_service:
            errors.append(f"{tag}: ledger_service {svc!r} not declared in service_identity")
        if not isinstance(req, list) or not req:
            errors.append(
                f"{tag}: requires_probes must be a non-empty list "
                "(a coverage entry with no required probes is liveness-equivalent)"
            )
            req = []
        # identity consistency: the capability's registry paths must include the path
        # its declared ledger_service maps to.
        mapped_paths = {e["capability_service_path"] for e in by_service.get(svc, [])}
        if cap in cap_paths and not (cap_paths[cap] & mapped_paths):
            errors.append(
                f"{tag}: capability {cap} services {sorted(cap_paths[cap])} do not "
                f"include any mapped path {sorted(mapped_paths)}"
            )
        # required probes must exist in the service's functional plan.
        plan_name = next((e.get("functional_plan") for e in by_service.get(svc, [])), None)
        probe_ids = functional_plan_probe_ids(plan_name) if plan_name else None
        if probe_ids is None:
            errors.append(f"{tag}: no functional plan for ledger_service {svc!r}")
        else:
            missing = [p for p in req if p not in probe_ids]
            if missing:
                errors.append(f"{tag}: required probes not in functional plan: {missing}")
    return errors


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def valid_evidence_passed_probes(
    evidence: dict[str, Any], policy: dict[str, Any], target_sha: str, now: datetime
) -> tuple[set[str], str | None]:
    """Return (passed_probe_ids, rejection_reason). A non-None reason means the
    evidence is not usable; passed set is empty in that case."""
    if policy.get("require_kind") and evidence.get("kind") != policy["require_kind"]:
        return set(), f"not_{policy['require_kind']}_evidence (kind={evidence.get('kind')!r})"
    if policy.get("reject_liveness_only") and evidence.get("kind") in {"health", "liveness"}:
        return set(), "liveness_only_evidence_rejected"
    if policy.get("require_sha_match"):
        if not isinstance(evidence.get("tested_sha"), str) or evidence["tested_sha"] != target_sha:
            return set(), f"sha_mismatch (evidence={str(evidence.get('tested_sha'))[:12]!r})"
    if policy.get("require_environment") and not str(evidence.get("environment_id") or "").strip():
        return set(), "missing_environment_id"
    gen = _parse_time(evidence.get("generated_at"))
    if gen is None:
        return set(), "invalid_or_missing_generated_at"
    max_age = policy.get("max_age_seconds")
    if isinstance(max_age, (int, float)) and (now - gen).total_seconds() > max_age:
        return set(), "stale_evidence"
    passed = {
        r.get("probe_id")
        for r in evidence.get("probe_results", [])
        if isinstance(r, dict) and r.get("status") == "passed" and r.get("probe_id")
    }
    return passed, None


def evaluate_propagation(
    bridge: dict[str, Any],
    evidence_by_service: dict[str, list[dict[str, Any]]],
    target_sha: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Compute, without mutating anything, which capabilities WOULD be eligible for
    runtime_verified and which stay zero (with a reason). Never writes."""
    policy = bridge.get("evidence_policy", {})
    out: list[dict[str, Any]] = []
    for c in bridge.get("capability_functional_coverage", []):
        cap = c.get("capability")
        svc = c.get("ledger_service")
        required = set(c.get("requires_probes", []) or [])
        evidences = evidence_by_service.get(svc, [])
        if not evidences:
            out.append(
                {
                    "capability": cap,
                    "eligible": False,
                    "reason": "no_functional_evidence",
                    "would_set_runtime_verified": False,
                }
            )
            continue
        best_passed: set[str] = set()
        last_reason = "no_valid_evidence"
        for ev in evidences:
            passed, reason = valid_evidence_passed_probes(ev, policy, target_sha, now)
            if reason is None:
                best_passed |= passed
            else:
                last_reason = reason
        if not best_passed:
            out.append(
                {
                    "capability": cap,
                    "eligible": False,
                    "reason": last_reason,
                    "would_set_runtime_verified": False,
                }
            )
            continue
        missing = sorted(required - best_passed)
        eligible = not missing
        out.append(
            {
                "capability": cap,
                "eligible": eligible,
                "reason": "covered" if eligible else f"partial_coverage missing={missing}",
                "would_set_runtime_verified": eligible,
            }
        )
    return out


def load_committed_evidence() -> dict[str, list[dict[str, Any]]]:
    """Load whatever functional evidence is present on disk (gitignored dir — in CI /
    a clean checkout this is empty, which is exactly why the bridge reports zero)."""
    by_service: dict[str, list[dict]] = {}
    if not FUNCTIONAL_EVIDENCE_DIR.exists():
        return by_service
    for path in sorted(FUNCTIONAL_EVIDENCE_DIR.glob("*.json")):
        try:
            ev = _load(path)
        except (OSError, ValueError):
            continue
        svc = ev.get("service")
        if isinstance(svc, str):
            by_service.setdefault(svc, []).append(ev)
    return by_service


def _head_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cmd_check() -> int:
    if not IDENTITY_MAP.exists():
        print("runtime_identity_bridge: identity map missing (fail-closed)", file=sys.stderr)
        return 1
    errors = validate_identity_map(_load(IDENTITY_MAP))
    if errors:
        print("identity bridge validation FAILED (fail-closed):", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    bridge = _load(IDENTITY_MAP)
    n_ident = len(bridge["service_identity"])
    n_cov = len(bridge["capability_functional_coverage"])
    print(f"runtime_identity_bridge_ok identities={n_ident} coverage={n_cov} (bridge ready, inert)")
    return 0


def cmd_dry_run(target_sha: str | None) -> int:
    if not IDENTITY_MAP.exists():
        print("identity map missing (fail-closed)", file=sys.stderr)
        return 1
    bridge = _load(IDENTITY_MAP)
    errors = validate_identity_map(bridge)
    if errors:
        print("identity bridge invalid; refusing to evaluate (fail-closed):", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    sha = target_sha or _head_sha()
    evaluation = evaluate_propagation(bridge, load_committed_evidence(), sha, datetime.now(UTC))
    would_flip = [e for e in evaluation if e["would_set_runtime_verified"]]
    print("=== runtime identity bridge — DRY RUN (no writes) ===")
    print(f"target_sha: {sha[:12]}")
    print(f"capabilities evaluated: {len(evaluation)}")
    for e in evaluation:
        state = "WOULD SET runtime_verified" if e["eligible"] else "stays 0"
        print(f"  {e['capability']}: {state} — {e['reason']}")
    print("")
    print(
        f"would_set_runtime_verified: {len(would_flip)}  (capabilities: "
        f"{[e['capability'] for e in would_flip]})"
    )
    print(f"stays_zero: {len(evaluation) - len(would_flip)}")
    print("runtime_verified written by this tool: 0 (read-only, dry-run)")
    print("production_certified: 0 (never set here)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="validate the bridge fail-closed (CI-safe)")
    g.add_argument("--dry-run", action="store_true", help="report what would change and why")
    p.add_argument("--target-sha", default=None)
    a = p.parse_args(argv)
    return cmd_check() if a.check else cmd_dry_run(a.target_sha)


if __name__ == "__main__":
    raise SystemExit(main())
