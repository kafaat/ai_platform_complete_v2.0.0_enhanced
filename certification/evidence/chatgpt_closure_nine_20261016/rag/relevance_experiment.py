"""Read-only Arabic Nomic experiment over two pre-existing isolated collections.

No collection creation, ingestion, deletion, alias cutover, or production source
change. A completed measurement is not an approval or a gap-closure verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
STAGES = ("dense", "sparse", "fusion", "expansion_reranked")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def metrics(ids, judgments, k):
    if type(k) is not int or k < 1 or len(ids) != len(set(ids)):
        raise ValueError("positive k and unique ranked identities required")
    if set(ids) - set(judgments):
        raise ValueError("unjudged result; do not silently grade it as irrelevant")
    if any(type(g) is not int or not 0 <= g <= 3 for g in judgments.values()):
        raise ValueError("relevance grades must be integers from zero through three")
    relevant = sum(g > 0 for g in judgments.values())
    if not relevant:
        raise ValueError("positive relevance judgment required for ranking metrics")
    gains = [judgments[cid] for cid in ids[:k]]
    ideal = sorted(judgments.values(), reverse=True)[:k]

    def dcg(gs):
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gs))

    return {
        "precision_at_k": sum(g > 0 for g in gains) / k,
        "recall_at_k": sum(g > 0 for g in gains) / relevant,
        "mrr_at_k": next((1 / (i + 1) for i, g in enumerate(gains) if g), 0),
        "ndcg_at_k": dcg(gains) / dcg(ideal),
    }


def validate_manifest(manifest):
    for key in ("version", "judgment_provenance", "model", "model_digest", "subject_sha"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"missing manifest {key}")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["subject_sha"]):
        raise ValueError("subject SHA must be pinned")
    if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", manifest["model_digest"]):
        raise ValueError("exact model digest required")
    if manifest["model"].split(":")[0] not in {
        "nomic-embed-text",
        "nomic-ai/nomic-embed-text-v1.5",
    }:
        raise ValueError("this experiment is specifically for the Nomic text contract")
    names = manifest.get("collections", {})
    if set(names) != {"raw", "prefixed"} or len(set(names.values())) != 2:
        raise ValueError("two distinct raw/prefixed collections required")
    if any(not re.fullmatch(r"sahool_rag_experiment_[a-zA-Z0-9_-]+", v) for v in names.values()):
        raise ValueError("only explicitly named isolated experiment collections allowed")
    queries = manifest.get("queries", [])
    if not queries or {q.get("split") for q in queries} != {"selection", "acceptance"}:
        raise ValueError("separate selection and acceptance queries required")
    if len({q.get("id") for q in queries}) != len(queries):
        raise ValueError("duplicate query identity")
    if len({q.get("text") for q in queries}) != len(queries):
        raise ValueError("query text overlaps across selection and acceptance")
    for q in queries:
        if not q.get("id") or not re.search(r"[\u0600-\u06ff]", q.get("text", "")):
            raise ValueError("identified Arabic queries required")
        if not q.get("tenant_id") or q["tenant_id"].startswith("__"):
            raise ValueError("explicit ordinary tenant required")
        metrics([], q.get("judgments", {}), manifest.get("k", 5))


def load_module():
    spec = importlib.util.spec_from_file_location("rag_relevance_subject", SOURCE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def safe_endpoint(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("HTTP endpoint without URL credentials required")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("endpoint must be an origin")
    return value.rstrip("/")


def read_points(client, max_points):
    rows, offset, seen = [], None, set()
    while True:
        body = {"limit": min(128, max_points + 1), "with_payload": True, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        result = client._request("POST", f"/collections/{client.collection}/points/scroll", body)
        result = result["result"]
        rows.extend(result["points"])
        if len(rows) > max_points:
            raise ValueError("bounded corpus exceeded; no partial experiment accepted")
        offset = result.get("next_page_offset")
        if offset is None:
            break
        key = str(offset)
        if key in seen:
            raise ValueError("Qdrant scroll cycle")
        seen.add(key)
    if not rows or len({str(r["id"]) for r in rows}) != len(rows):
        raise ValueError("empty or duplicate point inventory")
    return sorted(rows, key=lambda r: str(r["id"]))


def vector_matches(actual, expected):
    return (
        isinstance(actual, list)
        and len(actual) == len(expected)
        and bool(expected)
        and any(float(v) != 0 for v in expected)
        and all(
            math.isfinite(float(a))
            and math.isfinite(float(b))
            and math.isclose(float(a), float(b), rel_tol=1e-4, abs_tol=1e-5)
            for a, b in zip(actual, expected, strict=True)
        )
    )


def cosine_storage_vector(vector):
    """Qdrant normalizes vectors on insertion for a Cosine collection."""
    norm = math.sqrt(sum(float(v) ** 2 for v in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("finite nonzero vector required")
    return [float(v) / norm for v in vector]


class NomicOnnx:
    """Actual CPU model; no hash fallback or fake Ollama server."""

    def __init__(self, model_dir):
        if os.getenv("ORT_DISABLE_TELEMETRY") != "1":
            raise ValueError("ORT_DISABLE_TELEMETRY=1 is required before process launch")
        from fastembed import TextEmbedding

        self.path = Path(model_dir)
        self.model = TextEmbedding(
            "nomic-ai/nomic-embed-text-v1.5",
            specific_model_path=str(self.path),
            local_files_only=True,
            threads=2,
        )
        self.cache = {}

    def embed(self, text):
        if text not in self.cache:
            self.cache[text] = list(self.model.embed([text]))[0].tolist()
        return self.cache[text]

    def identity(self):
        from importlib.metadata import version

        return {
            "backend": "fastembed-onnx-cpu-not-ollama",
            "fastembed_version": version("fastembed"),
            "onnxruntime_version": version("onnxruntime"),
            "model_digest": hashlib.sha256(
                (self.path / "onnx/model.onnx").read_bytes()
            ).hexdigest(),
            "tokenizer_digest": hashlib.sha256(
                (self.path / "tokenizer.json").read_bytes()
            ).hexdigest(),
        }


def run(manifest, *, qdrant_url, ollama_url=None, onnx_model_dir=None):
    validate_manifest(manifest)
    actual_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual_sha != manifest["subject_sha"]:
        raise ValueError("manifest source SHA differs from current checkout")
    if subprocess.check_output(["git", "diff", "HEAD", "--", str(SOURCE)], cwd=ROOT):
        raise ValueError("retrieval source has uncommitted changes")
    pq = load_module()
    qdrant_url = safe_endpoint(qdrant_url)
    api_key = os.getenv("RAG_EXPERIMENT_QDRANT_API_KEY") or None
    model = manifest["model"]
    if onnx_model_dir:
        if model != "nomic-ai/nomic-embed-text-v1.5":
            raise ValueError("ONNX runtime needs exact supported model name")
        embed = NomicOnnx(onnx_model_dir)
        model_api = None
    else:
        ollama_url = safe_endpoint(ollama_url)
        embed = pq.OllamaEmbeddingProvider(ollama_url, model)
        model_api = pq.QdrantHttpClient(ollama_url, "unused")

    def identity():
        if onnx_model_dir:
            observed = embed.identity()
            if observed["model_digest"] != manifest["model_digest"]:
                raise ValueError("ONNX model digest differs from pinned manifest")
            return observed
        tags = model_api._request("GET", "/api/tags")["models"]
        matched = [t for t in tags if t.get("name") == model or t.get("model") == model]
        if len(matched) != 1 or matched[0]["digest"] != manifest["model_digest"]:
            raise ValueError("loaded Nomic identity does not match pinned manifest")
        return {"model_digest": matched[0]["digest"], **model_api._request("GET", "/api/version")}

    model_before = identity()
    max_points = manifest.get("max_points", 1000)
    if type(max_points) is not int or not 1 <= max_points <= 10000:
        raise ValueError("explicit bounded experiment corpus required")
    inventories, measurements = {}, {}
    qdrant_version = None
    k = manifest.get("k", 5)
    for mode, collection in manifest["collections"].items():
        client = pq.QdrantHttpClient(qdrant_url, collection, api_key=api_key)
        version = client._request("GET", "/")["version"]
        if qdrant_version is not None and qdrant_version != version:
            raise ValueError("Qdrant version changed during experiment")
        qdrant_version = version
        points = read_points(client, max_points)
        config = client._request("GET", f"/collections/{collection}")["result"]["config"]["params"][
            "vectors"
        ]
        if config.get("distance") != "Cosine":
            raise ValueError("experiment requires the source's Cosine collection contract")
        inventory = [(str(r["id"]), r["payload"]) for r in points]
        inventories[mode] = digest(inventory)
        chunks = {}
        for point in points:
            chunk = pq.KnowledgeChunk.from_payload(point["payload"], fallback_id=str(point["id"]))
            if chunk.chunk_id in chunks:
                raise ValueError("logical identity collision requires explicit disposition")
            chunks[chunk.chunk_id] = chunk
            prefix = "search_document: " if mode == "prefixed" else ""
            if not vector_matches(
                point["vector"], cosine_storage_vector(embed.embed(prefix + chunk.text))
            ):
                raise ValueError("stored document vector differs from observed model/prefix")
        if "__seed_quarantine__" not in {c.tenant_id for c in chunks.values()}:
            raise ValueError("quarantine adversarial documents required")
        retriever = pq.HybridQdrantRetriever(client, embed)
        retriever._chunks = chunks
        retriever.bm25.rebuild(list(chunks.values()))
        query_rows = []
        for query in manifest["queries"]:
            tenant, filters = query["tenant_id"], query.get("filters", {})
            if not any(
                c.tenant_id not in {tenant, "__global__", "__seed_quarantine__"}
                for c in chunks.values()
            ):
                raise ValueError("cross-tenant adversarial documents required")
            visible = {
                cid
                for cid, c in chunks.items()
                if c.tenant_id in {tenant, "__global__"} and pq.matches_scope_filters(c, filters)
            }
            if set(query["judgments"]) != visible:
                raise ValueError("judgments must cover precisely the entire eligible corpus")
            prefix = "search_query: " if mode == "prefixed" else ""
            dense = client.search(
                embed.embed(prefix + query["text"]), tenant_id=tenant, filters=filters, limit=12
            )
            dense_map = {
                pq.KnowledgeChunk.from_payload(p, fallback_id=i).chunk_id: s for i, s, p in dense
            }
            sparse_map = {
                c.chunk_id: s
                for c, s in retriever.bm25.search(
                    query["text"], tenant_id=tenant, filters=filters, limit=12
                )
            }
            scores, dr, sr = pq.weighted_rrf_scores(dense_map, sparse_map)
            fused = [
                pq.RetrievedAnnotation(
                    chunks[cid],
                    dense_map.get(cid),
                    sparse_map.get(cid),
                    scores[cid],
                    dense_rank=dr.get(cid),
                    bm25_rank=sr.get(cid),
                )
                for cid in sorted(scores, key=lambda cid: (-scores[cid], cid))[:12]
            ]
            expanded = retriever._rerank(
                query["text"], retriever._expand_neighbors(fused, filters=filters)
            )
            stages = {
                "dense": sorted(dense_map, key=lambda cid: (-dense_map[cid], cid)),
                "sparse": sorted(sparse_map, key=lambda cid: (-sparse_map[cid], cid)),
                "fusion": [r.chunk.chunk_id for r in fused],
                "expansion_reranked": [r.chunk.chunk_id for r in expanded],
            }
            if any(set(ids) - visible for ids in stages.values()):
                raise ValueError("tenant, quarantine, or scope leak detected")
            query_rows.append(
                {
                    "id": query["id"],
                    "split": query["split"],
                    "stages": {
                        stage: {"ids": ids[:k], **metrics(ids, query["judgments"], k)}
                        for stage, ids in stages.items()
                    },
                }
            )
        if (
            digest([(str(r["id"]), r["payload"]) for r in read_points(client, max_points)])
            != inventories[mode]
        ):
            raise ValueError("corpus changed during experiment")
        measurements[mode] = query_rows
    if len(set(inventories.values())) != 1:
        raise ValueError("raw/prefixed corpora differ; paired comparison invalid")
    if identity() != model_before:
        raise ValueError("model changed during experiment")
    aggregates = {}
    for mode, rows in measurements.items():
        aggregates[mode] = {}
        for split in ("selection", "acceptance"):
            selected = [r for r in rows if r["split"] == split]
            aggregates[mode][split] = {
                stage: {
                    metric: sum(r["stages"][stage][metric] for r in selected) / len(selected)
                    for metric in metrics([], manifest["queries"][0]["judgments"], k)
                }
                for stage in STAGES
            }
    return {
        "schema": "sahool.arabic-relevance-experiment/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": actual_sha,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "manifest_sha256": digest(manifest),
        "model": model_before,
        "qdrant_version": qdrant_version,
        "payload_inventory_sha256": inventories,
        "measurements": measurements,
        "aggregates": aggregates,
        "paired_deltas": {
            split: {
                stage: {
                    metric: aggregates["prefixed"][split][stage][metric]
                    - aggregates["raw"][split][stage][metric]
                    for metric in aggregates["raw"][split][stage]
                }
                for stage in STAGES
            }
            for split in ("selection", "acceptance")
        },
        "read_only": True,
        "cutover_authorized": False,
        "gap_closure": False,
        "acceptance": "REQUIRES_REVIEW_OF_VERSIONED_JUDGMENTS_AND_PAIRED_RESULTS",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--onnx-model-dir", type=Path)
    args = parser.parse_args()
    result = run(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        qdrant_url=os.environ["RAG_EXPERIMENT_QDRANT_URL"],
        ollama_url=os.getenv("RAG_EXPERIMENT_OLLAMA_URL"),
        onnx_model_dir=args.onnx_model_dir,
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
