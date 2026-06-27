from shared.federated_agents_phase11 import (
    build_agent_context,
    create_autonomous_operation_plan,
    design_shadow_experiment,
    evaluate_agent_consensus_quality,
    reach_consensus,
    run_phase11_federation_cycle,
    run_specialist_agents,
)


def sample_state(**overrides):
    state = {
        "field_id": "field-1",
        "crop": "wheat",
        "confidence": 0.82,
        "operational_truths": {
            "water_stress": 0.72,
            "soil_moisture": 0.21,
            "heat_risk": 0.6,
            "vigor": 0.52,
            "disease_risk": 0.2,
            "salinity_risk": 0.2,
        },
    }
    state.update(overrides)
    return state


def test_context_and_specialist_agents_generate_irrigation_proposal():
    ctx = build_agent_context(canonical_field_state=sample_state(), market_context={"expected_margin": 0.2})
    proposals = run_specialist_agents(ctx)
    assert any(p["action"] == "irrigate" and p["agent_role"] == "water" for p in proposals)
    assert ctx["field_id"] == "field-1"


def test_consensus_blocks_on_safety_veto():
    ctx = build_agent_context(canonical_field_state=sample_state(operational_truths={"water_stress": 0.8, "salinity_risk": 0.9}))
    proposals = run_specialist_agents(ctx)
    consensus = reach_consensus(proposals, execution_mode="autonomous")
    assert consensus["status"] == "blocked"
    assert consensus["selected_action"] is None
    assert consensus["vetoes"]


def test_operation_plan_requires_human_for_actuation_in_human_loop():
    ctx = build_agent_context(canonical_field_state=sample_state())
    proposals = run_specialist_agents(ctx)
    consensus = reach_consensus(proposals, execution_mode="human_in_loop")
    plan = create_autonomous_operation_plan(consensus, ctx, execution_mode="human_in_loop")
    assert plan["action"] in {"irrigate", "scout", "wait", "recompute", None}
    assert plan["execution_mode"] == "human_in_loop"
    assert isinstance(plan["safety_gates"], list)


def test_shadow_experiment_caps_traffic_and_sets_guardrails():
    exp = design_shadow_experiment(name="policy-test", objective="yield", champion_policy="v1", challenger_policy="v2", traffic_pct=0.8)
    assert exp["traffic_split"]["challenger"] == 0.5
    assert exp["guardrails"]["human_approval_for_actuation"] is True


def test_full_phase11_cycle_includes_consensus_and_experiment():
    cycle = run_phase11_federation_cycle(
        canonical_field_state=sample_state(),
        execution_mode="shadow",
        experiment={"name": "shadow-policy", "champion_policy": "safe-v1", "challenger_policy": "smart-v2"},
    )
    assert cycle["cycle_id"].startswith("fedcycle_")
    assert cycle["proposals"]
    assert cycle["consensus"]["proposal_count"] == len(cycle["proposals"])
    assert cycle["operation_plan"]["dispatch_ready"] is False
    assert cycle["experiment_plan"]["mode"] == "shadow"


def test_consensus_quality_recommends_shadow_for_low_confidence():
    cycles = [
        {"consensus": {"status": "needs_human_approval", "confidence": 0.4}},
        {"consensus": {"status": "needs_human_approval", "confidence": 0.5}},
    ]
    quality = evaluate_agent_consensus_quality(cycles)
    assert quality["status"] == "shadow_only"
