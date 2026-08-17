#!/usr/bin/env python3
"""Produce live, machine-readable evidence for ARCH-S3 RAG cutover.

The probe is deliberately read-only. It compares the existing direct dense-Qdrant
path with the canonical rag-retrieval API using the same Ollama embedding model,
and proves the live collection vector dimension matches the model response.
It NEVER edits the convergence policy or promotes authority automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _post(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - operator-supplied internal URLs
        return json.loads(resp.read().decode())


def _get(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def _fp(text: str) -> str:
    return hashlib.sha256(" ".join((text or "").split()).encode()).hexdigest()


def _vector_size(collection_info: dict) -> int:
    vectors = collection_info.get("result", {}).get("config", {}).get("params", {}).get("vectors")
    if not isinstance(vectors, dict) or not isinstance(vectors.get("size"), int):
        raise ValueError("unsupported Qdrant vector schema")
    return int(vectors["size"])


def run_probe(
    *,
    tenant_id: str,
    queries: list[str],
    final_k: int,
    qdrant_url: str,
    collection: str,
    ollama_url: str,
    model: str,
    retrieval_url: str,
    subject_sha: str,
    contract_sha256: str,
    qdrant_api_key: str | None = None,
) -> dict:
    if not queries:
        raise ValueError("at least one parity query is required")
    qheaders = {"api-key": qdrant_api_key} if qdrant_api_key else {}
    info = _get(f"{qdrant_url.rstrip('/')}/collections/{collection}", qheaders)
    collection_dim = _vector_size(info)
    rows = []
    for query in queries:
        emb = _post(
            f"{ollama_url.rstrip('/')}/api/embeddings", {"model": model, "prompt": query}
        ).get("embedding")
        if not isinstance(emb, list) or not emb:
            raise ValueError("Ollama returned no embedding")
        if len(emb) != collection_dim:
            raise ValueError(f"embedding/Qdrant dimension mismatch: {len(emb)} != {collection_dim}")
        direct = _post(
            f"{qdrant_url.rstrip('/')}/collections/{collection}/points/search",
            {
                "vector": emb,
                "limit": final_k,
                "with_payload": True,
                "filter": {"must": [{"key": "metadata.tenant_id", "match": {"value": tenant_id}}]},
            },
            qheaders,
        ).get("result", [])
        canonical = _post(
            f"{retrieval_url.rstrip('/')}/v1/search",
            {"tenant_id": tenant_id, "query": query, "final_k": final_k},
            {"X-Tenant-Id": tenant_id},
        ).get("annotations", [])
        d = {
            _fp(str((r.get("payload") or {}).get("page_content") or ""))
            for r in direct
            if (r.get("payload") or {}).get("page_content")
        }
        c = {_fp(str(r.get("text") or "")) for r in canonical if r.get("text")}
        union = d | c
        overlap = (len(d & c) / len(union)) if union else 1.0
        rows.append(
            {
                "query_sha256": _fp(query),
                "direct_hits": len(d),
                "canonical_hits": len(c),
                "jaccard": round(overlap, 6),
            }
        )
    return {
        "schema": "sahool.rag-live-parity-receipt/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": subject_sha,
        "embedding_contract_sha256": contract_sha256,
        "tenant_id_sha256": _fp(tenant_id),
        "collection": collection,
        "embedding_provider": "ollama",
        "embedding_model": model,
        "vector_size": collection_dim,
        "queries": rows,
        "query_count": len(rows),
        "min_jaccard": min(r["jaccard"] for r in rows),
        "mean_jaccard": round(sum(r["jaccard"] for r in rows) / len(rows), 6),
        "read_only": True,
        "authority_promotion": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--query", action="append", required=True)
    ap.add_argument("--final-k", type=int, default=5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--subject-sha", default=os.getenv("GITHUB_SHA", ""))
    a = ap.parse_args()
    if len(a.subject_sha) != 40 or any(c not in "0123456789abcdefABCDEF" for c in a.subject_sha):
        raise SystemExit("--subject-sha (or GITHUB_SHA) must be a 40-hex commit SHA")
    contract_path = (
        Path(__file__).resolve().parents[2] / "docs/architecture/rag_embedding_contract.json"
    )
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    receipt = run_probe(
        tenant_id=a.tenant_id,
        queries=a.query,
        final_k=a.final_k,
        qdrant_url=os.getenv("QDRANT_URL", "http://sahool-qdrant:6333"),
        collection=os.getenv("QDRANT_COLLECTION", "sahool_agri_kb"),
        ollama_url=os.getenv("OLLAMA_BASE_URL", "http://sahool-ollama:11434"),
        model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        retrieval_url=os.getenv("RAG_RETRIEVAL_URL", "http://sahool-rag-retrieval:8000"),
        subject_sha=a.subject_sha.lower(),
        contract_sha256=contract_sha,
        qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
    )
    Path(a.out).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"rag_live_parity_receipt_written queries={receipt['query_count']} min={receipt['min_jaccard']} mean={receipt['mean_jaccard']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
