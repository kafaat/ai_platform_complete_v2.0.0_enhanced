import pytest
from core.decision_firewall import (
    CanonicalFieldStateFirewall,
    FieldSignal,
    InsufficientEvidenceError,
    from_context_bundle,
)
from core.field_context_coordinator import FieldContextCoordinator
from core.kg_graphql_readonly import KnowledgeEdge, ReadOnlyAgKnowledgeGraph
from core.resumable_stream import InMemoryStreamStore


def test_rag_and_kg_are_annotations_not_recommendation_inputs():
    bundle = FieldContextCoordinator().assemble(
        "F1",
        [
            {
                "source": "lab",
                "kind": "lab",
                "payload": {"name": "soil_ec", "value": 3.2, "verified": True},
            },
            {"source": "rag", "kind": "rag", "payload": {"text": "manual says irrigate"}},
            {"source": "kg", "kind": "kg", "payload": {"edge": "wheat historically_used_for X"}},
        ],
    )
    fw = from_context_bundle(bundle)
    assert fw.recommendation_inputs() == {"soil_ec": 3.2}
    assert len(fw.annotations) == 2
    with pytest.raises(AttributeError):
        _ = bundle.recommendation


def test_firewall_requires_verified_inputs():
    fw = CanonicalFieldStateFirewall("F1").add_signal(
        FieldSignal("weather", {"et0": 6}, "weather", verified=False)
    )
    with pytest.raises(InsufficientEvidenceError):
        fw.require("weather")


def test_resumable_stream_returns_chunks_after_offset():
    store = InMemoryStreamStore()
    store.append("s1", "a")
    store.append("s1", "b")
    store.append("s1", "c")
    assert store.checkpoint("s1").offset == 3
    assert store.resume("s1", after_offset=1) == ["b", "c"]


def test_kg_graphql_is_reference_only():
    kg = ReadOnlyAgKnowledgeGraph(
        [
            KnowledgeEdge("wheat", "historically_susceptible_to", "stripe_rust"),
            KnowledgeEdge("soil_ec", "historically_limits", "wheat"),
        ]
    )
    rows = kg.graphql('query { edges(subject:"wheat") { relation object } }')["edges"]
    assert rows[0]["confidence"] == "reference"
    assert rows[0]["prescriptive"] is False
