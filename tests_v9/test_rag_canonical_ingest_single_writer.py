"""The canonical ingest keeps exactly one writer, and that writer stays one process.

RAG-INGEST-CROSS-REPLICA-PUBLICATION-NOT-COORDINATED-01 (open): rag-retrieval runs replicas
over one Qdrant collection with no shared lock, so two publications of one document racing
there can strip a chunk shared by both revisions from the winner (lab receipt 1582-v4).
#1582 closes the race where every publication starts: local-ai-rag, the only writer of
``/v1/ingest``, serialises publication per (tenant, document) in one process. That holds
only while (1) nothing else calls rag-retrieval's ingest, (2) local-ai-rag runs one worker
and one replica, and (3) the canonical call stays inside ``_publishing``. Each of these
fails here when it stops being true, so the mitigation cannot erode silently; the gap's
closing options (a shared per-document lock, or per-publication storage ids) are the way to
relax them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "services" / "local-ai-rag" / "main.py"
SOURCE_DIRS = ("services", "agents", "bots", "scripts", "shared", "deploy")
_HTTP_METHODS = {"post", "put", "request", "send"}


def _calls_rag_ingest(path: Path) -> bool:
    """An HTTP call whose URL names rag-retrieval's ingest (its configured URL or its host).

    Parsed, not grepped: a guard that only mentions the path in a string is not a writer.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) in _HTTP_METHODS):
            continue
        for arg in [*node.args, *(k.value for k in node.keywords)]:
            text = ast.unparse(arg)
            if "/v1/ingest" in text and ("RAG_RETRIEVAL_URL" in text or "rag-retrieval" in text):
                return True
    return False


def _sources():
    for top in SOURCE_DIRS:
        for path in (ROOT / top).rglob("*.py"):
            parts = set(path.parts)
            if "tests" in parts or path.name.startswith("test_") or "__pycache__" in parts:
                continue
            yield path


def test_only_local_ai_rag_calls_the_canonical_ingest():
    writers = sorted(str(p.relative_to(ROOT)) for p in _sources() if _calls_rag_ingest(p))
    assert writers == ["services/local-ai-rag/main.py"], (
        "a second writer of rag-retrieval /v1/ingest bypasses local-ai-rag's per-document "
        "serialisation (RAG-INGEST-CROSS-REPLICA-PUBLICATION-NOT-COORDINATED-01): " + str(writers)
    )


# Code that drives the indexing service's write path directly. Allowed, with the reason:
#   production_qdrant.py      the write path itself (ingest -> ingest_documents -> settle);
#   rag-retrieval/main.py     the indexing service's /v1/ingest handler, i.e. local-ai-rag's
#                             calls arriving;
#   rag-retrieval/reindex_manifest.py  builds a separate versioned target collection, never
#                             the live one that tenant uploads publish into;
#   qdrant-seed/seed.py       writes the reference corpus, which no tenant ingest withdraws.
_WRITE_CALLS = {
    "ingest",
    "ingest_documents",
    "withdraw_document_points",
    "settle_document_publications",
    "upsert",
}
_KNOWN_WRITE_PATHS = {
    "services/sahool-platform/core/rag/production_qdrant.py",
    "services/rag-retrieval/main.py",
    "services/rag-retrieval/reindex_manifest.py",
    "services/qdrant-seed/seed.py",
}
_INDEX_CLIENTS = ("production_qdrant", "HybridQdrantRetriever", "QdrantHttpClient")


def _drives_index_writes(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not any(name in text for name in _INDEX_CLIENTS):
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", None) in _WRITE_CALLS
        for n in ast.walk(tree)
    )


def test_nothing_else_drives_the_index_write_path_directly():
    drivers = sorted(
        str(p.relative_to(ROOT))
        for p in _sources()
        if _drives_index_writes(p) and str(p.relative_to(ROOT)) not in _KNOWN_WRITE_PATHS
    )
    assert drivers == [], (
        "a module calling the retriever's ingest/withdraw/settle or the Qdrant upsert "
        "directly bypasses local-ai-rag's per-document serialisation: " + str(drivers)
    )


def test_local_ai_rag_runs_one_worker():
    service = ROOT / "services" / "local-ai-rag"
    dockerfile = (service / "Dockerfile").read_text(encoding="utf-8")
    cmd = [line for line in dockerfile.splitlines() if line.strip().startswith("CMD")]
    assert len(cmd) == 1 and '"--workers", "1"' in cmd[0], (
        "more than one uvicorn worker splits the in-process publication locks"
    )
    assert "gunicorn" not in dockerfile.lower()
    assert not [p.name for p in service.iterdir() if p.name.startswith("gunicorn")], (
        "a gunicorn config would run local-ai-rag under several worker processes"
    )


def test_local_ai_rag_runs_one_replica():
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    start = compose.index("\n  sahool-local-ai-rag:\n")
    nxt = re.search(r"\n  [a-z0-9][a-z0-9_-]*:\n", compose[start + 1 :])
    block = compose[start : start + 1 + (nxt.start() if nxt else len(compose))]
    replicas = re.findall(r"replicas:\s*(\S+)", block)
    assert all(r.strip("'\"") == "1" for r in replicas), replicas
    assert "scale:" not in block
    # A command, entrypoint or worker setting here would replace the Dockerfile's one worker.
    for key in ("command:", "entrypoint:", "WEB_CONCURRENCY", "UVICORN_WORKERS", "--workers"):
        assert key not in block, f"compose sets {key!r} for local-ai-rag"
    for chart in (ROOT / "helm").rglob("*.yaml"):
        text = chart.read_text(encoding="utf-8", errors="replace")
        assert "local-ai-rag" not in text and "localAiRag" not in text, (
            f"{chart.relative_to(ROOT)} deploys local-ai-rag; a second replica splits the locks"
        )


def test_the_canonical_call_stays_inside_the_publication_lock():
    tree = ast.parse(WRITER.read_text(encoding="utf-8"))
    fn = next(
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "ingest_documents"
    )
    guarded = []
    for node in ast.walk(fn):
        if isinstance(node, ast.AsyncWith) and any(
            isinstance(item.context_expr, ast.Call)
            and getattr(item.context_expr.func, "id", None) == "_publishing"
            for item in node.items
        ):
            guarded.extend(
                inner
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and getattr(inner.func, "attr", None) == "post"
            )
    posts = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "post"
    ]
    assert posts and posts == guarded, "every canonical ingest POST must run inside _publishing"
