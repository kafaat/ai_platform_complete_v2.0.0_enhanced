"""Read-only GraphQL-like query facade for the agricultural knowledge graph.

This is intentionally a tiny dependency-free adapter, not a full GraphQL server.
It establishes the contract: KG is reference-only, relationships are not
prescriptive, and every returned edge carries confidence='reference'.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class KnowledgeEdge:
    subject: str
    relation: str
    object: str
    confidence: str = "reference"
    prescriptive: bool = False


class ReadOnlyAgKnowledgeGraph:
    def __init__(self, edges: list[KnowledgeEdge] | None = None) -> None:
        self.edges = edges or []

    def query_edges(self, subject: str | None = None, relation: str | None = None) -> list[dict]:
        rows = []
        for edge in self.edges:
            if subject is not None and edge.subject != subject:
                continue
            if relation is not None and edge.relation != relation:
                continue
            rows.append(asdict(edge))
        return rows

    def graphql(self, query: str) -> dict:
        """Very small safe query adapter for tests/UI exploration.

        Supports simple text filters like subject:"wheat" and relation:"historically_limits".
        Unknown query text returns all edges, still read-only.
        """
        subject = None
        relation = None
        if 'subject:"' in query:
            subject = query.split('subject:"', 1)[1].split('"', 1)[0]
        if 'relation:"' in query:
            relation = query.split('relation:"', 1)[1].split('"', 1)[0]
        return {"edges": self.query_edges(subject=subject, relation=relation)}
