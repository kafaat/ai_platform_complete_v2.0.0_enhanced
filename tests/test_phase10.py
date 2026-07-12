from services.ai_agronomist.policy_engine import PolicyEngine


def test_policy():
    assert PolicyEngine().evaluate({"dose_kg_ha": 100}).allowed
