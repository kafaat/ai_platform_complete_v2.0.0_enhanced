"""B6-STRUCTURED-PROPOSAL-CORE-LANDED-DISABLED-01: real HTTP route and rules.

Isolated subprocess avoids collisions with other services named main. ASGI runs
in process without deployment lifespan; persistence entry points fail if reached.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_real_evaluation_route_rules_and_no_persistence():
    script = r"""
import asyncio
import json
from uuid import uuid4
import httpx
import asyncpg
import main

async def forbidden(*args, **kwargs):
    raise AssertionError("evaluation attempted persistence")

async def run():
    engine = main.get_guardrails_engine()
    engine.human_workflow.create = forbidden
    asyncpg.connect = forbidden
    asyncpg.create_pool = forbidden
    tenant = str(uuid4())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://local") as client:
        for action, chemical, cost, expected in [
            ("pesticide", "sulfur", 100, None),
            ("pesticide", "ddt", 100, "banned_substance"),
            ("pesticide", "unknown_test_chemical", 100, "unknown_chemical"),
            ("investment", "sulfur", 4000, "investment_capacity_exceeded"),
        ]:
            request = dict(action_type=action, action_data=dict(chemical=chemical, crop="grape", dosage_kg_ha=1, cost_usd=cost, projected_revenue_increase_usd=6000), farm_context=dict(annual_revenue_usd=10000, annual_costs_usd=1200, cash_reserve_usd=1000), tenant_id=tenant, user_id=1, evaluation_only=False, auto_approve_low_risk=True)
            response = await client.post("/v1/evaluate", json=request, headers={"X-Agent-Token": main._GR_AGENT_TOKEN})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["allowed"] is False and result["evaluation_only"] is True
            assert result["approval_workflow_id"] is None
            failed = [check for check in result["tier_checks"] if not check["passed"]]
            rules = [finding.get("rule") for check in failed for finding in check["findings"]]
            if expected:
                assert expected in rules, result
                assert rules and all(rules), result
            else:
                assert not failed, result
            print(json.dumps({"case": expected or "valid_evaluation_only", "result": result}))
        request["farm_context"] = {}
        malformed = await client.post("/v1/evaluate", json=request, headers={"X-Agent-Token": main._GR_AGENT_TOKEN})
        assert malformed.status_code == 422, malformed.text
        assert "annual_revenue_usd" in malformed.text
        unauthorized = await client.post("/v1/evaluate", json=request)
        assert unauthorized.status_code in (401,403), unauthorized.text
asyncio.run(run())
"""
    env = dict(os.environ, PYTHONPATH=str(ROOT), SAHOOL_AGENT_TOKEN="test-" + os.urandom(24).hex())
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "services/guardrails-engine",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
