#!/usr/bin/env python3
"""Collect and verify a subject-bound, read-only C12 live activation receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

SCHEMA = "sahool.c12-live-activation-receipt/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
IDENT_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def canonical_digest(body: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in body.items() if key != "evidence_sha256"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finalize(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    out["evidence_sha256"] = canonical_digest(out)
    return out


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def problems(
    body: Any,
    *,
    expected_subject_sha: str,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
) -> list[str]:
    if not isinstance(body, dict):
        return ["receipt_must_be_an_object"]
    out: list[str] = []
    if body.get("schema") != SCHEMA:
        out.append("unsupported_receipt_schema")
    subject = body.get("subject_sha")
    if not isinstance(subject, str) or not SHA_RE.fullmatch(subject):
        out.append("invalid_subject_sha")
    elif subject != expected_subject_sha:
        out.append("subject_sha_mismatch")
    observed = _parse_time(body.get("observed_at"))
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    if observed is None:
        out.append("invalid_observed_at")
    elif observed > clock + timedelta(minutes=5) or clock - observed > max_age:
        out.append("receipt_outside_freshness_window")
    source = body.get("source")
    if not isinstance(source, dict):
        out.append("missing_source")
    else:
        if source.get("kind") != "postgresql":
            out.append("source_is_not_postgresql")
        if source.get("read_only") is not True:
            out.append("source_not_read_only")
        if source.get("authoritative") is not True:
            out.append("source_not_authoritative")
    if body.get("classification") != "PASSED" or body.get("live_evidence_complete") is not True:
        out.append("live_evidence_not_complete")
    chain = body.get("chain")
    if not isinstance(chain, dict):
        out.append("missing_activation_chain")
        chain = {}
    required_ids = (
        "promotion_decision_id",
        "activation_request_id",
        "activation_review_id",
        "activation_command_id",
        "activation_claim_id",
        "activation_receipt_id",
        "verification_id",
        "rollout_plan_id",
        "rollout_receipt_id",
        "monitoring_snapshot_id",
    )
    for key in required_ids:
        if not isinstance(chain.get(key), str) or not chain.get(key, "").strip():
            out.append(f"missing_chain_id:{key}")
    expected_states = {
        "decision_state": "promotion_eligible",
        "requested_state": "pending_activation_approval",
        "review_decision": "approved",
        "command_state": "queued",
        "receipt_state": "activated",
        "verification_state": "verified_healthy",
        "rollout_receipt_state": "applied",
        "drift_state": "stable",
    }
    for key, expected in expected_states.items():
        if chain.get(key) != expected:
            out.append(f"invalid_chain_state:{key}")
    if chain.get("target_environment") not in {"staging", "production"}:
        out.append("invalid_target_environment")
    if chain.get("rollout_mode") not in {"canary", "full"}:
        out.append("non_serving_rollout_mode")
    traffic = chain.get("traffic_percent")
    observed_traffic = chain.get("observed_traffic_percent")
    if not isinstance(traffic, (int, float)) or isinstance(traffic, bool) or traffic <= 0:
        out.append("rollout_traffic_not_positive")
    if observed_traffic != traffic:
        out.append("rollout_traffic_mismatch")
    samples = chain.get("sample_count")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples <= 0:
        out.append("monitoring_sample_count_not_positive")
    requested_by = chain.get("requested_by")
    reviewed_by = chain.get("reviewed_by")
    if not all(isinstance(v, str) and v.strip() for v in (requested_by, reviewed_by)):
        out.append("missing_request_or_review_identity")
    elif requested_by == reviewed_by:
        out.append("activation_self_approval")
    digests = [
        chain.get("candidate_artifact_digest"),
        chain.get("active_artifact_digest"),
        chain.get("verification_artifact_digest"),
        chain.get("rollout_candidate_artifact_digest"),
    ]
    if any(not isinstance(value, str) or not DIGEST_RE.fullmatch(value) for value in digests):
        out.append("invalid_artifact_digest")
    elif len(set(digests)) != 1:
        out.append("artifact_digest_chain_mismatch")
    evidence_digest = body.get("evidence_sha256")
    if not isinstance(evidence_digest, str) or not DIGEST_RE.fullmatch(evidence_digest):
        out.append("invalid_evidence_digest")
    elif evidence_digest != canonical_digest(body):
        out.append("evidence_digest_mismatch")
    return sorted(set(out))


def _validated_identifier(value: str, label: str) -> str:
    if not IDENT_RE.fullmatch(value):
        raise ValueError(f"{label} must match {IDENT_RE.pattern}")
    return value


def _sql(tenant_id: str, model_id: str, feature_set_id: str | None, environment: str) -> str:
    tenant = str(UUID(tenant_id))
    model = _validated_identifier(model_id, "model_id")
    feature = _validated_identifier(feature_set_id, "feature_set_id") if feature_set_id else None
    if environment not in {"staging", "production"}:
        raise ValueError("target_environment must be staging or production")
    feature_predicate = (
        f"c.feature_set_id = '{feature}'" if feature is not None else "c.feature_set_id IS NULL"
    )
    return f"""
SELECT json_build_object(
 'tenant_id', c.tenant_id::text, 'model_id', c.model_id,
 'feature_set_id', c.feature_set_id, 'target_environment', c.target_environment,
 'promotion_decision_id', p.promotion_decision_id, 'decision_state', p.decision_state,
 'decided_by', p.decided_by, 'candidate_artifact_digest', lower(c.candidate_artifact_digest),
 'activation_request_id', q.activation_request_id, 'requested_state', q.requested_state,
 'requested_by', q.requested_by, 'activation_review_id', v.activation_review_id,
 'review_decision', v.review_decision, 'reviewed_by', v.reviewed_by,
 'activation_command_id', c.activation_command_id, 'command_state', c.command_state,
 'activation_claim_id', cl.activation_claim_id, 'adapter_id', cl.adapter_id,
 'activation_receipt_id', ar.activation_receipt_id, 'receipt_state', ar.receipt_state,
 'active_artifact_digest', lower(ar.active_artifact_digest), 'recorded_by', ar.recorded_by,
 'verification_id', pv.verification_id, 'verification_state', pv.verification_state,
 'verification_artifact_digest', lower(pv.artifact_digest), 'verified_by', pv.verified_by,
 'rollout_plan_id', rp.rollout_plan_id, 'rollout_mode', rp.mode,
 'traffic_percent', rp.traffic_percent::float8,
 'rollout_receipt_id', rr.rollout_receipt_id, 'rollout_receipt_state', rr.receipt_state,
 'observed_traffic_percent', rr.observed_traffic_percent::float8,
 'rollout_candidate_artifact_digest', lower(rr.candidate_artifact_digest),
 'controller_id', rr.controller_id, 'monitoring_snapshot_id', ms.monitoring_snapshot_id,
 'sample_count', ms.sample_count, 'drift_state', ms.drift_state, 'captured_by', ms.captured_by
)::text
FROM decision_model_registry_activation_commands c
JOIN decision_model_activation_reviews v ON v.tenant_id=c.tenant_id AND v.activation_review_id=c.activation_review_id
JOIN decision_model_activation_requests q ON q.tenant_id=c.tenant_id AND q.activation_request_id=c.activation_request_id
JOIN decision_model_promotion_decisions p ON p.tenant_id=c.tenant_id AND p.promotion_decision_id=q.promotion_decision_id
JOIN decision_model_registry_activation_claims cl ON cl.tenant_id=c.tenant_id AND cl.activation_command_id=c.activation_command_id
JOIN decision_model_registry_activation_receipts ar ON ar.tenant_id=c.tenant_id AND ar.activation_command_id=c.activation_command_id
JOIN decision_model_post_activation_verifications pv ON pv.tenant_id=c.tenant_id AND pv.activation_receipt_id=ar.activation_receipt_id
JOIN decision_model_rollout_plans rp ON rp.tenant_id=c.tenant_id AND rp.activation_receipt_id=ar.activation_receipt_id
JOIN decision_model_rollout_receipts rr ON rr.tenant_id=c.tenant_id AND rr.rollout_plan_id=rp.rollout_plan_id
JOIN LATERAL (
 SELECT m.* FROM decision_model_monitoring_snapshots m
 WHERE m.tenant_id=c.tenant_id AND m.model_id=c.model_id
   AND m.feature_set_id IS NOT DISTINCT FROM c.feature_set_id
   AND m.target_environment=c.target_environment AND m.captured_at >= ar.recorded_at
 ORDER BY m.captured_at DESC LIMIT 1
) ms ON true
WHERE c.tenant_id='{tenant}'::uuid AND c.model_id='{model}' AND {feature_predicate}
  AND c.target_environment='{environment}' AND p.decision_state='promotion_eligible'
  AND v.review_decision='approved' AND ar.receipt_state='activated'
ORDER BY ar.recorded_at DESC LIMIT 1;
""".strip()


def collect(args: argparse.Namespace) -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    if os.getenv("DECISION_SERVICE_SOR_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError("DECISION_SERVICE_SOR_ENABLED=true is required")
    if not SHA_RE.fullmatch(args.subject_sha):
        raise ValueError("subject_sha must be 40 lowercase hex")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=10,
    )
    local_subject = (head.stdout or "").strip().lower()
    if head.returncode or local_subject != args.subject_sha:
        raise RuntimeError("real checkout HEAD does not match subject_sha")
    query = _sql(args.tenant_id, args.model_id, args.feature_set_id, args.target_environment)
    proc = subprocess.run(
        ["psql", database_url, "-X", "--set=ON_ERROR_STOP=1", "-At", "-c", query],
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=60,
    )
    if proc.returncode:
        raise RuntimeError(f"PostgreSQL C12 collection failed: {(proc.stdout or '')[-1000:]}")
    raw_lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    raw = raw_lines[-1].strip() if raw_lines else ""
    if not raw:
        raise RuntimeError("no complete C12 activation chain found")
    chain = json.loads(raw)
    body = finalize(
        {
            "schema": SCHEMA,
            "subject_sha": args.subject_sha,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": {"kind": "postgresql", "read_only": True, "authoritative": True},
            "classification": "PASSED",
            "live_evidence_complete": True,
            "authority_changed": False,
            "chain": chain,
        }
    )
    found = problems(body, expected_subject_sha=args.subject_sha)
    if found:
        raise RuntimeError("collected C12 evidence failed verification: " + ",".join(found))
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_collect = sub.add_parser("collect")
    p_collect.add_argument("--subject-sha", required=True)
    p_collect.add_argument("--tenant-id", required=True)
    p_collect.add_argument("--model-id", required=True)
    p_collect.add_argument("--feature-set-id")
    p_collect.add_argument("--target-environment", choices=("staging", "production"), required=True)
    p_collect.add_argument("--output", required=True, type=Path)
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--subject-sha", required=True)
    p_verify.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "collect":
        try:
            body = collect(args)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            print(json.dumps({"classification": "FAILED", "findings": [str(exc)]}, sort_keys=True))
            return 2
    else:
        try:
            body = json.loads(args.receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"classification": "FAILED", "findings": [f"receipt_unreadable:{exc}"]}, sort_keys=True))
            return 2
        found = problems(body, expected_subject_sha=args.subject_sha)
        if found:
            print(json.dumps({"classification": "FAILED", "findings": found}, sort_keys=True))
            return 2
    print(json.dumps(body, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
