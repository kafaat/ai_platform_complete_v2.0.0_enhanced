#!/usr/bin/env python3
"""Build a read-only D12 logical-identity migration plan from a D08 corpus receipt.

The plan is evidence, not a migration executor.  It never connects to Qdrant and
never invents a logical identity from a storage UUID.  Rows whose only identity is
Qdrant's point ID are held for evidence instead of being made canonical by fiat.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS_GUARD = ROOT / "scripts/architecture/rag_corpus_audit_receipt_guard.py"
PQ_PATH = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
SCHEMA = "sahool.rag-logical-identity-migration-plan/v1"
_FORBIDDEN_KEYS = {"page_content", "text", "payload", "document_body", "content"}


def _sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def _load_corpus_guard():
    spec = importlib.util.spec_from_file_location("rag_d12_corpus_guard", CORPUS_GUARD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load corpus receipt guard from {CORPUS_GUARD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_pq():
    spec = importlib.util.spec_from_file_location("rag_d12_plan_pq", PQ_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical retrieval module from {PQ_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_writer_point_id(chunk_id: str) -> str:
    """The canonical writer's own projection — **imported, never restated**.

    A mirrored copy of the formula would drift: change the namespace or prefix in
    the writer and this planner would compute migration destinations the writer
    never produces, with nothing turning red. So the writer owns it and this is a
    thin delegation.

    The direction is legal because it starts from an explicit logical identity.
    There is intentionally no inverse helper from point UUID to logical chunk ID.
    """
    return _load_pq().canonical_storage_point_id(chunk_id)


def _base_row(source: dict[str, Any]) -> dict[str, Any]:
    point_id = str(source["point_id"])
    classification = str(source["classification"])
    scope = str(source.get("scope") or "unknown")
    explicit = source.get("explicit_logical_chunk_id")
    explicit = str(explicit).strip() if explicit is not None else None
    if explicit == "":
        explicit = None
    fallback = source.get("fallback_identity_used") is True

    action: str
    reason: str
    canonical_chunk_id: str | None = None
    writer_point_id: str | None = None

    if classification in {"CANONICAL_ACTIVE", "CANONICAL_GLOBAL_REFERENCE"}:
        if explicit is None:
            raise ValueError(f"canonical point {point_id} lacks explicit logical chunk identity")
        action = "NOOP_CANONICAL"
        reason = "canonical serving row already owns an explicit logical chunk identity"
        canonical_chunk_id = explicit
    elif classification == "CANONICAL_QUARANTINE":
        action = "NOOP_QUARANTINE"
        reason = "canonical quarantine remains non-serving and is not a migration candidate"
        canonical_chunk_id = explicit
    elif classification == "LEGACY_MIGRATABLE":
        if scope == "quarantine":
            action = "HOLD_QUARANTINE"
            reason = "quarantine is explicitly non-serving and requires separate disposition"
        elif fallback or explicit is None:
            action = "HOLD_IDENTITY_EVIDENCE"
            reason = "storage point ID is not legal evidence for a logical chunk identity"
        else:
            action = "MIGRATION_CANDIDATE"
            reason = "legacy row has an explicit logical chunk identity; no provenance is invented"
            canonical_chunk_id = explicit
            writer_point_id = canonical_writer_point_id(explicit)
    elif classification == "LEGACY_PROVENANCE_INCOMPLETE":
        action = "HOLD_PROVENANCE_EVIDENCE"
        reason = "required provenance is incomplete; identity alone cannot authorize migration"
        canonical_chunk_id = explicit
    elif classification == "ORPHANED_UNATTRIBUTED":
        action = "HOLD_UNATTRIBUTED"
        reason = "point lacks enough attribution for a governed migration decision"
        canonical_chunk_id = explicit
    elif classification == "INVALID":
        action = "HOLD_INVALID"
        reason = "invalid point requires adjudication before any rewrite"
        canonical_chunk_id = explicit
    else:
        raise ValueError(f"unsupported corpus classification for D12: {classification}")

    return {
        "point_id": point_id,
        "classification": classification,
        "scope": scope,
        "logical_identity_source": source.get("logical_identity_source"),
        "explicit_logical_chunk_id": explicit,
        "fallback_identity_used": fallback,
        "canonical_chunk_id": canonical_chunk_id,
        "canonical_writer_point_id": writer_point_id,
        "action": action,
        "reason": reason,
    }


def build_plan(corpus_receipt: dict[str, Any]) -> dict[str, Any]:
    subject_sha = str(corpus_receipt.get("subject_sha") or "")
    subject_tree = str(corpus_receipt.get("subject_tree") or "")
    guard = _load_corpus_guard()
    problems = guard.findings(corpus_receipt, subject_sha, subject_tree)
    if problems:
        raise ValueError("invalid corpus receipt: " + "; ".join(problems))

    records = corpus_receipt.get("point_records")
    if not isinstance(records, list):
        raise ValueError("corpus receipt point_records missing")
    rows = [_base_row(source) for source in records]

    # A logical ID already owned by another physical point is not a safe automatic
    # destination.  Hold every legacy candidate in such a group; never overwrite the
    # canonical owner or choose one duplicate by ordering accident.
    by_logical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        logical = row.get("canonical_chunk_id")
        if logical and row["action"] in {"NOOP_CANONICAL", "MIGRATION_CANDIDATE"}:
            by_logical[str(logical)].append(row)
    collision_groups = {
        logical: members for logical, members in by_logical.items() if len(members) > 1
    }
    for members in collision_groups.values():
        for row in members:
            if row["action"] == "MIGRATION_CANDIDATE":
                row["action"] = "HOLD_LOGICAL_ID_COLLISION"
                row["reason"] = "logical chunk identity is already represented by another point"
                row["canonical_writer_point_id"] = None

    rows.sort(key=lambda row: row["point_id"])
    action_counts = Counter(str(row["action"]) for row in rows)
    return {
        "schema": SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "subject_sha": subject_sha,
        "subject_tree": subject_tree,
        "collection": corpus_receipt.get("collection"),
        "corpus_receipt_sha256": _sha256_json(corpus_receipt),
        "corpus_point_inventory_sha256": corpus_receipt.get("point_inventory_sha256"),
        "read_only": True,
        "writes_performed": False,
        "migration_authorized": False,
        "authority_promotion": False,
        "point_count": len(rows),
        "action_counts": dict(sorted(action_counts.items())),
        "migration_candidate_count": action_counts["MIGRATION_CANDIDATE"],
        "identity_evidence_required_count": action_counts["HOLD_IDENTITY_EVIDENCE"],
        "provenance_evidence_required_count": action_counts["HOLD_PROVENANCE_EVIDENCE"],
        "logical_id_collision_group_count": len(collision_groups),
        "logical_id_collision_point_count": sum(len(v) for v in collision_groups.values()),
        "plan_rows": rows,
        "plan_rows_sha256": _sha256_json(rows),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-receipt", required=True)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    try:
        receipt = json.loads(pathlib.Path(args.corpus_receipt).read_text(encoding="utf-8"))
        plan = build_plan(receipt)
    except Exception as exc:  # noqa: BLE001 - evidence tooling fails closed
        print(f"rag_logical_identity_plan_fail {exc}", file=sys.stderr)
        return 1
    text = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        pathlib.Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
