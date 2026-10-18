"""Reproducible synthetic fixture experiment; NOT live Qdrant/Ollama or prefix-quality proof."""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--before", type=Path, required=True)
parser.add_argument("--after", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
FIXTURE = {
    "version": "arabic-scope-safety-v1",
    "synthetic": True,
    "topics": [
        ["wheat", "القمح", "ري القمح ومراقبة رطوبة التربة", "تسجيل كمية المياه قبل ري القمح"],
        ["grape", "العنب", "تقليم العنب ومراقبة نمو الأوراق", "توثيق مرحلة نمو العنب قبل التقليم"],
        [
            "soil",
            "الملوحة",
            "قياس الملوحة في التربة قبل إدارة الري",
            "عينات التربة تساعد متابعة الملوحة",
        ],
        ["maize", "الذرة", "حصاد الذرة وتسجيل الإنتاج", "مراقبة رطوبة محصول الذرة قبل الحصاد"],
    ],
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def measure(repo, name):
    pq = load(repo / "services/sahool-platform/core/rag/production_qdrant.py", name)
    embed = pq.HashEmbeddingProvider(256)
    chunks = []
    for topic, _term, primary, context in FIXTURE["topics"]:
        for i, text in enumerate([primary, context]):
            chunks.append(
                pq.KnowledgeChunk(
                    chunk_id=f"{topic}-{i}",
                    tenant_id="__global__",
                    text=text,
                    source_type="curated_reference",
                    document_id=topic,
                    chunk_index=i,
                    total_chunks=2,
                    metadata={
                        "evidence_level": "document",
                        "source_uri": f"fixture://{topic}",
                        "source_revision": FIXTURE["version"],
                        "publisher": "fixture",
                        "license": "synthetic",
                    },
                )
            )
    for tenant in ["tenant-b", "__seed_quarantine__"]:
        chunks.append(
            pq.KnowledgeChunk(
                chunk_id=tenant,
                tenant_id=tenant,
                text="القمح العنب الملوحة الذرة",
                source_type="uploaded_document",
                document_id=tenant,
                chunk_index=0,
                total_chunks=1,
                metadata={
                    "evidence_level": "document",
                    "source_uri": "fixture://blocked",
                    "source_revision": "v1",
                },
            )
        )

    class Store:
        vector_size = 256

        def search(self, vector, *, tenant_id, filters=None, limit=12):
            candidates = [
                c
                for c in chunks
                if c.tenant_id in {tenant_id, "__global__"} and pq.matches_scope_filters(c, filters)
            ]
            scored = [
                (
                    c.chunk_id,
                    sum(a * b for a, b in zip(vector, embed.embed(c.text), strict=True)),
                    c.payload,
                )
                for c in candidates
            ]
            return sorted(scored, key=lambda row: (-row[1], row[0]))[:limit]

        def scroll_payloads(self):
            return [(c.chunk_id, c.payload) for c in chunks]

    store = Store()
    retriever = pq.HybridQdrantRetriever(store, embed)
    retriever.rebuild_sparse_index()
    results = []
    for topic, query, _, _ in FIXTURE["topics"]:
        filters = {"crop": topic, "region": "YE", "field_id": "fixture-field"}
        dense = [
            r[0]
            for r in store.search(
                embed.embed(query), tenant_id="tenant-a", filters=filters, limit=3
            )
        ]
        sparse = [
            r[0].chunk_id
            for r in retriever.bm25.search(query, tenant_id="tenant-a", filters=filters, limit=3)
        ]
        hybrid_rows = retriever.retrieve(query, tenant_id="tenant-a", filters=filters, final_k=3)
        hybrid = [r.chunk.chunk_id for r in hybrid_rows]
        relevant = {f"{topic}-0", f"{topic}-1"}
        modes = {}
        for mode, ids in [("dense", dense), ("sparse", sparse), ("fusion_with_expansion", hybrid)]:
            gains = [int(cid in relevant) for cid in ids]
            hits = sum(gains)
            modes[mode] = {
                "ids": ids,
                "precision_at_3": hits / 3,
                "recall_at_3": hits / 2,
                "mrr": next((1 / (i + 1) for i, g in enumerate(gains) if g), 0),
                "ndcg_at_3": sum(g / math.log2(i + 2) for i, g in enumerate(gains))
                / (1 + 1 / math.log2(3)),
                "tenant_or_quarantine_leaks": sum(
                    cid in {"tenant-b", "__seed_quarantine__"} for cid in ids
                ),
            }
        modes["fusion_with_expansion"]["neighbor_fraction"] = sum(
            r.role == "neighbor" for r in hybrid_rows
        ) / max(1, len(hybrid_rows))
        results.append({"query": query, "modes": modes})
    aggregate = {}
    for mode in results[0]["modes"]:
        aggregate[mode] = {
            key: sum(row["modes"][mode][key] for row in results) / len(results)
            for key in results[0]["modes"][mode]
            if key != "ids"
        }
    return {"aggregate": aggregate, "queries": results}


output = {
    "classification": "OFFLINE_SYNTHETIC_SAFETY_FIXTURE_NOT_LIVE_RETRIEVAL_QUALITY",
    "fixture": FIXTURE,
    "fixture_sha256": hashlib.sha256(
        json.dumps(FIXTURE, ensure_ascii=True, sort_keys=True).encode()
    ).hexdigest(),
    "embedding": "HashEmbeddingProvider256; no Ollama, no Nomic, no prefix changes",
    "scope": "Exact in-process retrieval behavior; dense candidate store is a simulator, not live Qdrant.",
    "before": measure(args.before.resolve(), "arabic_before"),
    "after": measure(args.after.resolve(), "arabic_after"),
    "rag01_empirical_gate_satisfied": False,
    "rag07_reindex_executed": False,
}
args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    json.dumps(
        {"before": output["before"]["aggregate"], "after": output["after"]["aggregate"]}, indent=2
    )
)
