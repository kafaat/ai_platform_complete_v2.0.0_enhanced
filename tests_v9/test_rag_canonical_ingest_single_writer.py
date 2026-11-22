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


def test_local_ai_rag_runs_one_worker():
    dockerfile = (ROOT / "services" / "local-ai-rag" / "Dockerfile").read_text(encoding="utf-8")
    cmd = [line for line in dockerfile.splitlines() if line.strip().startswith("CMD")]
    assert len(cmd) == 1 and '"--workers", "1"' in cmd[0], (
        "more than one uvicorn worker splits the in-process publication locks"
    )


def test_local_ai_rag_runs_one_replica():
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    start = compose.index("\n  sahool-local-ai-rag:\n")
    nxt = re.search(r"\n  [a-z0-9][a-z0-9_-]*:\n", compose[start + 1 :])
    block = compose[start : start + 1 + (nxt.start() if nxt else len(compose))]
    replicas = re.findall(r"replicas:\s*(\S+)", block)
    assert all(r.strip("'\"") == "1" for r in replicas), replicas
    assert "scale:" not in block
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
