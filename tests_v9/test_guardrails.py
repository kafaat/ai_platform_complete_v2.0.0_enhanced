"""Guardrails Engine Tests — SAHOOL v9.1.0

The unit tests here exercise the real engine and its tiers (loaded from
``services/guardrails-engine``), not restated constants.
"""

import asyncio
import importlib.util
import os
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.join(os.path.dirname(__file__), "..")
GR = os.path.join(ROOT, "services/guardrails-engine")
TENANT = "11111111-1111-4111-8111-111111111111"
_PREFIXES = (
    "main",
    "contracts",
    "human_in_loop",
    "tiers",
    "routers",
    "router_registry",
    "diff_generator",
)


def _owned(name: str) -> bool:
    return any(name == p or name.startswith(p + ".") for p in _PREFIXES)


@pytest.fixture(scope="module")
def gr_mod():
    # Deployment-local absolute imports (main, tiers, ...) collide with other services.
    saved = {k: v for k, v in sys.modules.items() if _owned(k)}
    for name in saved:
        sys.modules.pop(name)
    sys.path.insert(0, GR)
    try:
        spec = importlib.util.spec_from_file_location("main", os.path.join(GR, "main.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["main"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path.remove(GR)
        for name in list(sys.modules):
            if _owned(name):
                sys.modules.pop(name)
        sys.modules.update(saved)


def _pesticide(chemical, dosage, crop=None, ctx_crop=None):
    data = {
        "chemical": chemical,
        "dosage_kg_ha": dosage,
        "cost_usd": 50,
        "projected_revenue_increase_usd": 200,
    }
    ctx = {"annual_revenue_usd": 10000, "annual_costs_usd": 6000, "cash_reserve_usd": 5000}
    if crop is not None:
        data["crop"] = crop
    if ctx_crop is not None:
        ctx["crop"] = ctx_crop
    return {
        "action_type": "pesticide",
        "action_data": data,
        "farm_context": ctx,
        "user_id": 1,
        "tenant_id": TENANT,
    }


def _chem(gr_mod, chemical, dosage, crop=None, ctx_crop=None):
    p = _pesticide(chemical, dosage, crop, ctx_crop)
    tier = gr_mod.ChemicalSafetyTier()
    return asyncio.run(tier.validate("pesticide", p["action_data"], p["farm_context"]))


def _rules(check):
    return {f["rule"]: f["severity"] for f in check["findings"]}


def _engine(gr_mod):
    eng = gr_mod.SAHOOLGuardrailsEngine()
    eng.human_workflow.create = AsyncMock(return_value="persisted-review")
    return eng


class TestChemicalTier:
    @pytest.mark.unit
    @pytest.mark.parametrize("crop", ["tomato", "Tomato", " TOMATO "])
    def test_crop_ban_matches_regardless_of_case(self, gr_mod, crop):
        check = _chem(gr_mod, "chlorpyrifos", 0.3, crop=crop)
        assert _rules(check).get("banned_for_crop") == "CRITICAL"
        assert check["passed"] is False

    @pytest.mark.unit
    @pytest.mark.parametrize("action_crop", [None, "", "  "])
    def test_crop_ban_uses_farm_context_crop(self, gr_mod, action_crop):
        check = _chem(gr_mod, "chlorpyrifos", 0.3, crop=action_crop, ctx_crop="Tomato")
        assert _rules(check).get("banned_for_crop") == "CRITICAL"
        assert check["passed"] is False

    @pytest.mark.unit
    def test_crop_dosage_limit_matches_regardless_of_case(self, gr_mod):
        # abamectin: absolute 0.03, tomato 0.02.
        check = _chem(gr_mod, "abamectin", 0.03, crop="Tomato")
        assert _rules(check).get("crop_dosage_exceeded") == "MEDIUM"

    @pytest.mark.unit
    @pytest.mark.parametrize("crop", [None, "", "   "])
    def test_missing_crop_for_crop_specific_chemical_fails_closed(self, gr_mod, crop):
        check = _chem(gr_mod, "chlorpyrifos", 0.3, crop=crop)
        assert _rules(check).get("crop_unspecified") == "HIGH"
        assert check["passed"] is False

    @pytest.mark.unit
    def test_known_crop_within_limits_passes(self, gr_mod):
        check = _chem(gr_mod, "chlorpyrifos", 0.3, crop="Wheat")
        assert check["findings"] == [] and check["passed"] is True

    @pytest.mark.unit
    def test_banned_substance_is_critical(self, gr_mod):
        check = _chem(gr_mod, "DDT", 1, crop="wheat")
        assert _rules(check).get("banned_substance") == "CRITICAL"


class TestEnvironmentalTier:
    @pytest.mark.unit
    def test_carbon_budget_matches_crop_regardless_of_case(self, gr_mod):
        # potato budget 300; 40 kg N * 8 = 320 kg CO2e (under the 500 default).
        tier = gr_mod.EnvironmentalSafetyTier()
        check = asyncio.run(
            tier.validate(
                "fertilization",
                {"N_kg_ha": 40, "P_kg_ha": 0, "K_kg_ha": 0},
                {"crop": "Potato", "season_carbon_kg_co2e": 0, "annual_N_kg_ha": 0},
            )
        )
        assert any("(300)" in f["message_ar"] for f in check["findings"]), check


class TestEngineDecision:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "chemical,crop,rule",
        [
            ("ddt", "wheat", "banned_substance"),
            ("paraquat", "wheat", "banned_substance"),
            ("chlorpyrifos", "Tomato", "banned_for_crop"),
        ],
    )
    def test_banned_is_rejected_without_approval_workflow(self, gr_mod, chemical, crop, rule):
        eng = _engine(gr_mod)
        request = gr_mod.GuardrailsRequest(**_pesticide(chemical, 0.3, crop=crop))
        result = asyncio.run(eng.validate(request))
        rules = {f.get("rule") for c in result.tier_checks for f in c["findings"]}
        assert rule in rules
        assert result.allowed is False
        assert result.requires_human_approval is False
        assert result.approval_workflow_id is None
        assert result.diff is not None
        assert "تم الرفض" in result.arabic_explanation
        eng.human_workflow.create.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.parametrize("chemical", ["unlisted_compound", "glyphosate", "atrazine"])
    def test_restricted_or_unknown_still_goes_to_human_review(self, gr_mod, chemical):
        # glyphosate/atrazine are restricted (MEDIUM/HIGH banned_substance), not prohibited.
        eng = _engine(gr_mod)
        request = gr_mod.GuardrailsRequest(**_pesticide(chemical, 0.3, crop="wheat"))
        result = asyncio.run(eng.validate(request))
        assert result.allowed is False and result.requires_human_approval is True
        assert result.approval_workflow_id == "persisted-review"
        eng.human_workflow.create.assert_awaited_once()

    @pytest.mark.unit
    def test_evaluation_only_with_banned_substance_is_unchanged(self, gr_mod):
        eng = _engine(gr_mod)
        p = _pesticide("ddt", 0.3, crop="wheat")
        p["evaluation_only"] = True
        result = asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p)))
        assert result.evaluation_only is True and result.allowed is False
        assert result.approval_workflow_id is None
        eng.human_workflow.create.assert_not_awaited()


class TestReadiness:
    @pytest.mark.unit
    @pytest.mark.parametrize("token", ["", "tökén"])
    def test_readyz_not_ready_without_service_token(self, gr_mod, monkeypatch, token):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(gr_mod, "_GR_AGENT_TOKEN", token)
        response = TestClient(gr_mod.app).get("/readyz")
        assert response.status_code == 503
        assert "service_token" in response.text

    @pytest.mark.unit
    def test_readyz_ready_with_service_token(self, gr_mod, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(gr_mod, "_GR_AGENT_TOKEN", "service-token")
        response = TestClient(gr_mod.app).get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


class TestGuardrailsEndpoints:
    @pytest.mark.integration
    async def test_validate_endpoint(self, http_client, auth_headers):
        from conftest import service_urls

        resp = await http_client.post(
            f"{service_urls['guardrails']}/v1/validate",
            json={"action": "irrigate", "field_id": "field_01", "amount_mm": 25},
            headers=auth_headers,
        )
        assert resp.status_code in [200, 201]
        data = resp.json()
        assert "risk" in data or "overall_risk" in data
