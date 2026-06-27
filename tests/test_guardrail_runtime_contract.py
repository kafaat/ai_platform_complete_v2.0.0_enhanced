
def test_runtime_flags_safe_defaults():
    from config.guardrail_feature_flags import (
        ENABLE_PONYTAIL_GUARDRAILS,
        ENABLE_LEGACY_RECOMMENDATION_FALLBACK,
        REQUIRE_CANONICAL_FIELD_STATE,
    )
    assert ENABLE_LEGACY_RECOMMENDATION_FALLBACK is True
    assert REQUIRE_CANONICAL_FIELD_STATE is True


def test_ponytail_irrigation_requires_weather_before_bypass():
    import importlib.util, sys
    from pathlib import Path
    core = Path(__file__).resolve().parents[1] / "services" / "sahool-platform" / "core" / "guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails_contract_order", core)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["guardrails_contract_order"] = mod
    spec.loader.exec_module(mod)
    out = mod.RecommendationPonytail().filter(
        mod.PonytailIntent("irrigation", "simple_query", "F-1"),
        mod.FieldStateSnapshot(irrigation_state={"etc_mm": 40}, confidence=0.9),
        mod.EvidenceSummary(has_weather=False),
    )
    assert out.action == mod.PonytailAction.INSUFFICIENT_EVIDENCE


def test_ponytail_bypass_payload_is_hint_not_decision():
    import importlib.util, sys
    from pathlib import Path
    core = Path(__file__).resolve().parents[1] / "services" / "sahool-platform" / "core" / "guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails_contract_hint", core)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["guardrails_contract_hint"] = mod
    spec.loader.exec_module(mod)
    out = mod.RecommendationPonytail().filter(
        mod.PonytailIntent("irrigation", "simple_query", "F-1"),
        mod.FieldStateSnapshot(irrigation_state={"etc_mm": 40}, weather_state={"et0": 5}, confidence=0.9),
        mod.EvidenceSummary(has_weather=True),
    )
    assert out.action == mod.PonytailAction.BYPASS_LLM
    assert out.response["response_type"] == "computed_field_state_hint"
    assert "action" not in out.response
