"""P6 fail-closed runtime certification evaluation and immutable manifest hashing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from shared.contracts.soil.p6 import CertificationPolicy, RuntimeCertificationRun


def canonical_manifest(run: RuntimeCertificationRun) -> dict:
    data = run.model_dump(mode="json")
    data.pop("manifest_sha256", None)
    return data


def manifest_hash(run: RuntimeCertificationRun) -> str:
    raw = json.dumps(canonical_manifest(run), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def evaluate_run(
    run: RuntimeCertificationRun, policy: CertificationPolicy | None = None
) -> RuntimeCertificationRun:
    policy = policy or CertificationPolicy()
    by = {c.check_name: c for c in run.checks}
    blockers = []
    for name in policy.required_checks:
        check = by.get(name)
        if check is None:
            blockers.append(f"missing_check:{name}")
        elif check.status != "passed":
            blockers.append(f"check_not_passed:{name}")
        elif check.required and not check.evidence_ids:
            blockers.append(f"evidence_missing:{name}")
    evidence_ids = {e.evidence_id for e in run.evidence}
    for check in run.checks:
        missing = [eid for eid in check.evidence_ids if eid not in evidence_ids]
        blockers.extend(f"unknown_evidence:{check.check_name}:{eid}" for eid in missing)
    if run.migrations_applied_through != "v166":
        blockers.append("migrations_not_applied_through_v166")
    blockers = list(dict.fromkeys(blockers))
    run.blockers = blockers
    if blockers:
        run.status = "blocked"
    elif len(set(run.approvals)) < policy.min_approvals:
        run.status = "ready_for_approval"
    else:
        run.status = "certified"
        run.completed_at = datetime.now(UTC)
    run.manifest_sha256 = manifest_hash(run)
    return run


def verify_manifest(run: RuntimeCertificationRun) -> bool:
    return bool(run.manifest_sha256) and run.manifest_sha256 == manifest_hash(run)
