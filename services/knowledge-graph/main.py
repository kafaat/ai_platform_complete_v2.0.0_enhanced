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
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

app = FastAPI(title="SAHOOL Agricultural Knowledge Graph", version="2026.2")
store = SQLiteAgGraphStore(os.getenv("KG_SQLITE_PATH", "/data/kg.sqlite"))
seed_reference_ontology(store)


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


@app.post("/nodes")
async def upsert_node(node: NodeIn):
    store.upsert_node(GraphNode(**node.model_dump()))
    return {"ok": True}


@app.post("/edges")
async def upsert_edge(edge: EdgeIn):
    try:
        store.upsert_edge(GraphEdge(**edge.model_dump()))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.get("/edges")
async def edges(
    subject_id: str | None = None, relation: str | None = None, object_id: str | None = None
):
    return {
        "edges": store.query_edges(subject_id=subject_id, relation=relation, object_id=object_id)
    }


@app.post("/graphql")
async def graphql(req: GraphQLRequest):
    try:
        return graphql_readonly(store, req.query)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
