"""SEC-3 — gateway-trusted identity (Option B).

The nginx gateway verifies the JWT and injects the AUTHENTICATED ``X-Tenant-Id``
(clearing any client-supplied value). Inside internal AI/RAG/KG services that
header is the ONLY tenant source of truth; a body ``tenant_id`` may only echo it.
Write/mutating endpoints additionally require the trusted service token
``X-Agent-Token == SAHOOL_AGENT_TOKEN``.

Two tiers:
- Pure-unit (no FastAPI): the ``resolve_trusted_tenant`` / ``service_token_ok``
  decision functions — run in the no-fastapi CI tier.
- Endpoint (``pytest.importorskip("fastapi")``): the real ai_agronomist / rag /
  kg apps, proving fail-closed 403 on missing header, body!=header mismatch, and
  missing service token; and pass-through when the contract is satisfied.

منطق صرف عدا نقاط الـHTTP (importorskip) — وظيفة Unit Tests.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.security.trusted_tenant import (  # noqa: E402
    ERROR_MISSING_TENANT,
    ERROR_TENANT_MISMATCH,
    TrustedTenantError,
    resolve_trusted_tenant,
    service_token_ok,
)

_AGENT_TOKEN = "test-agent-token-sec3"


# ═══════════════════════════ pure-unit tier (no fastapi) ═══════════════════════
def test_resolve_missing_header_fails_closed():
    for missing in (None, "", "   "):
        with pytest.raises(TrustedTenantError) as ei:
            resolve_trusted_tenant(missing, "tenant-1")
        assert ei.value.code == ERROR_MISSING_TENANT


def test_resolve_body_mismatch_fails_closed():
    with pytest.raises(TrustedTenantError) as ei:
        resolve_trusted_tenant("tenant-1", "tenant-2")
    assert ei.value.code == ERROR_TENANT_MISMATCH


def test_resolve_body_matches_header_passes():
    assert resolve_trusted_tenant("tenant-1", "tenant-1") == "tenant-1"
    # whitespace is trimmed on both sides before the equality check.
    assert resolve_trusted_tenant("  tenant-1 ", "tenant-1") == "tenant-1"


def test_resolve_body_absent_uses_header():
    assert resolve_trusted_tenant("tenant-1", None) == "tenant-1"
    assert resolve_trusted_tenant("tenant-1", "") == "tenant-1"
    assert resolve_trusted_tenant("tenant-1") == "tenant-1"


def test_service_token_ok_is_fail_closed():
    assert service_token_ok(_AGENT_TOKEN, _AGENT_TOKEN) is True
    assert service_token_ok("wrong", _AGENT_TOKEN) is False
    assert service_token_ok(None, _AGENT_TOKEN) is False
    # Unset/blank expected secret rejects everyone (never silently open).
    assert service_token_ok(_AGENT_TOKEN, "") is False
    assert service_token_ok("", "") is False


# ═══════════════════════════ endpoint tier (fastapi) ═══════════════════════════
_MODULE_CACHE: dict[str, object] = {}


def _load_service_module(name: str, relpath: str, extra_paths: list[str], env: dict | None):
    """Best-effort load of a hyphen-named service module by file path.

    Returns the module or raises to let the caller ``pytest.skip`` when the
    service's heavy deps are absent (keeps the endpoint tier optional)."""
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]
    for p in extra_paths:
        ap = str(ROOT / p)
        if ap not in sys.path:
            sys.path.insert(0, ap)
    for k, v in (env or {}).items():
        os.environ[k] = v
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relpath))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec so Pydantic can resolve the module globals for the
    # ``from __future__ import annotations`` forward refs on its request models.
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    _MODULE_CACHE[name] = module
    return module


# ── ai_agronomist: X-Tenant-Id is the tenant source of truth on read endpoints ──
def _ai_client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.ai_agronomist import main as M

    return M, TestClient(M.app, raise_server_exceptions=False)


@pytest.mark.parametrize("endpoint", ["/query", "/chat", "/explain", "/recommend"])
def test_ai_missing_tenant_header_rejected(endpoint):
    _M, client = _ai_client()
    r = client.post(endpoint, json={"question": "q", "tenant_id": "tenant-1"})
    assert r.status_code == 403
    assert r.json()["detail"] == ERROR_MISSING_TENANT


@pytest.mark.parametrize("endpoint", ["/query", "/chat", "/explain", "/recommend"])
def test_ai_body_tenant_mismatch_rejected(endpoint):
    _M, client = _ai_client()
    r = client.post(
        endpoint,
        json={"question": "q", "tenant_id": "tenant-EVIL"},
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == ERROR_TENANT_MISMATCH


def test_ai_body_matches_header_passes_guard(monkeypatch):
    M, client = _ai_client()

    class _Resp:
        def __init__(self, payload):
            self.status_code = 200
            self._p = payload
            self.text = ""

        def json(self):
            return self._p

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **k):
            return _Resp({"annotations": []})

        async def get(self, url, **k):
            return _Resp({"edges": []})

    monkeypatch.setattr(M.httpx, "AsyncClient", _FakeAsyncClient)
    r = client.post(
        "/query",
        json={"question": "q", "tenant_id": "tenant-1"},
        headers={"X-Tenant-Id": "tenant-1"},
    )
    assert r.status_code == 200
    body = r.json()
    # The response echoes the gateway-trusted tenant, never a spoofed body value.
    assert body["tenant_id"] == "tenant-1"


def test_ai_header_only_no_body_tenant_passes_guard(monkeypatch):
    M, client = _ai_client()
    # Reuse the same fake as above via the happy-path helper style.
    import types

    async def _aenter(self):
        return self

    async def _aexit(self, *a):
        return False

    async def _post(self, url, **k):
        return types.SimpleNamespace(status_code=200, text="", json=lambda: {"annotations": []})

    async def _get(self, url, **k):
        return types.SimpleNamespace(status_code=200, text="", json=lambda: {"edges": []})

    Fake = type(
        "Fake",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "__aenter__": _aenter,
            "__aexit__": _aexit,
            "post": _post,
            "get": _get,
        },
    )
    monkeypatch.setattr(M.httpx, "AsyncClient", Fake)
    r = client.post("/query", json={"question": "q"}, headers={"X-Tenant-Id": "tenant-9"})
    assert r.status_code == 200
    assert r.json()["tenant_id"] == "tenant-9"


# ── ai_agronomist: approvals require a gateway-authenticated tenant AND user (SEC-3.1) ──
# SEC-3 correction: approvals are web-UI human decisions (docstrings say so). The gateway
# strips X-Agent-Token, so a service-token gate would make them internal-only (break the
# human path). Instead they require the gateway-injected AUTHENTICATED X-Tenant-Id — a body
# alone can no longer reach them.
# SEC-3.1 (now implemented): a human decision must also be tied to an authenticated USER, not
# just a JSON body. nginx injects X-User-Id (from the verified JWT ``sub``) on the AI path;
# the approver of record is that trusted id, never the body's ``approver`` field. Missing
# X-User-Id ⇒ 403 missing_user.
_APPROVAL_BODY = {
    "approval": {
        "id": "req-sec3",
        "tool": "request_imagery_backfill",
        "params": {"field_id": "f1"},
        "tenant_id": "tenant-1",
        "status": "pending",
    },
    "approver": "user-1",
}
_APPROVAL_HEADERS = {"X-Tenant-Id": "tenant-1", "X-User-Id": "user-1"}


@pytest.mark.parametrize("path", ["/approvals/approve", "/approvals/deny"])
def test_approvals_without_tenant_rejected(path):
    _M, client = _ai_client()
    r = client.post(path, json=_APPROVAL_BODY)  # no X-Tenant-Id
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_tenant"


@pytest.mark.parametrize("path", ["/approvals/approve", "/approvals/deny"])
def test_approvals_without_user_rejected(path):
    """Tenant present but no authenticated user ⇒ fail-closed 403 missing_user (SEC-3.1)."""
    _M, client = _ai_client()
    r = client.post(path, json=_APPROVAL_BODY, headers={"X-Tenant-Id": "tenant-1"})
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_user"


def test_approvals_resume_without_tenant_rejected():
    _M, client = _ai_client()
    r = client.post("/approvals/resume", json={"approval_id": "whatever"})  # no X-Tenant-Id
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_tenant"


def test_approvals_resume_without_user_rejected():
    _M, client = _ai_client()
    r = client.post(
        "/approvals/resume", json={"approval_id": "whatever"}, headers={"X-Tenant-Id": "tenant-1"}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_user"


def test_approvals_with_tenant_and_user_passes_auth_gate():
    """With X-Tenant-Id + X-User-Id the auth gate passes (decision logic may 4xx, not 403)."""
    _M, client = _ai_client()
    r = client.post("/approvals/approve", json=_APPROVAL_BODY, headers=_APPROVAL_HEADERS)
    assert r.status_code != 403


def test_approvals_approver_of_record_is_authenticated_user():
    """SEC-3.1: the audited approver is the trusted X-User-Id, not the body's ``approver``."""
    _M, client = _ai_client()
    body = {**_APPROVAL_BODY, "approver": "spoofed-body-user"}
    r = client.post(
        "/approvals/approve",
        json=body,
        headers={"X-Tenant-Id": "tenant-1", "X-User-Id": "real-user-42"},
    )
    assert r.status_code == 200
    assert r.json()["approval"]["decided_by"] == "real-user-42"


# ── rag-retrieval: /search trusted-tenant guard ────────────────────────────────
def _rag_module():
    pytest.importorskip("fastapi")
    try:
        return _load_service_module(
            "rag_main_sec3",
            "services/rag-retrieval/main.py",
            ["services/sahool-platform", "services/rag-retrieval"],
            None,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"rag-retrieval module unavailable: {exc}")


def _rag_client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    M = _rag_module()
    return M, TestClient(M.app, raise_server_exceptions=False)


def _rag_search_body(tenant="tenant-1"):
    return {"tenant_id": tenant, "query": "q"}


def test_rag_search_missing_header_rejected():
    _M, client = _rag_client()
    r = client.post("/search", json=_rag_search_body())
    assert r.status_code == 403
    assert r.json()["detail"] == ERROR_MISSING_TENANT


def test_rag_search_body_mismatch_rejected():
    _M, client = _rag_client()
    r = client.post(
        "/search", json=_rag_search_body("tenant-EVIL"), headers={"X-Tenant-Id": "tenant-1"}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == ERROR_TENANT_MISMATCH


def test_rag_search_matching_tenant_uses_trusted_value(monkeypatch):
    M, client = _rag_client()
    captured = {}

    def _fake_retrieve(query, *, tenant_id, filters, final_k):
        captured["tenant_id"] = tenant_id
        return []

    monkeypatch.setattr(M._retriever, "retrieve", _fake_retrieve)
    r = client.post(
        "/search", json=_rag_search_body("tenant-1"), headers={"X-Tenant-Id": "tenant-1"}
    )
    assert r.status_code == 200
    assert captured["tenant_id"] == "tenant-1"


# ── rag-retrieval: /ingest is an internal write ⇒ requires the service token (SEC-4) ──
_INGEST_BODY = {
    "chunks": [
        {
            "chunk_id": "c-sec4",
            "tenant_id": "tenant-1",
            "text": "wheat needs water",
            "source_type": "manual",
            "document_id": "doc-1",
            "chunk_index": 0,
            "total_chunks": 1,
            "metadata": {"evidence_level": "field"},
        }
    ]
}


def test_rag_ingest_without_token_rejected(monkeypatch):
    _M, client = _rag_client()
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)
    r = client.post("/ingest", json=_INGEST_BODY)  # no X-Agent-Token
    assert r.status_code == 403
    assert r.json()["detail"] == "service_token_required"


def test_rag_ingest_with_token_not_rejected(monkeypatch):
    M, client = _rag_client()
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)
    # Stub the data-plane write so the test asserts the auth gate, not Qdrant I/O.
    monkeypatch.setattr(M._retriever, "ingest", lambda chunks: len(chunks))
    r = client.post("/ingest", json=_INGEST_BODY, headers={"X-Agent-Token": _AGENT_TOKEN})
    assert r.status_code != 403
    assert r.status_code == 200
    assert r.json()["ingested"] == 1


# ── knowledge-graph: writes require the service token, reads stay open ──────────
def _kg_module():
    pytest.importorskip("fastapi")
    try:
        tmp = os.path.join(tempfile.gettempdir(), "sec3_kg_test.sqlite")
        return _load_service_module(
            "kg_main_sec3",
            "services/knowledge-graph/main.py",
            ["services/sahool-platform", "services/knowledge-graph"],
            {"KG_SQLITE_PATH": tmp},
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"knowledge-graph module unavailable: {exc}")


def _kg_client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    M = _kg_module()
    return M, TestClient(M.app, raise_server_exceptions=False)


_NODE = {"node_id": "n-sec3", "label": "Crop", "name": "wheat"}
_EDGE = {
    "edge_id": "e-sec3",
    "subject_id": "n-sec3",
    "relation": "affects",
    "object_id": "n-sec3",
}


@pytest.mark.parametrize("path,payload", [("/nodes", _NODE), ("/edges", _EDGE)])
def test_kg_write_without_token_rejected(monkeypatch, path, payload):
    _M, client = _kg_client()
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)
    r = client.post(path, json=payload)
    assert r.status_code == 403
    assert r.json()["detail"] == "service_token_required"


def test_kg_write_with_token_allowed(monkeypatch):
    _M, client = _kg_client()
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)
    r = client.post("/nodes", json=_NODE, headers={"X-Agent-Token": _AGENT_TOKEN})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_kg_read_edges_stays_open_without_token():
    _M, client = _kg_client()
    # GET /edges is a read used by ai_agronomist without a token — must stay open.
    r = client.get("/edges", params={"subject_id": "anything"})
    assert r.status_code == 200
    assert "edges" in r.json()
