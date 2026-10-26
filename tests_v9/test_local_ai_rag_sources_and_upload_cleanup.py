"""local-ai-rag: a refusal cites nothing, global chunks cite their real source, temp files go.

- ``query_rag`` returned every retrieved chunk as ``sources`` even when the model answered
  with the grounded refusal, and cited ``__global__`` reference chunks (which carry
  ``source_uri``/``publisher``, not ``source_file``) as ``"unknown"`` page 0.
- ``/v1/ingest`` removed its temp files only on success: an unsupported or oversized later
  file, or a failed ingest, left the earlier ones on disk.

The real functions are compiled out of ``main.py`` with injected doubles — no LangChain,
Qdrant or Ollama.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import logging
import sys
import tempfile
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "services" / "local-ai-rag" / "main.py"
REFUSAL = "لا تتوفّر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال."


class _HTTPError(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _functions(names: set[str], namespace: dict) -> dict:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    nodes = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
    ]
    assert {n.name for n in nodes} == names
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN), "exec"), namespace)
    return namespace


# ── sources ─────────────────────────────────────────────────────────────────


def _query(monkeypatch, metas, answer):
    class _Doc:
        def __init__(self, meta):
            self.page_content = "سياق"
            self.metadata = meta

    class _VS:
        def as_retriever(self, **_kw):
            return types.SimpleNamespace(invoke=lambda _q: [_Doc(m) for m in metas])

    class _LLM:
        def invoke(self, _prompt):
            return types.SimpleNamespace(content=answer)

    async def _shadow(*_a):
        return None

    models = types.ModuleType("qdrant_client.http.models")
    models.FieldCondition = models.Filter = models.MatchAny = lambda **kw: kw
    http = types.ModuleType("qdrant_client.http")
    http.models = models
    root = types.ModuleType("qdrant_client")
    root.http = http
    monkeypatch.setitem(sys.modules, "qdrant_client", root)
    monkeypatch.setitem(sys.modules, "qdrant_client.http", http)
    monkeypatch.setitem(sys.modules, "qdrant_client.http.models", models)
    namespace = {
        "asyncio": asyncio,
        "init_vectorstore": _VS,
        "init_llm": _LLM,
        "init_retry": types.SimpleNamespace(
            assert_legacy_encoder_hits=lambda *_a: None, InitNotReady=RuntimeError
        ),
        "HTTPException": _HTTPError,
        "_shadow_canonical_retrieval": _shadow,
        "_GLOBAL_REFERENCE_TENANT": "__global__",
        "_NO_KNOWLEDGE_AR": REFUSAL,
        "_GROUNDED_PROMPT": "{context}\n{question}",
        "LLM_MODEL": "m",
        "COLLECTION_NAME": "sahool_agri_kb",
        "datetime": dt.datetime,
        "UTC": dt.UTC,
        "logger": logging.getLogger("test-local-ai-rag-sources"),
        "Document": object,
    }
    query_rag = _functions({"query_rag", "_is_refusal_answer", "_source_citation"}, namespace)[
        "query_rag"
    ]
    return asyncio.run(query_rag("كيف أسمّد القمح؟", "t1"))


_FILE = {"tenant_id": "t1", "source_file": "wheat.pdf", "page": 3}
_GLOBAL = {
    "tenant_id": "__global__",
    "source_uri": "https://www.fao.org/wheat-guide",
    "publisher": "FAO",
}


@pytest.mark.parametrize(
    "answer",
    [
        REFUSAL,
        f"«{REFUSAL}»",
        # the model dropped the shadda — still the refusal
        "لا تتوفر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال",
    ],
)
def test_a_refusal_cites_no_sources(monkeypatch, answer):
    out = _query(monkeypatch, [_FILE, _GLOBAL], answer)
    assert out["answer"] == answer
    assert out["sources"] == []


def test_a_grounded_answer_still_cites_its_chunks(monkeypatch):
    out = _query(monkeypatch, [_FILE], "يُسمَّد القمح على دفعتين.")
    assert [(s["source"], s["page"]) for s in out["sources"]] == [("wheat.pdf", 3)]


def test_a_global_chunk_is_cited_by_its_uri_and_publisher(monkeypatch):
    out = _query(monkeypatch, [_GLOBAL], "يُسمَّد القمح على دفعتين.")
    (citation,) = out["sources"]
    assert citation["source"] == "https://www.fao.org/wheat-guide"
    assert citation["publisher"] == "FAO"
    assert citation["page"] is None, "no page is known; page 0 is a fabricated locator"


# ── upload temp files ─────────────────────────────────────────────────────────


class _Upload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data

    async def read(self, n: int) -> bytes:
        chunk, self._data = self._data[:n], self._data[n:]
        return chunk


def _ingest_endpoint(monkeypatch, tmp_path, ingest_documents, max_mb=1):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    stub = lambda *_a, **_k: None  # noqa: E731
    namespace = {
        "tempfile": tempfile,
        "Path": Path,
        "HTTPException": _HTTPError,
        "MAX_UPLOAD_MB": max_mb,
        "ingest_documents": ingest_documents,
        "_require_service_token": stub,
        "_require_ready": stub,
        "_validate_tenant_id": lambda t: t,
        "File": stub,
        "Form": stub,
        "Header": stub,
        "UploadFile": object,
    }
    return _functions({"ingest_endpoint"}, namespace)["ingest_endpoint"]


async def _ok_ingest(paths, tenant_id, *, source_names):
    return {"chunks": len(paths)}


async def _failing_ingest(paths, tenant_id, *, source_names):
    assert all(p.exists() for p in paths)
    raise RuntimeError("qdrant down")


@pytest.mark.parametrize(
    ("files", "ingest", "error"),
    [
        ([("a.txt", b"one"), ("b.exe", b"x")], _ok_ingest, _HTTPError),
        ([("a.txt", b"one"), ("b.txt", b"x" * (1024 * 1024 + 1))], _ok_ingest, _HTTPError),
        ([("a.txt", b"one"), ("b.md", b"two")], _failing_ingest, RuntimeError),
    ],
    ids=["unsupported-later-file", "oversized-later-file", "ingest-fails"],
)
def test_temp_files_are_removed_when_the_upload_fails(monkeypatch, tmp_path, files, ingest, error):
    endpoint = _ingest_endpoint(monkeypatch, tmp_path, ingest)
    uploads = [_Upload(name, data) for name, data in files]
    with pytest.raises(error):
        asyncio.run(endpoint(files=uploads, tenant_id="t1", x_agent_token="tok"))
    assert list(tmp_path.iterdir()) == []


def test_temp_files_are_removed_after_a_successful_upload(monkeypatch, tmp_path):
    endpoint = _ingest_endpoint(monkeypatch, tmp_path, _ok_ingest)
    out = asyncio.run(
        endpoint(files=[_Upload("a.txt", b"one")], tenant_id="t1", x_agent_token="tok")
    )
    assert out == {"status": "ingested", "chunks": 1}
    assert list(tmp_path.iterdir()) == []
