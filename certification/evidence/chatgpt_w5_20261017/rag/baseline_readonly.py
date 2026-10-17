"""Read-only current-source baseline; absent dependencies produce no ranking scores.

Only loopback endpoints are accepted. No ingest, collection create, model pull,
prefix rewrite or model substitution. Snapshot BM25 is explicitly a separate
offline diagnostic, not a current-stack baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
STAGES = ("dense", "sparse", "fusion", "expansion", "expansion_reranked")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def loopback(value):
    parts = urlsplit(value)
    if parts.scheme != "http" or parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("only an existing loopback test stack is allowed")
    if (
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError("use an origin without credentials or path")
    return value.rstrip("/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path, default=HERE / "baseline-results.json")
    args = parser.parse_args()
    qurl, ourl = loopback(args.qdrant_url), loopback(args.ollama_url)
    manifest = json.loads((HERE / "evaluation-v1.json").read_text())
    corpus_path = ROOT / manifest["corpus_path"]
    assert hashlib.sha256(corpus_path.read_bytes()).hexdigest() == manifest["corpus_sha256"]
    corpus = json.loads(corpus_path.read_text())
    pq = load(SOURCE, "w5_current_retriever")
    old = load(
        ROOT / "certification/evidence/chatgpt_closure_nine_20261016/rag/relevance_experiment.py",
        "w5_metrics",
    )
    report = {
        "schema": "sahool.yemen-baseline/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "evaluation_sha256": hashlib.sha256((HERE / "evaluation-v1.json").read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "scope": "local only; current source and existing data; no external environment",
        "mutations": [],
        "dependency_probes": {},
        "measurements": [],
    }

    # The probe subclass also prevents accidental writes by this evidence tool.
    class ReadOnlyClient(pq.QdrantHttpClient):
        def _request(self, method, path, payload=None):
            allowed_post = path.endswith(("/points/scroll", "/points/search", "/api/embeddings"))
            if method != "GET" and not (method == "POST" and allowed_post):
                raise RuntimeError("baseline prohibits remote mutations")
            return super()._request(method, path, payload)

        def scroll_payloads(self, **kwargs):
            return super().scroll_payloads(page_size=256, max_pages=40)

        def search(self, *args, **kwargs):
            rows = super().search(*args, **kwargs)
            self.observed_dense = rows
            return rows

    class ObservedBM25(pq.BM25Index):
        def search(self, *args, **kwargs):
            self.observed_sparse = super().search(*args, **kwargs)
            return self.observed_sparse

    class ObservedRetriever(pq.HybridQdrantRetriever):
        def _expand_neighbors(self, rows, **kwargs):
            self.observed_fusion = list(rows)
            self.observed_expansion = super()._expand_neighbors(rows, **kwargs)
            return self.observed_expansion

    client = ReadOnlyClient(
        qurl, manifest["collection"], api_key=os.getenv("QDRANT_API_KEY"), timeout_s=3
    )
    model_api = ReadOnlyClient(ourl, "unused", timeout_s=3)
    for name, api, path in [("qdrant", client, "/"), ("ollama", model_api, "/api/tags")]:
        try:
            report["dependency_probes"][name] = {
                "status": "AVAILABLE",
                "response": api._request("GET", path),
            }
        except Exception as exc:
            report["dependency_probes"][name] = {
                "status": "UNAVAILABLE",
                "error_type": type(exc).__name__,
            }
    available = all(p["status"] == "AVAILABLE" for p in report["dependency_probes"].values())
    if available:
        try:
            tags = report["dependency_probes"]["ollama"]["response"]["models"]
            matched = [
                m
                for m in tags
                if (m.get("name") or m.get("model", "")).split(":")[0]
                == manifest["embedding_model"]
            ]
            if len(matched) != 1 or not matched[0].get("digest"):
                raise ValueError("MODEL_IDENTITY_UNRESOLVED")
            report["model_identity"] = matched[0]
            embed = pq.OllamaEmbeddingProvider(ourl, manifest["embedding_model"], timeout_s=10)
            retriever = ObservedRetriever(client, embed)
            # An empty BM25 object is falsey; passing it through the production
            # constructor's `bm25 or BM25Index()` would discard this observer.
            retriever.bm25 = ObservedBM25()
            report["hydration"] = retriever.rebuild_sparse_index()
            reference_text = {d["chunk_id"]: d["text"] for d in corpus["documents"]}
            for query in manifest["queries"]:
                visible = {
                    cid: chunk
                    for cid, chunk in retriever._chunks.items()
                    if chunk.tenant_id in {query["tenant_id"], pq.GLOBAL_REFERENCE_TENANT}
                    and pq.matches_scope_filters(chunk, {})
                }
                if set(visible) != set(query["judgments"]) or any(
                    chunk.text != reference_text.get(cid) for cid, chunk in visible.items()
                ):
                    raise ValueError("CURRENT_CORPUS_NEEDS_NEW_JUDGMENTS")
                result = retriever.retrieve(
                    query["text"],
                    tenant_id=query["tenant_id"],
                    top_k_initial=manifest["top_k_initial"],
                    final_k=manifest["k"],
                )
                stages = {
                    "dense": [
                        pq.KnowledgeChunk.from_payload(p, fallback_id=i).chunk_id
                        for i, _, p in client.observed_dense
                    ],
                    "sparse": [c.chunk_id for c, _ in retriever.bm25.observed_sparse],
                    "fusion": [r.chunk.chunk_id for r in retriever.observed_fusion],
                    "expansion": [r.chunk.chunk_id for r in retriever.observed_expansion],
                    "expansion_reranked": [r.chunk.chunk_id for r in result],
                }
                scores = {}
                for stage, ids in stages.items():
                    try:
                        scores[stage] = {
                            "ids": ids,
                            "metrics": old.metrics(ids, query["judgments"], manifest["k"]),
                        }
                    except ValueError:
                        scores[stage] = {
                            "ids": ids,
                            "metrics": None,
                            "reason": "judgments do not cover current corpus identities",
                        }
                report["measurements"].append(
                    {"query_id": query["id"], "status": "MEASURED", "stages": scores}
                )
        except Exception as exc:
            report["runtime_blocker"] = type(exc).__name__
    completed = {r["query_id"] for r in report["measurements"]}
    for query in manifest["queries"]:
        if query["id"] not in completed:
            report["measurements"].append(
                {
                    "query_id": query["id"],
                    "status": "BLOCKED",
                    "stages": {s: {"metrics": None, "ids": None} for s in STAGES},
                }
            )

    # No dense stand-in: evaluate only the actual BM25 implementation on the
    # versioned historical corpus in memory. No serving/quarantine claim follows.
    sparse = pq.BM25Index()
    for doc in corpus["documents"]:
        sparse.add(
            pq.KnowledgeChunk(
                chunk_id=doc["chunk_id"],
                tenant_id="experiment-a",
                text=doc["text"],
                source_type="internal_document",
                document_id=doc["chunk_id"],
                chunk_index=0,
                total_chunks=1,
                metadata={"evidence_level": "document", "source_class": "internal_document"},
            )
        )
    report["offline_snapshot_sparse"] = []
    for query in manifest["queries"]:
        ids = [
            c.chunk_id
            for c, _ in sparse.search(query["text"], tenant_id="experiment-a", limit=manifest["k"])
        ]
        report["offline_snapshot_sparse"].append(
            {
                "query_id": query["id"],
                "ids": ids,
                **old.metrics(ids, query["judgments"], manifest["k"]),
            }
        )
    report["offline_snapshot_limit"] = (
        "in-memory historical 64 passages treated as one diagnostic corpus; not live tenant visibility, dense quality, model provenance or agricultural validity"
    )
    report["status"] = (
        "BLOCKED" if any(r["status"] == "BLOCKED" for r in report["measurements"]) else "MEASURED"
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "live_queries": len(completed),
                "blocked_queries": len(manifest["queries"]) - len(completed),
                "offline_sparse_queries": len(report["offline_snapshot_sparse"]),
            }
        )
    )
    return 2 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
