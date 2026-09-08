"""Real request/engine/HIL behavior. Storage doubles are not proof of live PostgreSQL RLS."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

pytestmark = pytest.mark.unit
ROOT = os.path.join(os.path.dirname(__file__), "..")
GR = os.path.join(ROOT, "services/guardrails-engine")
TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


@pytest.fixture(scope="module")
def gr_mod():
    # The service uses deployment-local absolute imports; isolate them from other services.
    prefixes = (
        "main",
        "contracts",
        "human_in_loop",
        "tiers",
        "routers",
        "router_registry",
        "diff_generator",
    )
    saved = {
        k: v
        for k, v in sys.modules.items()
        if any(k == p or k.startswith(p + ".") for p in prefixes)
    }
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
            if any(name == p or name.startswith(p + ".") for p in prefixes):
                sys.modules.pop(name)
        sys.modules.update(saved)


def payload(action="investment"):
    data = {"cost_usd": 100, "projected_revenue_increase_usd": 150}
    data.update({"loan_amount_usd": 100} if action == "loan" else {})
    data.update({"contract_value_usd": 100} if action == "contract" else {})
    data.update({"water_m3": 10} if action == "irrigation" else {})
    data.update({"chemical": "glyphosate", "dosage_kg_ha": 1} if action == "pesticide" else {})
    return {
        "action_type": action,
        "action_data": data,
        "farm_context": {
            "annual_revenue_usd": 10000,
            "annual_costs_usd": 1200,
            "cash_reserve_usd": 1000,
            "current_debt_usd": 0,
            "field_area_ha": 2,
            "season_water_used_m3_ha": 100,
            "water_source": "groundwater",
        },
        "user_id": "42",
        "tenant_id": TENANT,
    }


def test_contract_violations_pure(gr_mod):
    p = payload()
    assert gr_mod.contract_violations(p["action_type"], p["action_data"], p["farm_context"]) == []
    p["action_data"].pop("cost_usd")
    assert "action_data.cost_usd" in gr_mod.contract_violations(
        p["action_type"], p["action_data"], p["farm_context"]
    )


@pytest.mark.parametrize(
    "action", ["investment", "loan", "contract", "irrigation", "fertilization", "pesticide"]
)
def test_missing_financial_evidence_rejected_at_http_boundary(gr_mod, monkeypatch, action):
    monkeypatch.setattr(gr_mod, "_GR_AGENT_TOKEN", "service-token")
    p = payload(action)
    p["action_data"] = {k: v for k, v in p["action_data"].items() if not k.endswith("_usd")}
    response = TestClient(gr_mod.app).post(
        "/v1/validate", json=p, headers={"X-Agent-Token": "service-token"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad", [True, -1, "100", None, float("nan"), float("inf"), 10**400])
def test_invalid_amounts_cannot_become_low_risk(gr_mod, monkeypatch, bad):
    monkeypatch.setattr(gr_mod, "_GR_AGENT_TOKEN", "service-token")
    p = payload()
    p["action_data"]["cost_usd"] = bad
    response = TestClient(gr_mod.app).post(
        "/v1/validate",
        content=json.dumps(p),
        headers={"X-Agent-Token": "service-token", "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "approval_workflow_id" not in response.json()


@pytest.mark.parametrize(
    "key,value", [("water_source", {}), ("crop", []), ("field_state", {"value": float("nan")})]
)
def test_malformed_context_returns_422_not_internal_error(gr_mod, monkeypatch, key, value):
    monkeypatch.setattr(gr_mod, "_GR_AGENT_TOKEN", "service-token")
    p = payload("irrigation")
    p["farm_context"][key] = value
    response = TestClient(gr_mod.app).post(
        "/v1/validate",
        content=json.dumps(p),
        headers={"X-Agent-Token": "service-token", "Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad", [True, 1.5, 0, -1, "u1", "1.0", 2147483648])
def test_user_id_contract_matches_integer_column(gr_mod, bad):
    p = payload()
    assert gr_mod.GuardrailsRequest(**p).user_id == 42
    p["user_id"] = bad
    with pytest.raises(ValidationError):
        gr_mod.GuardrailsRequest(**p)


@pytest.mark.parametrize("action", ["investment", "pesticide"])
def test_excessive_spending_runs_economic_tier(gr_mod, action):
    p = payload(action)
    p["action_data"]["cost_usd"] = 90000
    eng = gr_mod.SAHOOLGuardrailsEngine()
    eng.human_workflow.create = AsyncMock(return_value="persisted-review")
    result = asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p)))
    assert not result.allowed and result.requires_human_approval
    assert any(
        f.get("rule") == "investment_capacity_exceeded"
        for c in result.tier_checks
        for f in c["findings"]
    )
    eng.human_workflow.create.assert_awaited_once()


@pytest.mark.parametrize("action", ["investment", "loan", "contract"])
def test_explicit_zero_revenue_requires_review(gr_mod, action):
    p = payload(action)
    p["farm_context"]["annual_revenue_usd"] = 0
    eng = gr_mod.SAHOOLGuardrailsEngine()
    eng.human_workflow.create = AsyncMock(return_value="persisted-review")
    result = asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p)))
    assert result.allowed is False and result.overall_risk == "HIGH"


def test_zero_projected_loan_revenue_requires_review(gr_mod):
    p = payload("loan")
    p["farm_context"]["projected_annual_revenue_usd"] = 0
    eng = gr_mod.SAHOOLGuardrailsEngine()
    eng.human_workflow.create = AsyncMock(return_value="persisted-review")
    assert asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p))).allowed is False


def test_only_opted_in_low_risk_is_automatically_approved(gr_mod):
    eng = gr_mod.SAHOOLGuardrailsEngine()
    eng.human_workflow.create = AsyncMock(return_value="persisted-review")
    p = payload()
    assert asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p))).allowed is True
    p["auto_approve_low_risk"] = False
    assert asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p))).allowed is False
    p["auto_approve_low_risk"] = True
    p["action_data"]["projected_revenue_increase_usd"] = 10
    result = asyncio.run(eng.validate(gr_mod.GuardrailsRequest(**p)))
    assert result.overall_risk == "MEDIUM" and result.allowed is False


class Store:
    """Exercise transaction order and pool reuse; PostgreSQL is tested separately."""

    def __init__(self):
        self.rows = {}
        self.settings = {}
        self.in_transaction = False
        self.fail_insert = False

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction = True
        try:
            yield self
        finally:
            self.settings.clear()
            self.in_transaction = False

    async def execute(self, sql, *args):
        assert self.in_transaction
        if "set_config" in sql:
            assert "true" in sql
            self.settings[
                "app.current_tenant" if "app.current_tenant" in sql else "app.tenant_id"
            ] = args[0]
            return
        assert self.settings["app.current_tenant"] == self.settings["app.tenant_id"]
        if "INSERT INTO approval_workflows" in sql:
            if self.fail_insert:
                raise ConnectionError("injected database failure")
            assert args[1] == self.settings["app.tenant_id"]
            assert type(args[2]) is int
            keys = [
                "workflow_id",
                "tenant_id",
                "user_id",
                "status",
                "risk_level",
                "action_type",
                "action_data",
                "farm_context",
                "required_roles",
                "approvals",
                "rejections",
                "escalation_count",
                "expires_at",
            ]
            self.rows[args[0]] = dict(
                zip(keys, args, strict=True), created_at=datetime.now(UTC), resolved_at=None
            )
        elif "status='expired'" in sql:
            self.rows[args[0]]["status"] = "expired"
        elif "approvals=$2" in sql:
            self.rows[args[2]].update(status=args[0], approvals=args[1])
        elif "rejections=$2" in sql:
            self.rows[args[2]].update(status=args[0], rejections=args[1])
        elif "escalation_count=$1" in sql:
            self.rows[args[2]].update(escalation_count=args[0], required_roles=args[1])

    async def fetchrow(self, sql, *args):
        assert self.in_transaction and "FOR UPDATE" in sql and "tenant_id::TEXT=$2" in sql
        assert self.settings["app.current_tenant"] == self.settings["app.tenant_id"] == args[1]
        row = self.rows.get(args[0])
        return row if row and row["tenant_id"] == args[1] else None


@pytest.fixture
def storage(gr_mod, monkeypatch):
    mod = sys.modules[gr_mod.HumanApprovalWorkflow.__module__]
    store = Store()
    monkeypatch.setattr(mod, "_pool", store)
    return store


def test_hil_create_read_isolation_and_pool_context_reset(gr_mod, storage):
    async def scenario():
        hil = gr_mod.HumanApprovalWorkflow()
        wid = await hil.create(
            gr_mod.GuardrailsRequest(**payload()), [{"tier": "economic", "passed": False}], "HIGH"
        )
        assert not storage.settings
        status = await hil.get_status(wid, TENANT)
        assert status["status"] == "pending" and status["notification_delivery"] == "not_configured"
        assert await hil.get_status(wid, OTHER) is None
        assert not storage.settings
        return wid

    assert asyncio.run(scenario()) in storage.rows


def test_hil_specialists_expiration_duplicate_and_cross_tenant_decisions(gr_mod, storage):
    async def scenario():
        hil = gr_mod.HumanApprovalWorkflow()
        wid = await hil.create(
            gr_mod.GuardrailsRequest(**payload()), [{"tier": "economic", "passed": False}], "HIGH"
        )
        assert (await hil.approve(wid, "1", "financial_advisor", OTHER))["status"] == "not_found"
        assert (await hil.reject(wid, "1", "water_specialist", "x", TENANT))[
            "status"
        ] == "unauthorized"
        assert (await hil.approve(wid, "1", "expert", TENANT))["status"] == "unauthorized"
        assert (await hil.approve(wid, "1", "financial_advisor", TENANT))["status"] == "pending"
        assert (await hil.approve(wid, "1", "financial_advisor", TENANT))["approvals_received"] == 1
        assert (await hil.approve(wid, "2", "financial_advisor", TENANT))["status"] == "approved"
        assert (await hil.reject(wid, "2", "financial_advisor", "x", TENANT))[
            "status"
        ] == "approved"
        storage.rows[wid].update(
            status="pending", expires_at=datetime.now(UTC) - timedelta(seconds=1)
        )
        assert (await hil.approve(wid, "3", "financial_advisor", TENANT))["status"] == "expired"
        assert (await hil.escalate(wid, "late", TENANT))["status"] == "expired"

    asyncio.run(scenario())


@pytest.mark.parametrize("configured", [False, True])
def test_hil_storage_failure_returns_503_without_phantom_workflow(
    gr_mod, monkeypatch, storage, configured
):
    mod = sys.modules[gr_mod.HumanApprovalWorkflow.__module__]
    monkeypatch.setattr(gr_mod, "_GR_AGENT_TOKEN", "service-token")
    monkeypatch.setattr(mod, "DATABASE_URL", "")
    if configured:
        storage.fail_insert = True
    else:
        monkeypatch.setattr(mod, "_pool", None)
    p = payload()
    p["action_data"]["cost_usd"] = 90000
    response = TestClient(gr_mod.app).post(
        "/v1/validate", json=p, headers={"X-Agent-Token": "service-token"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "approval_store_unavailable"
    assert storage.rows == {}


def test_specialist_token_can_reach_approval_endpoint(gr_mod, monkeypatch, storage):
    import jwt

    from conftest import make_token

    monkeypatch.setattr(gr_mod, "_GR_JWT_SECRET", os.environ["JWT_SECRET"])
    monkeypatch.setattr(gr_mod, "_GR_JWT_ALG", "HS256")
    hil = gr_mod.HumanApprovalWorkflow()
    wid = asyncio.run(
        hil.create(
            gr_mod.GuardrailsRequest(**payload()), [{"tier": "economic", "passed": False}], "MEDIUM"
        )
    )
    client = TestClient(gr_mod.app)
    token = make_token(role="financial_advisor", tenant_id=TENANT)
    assert (
        client.post(
            f"/v1/approve/{wid}?approved=true", headers={"Authorization": f"Bearer {token}"}
        ).json()["status"]
        == "approved"
    )
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"], audience="sahool")
    claims.pop("tenant_id")
    incomplete = jwt.encode(claims, os.environ["JWT_SECRET"], algorithm="HS256")
    assert (
        client.get(
            f"/v1/workflow/{wid}", headers={"Authorization": f"Bearer {incomplete}"}
        ).status_code
        == 401
    )
