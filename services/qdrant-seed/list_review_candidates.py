#!/usr/bin/env python3
"""List reference excerpts that still await an agronomist's review.

Read-only: it prints candidates and writes no approval. A reviewer copies the printed
``content_digest`` and ``source_revision`` into a record of
``shared/ai/reference_approvals.json`` (format in ``shared/ai/reference_approvals.py``).

    python services/qdrant-seed/list_review_candidates.py
    python services/qdrant-seed/list_review_candidates.py --payloads qdrant_export.json --all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(Path(__file__).parent), str(ROOT)]

from shared.ai.reference_approvals import (  # noqa: E402
    MANIFEST_PATH,
    ApprovalManifestError,
    content_digest,
    excerpt_text,
    index_approvals,
    load_manifest,
)
from shared.ai.seed_claims import seed_claim_details  # noqa: E402


def seed_excerpts() -> list[dict]:
    """The seed corpus with the identity fields ``seed.py`` writes for the configured tenant."""
    import seed

    is_global = seed.SEED_TENANT_ID == "__global__"
    provenance = seed._load_provenance_manifest()
    excluded = seed._load_excluded_chunk_ids()
    excerpts = []
    for doc in seed.KNOWLEDGE_BASE:
        chunk_id = f"seed:{doc['id']}"
        if chunk_id in excluded:
            continue
        source = str(doc.get("source") or "")
        excerpts.append(
            {
                "chunk_id": chunk_id,
                "document_id": f"reference:{doc.get('source', 'unknown')}:{doc['id']}",
                "source_label": source,
                "source_revision": provenance.get(source, {}).get("source_revision")
                if is_global
                else seed.SEED_REVISION,
                "claim_locator": doc.get("claim_locator"),
                "claim_verification": doc.get("claim_verification"),
                "text": doc["text"],
            }
        )
    return excerpts


def payload_excerpts(path: Path) -> list[dict]:
    """Excerpts from a JSON list of Qdrant payloads (``page_content`` + ``metadata``)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("--payloads must hold a JSON list of payload objects")
    excerpts = []
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        excerpts.append({**metadata, "text": row.get("page_content", row.get("text"))})
    return excerpts


def review_status(excerpt: dict, approvals: dict, today: date) -> str:
    if seed_claim_details(excerpt):
        return "flagged_not_verified_against_original"
    text = excerpt_text(excerpt)
    if text is None:
        return "no_text"
    record = approvals.get((content_digest(text), excerpt.get("source_revision")))
    if record is None:
        return "awaiting_review"
    if today < date.fromisoformat(record["reviewed_on"]):
        return "approval_not_yet_effective"
    if today > date.fromisoformat(record["valid_until"]):
        return "approval_expired"
    return "approved"


def list_candidates(
    excerpts: list[dict], approvals: dict, *, today: date | None = None, include_approved=False
) -> list[dict]:
    today = today or datetime.now(UTC).date()
    candidates = []
    for excerpt in excerpts:
        status = review_status(excerpt, approvals, today)
        if status == "approved" and not include_approved:
            continue
        text = excerpt_text(excerpt)
        candidates.append(
            {
                "chunk_id": excerpt.get("chunk_id"),
                "document_id": excerpt.get("document_id"),
                "source_label": excerpt.get("source_label") or excerpt.get("claim_source_label"),
                "source_revision": excerpt.get("source_revision"),
                "content_digest": content_digest(text) if text is not None else None,
                "claim_locator": excerpt.get("claim_locator"),
                "review_status": status,
                "text": text,
            }
        )
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--payloads", type=Path, help="JSON list of Qdrant payloads to list")
    parser.add_argument("--all", action="store_true", help="also list approved excerpts")
    args = parser.parse_args(argv)
    try:
        approvals = index_approvals(load_manifest(args.manifest))
    except ApprovalManifestError as exc:
        print(f"approval manifest rejected: {exc}", file=sys.stderr)
        return 2
    try:
        excerpts = payload_excerpts(args.payloads) if args.payloads else seed_excerpts()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"excerpts unavailable: {exc}", file=sys.stderr)
        return 2
    candidates = list_candidates(excerpts, approvals, include_approved=args.all)
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate["review_status"]] = counts.get(candidate["review_status"], 0) + 1
    json.dump(
        {
            "manifest": str(args.manifest),
            "approval_records": len(approvals),
            "excerpts_examined": len(excerpts),
            "review_status_counts": counts,
            "candidates": candidates,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
