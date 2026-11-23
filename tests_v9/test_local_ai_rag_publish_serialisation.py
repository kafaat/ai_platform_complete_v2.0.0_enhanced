"""local-ai-rag publishes one upload of a document at a time and names superseded files.

Review on #1582: rag-retrieval runs replicas over one Qdrant collection with no shared lock,
and two revisions of a document often share an identical chunk (one storage point), so an
older publication landing after a newer one can strip that chunk from the newer revision.
local-ai-rag is the only writer of the canonical ingest and runs one worker, so it
serialises the canonical call per (tenant, document). It also reads the per-document
receipts: a document another publication replaced is named (``superseded_files``) instead
of being answered as ingested.

A canonical call that fails after the request may have reached rag-retrieval (timeout,
broken connection, cancelled handler) leaves the document blocked, in doubt: rag-retrieval
may still be writing, so a second upload must not race it (lab 1582-v5). A failure before
anything was sent releases the document.

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
from types import SimpleNamespace

import httpx
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
    "_PUBLICATION_IN_DOUBT",
    "_CANONICAL_INGEST_TIMEOUT_S",
    "_request_never_sent",
}


class _Doc:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


def _compile(post):
    timeouts: list = []
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        name = getattr(node, "name", None)
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if name in _NAMES or any(getattr(t, "id", None) in _NAMES for t in targets if t):
            body.append(node)

    class _Client:
        def __init__(self, *a, **k):
            timeouts.append(k.get("timeout"))

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
        "httpx": SimpleNamespace(
            AsyncClient=_Client,
            ConnectError=httpx.ConnectError,
            ConnectTimeout=httpx.ConnectTimeout,
            PoolTimeout=httpx.PoolTimeout,
        ),
        "AGENT_TOKEN": "agent-token",
        "RAG_RETRIEVAL_URL": "http://rag",
    }
    exec(compile(ast.Module(body, []), str(MAIN), "exec"), ns)  # noqa: S102 - our own source
    ns["_timeouts"] = timeouts
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


def _writer_that_outlives_the_client(failure):
    """rag-retrieval keeps writing after the uploader's call failed (lab 1582-v5).

    ``failure`` is raised to the uploader once the server has started; the server's write
    keeps going for a while after that, as a threadpool write does when its client leaves.
    """
    state = {"writing": 0, "overlap": 0, "calls": 0, "server": []}

    async def server_write():
        state["writing"] += 1
        await asyncio.sleep(0.2)
        state["writing"] -= 1

    async def post(body):
        state["calls"] += 1
        if state["writing"]:
            state["overlap"] += 1
        task = asyncio.ensure_future(server_write())
        state["server"].append(task)
        if state["calls"] == 1 and failure is not None:
            await asyncio.sleep(0.01)
            raise failure
        await task
        return _Response({"ingested": len(body["chunks"]), "receipts": []})

    return state, post


def _first_fails_then_second(tmp_path, failure, second_name="guide.txt"):
    state, post = _writer_that_outlives_the_client(failure)
    ingest, ns = _compile(post)

    async def run():
        a = _upload(tmp_path, "a", [("guide.txt", "first revision")])
        b = _upload(tmp_path, "b", [(second_name, "second revision")])
        with pytest.raises(HTTPException) as first:
            await ingest(a[0], "tenant-a", source_names=a[1])
        try:
            second = await ingest(b[0], "tenant-a", source_names=b[1])
        except HTTPException as exc:
            second = exc
        await asyncio.gather(*state["server"])
        return first.value, second

    first, second = asyncio.run(run())
    return state, ns, first, second


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("timed out"),
        httpx.RemoteProtocolError("server disconnected"),
        httpx.WriteTimeout("timed out"),
    ],
    ids=["read-timeout", "connection-dropped", "write-timeout"],
)
def test_a_document_whose_write_may_still_run_is_not_published_again(tmp_path, failure):
    state, ns, first, second = _first_fails_then_second(tmp_path, failure)
    assert first.status_code == 503
    assert state["overlap"] == 0, "a second upload raced a write rag-retrieval was still doing"
    assert isinstance(second, HTTPException) and second.status_code == 409
    assert second.detail["code"] == "DOCUMENT_PUBLICATION_IN_DOUBT"
    assert state["calls"] == 1, "the refused upload never reaches the canonical ingest"
    assert ns["_PUBLISHING"] == {} and ns["_PUBLISHING_USERS"] == {}, "locks are released"


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ConnectTimeout("no route")],
    ids=["connection-refused", "connect-timeout"],
)
def test_a_request_that_never_left_releases_the_document(tmp_path, failure):
    async def post(body):
        if not calls:
            calls.append(1)
            raise failure
        calls.append(1)
        return _Response({"ingested": len(body["chunks"]), "receipts": []})

    calls: list[int] = []
    ingest, ns = _compile(post)

    async def run():
        a = _upload(tmp_path, "a", [("guide.txt", "first revision")])
        b = _upload(tmp_path, "b", [("guide.txt", "second revision")])
        with pytest.raises(HTTPException):
            await ingest(a[0], "tenant-a", source_names=a[1])
        return await ingest(b[0], "tenant-a", source_names=b[1])

    out = asyncio.run(run())
    assert out["chunks"] == 1 and ns["_PUBLICATION_IN_DOUBT"] == set()


def test_a_cancelled_upload_leaves_its_document_in_doubt(tmp_path):
    async def run():
        reached = asyncio.Event()

        async def post(body):
            reached.set()
            await asyncio.sleep(10)

        ingest, ns = _compile(post)
        a = _upload(tmp_path, "a", [("guide.txt", "first revision")])
        task = asyncio.ensure_future(ingest(a[0], "tenant-a", source_names=a[1]))
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return ns

    ns = asyncio.run(run())
    assert len(ns["_PUBLICATION_IN_DOUBT"]) == 1
    assert ns["_PUBLISHING"] == {} and ns["_PUBLISHING_USERS"] == {}


def test_a_document_in_doubt_does_not_block_other_documents(tmp_path):
    state, _ns, _first, second = _first_fails_then_second(
        tmp_path, httpx.ReadTimeout("timed out"), second_name="calendar.txt"
    )
    assert isinstance(second, dict) and second["chunks"] == 1


def test_the_upload_waits_for_rag_retrieval_longer_than_a_short_request(tmp_path):
    async def post(body):
        return _Response({"ingested": len(body["chunks"])})

    ingest, ns = _compile(post)
    paths, names = _upload(tmp_path, "a", [("guide.txt", "guide")])
    asyncio.run(ingest(paths, "tenant-a", source_names=names))
    assert ns["_timeouts"] == [ns["_CANONICAL_INGEST_TIMEOUT_S"]]
    assert ns["_CANONICAL_INGEST_TIMEOUT_S"] >= 600


def test_the_in_doubt_refusal_names_the_files_of_a_multi_file_upload(tmp_path):
    """Hospital review on #1582: the 409 named no document, so a multi-file upload could not
    tell which of its files was blocked."""
    state, post = _writer_that_outlives_the_client(httpx.ReadTimeout("timed out"))
    ingest, _ns = _compile(post)

    async def run():
        a = _upload(tmp_path, "a", [("guide.txt", "first revision")])
        b = _upload(tmp_path, "b", [("guide.txt", "second revision"), ("calendar.txt", "cal")])
        with pytest.raises(HTTPException):
            await ingest(a[0], "tenant-a", source_names=a[1])
        with pytest.raises(HTTPException) as second:
            await ingest(b[0], "tenant-a", source_names=b[1])
        await asyncio.gather(*state["server"])
        return second.value

    refused = asyncio.run(run())
    assert refused.status_code == 409
    assert refused.detail["code"] == "DOCUMENT_PUBLICATION_IN_DOUBT"
    assert refused.detail["files"] == ["guide.txt"]
    assert "document_ids" not in refused.detail
    assert state["calls"] == 1, "nothing of the refused upload was sent"
