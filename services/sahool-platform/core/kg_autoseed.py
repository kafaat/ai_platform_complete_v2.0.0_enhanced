"""Auto-seed contract for agricultural knowledge graph ontology.

This module is safe to run at container startup. It seeds only reference edges
when the graph is empty; it does not overwrite tenant data or prescriptive rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .kg_graphql_readonly import KnowledgeEdge


class GraphStore(Protocol):
    def count_edges(self) -> int: ...
    def insert_edges(self, edges: list[KnowledgeEdge]) -> int: ...


@dataclass
class InMemoryGraphStore:
    edges: list[KnowledgeEdge]

    def count_edges(self) -> int:
        return len(self.edges)

    def insert_edges(self, edges: list[KnowledgeEdge]) -> int:
        self.edges.extend(edges)
        return len(edges)


DEFAULT_REFERENCE_ONTOLOGY = [
    KnowledgeEdge("wheat", "historically_susceptible_to", "stripe_rust"),
    KnowledgeEdge("stripe_rust", "historically_favored_by", "cool_humid_weather"),
    KnowledgeEdge("soil_ec", "historically_limits", "salt_sensitive_crops"),
    KnowledgeEdge("irrigation_water_sar", "historically_increases_risk_of", "sodicity"),
]


def autoseed_if_empty(
    store: GraphStore, edges: list[KnowledgeEdge] | None = None
) -> dict[str, object]:
    if store.count_edges() > 0:
        return {"seeded": False, "inserted": 0, "reason": "graph_not_empty"}
    chosen = edges or DEFAULT_REFERENCE_ONTOLOGY
    for edge in chosen:
        if edge.prescriptive or edge.confidence != "reference":
            raise ValueError("Auto-seed accepts reference-only non-prescriptive edges")
    inserted = store.insert_edges(chosen)
    return {"seeded": True, "inserted": inserted, "reason": "graph_empty"}
