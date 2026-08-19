"""SQLite-backed agricultural graph store.

This is a real persistent graph store with nodes/edges tables. It is not a
recommendation engine. Every edge is reference-only unless a separate agronomic
engine and human review convert a recommendation downstream.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED_REFERENCE_RELATIONS = (
    "historically_susceptible_to",
    "historically_favored_by",
    "historically_limits",
    "historically_used_for",
)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    name: str
    properties: dict[str, Any] | None = None


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    subject_id: str
    relation: str
    object_id: str
    confidence: str = "reference"
    prescriptive: bool = False
    properties: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.prescriptive:
            raise ValueError("Knowledge graph edges must not be prescriptive")
        if self.confidence != "reference":
            raise ValueError("Knowledge graph confidence must be 'reference'")
        if self.relation in {"controls", "recommends", "prescribes"}:
            raise ValueError("Use reference relation names such as historically_used_for")


class SQLiteAgGraphStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS kg_nodes (
                    node_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    name TEXT NOT NULL,
                    properties_json TEXT NOT NULL DEFAULT '{}'
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS kg_edges (
                    edge_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL REFERENCES kg_nodes(node_id),
                    relation TEXT NOT NULL,
                    object_id TEXT NOT NULL REFERENCES kg_nodes(node_id),
                    confidence TEXT NOT NULL CHECK(confidence='reference'),
                    prescriptive INTEGER NOT NULL CHECK(prescriptive=0),
                    properties_json TEXT NOT NULL DEFAULT '{}'
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_subject ON kg_edges(subject_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_relation ON kg_edges(relation)")

    def upsert_node(self, node: GraphNode) -> None:
        import json

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kg_nodes(node_id,label,name,properties_json) VALUES(?,?,?,?) "
                "ON CONFLICT(node_id) DO UPDATE SET label=excluded.label,name=excluded.name,properties_json=excluded.properties_json",
                (
                    node.node_id,
                    node.label,
                    node.name,
                    json.dumps(node.properties or {}, ensure_ascii=False),
                ),
            )

    def upsert_edge(self, edge: GraphEdge) -> None:
        import json

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kg_edges(edge_id,subject_id,relation,object_id,confidence,prescriptive,properties_json) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(edge_id) DO UPDATE SET relation=excluded.relation,properties_json=excluded.properties_json",
                (
                    edge.edge_id,
                    edge.subject_id,
                    edge.relation,
                    edge.object_id,
                    edge.confidence,
                    0,
                    json.dumps(edge.properties or {}, ensure_ascii=False),
                ),
            )

    def count_edges(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0])

    def query_edges(
        self,
        *,
        subject_id: str | None = None,
        relation: str | None = None,
        object_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT e.edge_id,e.subject_id,s.name AS subject_name,e.relation,e.object_id,o.name AS object_name,
                   e.confidence,e.prescriptive,e.properties_json
            FROM kg_edges e
            JOIN kg_nodes s ON s.node_id=e.subject_id
            JOIN kg_nodes o ON o.node_id=e.object_id
            WHERE 1=1
        """
        params: list[Any] = []
        if subject_id:
            query += " AND e.subject_id=?"
            params.append(subject_id)
        if relation:
            query += " AND e.relation=?"
            params.append(relation)
        if object_id:
            query += " AND e.object_id=?"
            params.append(object_id)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def graph_context_for_crop(self, crop_id: str) -> dict[str, Any]:
        return {
            "type": "kg_annotation",
            "verified": False,
            "decision_authority": "none",
            "edges": self.query_edges(subject_id=crop_id),
        }


def seed_reference_ontology(store: SQLiteAgGraphStore) -> int:
    if store.count_edges() > 0:
        return 0
    nodes = [
        GraphNode("wheat", "Crop", "Wheat"),
        GraphNode("stripe_rust", "Disease", "Stripe rust"),
        GraphNode("cool_humid_weather", "WeatherRisk", "Cool humid weather"),
        GraphNode("soil_ec", "SoilCondition", "Soil electrical conductivity"),
        GraphNode("salt_sensitive_crops", "CropGroup", "Salt-sensitive crops"),
        GraphNode(
            "fungicide_review_required",
            "Treatment",
            "Fungicide option requires agronomist review",
            {"requires_phi": True},
        ),
    ]
    for node in nodes:
        store.upsert_node(node)
    edges = [
        GraphEdge("e1", "wheat", SEED_REFERENCE_RELATIONS[0], "stripe_rust"),
        GraphEdge("e2", "stripe_rust", SEED_REFERENCE_RELATIONS[1], "cool_humid_weather"),
        GraphEdge("e3", "soil_ec", SEED_REFERENCE_RELATIONS[2], "salt_sensitive_crops"),
        GraphEdge(
            "e4",
            "fungicide_review_required",
            SEED_REFERENCE_RELATIONS[3],
            "stripe_rust",
            properties={"human_review_required": True},
        ),
    ]
    for edge in edges:
        store.upsert_edge(edge)
    return len(edges)


def graphql_readonly(store: SQLiteAgGraphStore, query: str) -> dict[str, Any]:
    """Dependency-free read-only GraphQL-like facade.

    Supports filters: subject:"wheat" relation:"historically_susceptible_to".
    Mutations are rejected explicitly.
    """
    lowered = query.lower()
    if "mutation" in lowered or "delete" in lowered or "update" in lowered:
        raise ValueError("Knowledge Graph GraphQL facade is read-only")
    subject = None
    relation = None
    if 'subject:"' in query:
        subject = query.split('subject:"', 1)[1].split('"', 1)[0]
    if 'relation:"' in query:
        relation = query.split('relation:"', 1)[1].split('"', 1)[0]
    return {"edges": store.query_edges(subject_id=subject, relation=relation)}
