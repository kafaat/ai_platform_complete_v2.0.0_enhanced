"""One upload with two different files of the same name is a client error (review on #1582).

local-ai-rag gives one document id to a tenant's file name, so two files called ``guide.txt``
in one upload would be one document with two revisions. The canonical ingest refuses that
batch as a whole (422), and the uploader used to report it as "service unavailable" (503).
The producer now refuses it first, with 400 naming the file, before any file is parsed or
anything is sent to the canonical ingest. The canonical mixed-revision guard stays as it is
(``tests_v9/test_rag_document_revision_withdrawal.py``).

The real ``ingest_documents`` is compiled from the service source with recording stand-ins
for the parser and the canonical client, so the test measures the shipped code path.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import logging
from pathlib import Path

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

MAIN = Path(__file__).resolve().parents[1] / "services" / "local-ai-rag" / "main.py"


class _Refused(Exception):
    pass


def _ingest(calls: list[str]):
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = next(
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "ingest_documents"
    )
    ns: dict = {
        "Path": Path,
        "HTTPException": HTTPException,
        "hashlib": hashlib,
        "logger": logging.getLogger("test-local-ai-rag-filename-conflict"),
    }

    def load_document(path):
        calls.append(f"parse:{path.name}")
        raise _Refused("parsing must not start")

    class _Client:
        def __init__(self, *a, **k):
            calls.append("canonical")
            raise _Refused("the canonical ingest must not be called")

    ns.update(load_document=load_document, httpx=type("H", (), {"AsyncClient": _Client}))
    exec(compile(ast.Module([fn], []), str(MAIN), "exec"), ns)  # noqa: S102 - our own source
    return ns["ingest_documents"]


def _files(tmp_path, names):
    paths, source_names = [], {}
    for i, name in enumerate(names):
        d = tmp_path / f"u{i}"
        d.mkdir()
        p = d / f"upload-{i}.tmp"
        p.write_bytes(f"content {i}".encode())
        paths.append(p)
        source_names[str(p)] = name
    return paths, source_names


def test_two_different_files_with_one_name_are_refused_with_400_naming_it(tmp_path):
    calls: list[str] = []
    paths, names = _files(tmp_path, ["guide.txt", "calendar.txt", "guide.txt"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_ingest(calls)(paths, "tenant-a", source_names=names))
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "CONFLICTING_UPLOAD_FILENAMES"
    assert exc.value.detail["files"] == ["guide.txt"]
    assert calls == [], "refused before any parse and before the canonical ingest"


def test_distinct_names_are_not_refused_by_the_name_check(tmp_path):
    calls: list[str] = []
    paths, names = _files(tmp_path, ["a.txt", "b.txt"])
    # The stand-in parser refuses every file (each is rejected on its own), so reaching it
    # for both proves the name check let the batch through.
    out = asyncio.run(_ingest(calls)(paths, "tenant-a", source_names=names))
    assert calls == ["parse:upload-0.tmp", "parse:upload-1.tmp"]
    assert out == {"ingested": 0, "chunks": 0, "rejected": 2}
