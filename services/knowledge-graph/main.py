from __future__ import annotations

import os
from typing import Any

from core.knowledge_graph.sqlite_graph import (
    GraphEdge,
    GraphNode,
    SQLiteAgGraphStore,
    graphql_readonly,
    seed_reference_ontology,
)
from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel

from shared.security.gateway_deps import require_service_token, require_trusted_tenant

app = FastAPI(title="SAHOOL Agricultural Knowledge Graph", version="2026.2")
store = SQLiteAgGraphStore(os.getenv("KG_SQLITE_PATH", "/data/kg.sqlite"))
seed_reference_ontology(store)

MAX_GRAPHQL_QUERY_BYTES = int(os.getenv("KG_GRAPHQL_MAX_QUERY_BYTES", "4096"))
MAX_GRAPHQL_DEPTH = int(os.getenv("KG_GRAPHQL_MAX_DEPTH", "6"))
MAX_GRAPHQL_TOKENS = int(os.getenv("KG_GRAPHQL_MAX_TOKENS", "120"))


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
    node_id: str
    label: str
    name: str
    properties: dict[str, Any] | None = None


class EdgeIn(BaseModel):
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
    return {"status": "ready", "service": "knowledge-graph", "edges": edge_count}


@app.post("/v1/nodes")
async def upsert_node(node: NodeIn, _token: None = Depends(require_service_token)):
    # SEC-3: graph writes are internal-only; require the trusted service token
    # (X-Agent-Token == SAHOOL_AGENT_TOKEN). Reads require gateway-injected tenant.
    store.upsert_node(GraphNode(**node.model_dump()))
    return {"ok": True}


@app.post("/v1/edges")
async def upsert_edge(edge: EdgeIn, _token: None = Depends(require_service_token)):
    try:
        store.upsert_edge(GraphEdge(**edge.model_dump()))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.get("/v1/edges")
async def edges(
    subject_id: str | None = None,
    relation: str | None = None,
    object_id: str | None = None,
    _tenant: str = Depends(require_trusted_tenant),
):
    # C5: graph reads require a trusted X-Tenant-Id (gateway-injected). A missing
    # header fails closed (403 missing_tenant), preventing anonymous cross-tenant reads.
    return {
        "edges": store.query_edges(subject_id=subject_id, relation=relation, object_id=object_id)
    }


@app.post("/graphql")
async def graphql(req: GraphQLRequest, _tenant: str = Depends(require_trusted_tenant)):
    _assert_graphql_query_budget(req.query)
    try:
        return graphql_readonly(store, req.query)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
