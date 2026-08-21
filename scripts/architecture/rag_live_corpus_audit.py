#!/usr/bin/env python3
"""Read-only live Qdrant corpus admissibility audit for SAHOOL RAG.

This is the D08-A measurement tool.  It never writes, deletes, migrates, upserts,
or promotes authority.  The receipt classifies every physical point using the same
``KnowledgeChunk`` parser/rejection taxonomy used by ``rag-retrieval`` while
keeping document bodies out of the artifact.

Usage from a host or the rag-retrieval container::

    python3 scripts/architecture/rag_live_corpus_audit.py \
      --subject-sha <40-hex> --subject-tree <40-hex> --output corpus-audit.json

Environment defaults are the runtime ones: ``QDRANT_URL``, ``QDRANT_COLLECTION``
and ``QDRANT_API_KEY``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import combinations
from typing import Any
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
PQ_PATH = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
SCHEMA = "sahool.rag-corpus-audit-receipt/v1"
QUARANTINE_TENANT = "__seed_quarantine__"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

# Canonical storage means the shape emitted by ``KnowledgeChunk.payload``.  Parser
# compatibility is intentionally wider and is measured separately.
_CANONICAL_META_KEYS = frozenset(
    {
        "chunk_id",
        "tenant_id",
        "source_type",
        "document_id",
        "chunk_index",
        "total_chunks",
        "evidence_level",
        "source_class",
        "content_digest",
    }
)

_CLASSIFICATIONS = (
    "CANONICAL_ACTIVE",
    "CANONICAL_GLOBAL_REFERENCE",
    "CANONICAL_QUARANTINE",
    "LEGACY_MIGRATABLE",
    "LEGACY_PROVENANCE_INCOMPLETE",
    "ORPHANED_UNATTRIBUTED",
    "INVALID",
    "UNCLASSIFIED",
)

_PROVENANCE_REASONS = frozenset(
    {
        "GLOBAL_REFERENCE_PROVENANCE_INCOMPLETE",
        "TENANT_DOCUMENT_PROVENANCE_INCOMPLETE",
    }
)
_ORPHAN_REASONS = frozenset(
    {
        "MISSING_CONTENT",
        "MISSING_CHUNK_IDENTITY",
        "MISSING_TENANT",
        "MISSING_SOURCE_TYPE",
        "MISSING_DOCUMENT_ID",
    }
)


def _load_pq():
    # In the production container ``PYTHONPATH=/app`` already exposes
    # ``core.rag.production_qdrant``; in a checkout we load the same file directly.
    # This keeps the audit runnable via ``docker cp ... /tmp`` without rebuilding the
    # image merely to place a diagnostic script inside it.
    try:
        from core.rag import production_qdrant as module  # type: ignore

        return module
    except ModuleNotFoundError as exc:
        spec = importlib.util.spec_from_file_location("rag_live_audit_pq", PQ_PATH)
        if spec is None or spec.loader is None:
            # يُسلسَل السببُ عمداً: الاستيرادُ فشل **و**الارتدادُ إلى الملفّ فشل، وكلاهما
            # حقيقةٌ يحتاجها المشغِّل. ورفعٌ بلا `from` يُخفي الأولى فيقرأ القارئ نصفَ العطل.
            raise RuntimeError(f"cannot load production_qdrant from {PQ_PATH}") from exc
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


def _parser_sha256(pq) -> str:
    source = pathlib.Path(str(getattr(pq, "__file__", PQ_PATH)))
    if not source.is_file():
        source = PQ_PATH
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def _safe_qdrant_identity(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme or 'http'}://{host}{port}" if host else "internal-qdrant"


def _nested_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("metadata")
    return dict(value) if isinstance(value, dict) else {}


def _effective_tenant(payload: dict[str, Any]) -> str | None:
    meta = _nested_metadata(payload)
    value = meta.get("tenant_id", payload.get("tenant_id"))
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _scope(tenant_id: str | None, global_tenant: str) -> str:
    if tenant_id is None:
        return "unknown"
    if tenant_id == QUARANTINE_TENANT:
        return "quarantine"
    if tenant_id == global_tenant:
        return "global"
    return "tenant"


def _canonical_shape(payload: dict[str, Any]) -> bool:
    meta = _nested_metadata(payload)
    if "page_content" not in payload or not isinstance(payload.get("page_content"), str):
        return False
    if not isinstance(payload.get("metadata"), dict):
        return False
    if not _CANONICAL_META_KEYS.issubset(meta):
        return False
    for key in ("chunk_id", "tenant_id", "source_type", "document_id", "evidence_level"):
        if not str(meta.get(key) or "").strip():
            return False
    if not isinstance(meta.get("chunk_index"), int) or not isinstance(
        meta.get("total_chunks"), int
    ):
        return False
    digest = meta.get("content_digest")
    return isinstance(digest, str) and len(digest) == 64


def classify_point(pq, point_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Classify one point without emitting its document content."""
    meta = _nested_metadata(payload)
    tenant_id = _effective_tenant(payload)
    scope = _scope(tenant_id, pq.GLOBAL_REFERENCE_TENANT)
    nested_tenant = str(meta.get("tenant_id") or "").strip() or None
    nested_chunk_id = str(meta.get("chunk_id") or "").strip() or None
    root_chunk_id = str(payload.get("chunk_id") or "").strip() or None

    parsed = None
    reject_reason: str | None = None
    missing_fields: tuple[str, ...] = ()
    try:
        parsed = pq.KnowledgeChunk.from_payload(payload, fallback_id=point_id)
    except (TypeError, ValueError):
        verdict = pq.classify_rejection(payload, fallback_id=point_id)
        if verdict is None:  # parser/rejection classifier disagreement is never hidden
            reject_reason = "CLASSIFIER_PARSER_DISAGREEMENT"
        else:
            reject_reason, missing_fields = verdict

    parse_pass = parsed is not None
    canonical_shape = _canonical_shape(payload)
    fallback_identity_used = bool(
        parse_pass
        and nested_chunk_id is None
        and root_chunk_id is None
        and parsed.chunk_id == point_id
    )
    current_dense_eligible = bool(nested_tenant and scope in {"tenant", "global"})
    current_sparse_eligible = bool(parse_pass and scope in {"tenant", "global"})
    dense_sparse_divergent = current_dense_eligible != current_sparse_eligible

    if parse_pass and canonical_shape:
        if scope == "quarantine":
            classification = "CANONICAL_QUARANTINE"
        elif scope == "global":
            classification = "CANONICAL_GLOBAL_REFERENCE"
        elif scope == "tenant":
            classification = "CANONICAL_ACTIVE"
        else:
            classification = "UNCLASSIFIED"
    elif parse_pass:
        classification = "LEGACY_MIGRATABLE"
    elif reject_reason in _PROVENANCE_REASONS:
        classification = "LEGACY_PROVENANCE_INCOMPLETE"
    elif reject_reason in _ORPHAN_REASONS:
        classification = "ORPHANED_UNATTRIBUTED"
    elif reject_reason:
        classification = "INVALID"
    else:
        classification = "UNCLASSIFIED"

    source_type = None
    source_class = None
    content_digest = None
    if parsed is not None:
        source_type = parsed.source_type
        source_class = parsed.metadata.get("source_class")
        content_digest = parsed.metadata.get("content_digest")
    else:
        source_type = meta.get("source_type", payload.get("source_type"))
        source_class = meta.get("source_class")
        content_digest = meta.get("content_digest")
    if not isinstance(content_digest, str) or len(content_digest) != 64:
        content_digest = None

    serving_candidate = scope != "quarantine"
    canonical_serving_eligible = classification in {
        "CANONICAL_ACTIVE",
        "CANONICAL_GLOBAL_REFERENCE",
    }

    return {
        "point_id": point_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "classification": classification,
        "parse_pass": parse_pass,
        "canonical_shape": canonical_shape,
        "current_dense_eligible": current_dense_eligible,
        "current_sparse_eligible": current_sparse_eligible,
        "dense_sparse_divergent": dense_sparse_divergent,
        "serving_candidate": serving_candidate,
        "canonical_serving_eligible": canonical_serving_eligible,
        "fallback_identity_used": fallback_identity_used,
        "reject_reason": reject_reason,
        "missing_fields": sorted(missing_fields),
        "source_type": str(source_type) if source_type is not None else None,
        "source_class": str(source_class) if source_class is not None else None,
        "content_digest": content_digest,
        "source_uri_present": bool(str(meta.get("source_uri") or "").strip()),
        "source_revision_present": bool(str(meta.get("source_revision") or "").strip()),
    }


def _duplicate_digest_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_digest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        digest = row.get("content_digest")
        if digest:
            by_digest[str(digest)].append(row)

    groups: list[dict[str, Any]] = []
    pair_counts: Counter[str] = Counter()
    affected_points: set[str] = set()
    for digest, rows in sorted(by_digest.items()):
        scopes = sorted({str(r.get("tenant_id") or "<unknown>") for r in rows})
        if len(scopes) < 2:
            continue
        ids = sorted(str(r["point_id"]) for r in rows)
        affected_points.update(ids)
        for left, right in combinations(scopes, 2):
            pair_counts[f"{left}|{right}"] += 1
        if len(groups) < 5:
            groups.append(
                {
                    "content_digest": digest,
                    "tenant_scopes": scopes,
                    "point_ids": ids[:10],
                    "point_count": len(ids),
                }
            )
    return {
        "digest_group_count": sum(
            1
            for rows in by_digest.values()
            if len({str(r.get("tenant_id") or "<unknown>") for r in rows}) >= 2
        ),
        "affected_point_count": len(affected_points),
        "scope_pair_group_counts": dict(sorted(pair_counts.items())),
        "bounded_samples": groups,
    }


def build_receipt(
    pq,
    rows: list[tuple[str, dict[str, Any]]],
    *,
    exact_count: int,
    subject_sha: str,
    subject_tree: str,
    collection: str,
    qdrant_identity: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    records = [classify_point(pq, point_id, payload) for point_id, payload in rows]
    records.sort(key=lambda r: r["point_id"])

    class_counts = Counter(str(r["classification"]) for r in records)
    for name in _CLASSIFICATIONS:
        class_counts.setdefault(name, 0)
    reason_counts = Counter(str(r["reject_reason"]) for r in records if r.get("reject_reason"))
    tenant_counts = Counter(str(r.get("tenant_id") or "<unknown>") for r in records)

    unclassified = class_counts["UNCLASSIFIED"]
    physical_complete = exact_count == len(rows)
    # The payload-parity property is deliberately about the potentially serving corpus.
    # Explicit quarantine may remain noncanonical, but every physical point must still be
    # classified and every non-quarantine candidate must satisfy the canonical contract.
    serving_blockers = [
        r for r in records if r["serving_candidate"] and not r["canonical_serving_eligible"]
    ]
    canonical_payload_parity = bool(
        physical_complete and unclassified == 0 and not serving_blockers
    )

    inventory_digest = _sha256_json(records)
    receipt = {
        "schema": SCHEMA,
        "observed_at": observed_at or datetime.now(UTC).isoformat(),
        "subject_sha": subject_sha,
        "subject_tree": subject_tree,
        "collection": collection,
        "qdrant_identity": qdrant_identity,
        "read_only": True,
        "authority_promotion": False,
        "exact_count": exact_count,
        "scroll_count": len(rows),
        "physical_count_complete": physical_complete,
        "classification_counts": dict(sorted(class_counts.items())),
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "tenant_scope_counts": dict(sorted(tenant_counts.items())),
        "parse_pass": sum(1 for r in records if r["parse_pass"]),
        "parse_fail": sum(1 for r in records if not r["parse_pass"]),
        "current_dense_eligible": sum(1 for r in records if r["current_dense_eligible"]),
        "current_sparse_eligible": sum(1 for r in records if r["current_sparse_eligible"]),
        "dense_sparse_divergent": sum(1 for r in records if r["dense_sparse_divergent"]),
        "fallback_identity_used": sum(1 for r in records if r["fallback_identity_used"]),
        "serving_candidate_count": sum(1 for r in records if r["serving_candidate"]),
        "canonical_serving_eligible_count": sum(
            1 for r in records if r["canonical_serving_eligible"]
        ),
        "unclassified_count": unclassified,
        "canonical_payload_parity": canonical_payload_parity,
        "duplicate_content_digest_cross_scope": _duplicate_digest_summary(records),
        "point_inventory_sha256": inventory_digest,
        "audit_tool_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
        "parser_sha256": _parser_sha256(pq),
        "point_records": records,
    }
    return receipt


def _validate_subject(value: str, label: str) -> str:
    value = value.lower()
    if not _HEX40.fullmatch(value):
        raise ValueError(f"{label} must be a full 40-character lowercase hex id")
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument("--subject-tree", required=True)
    ap.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://sahool-qdrant:6333"))
    ap.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "sahool_agri_kb"))
    ap.add_argument("--output")
    args = ap.parse_args(argv)

    try:
        subject_sha = _validate_subject(args.subject_sha, "subject_sha")
        subject_tree = _validate_subject(args.subject_tree, "subject_tree")
        pq = _load_pq()
        client = pq.QdrantHttpClient(
            args.qdrant_url,
            args.collection,
            vector_size=0,
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
        # Both calls are reads.  Exact Count is the physical authority; CollectionInfo
        # ``points_count`` is intentionally not consulted.
        exact_count = client.collection_point_count()
        rows = client.scroll_payloads()
        receipt = build_receipt(
            pq,
            rows,
            exact_count=exact_count,
            subject_sha=subject_sha,
            subject_tree=subject_tree,
            collection=args.collection,
            qdrant_identity=_safe_qdrant_identity(args.qdrant_url),
        )
    except Exception as exc:  # noqa: BLE001 - CLI evidence tool must fail closed
        print(f"rag_live_corpus_audit_fail {exc}", file=sys.stderr)
        return 1

    text = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        pathlib.Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    # A valid audit may document a non-parity corpus.  That is evidence, not tool failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
