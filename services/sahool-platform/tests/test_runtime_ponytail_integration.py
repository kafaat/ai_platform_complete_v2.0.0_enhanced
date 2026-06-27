from core import internal_orchestrator as orch
from core.canonical_schemas import UserRole, UserSchema


def _user(role=UserRole.AGRONOMIST, tenant="tnt_001"):
    return UserSchema(user_id="u", tenant_id=tenant, role=role, name_ar="x", is_active=True)


def _validation(**extra):
    base = {
        "quality_grade": "READY",
        "blocked": False,
        "missing_blockers": [],
        "missing_observables": [],
        "field_state": "ready",
    }
    base.update(extra)
    return base


def test_ponytail_runtime_flag_defaults_off(monkeypatch):
    assert orch.ENABLE_LEGACY_RECOMMENDATION_FALLBACK is True


def test_enabled_ponytail_blocks_fertilization_without_lab(monkeypatch):
    monkeypatch.setattr(orch, "ENABLE_PONYTAIL_GUARDRAILS", True)
    result = orch.orchestrate_recommendation(
        user=_user(),
        tenant_id="tnt_001",
        farm_id="frm_01",
        field_id="fld_03",
        crop="wheat",
        validation=_validation(has_lab=False),
        issue_type="fertilization",
        current_indicators={"ndvi": 0.55},
        field_state="ready",
    )
    assert not result.delivered
    assert result.base_recommendation.get("guardrail_blocked") is True
    assert "Ponytail" in result.reason_ar


def test_enabled_ponytail_allows_legacy_engine_when_evidence_present(monkeypatch):
    monkeypatch.setattr(orch, "ENABLE_PONYTAIL_GUARDRAILS", True)
    result = orch.orchestrate_recommendation(
        user=_user(),
        tenant_id="tnt_001",
        farm_id="frm_01",
        field_id="fld_03",
        crop="wheat",
        validation=_validation(has_lab=True, has_weather=True, lab_state={"ec": 2.1}),
        issue_type="fertilization",
        current_indicators={"ndvi": 0.55},
        field_state="ready",
    )
    assert result.delivered
