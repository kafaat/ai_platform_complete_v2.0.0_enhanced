"""Current-source W5 Arabic RAG baseline; absent dependencies produce no ranking scores.

What this tool touches, exactly ("read-only" means **no Qdrant writes**, nothing more):

* **Reads Qdrant.** ``GET /`` as a probe, then ``POST .../points/scroll`` and
  ``POST .../points/search``. Every other non-GET call is refused in-process before it
  is sent, so the tool cannot ingest, create a collection or delete points.
* **Consumes the embedding service.** ``GET /api/tags`` resolves the model digest, and
  one ``POST /api/embeddings`` per query computes the query vector. That is real load
  on the local Ollama; the tool pulls no model and substitutes none.
* **Writes one local report** at the explicit ``--output`` path, which must not exist
  yet. The file is created exclusively and never overwritten, so a run cannot replace
  the 17 October evidence (``baseline-results.json``) or any earlier run's report.

Only plain-HTTP loopback origins without credentials, path, query or fragment are
accepted. No prefix rewrite, reseed, model pull or model substitution. Snapshot BM25 is
explicitly a separate offline diagnostic, not a current-stack baseline.

Identity: the retriever keys its chunk cache by ``chunk_identity`` = ``(tenant_id,
chunk_id)`` (``services/sahool-platform/core/rag/production_qdrant.py``). The frozen
qrels are keyed by the logical ``chunk_id`` of the evaluated tenant. A chunk maps to a
qrel key only when its tenant is the query's tenant; another tenant's chunk (the global
reference corpus included) never counts. If such a chunk is eligible for the query, the
frozen judgments do not cover the eligible corpus and the query is blocked, not graded.

On failure the report keeps the exception class and a sanitized, length-capped detail:
credentials in URLs and secret-looking values are redacted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
STAGES = ("dense", "sparse", "fusion", "expansion", "expansion_reranked")
EXIT_OUTPUT_EXISTS = 3
DETAIL_CAP = 240
# A ranked result outside the evaluated tenant gets this key. It is never a qrel key
# (checked per query), so the metric refuses to grade it instead of counting it.
FOREIGN_PREFIX = "foreign-tenant:"

# userinfo: user and optional password without whitespace (a valid URL has none), so a
# later "@" in prose (``retry user@host``) is not swallowed with the text before it.
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]*(?::[^\s/@]*)?@")
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[^\s,;'\"]+")
# Unquoted ``key=value`` and quoted JSON / repr forms (``"api_key": "v"``, ``key='v'``),
# because a Qdrant HTTP error carries the raw (JSON) response body.
_SECRET_PAIR = re.compile(
    r"(?i)(?:\b(api[-_]?key|access[-_]?token|token|password|passwd|secret|authorization)|(?<=[?&])(key))"
    r"([\"']?\s*[:=]\s*[\"']?)([^\s,;&'\"}]+)"
)


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


def sanitize_detail(exc, secrets=()):
    """Exception message for the report: one line, no credentials, at most DETAIL_CAP chars."""
    # Bound the work before any pattern runs: the output is capped at DETAIL_CAP anyway, and
    # some inputs (long letter-and-dot runs) make the scheme pattern grow quadratically.
    text = str(exc)[:8192]
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _URL_USERINFO.sub(r"\1[REDACTED]@", text)
    text = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)} [REDACTED]", text)
    text = _SECRET_PAIR.sub(lambda m: f"{m.group(1) or m.group(2)}{m.group(3)}[REDACTED]", text)
    text = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
    if len(text) > DETAIL_CAP:
        text = text[: DETAIL_CAP - 1] + "…"
    return text


def qrel_key(chunk, tenant_id):
    """Qrel key for ``(tenant_id, chunk_id)``: the logical id for the evaluated tenant only."""
    if chunk.tenant_id == tenant_id:
        return chunk.chunk_id
    return f"{FOREIGN_PREFIX}{chunk.tenant_id}:{chunk.chunk_id}"


def evaluated_corpus(pq, chunks, query, reference_text):
    """The chunks eligible for ``query``, keyed by qrel key; raise when qrels do not cover them.

    ``chunks`` is the retriever's cache keyed by ``chunk_identity``. Only the query's
    tenant maps onto the qrels. An eligible chunk of another tenant blocks the query.
    """
    tenant_id = query["tenant_id"]
    judgments = query["judgments"]
    if any(str(key).startswith(FOREIGN_PREFIX) for key in judgments):
        raise ValueError("QREL_KEY_COLLIDES_WITH_FOREIGN_MARKER")
    own, foreign = {}, []
    for identity, chunk in chunks.items():
        if tuple(identity) != tuple(pq.chunk_identity(chunk)):
            raise ValueError("RETRIEVER_CHUNK_IDENTITY_CHANGED")
        if chunk.tenant_id not in {tenant_id, pq.GLOBAL_REFERENCE_TENANT}:
            continue
        if not pq.matches_scope_filters(chunk, {}):
            continue
        if chunk.tenant_id == tenant_id:
            own[chunk.chunk_id] = chunk
        else:
            foreign.append(identity)
    missing = set(judgments) - set(own)
    unjudged = set(own) - set(judgments)
    changed = [cid for cid, chunk in own.items() if chunk.text != reference_text.get(cid)]
    if foreign or missing or unjudged or changed:
        raise ValueError(
            f"CURRENT_CORPUS_NEEDS_NEW_JUDGMENTS: query {query['id']} tenant {tenant_id}: "
            f"{len(missing)} judged not visible, {len(unjudged)} visible unjudged, "
            f"{len(changed)} text changed, {len(foreign)} other-tenant visible"
        )
    return own


def score_stage(metrics, chunks, judgments, k, tenant_id):
    ids = [qrel_key(chunk, tenant_id) for chunk in chunks]
    entry = {"ids": ids, "identities": [[c.tenant_id, c.chunk_id] for c in chunks]}
    try:
        entry["metrics"] = metrics(ids, judgments, k)
    except ValueError:
        entry["metrics"] = None
        entry["reason"] = (
            "result includes chunks outside the evaluated tenant; not graded"
            if any(c.tenant_id != tenant_id for c in chunks)
            else "judgments do not cover current corpus identities"
        )
    return entry


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new report path; refused if it exists (the historical results are never rewritten)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    qurl, ourl = loopback(args.qdrant_url), loopback(args.ollama_url)
    # Checked before any request, so a refused run consumes no embedding call; the
    # exclusive create below still closes the window between this check and the write.
    # lexists: a dangling symlink also counts as an existing path.
    if os.path.lexists(args.output):
        print(f"refusing to overwrite existing report: {args.output}", file=sys.stderr)
        return EXIT_OUTPUT_EXISTS
    if not args.output.parent.is_dir():
        print(f"output directory does not exist: {args.output.parent}", file=sys.stderr)
        return EXIT_OUTPUT_EXISTS
    api_key = os.getenv("QDRANT_API_KEY")
    manifest = json.loads((HERE / "evaluation-v1.json").read_text(encoding="utf-8"))
    corpus_path = ROOT / manifest["corpus_path"]
    assert hashlib.sha256(corpus_path.read_bytes()).hexdigest() == manifest["corpus_sha256"]
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
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
        "access": "reads Qdrant; computes query embeddings on the local embedding service; "
        "writes this local report; no Qdrant writes",
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

    client = ReadOnlyClient(qurl, manifest["collection"], api_key=api_key, timeout_s=3)
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
                "error_detail": sanitize_detail(exc, (api_key,)),
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
                tenant_id = query["tenant_id"]
                evaluated_corpus(pq, retriever._chunks, query, reference_text)
                result = retriever.retrieve(
                    query["text"],
                    tenant_id=tenant_id,
                    top_k_initial=manifest["top_k_initial"],
                    final_k=manifest["k"],
                )
                stages = {
                    "dense": [
                        pq.KnowledgeChunk.from_payload(p, fallback_id=i)
                        for i, _, p in client.observed_dense
                    ],
                    "sparse": [c for c, _ in retriever.bm25.observed_sparse],
                    "fusion": [r.chunk for r in retriever.observed_fusion],
                    "expansion": [r.chunk for r in retriever.observed_expansion],
                    "expansion_reranked": [r.chunk for r in result],
                }
                scores = {
                    stage: score_stage(
                        old.metrics, chunks, query["judgments"], manifest["k"], tenant_id
                    )
                    for stage, chunks in stages.items()
                }
                report["measurements"].append(
                    {"query_id": query["id"], "status": "MEASURED", "stages": scores}
                )
        except Exception as exc:
            report["runtime_blocker"] = type(exc).__name__
            report["runtime_blocker_detail"] = sanitize_detail(exc, (api_key,))
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
    try:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError:
        print(f"refusing to overwrite existing report: {args.output}", file=sys.stderr)
        return EXIT_OUTPUT_EXISTS
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
