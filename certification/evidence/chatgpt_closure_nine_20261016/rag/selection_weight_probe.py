"""Selection-only parameter exploration; does not change production retrieval."""

import argparse
import importlib.util
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runtime-root", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
args = parser.parse_args()
b = args.runtime_root.resolve()
p = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location("e", p / "relevance_experiment.py")
e = importlib.util.module_from_spec(s)
s.loader.exec_module(e)
pq = e.load_module()
manifest = json.loads((p / "experiment-manifest.json").read_text())
corpus = json.loads((p / "arabic-corpus-v1.json").read_text())
logs = [
    (args.work_dir / "weight-qdrant.log").open("w"),
    (args.work_dir / "weight-ollama.log").open("w"),
]
servers = [
    subprocess.Popen(
        [
            str(b / "rag-runtime-native/qdrant"),
            "--config-path",
            str(b / "rag-runtime-native/config/experiment.yaml"),
        ],
        cwd=b / "rag-runtime-native",
        stdout=logs[0],
        stderr=logs[0],
    ),
    subprocess.Popen(
        [str(b / "rag-ollama-runtime/bin/ollama"), "serve"],
        env={
            **os.environ,
            "OLLAMA_HOST": "127.0.0.1:11435",
            "OLLAMA_MODELS": str(b / "rag-ollama-runtime/models"),
            "OLLAMA_NO_CLOUD": "true",
        },
        stdout=logs[1],
        stderr=logs[1],
    ),
]
try:
    for url in ["http://127.0.0.1:16333/", "http://127.0.0.1:11435/api/tags"]:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    json.load(r)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("native server unavailable")
    modelapi = pq.QdrantHttpClient("http://127.0.0.1:11435", "unused")
    assert modelapi._request("GET", "/api/tags")["models"][0]["digest"] == manifest["model_digest"]
    embed = pq.OllamaEmbeddingProvider("http://127.0.0.1:11435", "nomic-embed-text:latest", 120)
    cl = pq.QdrantHttpClient("http://127.0.0.1:16333", manifest["collections"]["prefixed"])
    stored = cl.scroll_payloads()
    expected = json.loads((p / "real-experiment-results.json").read_text())[
        "payload_inventory_sha256"
    ]["prefixed"]
    assert e.digest(sorted(stored, key=lambda row: row[0])) == expected
    chunks = {}
    for i, payload in stored:
        c = pq.KnowledgeChunk.from_payload(payload, fallback_id=i)
        chunks[c.chunk_id] = c
    retriever = pq.HybridQdrantRetriever(cl, embed)
    retriever._chunks = chunks
    retriever.bm25.rebuild(list(chunks.values()))

    def measures(query, weights):
        dense = {
            pq.KnowledgeChunk.from_payload(p, fallback_id=i).chunk_id: s
            for i, s, p in cl.search(
                embed.embed("search_query: " + query["text"]),
                tenant_id=query["tenant_id"],
                limit=12,
            )
        }
        sparse = {
            c.chunk_id: s
            for c, s in retriever.bm25.search(query["text"], tenant_id=query["tenant_id"], limit=12)
        }
        output = {}
        for weight in weights:
            scores, dr, sr = pq.weighted_rrf_scores(
                dense, sparse, dense_weight=weight, sparse_weight=1 - weight
            )
            fused = [
                pq.RetrievedAnnotation(
                    chunks[cid],
                    dense.get(cid),
                    sparse.get(cid),
                    scores[cid],
                    dense_rank=dr.get(cid),
                    bm25_rank=sr.get(cid),
                )
                for cid in sorted(scores, key=lambda cid: (-scores[cid], cid))[:12]
            ]
            results = retriever._rerank(
                query["text"], retriever._expand_neighbors(fused, filters={})
            )
            ids = [r.chunk.chunk_id for r in results]
            output[str(weight)] = {"ids": ids[:5], **e.metrics(ids, query["judgments"], 5)}
        return output

    weights = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    selection = [
        {"id": q["id"], "metrics": measures(q, weights)}
        for q in corpus["queries"]
        if q["split"] == "selection"
    ]
    aggregate = {
        str(w): {
            metric: sum(row["metrics"][str(w)][metric] for row in selection) / len(selection)
            for metric in ["precision_at_k", "recall_at_k", "mrr_at_k", "ndcg_at_k"]
        }
        for w in weights
    }
    chosen = max(
        weights,
        key=lambda w: (
            aggregate[str(w)]["ndcg_at_k"],
            aggregate[str(w)]["mrr_at_k"],
            -abs(0.7 - w),
        ),
    )
    decision = {
        "selection": selection,
        "selection_aggregate": aggregate,
        "chosen_dense_weight": chosen,
        "chosen_sparse_weight": 1 - chosen,
        "criterion": "max selection-only final nDCG@5; then MRR@5; then proximity to existing0.7. Both signals required nonzero.",
        "production_changed": False,
        "acceptance_queries_used_for_selection": False,
    }
    (p / "selection-weight-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n"
    )
    acceptance = [
        {"id": q["id"], "metrics": measures(q, [chosen])[str(chosen)]}
        for q in corpus["queries"]
        if q["split"] == "acceptance"
    ]
    final = {
        "chosen_dense_weight": chosen,
        "acceptance": acceptance,
        "aggregate": {
            metric: sum(row["metrics"][metric] for row in acceptance) / len(acceptance)
            for metric in ["precision_at_k", "recall_at_k", "mrr_at_k", "ndcg_at_k"]
        },
        "production_changed": False,
        "reserved_fusion_scope_not_edited": True,
        "interpretation": "Diagnostic candidate only; reserved fusion owner coordination and expanded independent relevance acceptance remain.",
    }
    (p / "selection-weight-validation.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(final), flush=True)
finally:
    for s in servers:
        s.terminate()
    for s in servers:
        s.wait(timeout=20)
    for f in logs:
        f.close()
