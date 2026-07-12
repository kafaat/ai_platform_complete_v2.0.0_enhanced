from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/sahool-platform"))
sys.path.insert(0, str(ROOT / "services/mcp_servers"))

from core.knowledge_graph.sqlite_graph import (  # noqa: E402
    GraphEdge,
    GraphNode,
    SQLiteAgGraphStore,
    graphql_readonly,
    seed_reference_ontology,
)
from core.mcp.independent_servers import IndependentMCPServer, MCPTool  # noqa: E402
from core.rag.production_qdrant import (  # noqa: E402
    HashEmbeddingProvider,
    HybridQdrantRetriever,
    KnowledgeChunk,
)


class FakeQdrant:
    vector_size = 32

    def __init__(self):
        self.points = {}

    def ensure_collection(self):
        self.ready = True

    def upsert(self, chunks, embeddings):
        for chunk, vector in zip(chunks, embeddings, strict=True):
            self.points[chunk.chunk_id] = (chunk, vector)

    def search(self, vector, *, tenant_id, filters=None, limit=12):
        filters = filters or {}
        rows = []
        for cid, (chunk, stored) in self.points.items():
            if chunk.tenant_id != tenant_id:
                continue
            if any(
                value is not None and chunk.payload.get(key) != value
                for key, value in filters.items()
            ):
                continue
            score = sum(a * b for a, b in zip(vector, stored, strict=True))
            rows.append((cid, score, chunk.payload))
        return sorted(rows, key=lambda row: row[1], reverse=True)[:limit]


def _chunk(cid, tenant, text, idx=0, crop="wheat"):
    return KnowledgeChunk(
        chunk_id=cid,
        tenant_id=tenant,
        text=text,
        source_type="manual",
        document_id="doc-1",
        chunk_index=idx,
        total_chunks=3,
        metadata={"evidence_level": "manual", "crop": crop, "section": "test", "page": 1},
    )


def test_hybrid_qdrant_retrieval_enforces_tenant_and_metadata():
    retriever = HybridQdrantRetriever(FakeQdrant(), HashEmbeddingProvider(32))
    retriever.ingest(
        [
            _chunk("a", "t1", "wheat irrigation EC pH nitrogen", 0),
            _chunk("b", "t1", "adjacent wheat salinity management", 1),
            _chunk("c", "t2", "wheat irrigation secret tenant", 0),
        ]
    )
    rows = retriever.retrieve(
        "EC pH irrigation", tenant_id="t1", filters={"crop": "wheat"}, final_k=5
    )
    ids = [r.chunk.chunk_id for r in rows]
    assert "a" in ids
    assert "c" not in ids
    assert all(r.as_annotation()["decision_authority"] == "none" for r in rows)


def test_rag_rejects_lab_evidence_level():
    try:
        KnowledgeChunk(
            chunk_id="bad",
            tenant_id="t1",
            text="lab result",
            source_type="lab_report",
            document_id="doc",
            chunk_index=0,
            total_chunks=1,
            metadata={"evidence_level": "lab"},
        )
    except ValueError as exc:
        assert "lab evidence" in str(exc)
    else:
        raise AssertionError("RAG must not claim lab evidence")


def test_sqlite_knowledge_graph_is_persistent_and_reference_only():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "kg.sqlite"
        store = SQLiteAgGraphStore(db)
        assert seed_reference_ontology(store) >= 1
        reopened = SQLiteAgGraphStore(db)
        edges = reopened.query_edges(subject_id="wheat")
        assert edges
        assert all(row["confidence"] == "reference" for row in edges)
        result = graphql_readonly(reopened, 'query { edges(subject:"wheat") { relation object } }')
        assert result["edges"]


def test_kg_rejects_prescriptive_edges_and_bad_relations():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteAgGraphStore(Path(tmp) / "kg.sqlite")
        store.upsert_node(GraphNode("a", "Treatment", "A"))
        store.upsert_node(GraphNode("b", "Disease", "B"))
        for edge in [
            lambda: GraphEdge("e", "a", "historically_used_for", "b", prescriptive=True),
            lambda: GraphEdge("e", "a", "controls", "b"),
        ]:
            try:
                edge()
            except ValueError:
                pass
            else:
                raise AssertionError("KG accepted a prescriptive edge")


def test_independent_mcp_server_emits_only_context_objects():
    server = IndependentMCPServer(
        server_name="lab-mcp-server",
        service_name="lab",
        tools={
            "get_lab_context": MCPTool(
                "get_lab_context",
                "lab",
                "signal",
                lambda args: {"type": "signal", "name": "lab", "value": args},
            )
        },
    )
    result = server.call_tool("get_lab_context", {"soil_ec": 2.1})
    assert result["type"] == "signal"
    assert result["output_contract"] == "signal"


def test_independent_mcp_server_rejects_recommendations():
    server = IndependentMCPServer(
        server_name="bad-mcp-server",
        service_name="bad",
        tools={
            "bad": MCPTool(
                "bad", "bad", "signal", lambda args: {"type": "signal", "recommendation": "apply"}
            )
        },
    )
    try:
        server.call_tool("bad", {})
    except ValueError as exc:
        assert "recommendations" in str(exc)
    else:
        raise AssertionError("MCP server emitted a recommendation")
