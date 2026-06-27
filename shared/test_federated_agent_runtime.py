from shared.federated_agent_runtime import (
    build_federation_event_envelope,
    create_authority_envelope,
    reputation_weighted_consensus,
    update_agent_reputation,
)


def _proposal(role, action, confidence=0.8, priority=20, flags=None):
    return {
        "proposal_id": f"p_{role}_{action}",
        "agent_role": role,
        "action": action,
        "confidence": confidence,
        "priority": priority,
        "safety_flags": flags or [],
        "evidence": {"source": "test"},
    }


def test_reputation_weighted_consensus_blocks_safety_veto():
    result = reputation_weighted_consensus(
        [
            _proposal("water", "irrigate", 0.94, 80),
            _proposal("safety", "block", 0.90, 90, ["unsafe_veto"]),
        ]
    )
    assert result["status"] == "blocked"
    assert result["selected_action"] is None
    assert result["approval_required"] is True
    assert result["vetoes"]


def test_high_impact_action_needs_human_approval_even_when_confident():
    result = reputation_weighted_consensus(
        [
            _proposal("water", "irrigate", 0.99, 80),
            _proposal("operations", "irrigate", 0.96, 70),
        ],
        execution_mode="autonomous",
        reputations={
            "water": {"score": 1.0, "sample_count": 10},
            "operations": {"score": 1.0, "sample_count": 10},
        },
    )
    assert result["selected_action"] == "irrigate"
    assert result["status"] == "needs_human_approval"
    assert result["approval_required"] is True


def test_authority_envelope_never_allows_direct_execution():
    cycle = {"cycle_id": "c1", "context": {"field_id": "field-1"}}
    resolution = {
        "resolution_id": "r1",
        "status": "needs_human_approval",
        "selected_action": "irrigate",
        "approval_required": True,
        "confidence": 0.8,
    }
    envelope = create_authority_envelope(
        cycle, resolution=resolution, requested_authority="execution"
    )
    assert envelope["may_execute"] is False
    assert "phase11_cannot_request_execution_authority" in envelope["blocked_reasons"]
    assert envelope["required_next_gate"] == "phase9_guardrails"


def test_reputation_update_penalizes_safety_incident():
    updated = update_agent_reputation(
        {"water": {"score": 0.8, "sample_count": 5}},
        agent_role="water",
        outcome="unsafe",
        safety_incident=True,
    )
    assert updated["water"]["score"] < 0.8
    assert updated["water"]["safety_incident_count"] == 1


def test_event_envelope_is_blocked_when_authority_cannot_publish():
    authority = {"envelope_id": "a1", "field_id": None, "may_publish_event": False}
    event = build_federation_event_envelope({"cycle_id": "c1"}, authority)
    assert event["event_type"] == "agent.federation.blocked"
    assert event["idempotency_key"].startswith("idem11_")
