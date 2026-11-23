"""F1 — a document uploaded for a field is found by that field's question.

Audit claim: ``local-ai-rag``'s upload path kept only a strict allow-list of loader
metadata, so no chunk ever carried ``field_id``/``crop``/``region``. The advisor's search
sends the field and its crop, and the canonical tenant filter
(``core.rag.production_qdrant.matches_scope_filters``) requires a tenant chunk to carry
every non-null filter key. Witness: one chunk ingested, found unscoped (1), with the field
(0), with the crop (0), with both (0).

Fix under test: the uploader may *name* a field; ``local-ai-rag`` asks the field's owner
(field-management-service ``GET /internal/fields/{field_id}``, service token + signed tenant
assertion) whether the field belongs to the tenant, and takes crop and region from that
owner record. File, parser and client body scope stays ignored.

Devin Review on #1582: two different files with one basename in one upload got one
``document_id`` with two revisions; the canonical ingest refused the batch (422) and the
uploader answered 503. The producer now refuses that batch itself with a 400 naming the file.

Real code end to end, no live service: the local-ai-rag functions are compiled out of
``main.py``; HTTP goes through ``httpx.MockTransport`` to a field-owner double and to the
real rag-retrieval ``/v1/ingest`` handler, which writes into the in-memory Qdrant double of
``test_rag_document_revision_withdrawal`` and is searched through the real retriever.
"""

from __future__ import annotations

import ast
import asyncio
import collections.abc
import contextlib
import datetime as dt
import hashlib
import json
import logging
import re
import types
import unicodedata
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from shared.security.service_tenant_assertion import verify_tenant_assertion
from shared.security.tenant_assertion_headers import (
    TenantAssertionError,
    tenant_assertion_headers,
)
from tests_v9.service_module import load_service_main
from tests_v9.test_rag_document_revision_withdrawal import Qdrant, pq

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LOCAL_MAIN = ROOT / "services" / "local-ai-rag" / "main.py"
KEY = "k" * 40
AGENT = "agent-token"

# The owner's table: tenant -> field_id -> record (the columns field-management returns).
OWNER = {
    "tenant-a": {
        "F1": {"field_id": "F1", "name": "north", "crop": "طماطم", "region": "صنعاء"},
        "F2": {"field_id": "F2", "name": "south", "crop": "قمح صلب", "region": "إب"},
    },
    "tenant-b": {
        "FB": {"field_id": "FB", "name": "theirs", "crop": "بن", "region": "حجة"},
    },
}

_COMPILED = {
    "ingest_documents",
    "_bind_field_scope",
    "_document_metadata",
    "_clean_metadata_text",
    "_DOC_METADATA_TEXT_KEYS",
    "_DOC_METADATA_INT_KEYS",
    "_DOC_METADATA_MAX_CHARS",
    "_FIELD_ID_RE",
    "FIELD_SERVICE_CALLER",
    # #1582: the canonical call runs inside the per-document publication lock.
    "_PUBLISHING",
    "_PUBLISHING_USERS",
    "_PUBLICATION_IN_DOUBT",
    "_CANONICAL_INGEST_TIMEOUT_S",
    "_request_never_sent",
    "_publishing_steps",
    "_publishing",
}


class _Doc:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class Stack:
    """local-ai-rag (compiled) -> owner double / rag-retrieval handler -> in-memory Qdrant."""

    def __init__(self, *, field_service_url="http://fields", owner_reply=None, owner_error=None):
        self.owner_calls: list[httpx.Request] = []
        self.ingest_calls: list[dict] = []
        self.owner_reply = owner_reply
        self.owner_error = owner_error
        self.rag = load_service_main(
            str(ROOT / "services/rag-retrieval"), required_attrs=("_ingest_blocking", "ingest")
        )
        self.rag._retriever = pq.HybridQdrantRetriever(Qdrant(), pq.HashEmbeddingProvider(32))
        self.rag._sparse_ready = True
        self.file_meta: dict[str, dict] = {}
        self.file_text: dict[str, str] = {}
        transport = httpx.MockTransport(self._route)
        real_httpx = httpx

        def client(**kw):
            kw.pop("transport", None)
            return real_httpx.AsyncClient(transport=transport, **kw)

        def load_document(path: Path):
            name = path.name
            return [
                _Doc(self.file_text.get(name, f"نصّ {name}"), dict(self.file_meta.get(name, {})))
            ]

        self.ns = {
            "re": re,
            "hashlib": hashlib,
            "unicodedata": unicodedata,
            "Mapping": collections.abc.Mapping,
            "Path": Path,
            "Document": _Doc,
            "load_document": load_document,
            "split_docs": lambda docs: list(docs),
            "datetime": dt.datetime,
            "UTC": dt.UTC,
            "logger": logging.getLogger("test-local-ai-rag-f1"),
            "httpx": types.SimpleNamespace(
                AsyncClient=client,
                HTTPError=httpx.HTTPError,
                ConnectError=httpx.ConnectError,
                ConnectTimeout=httpx.ConnectTimeout,
                PoolTimeout=httpx.PoolTimeout,
            ),
            "asyncio": asyncio,
            "asynccontextmanager": contextlib.asynccontextmanager,
            "HTTPException": HTTPException,
            "AGENT_TOKEN": AGENT,
            "RAG_RETRIEVAL_URL": "http://rag",
            "FIELD_SERVICE_URL": field_service_url,
            "FIELD_SERVICE_TENANT_ASSERTION_KEY": KEY,
            "FIELD_SERVICE_TENANT_ASSERTION_KEY_ID": "current",
            "tenant_assertion_headers": tenant_assertion_headers,
            "TenantAssertionError": TenantAssertionError,
        }
        _compile(_COMPILED, self.ns)

    # ── HTTP doubles ─────────────────────────────────────────────────────────
    async def _route(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "fields":
            return self._owner(request)
        if request.url.host == "rag" and request.url.path == "/v1/ingest":
            return await self._canonical_ingest(request)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def _owner(self, request: httpx.Request) -> httpx.Response:
        """field-management-service's guard and tenant-scoped read, as the owner does it."""
        self.owner_calls.append(request)
        if self.owner_error is not None:
            raise self.owner_error
        h = request.headers
        assert h["X-Agent-Token"] == AGENT
        verify_tenant_assertion(
            h["X-Tenant-Assertion"],
            {"current": KEY},
            h["X-Service-Name"],
            h["X-Tenant-Id"],
            expected_method=request.method,
            expected_path=request.url.path,
            expected_request_id=h["X-Request-Id"],
        )
        if self.owner_reply is not None:
            return self.owner_reply
        field_id = request.url.path.rsplit("/", 1)[-1]
        record = OWNER.get(h["X-Tenant-Id"], {}).get(field_id)
        if record is None:
            return httpx.Response(404, json={"detail": "field not found for this tenant"})
        return httpx.Response(200, json=record)

    async def _canonical_ingest(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.ingest_calls.append(body)
        try:
            out = await self.rag.ingest(
                self.rag.IngestRequest(**body),
                x_tenant_id=request.headers["X-Tenant-Id"],
                _token=None,
            )
        except HTTPException as exc:
            return httpx.Response(exc.status_code, json={"detail": exc.detail})
        return httpx.Response(200, json=out)

    # ── what the endpoint does, in its order ─────────────────────────────────
    def upload(self, tmp_path, files: dict[str, bytes], *, tenant="tenant-a", field_id=None):
        paths, names = [], {}
        for i, (name, data) in enumerate(files.items() if isinstance(files, dict) else files):
            path = tmp_path / f"upload-{len(self.ingest_calls)}-{i}{Path(name).suffix}"
            path.write_bytes(data)
            paths.append(path)
            names[str(path)] = name
            self.file_text.setdefault(path.name, data.decode())
            if name in self.file_meta:
                self.file_meta[path.name] = self.file_meta[name]

        async def run():
            # The endpoint binds only a named field; an unnamed one stays tenant-wide.
            kwargs = {}
            if field_id is not None:
                kwargs["scope"] = await self.ns["_bind_field_scope"](tenant, field_id)
            return await self.ns["ingest_documents"](paths, tenant, source_names=names, **kwargs)

        return asyncio.run(run())

    def search(self, query, *, tenant="tenant-a", **filters):
        rows = self.rag._retriever.retrieve(query, tenant_id=tenant, filters=filters, final_k=10)
        return [row.chunk for row in rows]

    def stored(self):
        return [payload for _vector, payload in self.rag._retriever.qdrant.points.values()]


def _compile(names: set[str], namespace: dict) -> dict:
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


TEXT = b"irrigation schedule notes for the north block"
QUERY = "irrigation schedule notes"


# ── the audit witness: a tenant-wide upload stays tenant-wide ─────────────────────────────


def test_witness_upload_without_a_field_is_invisible_to_a_field_question(tmp_path):
    stack = Stack()
    out = stack.upload(tmp_path, {"notes.txt": TEXT})
    assert out["chunks"] == 1
    assert len(stack.search(QUERY)) == 1
    assert stack.search(QUERY, field_id="F1") == []
    assert stack.search(QUERY, crop="طماطم") == []
    assert stack.search(QUERY, field_id="F1", crop="طماطم") == []
    assert stack.owner_calls == []  # no field named, no owner call


# ── REQUIRED 1: trusted server-side field scope ─────────────────────────────────────────


def test_upload_for_a_field_is_found_by_that_fields_question(tmp_path):
    stack = Stack()
    stack.upload(tmp_path, {"notes.txt": TEXT}, field_id="F1")
    assert len(stack.search(QUERY)) == 1
    assert len(stack.search(QUERY, field_id="F1")) == 1
    assert len(stack.search(QUERY, crop="طماطم")) == 1
    assert len(stack.search(QUERY, field_id="F1", crop="طماطم")) == 1
    assert len(stack.search(QUERY, field_id="F1", crop="طماطم", region="صنعاء")) == 1
    # Another field, crop or tenant does not see it.
    assert stack.search(QUERY, field_id="F2") == []
    assert stack.search(QUERY, crop="قمح صلب") == []
    assert stack.search(QUERY, tenant="tenant-b") == []
    (call,) = stack.owner_calls
    assert call.url.path == "/internal/fields/F1"
    assert call.headers["X-Tenant-Id"] == "tenant-a"
    assert call.headers["X-Service-Name"] == "local-ai-rag"


def test_forged_scope_and_authority_in_the_file_change_nothing(tmp_path):
    stack = Stack()
    stack.file_meta["guide.pdf"] = {
        "field_id": "F2",
        "crop": "wheat",
        "region": "forged-region",
        "publisher": "Ministry of Agriculture",
        "source_class": "agronomic_reference",
        "tenant_id": "tenant-b",
        "title": "دليل",
    }
    stack.upload(tmp_path, {"guide.pdf": TEXT}, field_id="F1")
    (payload,) = stack.stored()
    meta = payload["metadata"]
    assert (meta["field_id"], meta["crop"], meta["region"]) == ("F1", "طماطم", "صنعاء")
    assert meta["tenant_id"] == "tenant-a" and meta["source_class"] == "tenant_document"
    assert "publisher" not in meta
    assert meta["title"] == "دليل"
    assert stack.search(QUERY, crop="wheat") == []
    assert stack.search(QUERY, field_id="F2") == []
    assert stack.search(QUERY, region="forged-region") == []


def test_forged_scope_in_a_file_without_a_field_stays_tenant_wide(tmp_path):
    stack = Stack()
    stack.file_meta["guide.pdf"] = {"field_id": "F1", "crop": "طماطم", "region": "صنعاء"}
    stack.upload(tmp_path, {"guide.pdf": TEXT})
    (payload,) = stack.stored()
    assert not {"field_id", "crop", "region"} & set(payload["metadata"])
    assert stack.search(QUERY, field_id="F1") == []


def test_a_field_of_another_tenant_is_refused_and_nothing_is_written(tmp_path):
    stack = Stack()
    with pytest.raises(HTTPException) as exc:
        stack.upload(tmp_path, {"notes.txt": TEXT}, field_id="FB")
    assert exc.value.status_code == 404
    assert stack.ingest_calls == [] and stack.stored() == []
    (call,) = stack.owner_calls
    assert call.headers["X-Tenant-Id"] == "tenant-a"  # the owner was asked for this tenant


@pytest.mark.parametrize("field_id", ["../x", "F1/../../admin", "F 1", "F1?x=1", "x" * 51])
def test_a_malformed_field_id_is_refused_before_any_request(tmp_path, field_id):
    stack = Stack()
    with pytest.raises(HTTPException) as exc:
        stack.upload(tmp_path, {"notes.txt": TEXT}, field_id=field_id)
    assert exc.value.status_code == 400
    assert stack.owner_calls == [] and stack.ingest_calls == []


@pytest.mark.parametrize("missing", ["FIELD_SERVICE_URL", "FIELD_SERVICE_TENANT_ASSERTION_KEY"])
def test_an_unconfigured_owner_fails_closed(tmp_path, missing):
    stack = Stack()
    stack.ns[missing] = ""
    with pytest.raises(HTTPException) as exc:
        stack.upload(tmp_path, {"notes.txt": TEXT}, field_id="F1")
    assert exc.value.status_code == 503
    assert stack.owner_calls == [] and stack.ingest_calls == []


@pytest.mark.parametrize(
    ("reply", "error", "status"),
    [
        (httpx.Response(500), None, 503),
        (httpx.Response(401), None, 502),
        (httpx.Response(403), None, 502),
        (None, httpx.ConnectError("down"), 503),
        (httpx.Response(200, json={"field_id": "OTHER", "crop": "x"}), None, 502),
        (httpx.Response(200, json=["not", "a", "record"]), None, 502),
        (httpx.Response(200, content=b"not json"), None, 502),
    ],
    ids=["owner-500", "owner-401", "owner-403", "network", "wrong-id", "not-mapping", "not-json"],
)
def test_an_owner_failure_is_never_read_as_a_scope(tmp_path, reply, error, status):
    stack = Stack(owner_reply=reply, owner_error=error)
    with pytest.raises(HTTPException) as exc:
        stack.upload(tmp_path, {"notes.txt": TEXT}, field_id="F1")
    assert exc.value.status_code == status
    assert stack.ingest_calls == []


def test_same_file_name_for_two_fields_and_the_tenant_are_three_documents(tmp_path):
    stack = Stack()
    stack.upload(tmp_path, {"notes.txt": TEXT}, field_id="F1")
    stack.upload(tmp_path, {"notes.txt": TEXT}, field_id="F2")
    stack.upload(tmp_path, {"notes.txt": TEXT})
    assert len(stack.stored()) == 3
    assert len(stack.search(QUERY, field_id="F1")) == 1
    assert len(stack.search(QUERY, field_id="F2", crop="قمح صلب")) == 1


@pytest.mark.parametrize("field_first", [False, True], ids=["tenant-first", "field-first"])
def test_a_tenant_wide_name_spelling_a_field_prefix_is_not_that_fields_document(
    tmp_path, field_first
):
    """Devin on #1587: "field:F1:notes.txt" tenant-wide and "notes.txt" for F1 hashed alike.

    The canonical writer replaces an older revision of the same (tenant, document_id), so the
    second upload silently removed the first. Both must stay, in either order.
    """
    stack = Stack()
    uploads = [({"field:F1:notes.txt": TEXT}, None), ({"notes.txt": TEXT}, "F1")]
    for files, field_id in reversed(uploads) if field_first else uploads:
        stack.upload(tmp_path, files, field_id=field_id)
    stored = [p["metadata"] for p in stack.stored()]
    assert len({m["document_id"] for m in stored}) == 2
    assert {m["source_file"] for m in stored} == {"field:F1:notes.txt", "notes.txt"}


def test_a_tenant_wide_document_keeps_its_historical_identity(tmp_path):
    stack = Stack()
    stack.upload(tmp_path, {"notes.txt": TEXT})
    (doc_id,) = {p["metadata"]["document_id"] for p in stack.stored()}
    assert doc_id == hashlib.sha256(b"tenant-a:notes.txt").hexdigest()


def test_the_env_template_lets_local_ai_rag_call_the_field_owner():
    """Devin on #1587: .env.example's explicit allowlist overrode Compose's fallback.

    A stack started from the template (the local runbook copies it to .env) refused
    local-ai-rag's field lookup, so every field upload failed with 502. The template must
    list every caller the Compose fallback lists, local-ai-rag among them.
    """
    root = Path(__file__).resolve().parents[1]
    (template_line,) = [
        line
        for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.startswith("FIELD_SERVICE_ALLOWED_CALLERS=")
    ]
    template = {s.strip() for s in template_line.split("=", 1)[1].split(",") if s.strip()}
    compose = (root / "docker-compose.v9.yml").read_text(encoding="utf-8")
    (fallback,) = re.findall(
        r"FIELD_SERVICE_ALLOWED_CALLERS: \$\{FIELD_SERVICE_ALLOWED_CALLERS:-([^}]*)\}", compose
    )
    fallback_callers = {s.strip() for s in fallback.split(",") if s.strip()}
    caller = re.search(
        r'^FIELD_SERVICE_CALLER = "([^"]+)"', LOCAL_MAIN.read_text(encoding="utf-8"), re.M
    ).group(1)
    assert caller == "local-ai-rag"
    assert caller in fallback_callers
    assert fallback_callers <= template, sorted(fallback_callers - template)


def test_the_endpoint_binds_the_field_before_reading_files_and_takes_no_client_scope():
    """The endpoint accepts a field name only; crop/region/publisher are not parameters."""
    tree = ast.parse(LOCAL_MAIN.read_text(encoding="utf-8"))
    (endpoint,) = [
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "ingest_endpoint"
    ]
    params = {a.arg for a in [*endpoint.args.args, *endpoint.args.kwonlyargs]}
    assert "field_id" in params
    assert not params & {"crop", "region", "publisher", "source_class", "scope"}
    calls = [
        n.func.id
        for n in ast.walk(endpoint)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert calls.index("_bind_field_scope") < calls.index("ingest_documents")
    first_read = min(
        n.lineno
        for n in ast.walk(endpoint)
        if isinstance(n, ast.Attribute) and n.attr == "NamedTemporaryFile"
    )
    bind = min(
        n.lineno
        for n in ast.walk(endpoint)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_bind_field_scope"
    )
    assert bind < first_read


# ── REQUIRED 2: one basename, two files ─────────────────────────────────────────────────


def test_two_different_files_with_one_name_are_a_client_error_naming_the_file(tmp_path):
    stack = Stack()
    with pytest.raises(HTTPException) as exc:
        stack.upload(tmp_path, [("guide.txt", b"first version"), ("guide.txt", b"second one")])
    assert 400 <= exc.value.status_code < 500
    assert exc.value.detail["code"] == "CONFLICTING_UPLOAD_FILENAMES"
    assert exc.value.detail["files"] == ["guide.txt"]
    assert stack.ingest_calls == []  # refused by the producer, before the canonical ingest


def test_distinct_names_in_one_upload_are_still_ingested(tmp_path):
    stack = Stack()
    out = stack.upload(tmp_path, [("a.txt", b"alpha notes"), ("b.txt", b"beta notes")])
    assert out["chunks"] == 2 and len(stack.stored()) == 2


def test_the_canonical_mixed_revision_guard_is_unchanged(tmp_path):
    """The producer check is in front of the canonical guard, not instead of it."""
    stack = Stack()
    doc_id = hashlib.sha256(b"tenant-a:guide.txt").hexdigest()
    chunks = [
        {
            "chunk_id": f"c{i}",
            "tenant_id": "tenant-a",
            "text": text,
            "source_type": "uploaded_document",
            "document_id": doc_id,
            "chunk_index": i,
            "total_chunks": 2,
            "metadata": {
                "source_uri": "tenant-upload://tenant-a/guide.txt",
                "source_revision": f"sha256:{str(i) * 64}",
            },
        }
        for i, text in enumerate(["first", "second"])
    ]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            stack.rag.ingest(
                stack.rag.IngestRequest(chunks=chunks), x_tenant_id="tenant-a", _token=None
            )
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "MIXED_DOCUMENT_REVISION"
