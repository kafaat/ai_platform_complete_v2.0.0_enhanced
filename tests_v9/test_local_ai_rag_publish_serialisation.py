"""local-ai-rag publishes one upload of a document at a time and names superseded files.

Review on #1582: rag-retrieval runs replicas over one Qdrant collection with no shared lock,
and two revisions of a document often share an identical chunk (one storage point), so an
older publication landing after a newer one can strip that chunk from the newer revision.
local-ai-rag is the only writer of the canonical ingest and runs one worker, so it
serialises the canonical call per (tenant, document). It also reads the per-document
receipts: a document another publication replaced is named (``superseded_files``) instead
of being answered as ingested.

The real ``ingest_documents`` and ``_publishing`` are compiled from the service source with
recording stand-ins for the parser and the canonical HTTP client.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

MAIN = Path(__file__).resolve().parents[1] / "services" / "local-ai-rag" / "main.py"
_NAMES = {
    "ingest_documents",
    "_publishing_steps",
    "_publishing",
    "_PUBLISHING",
    "_PUBLISHING_USERS",
}


class _Doc:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


def _compile(post):
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        name = getattr(node, "name", None)
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if name in _NAMES or any(getattr(t, "id", None) in _NAMES for t in targets if t):
            body.append(node)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json, headers):
            return await post(json)

    ns: dict = {
        "asyncio": asyncio,
        "asynccontextmanager": asynccontextmanager,
        "hashlib": hashlib,
        "Path": Path,
        "HTTPException": HTTPException,
        "datetime": datetime,
        "UTC": UTC,
        "Document": _Doc,
        "logger": logging.getLogger("test-local-ai-rag-publish"),
        "load_document": lambda p: [_Doc(p.read_text(encoding="utf-8"), {})],
        "split_docs": lambda docs: list(docs),
        "_document_metadata": lambda meta: dict(meta),
        "httpx": type("H", (), {"AsyncClient": _Client}),
        "AGENT_TOKEN": "agent-token",
        "RAG_RETRIEVAL_URL": "http://rag",
    }
    exec(compile(ast.Module(body, []), str(MAIN), "exec"), ns)  # noqa: S102 - our own source
    return ns["ingest_documents"], ns


class _Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def _upload(tmp_path, tag, files):
    paths, names = [], {}
    for i, (name, text) in enumerate(files):
        d = tmp_path / f"{tag}{i}"
        d.mkdir()
        p = d / f"upload-{i}.tmp"
        p.write_text(text, encoding="utf-8")
        paths.append(p)
        names[str(p)] = name
    return paths, names


def test_two_uploads_of_one_document_never_reach_the_canonical_ingest_together(tmp_path):
    in_flight: list[int] = []
    overlap: list[int] = []

    async def post(body):
        in_flight.append(1)
        if len(in_flight) > 1:
            overlap.append(1)
        await asyncio.sleep(0.02)
        in_flight.pop()
        return _Response({"ingested": len(body["chunks"]), "receipts": []})

    ingest, ns = _compile(post)

    async def both():
        a = _upload(tmp_path, "a", [("guide.txt", "first revision")])
        b = _upload(tmp_path, "b", [("guide.txt", "second revision")])
        return await asyncio.gather(
            ingest(a[0], "tenant-a", source_names=a[1]),
            ingest(b[0], "tenant-a", source_names=b[1]),
        )

    results = asyncio.run(both())
    assert overlap == [], "the second upload of a document must wait for the first"
    assert all(r["chunks"] == 1 for r in results)
    assert ns["_PUBLISHING"] == {} and ns["_PUBLISHING_USERS"] == {}, "locks are released"


def test_uploads_of_different_documents_still_run_together(tmp_path):
    in_flight: list[int] = []
    overlap: list[int] = []

    async def post(body):
        in_flight.append(1)
        if len(in_flight) > 1:
            overlap.append(1)
        await asyncio.sleep(0.02)
        in_flight.pop()
        return _Response({"ingested": len(body["chunks"]), "receipts": []})

    ingest, _ns = _compile(post)

    async def both():
        a = _upload(tmp_path, "a", [("guide.txt", "guide text")])
        b = _upload(tmp_path, "b", [("calendar.txt", "calendar text")])
        await asyncio.gather(
            ingest(a[0], "tenant-a", source_names=a[1]),
            ingest(b[0], "tenant-a", source_names=b[1]),
        )

    asyncio.run(both())
    assert overlap == [1], "only one document's uploads are serialised, not every upload"


def test_a_superseded_document_is_named_not_answered_as_ingested(tmp_path):
    doc_id = hashlib.sha256(b"tenant-a:guide.txt").hexdigest()

    async def post(body):
        return _Response(
            {
                "ingested": len(body["chunks"]),
                "receipts": [
                    {"document_id": doc_id, "superseded": True},
                    {"document_id": "other", "superseded": False},
                ],
            }
        )

    ingest, _ns = _compile(post)
    paths, names = _upload(tmp_path, "a", [("guide.txt", "guide"), ("calendar.txt", "cal")])
    out = asyncio.run(ingest(paths, "tenant-a", source_names=names))
    assert out["status"] == "partially_superseded"
    assert out["superseded_files"] == ["guide.txt"]
    assert out["chunks"] == 2


def test_no_superseded_receipt_keeps_the_plain_answer(tmp_path):
    async def post(body):
        return _Response({"ingested": len(body["chunks"])})  # an older ingest without receipts

    ingest, _ns = _compile(post)
    paths, names = _upload(tmp_path, "a", [("guide.txt", "guide")])
    out = asyncio.run(ingest(paths, "tenant-a", source_names=names))
    assert out == {"ingested": 1, "chunks": 1, "rejected": 0}
