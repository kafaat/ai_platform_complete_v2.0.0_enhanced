from __future__ import annotations

import pytest
from core.crop_intelligence.policy_engine import (
    PolicyPack,
    PolicyRule,
    default_policy_packs,
    evaluate_crop_policy,
)


def test_default_policy_pack_is_complete_and_versioned():
    result = evaluate_crop_policy(facts={})
    assert {item["pack_type"] for item in result["policy_manifest"]} == {
        "crop",
        "water",
        "weather",
        "regional",
        "cultivar",
        "business",
    }
    assert all(item["policy_id"] and item["version"] for item in result["policy_manifest"])
    assert len(result["policy_digest"]) == 64


def test_policy_maps_facts_to_stress_and_urgency_deterministically():
    facts = {
        "water_needs_irrigation": True,
        "spectral_water_stress_confirmed": True,
        "weather_heat_stress": True,
        "weather_frost_risk": False,
        "crop_water_urgency_high": True,
    }
    first = evaluate_crop_policy(facts=facts)
    second = evaluate_crop_policy(facts=facts)
    assert first == second
    assert {flag["code"] for flag in first["stress_flags"]} == {
        "water_deficit",
        "spectral_water_stress",
        "heat_stress",
    }
    assert first["urgency"] == "high"
    assert first["decision_boundary"]["is_decision"] is False


def test_missing_required_pack_fails_closed():
    packs = tuple(p for p in default_policy_packs() if p.pack_type != "business")
    with pytest.raises(ValueError, match="missing required"):
        evaluate_crop_policy(facts={}, packs=packs)


def test_duplicate_rule_ids_fail_closed_even_inside_one_pack():
    packs = list(default_policy_packs())
    packs[0] = PolicyPack(
        "crop",
        "crop.custom",
        "1.0.0",
        (
            PolicyRule("duplicate", "weather_heat_stress", stress_code="a"),
            PolicyRule("duplicate", "weather_frost_risk", stress_code="b"),
        ),
    )
    with pytest.raises(ValueError, match="duplicate policy rule ids"):
        evaluate_crop_policy(facts={}, packs=packs)


def test_unknown_trigger_fails_closed():
    packs = list(default_policy_packs())
    packs[0] = PolicyPack(
        "crop",
        "crop.custom",
        "1.0.0",
        (PolicyRule("bad-trigger", "arbitrary_python_expression", stress_code="bad"),),
    )
    with pytest.raises(ValueError, match="unsupported policy trigger"):
        evaluate_crop_policy(facts={}, packs=packs)
