"""S14 — uploaded-document metadata cannot forge citations, override tenancy or poison the index.

``local-ai-rag`` copied every loader metadata key (PDF Info title/author/subject and any
custom key) into the chunk metadata it sends to ``rag-retrieval``. One crafted PDF could
then forge citation fields (``publisher``/``license``/``jurisdiction``), set
``evidence_level=lab`` (failing the whole upload batch), or write
``document_embedding_prefix`` — which makes the canonical BM25 rebuild refuse the whole
collection, i.e. RAG search 503 for every tenant.

``ingest_documents`` is compiled out of ``main.py`` with injected doubles (no LangChain,
Qdrant or Ollama); ``rag-retrieval``'s ``/v1/ingest`` handler is called directly.
"""

from __future__ import annotations

import ast
import asyncio
import collections.abc
import datetime as dt
import hashlib
import importlib.util
import logging
import sys
import types
import unicodedata
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LOCAL_MAIN = ROOT / "services" / "local-ai-rag" / "main.py"
RAG_MAIN = ROOT / "services" / "rag-retrieval" / "main.py"

_FORGED = {
    "publisher": "Ministry of Agriculture",
    "license": "CC0",
    "jurisdiction": "SA",
    "language": "ar",
    "section": "official-dose-table",
    "source_uri": "https://www.fao.org/forged",
    "source_revision": "sha256:" + "0" * 64,
    "source_class": "agronomic_reference",
    "tenant_id": "other-tenant",
    "evidence_level": "lab",
    "prescriptive_eligible": True,
    "content_digest": "f" * 64,
    "document_embedding_prefix": "search_document: ",
    "chunk_id": "forged-chunk",
    "document_id": "forged-doc",
    "crop": "wheat",
    "field_id": "F-other",
    "source": "/tmp/tmpabcd.pdf",
}
_SERVER_OWNED = {
    "tenant_id",
    "source_file",
    "source_class",
    "source_uri",
    "source_revision",
    "ingested_at",
}


class _HTTPError(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Doc:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


def _compile(names: set[str], namespace: dict) -> dict:
    """Compile the named top-level functions and constants of local-ai-rag/main.py."""
    tree = ast.parse(LOCAL_MAIN.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in names for t in node.targets
        ):
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(LOCAL_MAIN), "exec"), namespace)
    return namespace


def _ingest(tmp_path, files: dict[str, object]):
    """Run the real ``ingest_documents``; ``files`` maps name -> metadata or an Exception."""
    posted: list[dict] = []

    class _Response:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return {"ingested": len(self._body["chunks"])}

    class _Client:
        def __init__(self, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, _url, json, headers):
            posted.append({"json": json, "headers": headers})
            return _Response(json)

    paths = []
    for name in files:
        path = tmp_path / name
        path.write_bytes(name.encode())
        paths.append(path)

    def load_document(path: Path):
        meta = files[path.name]
        if isinstance(meta, Exception):
            raise meta
        return [_Doc(f"نصّ {path.name}", meta)]

    namespace = {
        "hashlib": hashlib,
        "unicodedata": unicodedata,
        "Mapping": collections.abc.Mapping,
        "Path": Path,
        "Document": _Doc,
        "load_document": load_document,
        "split_docs": lambda docs: list(docs),
        "datetime": dt.datetime,
        "UTC": dt.UTC,
        "logger": logging.getLogger("test-rag-metadata-s14"),
        "httpx": types.SimpleNamespace(AsyncClient=_Client),
        "HTTPException": _HTTPError,
        "AGENT_TOKEN": "agent-token",
        "RAG_RETRIEVAL_URL": "http://rag",
    }
    fn = _compile(
        {
            "ingest_documents",
            "_document_metadata",
            "_clean_metadata_text",
            "_DOC_METADATA_TEXT_KEYS",
            "_DOC_METADATA_INT_KEYS",
            "_DOC_METADATA_MAX_CHARS",
        },
        namespace,
    )["ingest_documents"]
    result = asyncio.run(fn(paths, "tenant-1"))
    chunks = [c for p in posted for c in p["json"]["chunks"]]
    return result, chunks


def test_forged_citation_tenant_and_contract_fields_never_reach_the_index(tmp_path):
    result, (chunk,) = _ingest(
        tmp_path, {"guide.pdf": {**_FORGED, "page": 2, "title": "دليل القمح"}}
    )
    meta = chunk["metadata"]
    assert result["chunks"] == 1
    for key in (
        "publisher",
        "license",
        "jurisdiction",
        "language",
        "section",
        "evidence_level",
        "prescriptive_eligible",
        "content_digest",
        "document_embedding_prefix",
        "chunk_id",
        "document_id",
        "crop",
        "field_id",
        "source",
    ):
        assert key not in meta, key
    assert meta["tenant_id"] == "tenant-1" == chunk["tenant_id"]
    assert meta["source_class"] == "tenant_document"
    assert meta["source_uri"] == "tenant-upload://tenant-1/guide.pdf"
    assert meta["source_revision"] == "sha256:" + hashlib.sha256(b"guide.pdf").hexdigest()
    assert meta["page"] == 2 and meta["title"] == "دليل القمح"
    assert set(meta) <= _SERVER_OWNED | {"page", "title"}


def test_huge_and_control_char_metadata_is_capped_and_cleaned(tmp_path):
    title = "Wheat\x00\x1b[31m\u202eguide\n" + "A" * 1_000_000
    _, (chunk,) = _ingest(tmp_path, {"big.pdf": {"title": title, "author": "x\u200by"}})
    meta = chunk["metadata"]
    assert len(meta["title"]) <= 256
    assert meta["title"].startswith("Wheat [31mguide AAAA")
    assert all(unicodedata.category(c) not in ("Cc", "Cf") for c in meta["title"])
    assert meta["author"] == "xy"


@pytest.mark.parametrize(
    "bad",
    [
        {"title": {"nested": ["x"] * 1000}},
        {"title": ["a", "b"]},
        {"page": "2"},
        {"page": -1},
        {"page": True},
        {"total_pages": 10**12},
    ],
)
def test_malformed_metadata_values_are_dropped_not_propagated(tmp_path, bad):
    _, (chunk,) = _ingest(tmp_path, {"m.pdf": bad})
    assert not set(bad) & set(chunk["metadata"])


def test_non_mapping_metadata_does_not_fail_the_document(tmp_path):
    result, (chunk,) = _ingest(tmp_path, {"weird.pdf": ["not", "a", "mapping"]})
    assert result["rejected"] == 0
    assert chunk["metadata"]["tenant_id"] == "tenant-1"


def test_one_unreadable_document_is_rejected_alone(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="test-rag-metadata-s14")
    result, chunks = _ingest(
        tmp_path,
        {"broken.pdf": ValueError("crafted xref"), "good.pdf": {"title": "ok"}},
    )
    assert result == {"ingested": 1, "chunks": 1, "rejected": 1}
    assert [c["metadata"]["source_file"] for c in chunks] == ["good.pdf"]
    assert "RAG_INGEST_DOCUMENT_REJECTED" in caplog.text and "broken.pdf" in caplog.text


# ── rag-retrieval: reserved encoder/parser keys are refused at the write boundary ──


@pytest.fixture
def rag(monkeypatch):
    pytest.importorskip("fastapi")
    for path in (str(RAG_MAIN.parent), str(ROOT)):
        if path not in sys.path:
            monkeypatch.syspath_prepend(path)
    monkeypatch.delenv("RAG_REINDEX_PROFILE_MANIFEST", raising=False)
    spec = importlib.util.spec_from_file_location("_rag_metadata_s14_main", RAG_MAIN)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so Pydantic resolves the postponed annotations.
    monkeypatch.setitem(sys.modules, "_rag_metadata_s14_main", module)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 — تبعيّاتٌ ناقصةٌ في بيئةٍ خفيفة
        pytest.skip("تعذّر استيراد rag-retrieval (تبعيّات ناقصة)")
    return module


def _body(rag, metadata):
    chunk = {
        "chunk_id": "c1",
        "tenant_id": "tenant-1",
        "text": "wheat needs water",
        "source_type": "uploaded_document",
        "document_id": "d1",
        "chunk_index": 0,
        "total_chunks": 1,
        "metadata": {
            "source_uri": "tenant-upload://tenant-1/a.pdf",
            "source_revision": "sha256:" + "1" * 64,
            **metadata,
        },
    }
    return rag.IngestRequest(chunks=[chunk])


@pytest.mark.parametrize(
    "key,value",
    [
        ("document_embedding_prefix", "search_document: "),
        ("reindex_revision", "r1"),
        ("embedding_model_digest", "sha256:x"),
        ("retrieval_profile", "nomic"),
        ("chunk_id_source", "declared"),
    ],
)
def test_reserved_encoder_metadata_is_refused_before_any_write(rag, monkeypatch, key, value):
    written: list = []
    monkeypatch.setattr(rag._retriever, "ingest", lambda chunks: written.extend(chunks) or 0)
    with pytest.raises(rag.HTTPException) as exc:
        asyncio.run(rag.ingest(_body(rag, {key: value}), x_tenant_id="tenant-1", _token=None))
    assert exc.value.status_code == 422
    assert exc.value.detail == {"code": "RESERVED_RAG_METADATA", "keys": [key]}
    assert written == []


def test_clean_tenant_document_is_still_ingested(rag, monkeypatch):
    written: list = []
    monkeypatch.setattr(rag._retriever, "ingest", lambda chunks: written.extend(chunks) or 1)
    out = asyncio.run(
        rag.ingest(_body(rag, {"title": "دليل"}), x_tenant_id="tenant-1", _token=None)
    )
    assert out == {"ingested": 1}
    assert written[0].tenant_id == "tenant-1"
