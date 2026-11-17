from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from kg_store import (
    EDGE_QUERY_MAX_LIMIT,
    EdgeConflictError,
    GraphEdge,
    GraphNode,
    GraphWriteRefused,
    SQLiteAgGraphStore,
    assert_global_reference_payload,
    graphql_readonly,
    seed_reference_ontology,
)
from pydantic import BaseModel, ConfigDict

from shared.security.gateway_deps import require_service_token, require_trusted_tenant

app = FastAPI(title="SAHOOL Agricultural Knowledge Graph", version="2026.2")


def _contains_lone_surrogate(value: Any) -> bool:
    # Iterative, so a deeply nested invalid body cannot make the error handler itself fail.
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if any("\ud800" <= ch <= "\udfff" for ch in item):
                return True
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return False


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> Response:
    # With extra="allow" pydantic validates top-level extra keys as strings, so a lone
    # surrogate there is a validation error, and FastAPI's default handler then fails to
    # encode the echoed input (a 500 before the guard ever runs). Refuse it as the guard does.
    if _contains_lone_surrogate(exc.errors()):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "kg_payload_unprocessable",
                    "path": "<body>",
                    "reason": "request is not valid Unicode",
                }
            },
        )
    return await request_validation_exception_handler(request, exc)


store = SQLiteAgGraphStore(os.getenv("KG_SQLITE_PATH", "/data/kg.sqlite"))
seed_reference_ontology(store)

MAX_GRAPHQL_QUERY_BYTES = int(os.getenv("KG_GRAPHQL_MAX_QUERY_BYTES", "4096"))
MAX_GRAPHQL_DEPTH = int(os.getenv("KG_GRAPHQL_MAX_DEPTH", "6"))
MAX_GRAPHQL_TOKENS = int(os.getenv("KG_GRAPHQL_MAX_TOKENS", "120"))


def _source_sha256(path: Path) -> str:
    """Digest shipped source bytes so live evidence can bind to the reviewed checkout."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_source_identity() -> dict[str, str]:
    source = Path(__file__).resolve()
    here = source.parent
    # Image layout is /app/shared/...; source-checkout layout is <repo>/shared/....
    gateway = here / "shared" / "security" / "gateway_deps.py"
    if not gateway.is_file():
        # Container flattens main.py to /app/main.py (no repo-tree parents[2]); walk up
        # from here instead of hardcoding a parent index (2026-07-12 startup regression).
        for base in here.parents:
            candidate = base / "shared" / "security" / "gateway_deps.py"
            if candidate.is_file():
                gateway = candidate
                break
    return {
        "main_sha256": _source_sha256(source),
        "kg_store_sha256": _source_sha256(here / "kg_store.py"),
        "gateway_deps_sha256": _source_sha256(gateway),
    }


def _graphql_depth(query: str) -> int:
    depth = 0
    max_depth = 0
    in_string = False
    escape = False
    for ch in query:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return max_depth


def _assert_graphql_query_budget(query: str) -> None:
    if len(query.encode("utf-8")) > MAX_GRAPHQL_QUERY_BYTES:
        raise HTTPException(413, "graphql_query_too_large")
    if _graphql_depth(query) > MAX_GRAPHQL_DEPTH:
        raise HTTPException(400, "graphql_query_too_deep")
    token_count = len(
        query.replace("{", " ").replace("}", " ").replace("(", " ").replace(")", " ").split()
    )
    if token_count > MAX_GRAPHQL_TOKENS:
        raise HTTPException(400, "graphql_query_too_complex")
    lowered = query.lower()
    if "__schema" in lowered or "__type" in lowered:
        raise HTTPException(400, "graphql_introspection_disabled")


class NodeIn(BaseModel):
    # Extra keys are kept (not silently dropped) so the #1472 guard sees a
    # top-level ``tenant_id`` and refuses it instead of storing a stripped record.
    model_config = ConfigDict(extra="allow")

    node_id: str
    label: str
    name: str
    properties: dict[str, Any] | None = None


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    edge_id: str
    subject_id: str
    relation: str
    object_id: str
    confidence: str = "reference"
    prescriptive: bool = False
    properties: dict[str, Any] | None = None


class GraphQLRequest(BaseModel):
    query: str


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "knowledge-graph", "edges": store.count_edges()}


@app.get("/metrics")
async def metrics():
    try:
        edge_count = store.count_edges()
    except Exception:
        edge_count = -1
    body = "\n".join(
        [
            "# HELP sahool_knowledge_graph_edges Current edge count or -1 when unavailable",
            "# TYPE sahool_knowledge_graph_edges gauge",
            f"sahool_knowledge_graph_edges {edge_count}",
            "",
        ]
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.get("/readyz")
async def readyz():
    try:
        edge_count = store.count_edges()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"knowledge graph store not ready: {exc}") from exc
    return {
        "status": "ready",
        "service": "knowledge-graph",
        "edges": edge_count,
        "source_identity": _runtime_source_identity(),
    }


def _refuse_tenant_scoped(exc: GraphWriteRefused) -> HTTPException:
    # #1472 / ADR-0038: the graph is a global reference store. 422 (413 for an
    # oversized payload) with a stable code.
    return HTTPException(exc.status, {"code": exc.code, "path": exc.path, "reason": exc.reason})


def _declared_fields(model: BaseModel) -> dict[str, Any]:
    return {name: getattr(model, name) for name in type(model).model_fields}


@app.post("/v1/nodes")
async def upsert_node(node: NodeIn, _token: None = Depends(require_service_token)):
    # SEC-3: graph writes are internal-only; require the trusted service token
    # (X-Agent-Token == SAHOOL_AGENT_TOKEN). Reads require gateway-injected tenant.
    try:
        # Whole body, extras included: a top-level tenant_id is refused, not dropped.
        assert_global_reference_payload(node.model_dump())
        store.upsert_node(GraphNode(**_declared_fields(node)))
    except GraphWriteRefused as exc:
        raise _refuse_tenant_scoped(exc) from exc
    return {"ok": True}


@app.post("/v1/edges")
async def upsert_edge(edge: EdgeIn, _token: None = Depends(require_service_token)):
    try:
        assert_global_reference_payload(edge.model_dump())
        store.upsert_edge(GraphEdge(**_declared_fields(edge)))
    except GraphWriteRefused as exc:
        raise _refuse_tenant_scoped(exc) from exc
    except EdgeConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.get("/v1/edges")
async def edges(
    subject_id: str | None = None,
    relation: str | None = None,
    object_id: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=EDGE_QUERY_MAX_LIMIT),
    _tenant: str = Depends(require_trusted_tenant),
):
    # C5: graph reads require a trusted X-Tenant-Id (gateway-injected). A missing
    # header fails closed (403 missing_tenant), preventing anonymous reads.
    # #1472 / ADR-0038: the header authenticates only; it is NOT a row filter. The
    # store is global reference data, so every tenant reads the same rows.
    # Bounded and ordered: a limit above EDGE_QUERY_MAX_LIMIT is refused (422); a read with
    # no filter is capped at EDGE_QUERY_UNFILTERED_MAX rows and says so (filtered/truncated),
    # so it can no longer enumerate the whole graph.
    return store.query_edges_page(
        subject_id=subject_id, relation=relation, object_id=object_id, limit=limit
    )


@app.post("/graphql")
async def graphql(req: GraphQLRequest, _tenant: str = Depends(require_trusted_tenant)):
    # Authentication only (see edges()); the facade is read-only, so no write path.
    _assert_graphql_query_budget(req.query)
    try:
        return graphql_readonly(store, req.query)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
