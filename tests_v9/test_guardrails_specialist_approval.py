"""Approval authority of issued roles and separation of duties in the HIL workflow.

Slice of ROLE-DICTIONARY-DOES-NOT-CARRY-SPECIALIST-AUTHORITY-01 (owner option (b),
PROPOSAL awaiting the owner's decision). Auth issues only owner/admin/expert/farmer/
viewer (services/auth/main.py:441) and writes the role into the token as-is
(services/auth/main.py:608). The guardrails engine accepted approval only from
specialist names auth never issues, and nothing stopped a requester approving their
own request. These tests pin:

* ``expert`` approves exactly what ``agronomist`` approves, on every tier and after
  escalation, and nothing more (``economic`` stays closed to it);
* ``farmer``/``viewer`` (and ``owner``) are still refused, at the token gate and at
  the workflow gate;
* ``admin`` is unchanged: it approves every tier;
* whoever submitted the workflow cannot approve it, whatever their role.

Storage is an in-memory double; no database, network or migration is involved.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
GR = os.path.join(ROOT, "services/guardrails-engine")
TENANT = "11111111-1111-4111-8111-111111111111"
REQUESTER = 42  # approval_workflows.user_id (INTEGER users.id)
_PREFIXES = (
    "main",
    "contracts",
    "human_in_loop",
    "tiers",
    "routers",
    "router_registry",
    "diff_generator",
)


@pytest.fixture(scope="module")
def gr_mod():
    # Deployment-local absolute imports; isolate them from other services' modules.
    saved = {
        k: v
        for k, v in sys.modules.items()
        if any(k == p or k.startswith(p + ".") for p in _PREFIXES)
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
            if any(name == p or name.startswith(p + ".") for p in _PREFIXES):
                sys.modules.pop(name)
        sys.modules.update(saved)


@pytest.fixture
def hil_mod(gr_mod):
    return sys.modules[gr_mod.HumanApprovalWorkflow.__module__]


class _Conn:
    """One locked workflow row; records every write so refusals can prove none happened."""

    def __init__(self, row):
        self.row = row
        self.writes = []

    async def fetchrow(self, sql, workflow_id, tenant_id):
        assert "FOR UPDATE" in sql
        if workflow_id == self.row["workflow_id"] and tenant_id == self.row["tenant_id"]:
            return self.row
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        if "approvals=$2" in sql:
            self.row.update(status=args[0], approvals=args[1])
        elif "rejections=$2" in sql:
            self.row.update(status=args[0], rejections=args[1])


def _row(required_roles, risk_level="LOW", user_id=REQUESTER):
    return {
        "workflow_id": "SAHOOL-HIL-TEST",
        "tenant_id": TENANT,
        "user_id": user_id,
        "status": "pending",
        "risk_level": risk_level,
        "required_roles": list(required_roles),
        "approvals": "[]",
        "rejections": "[]",
        "escalation_count": 0,
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }


@pytest.fixture
def store(hil_mod, monkeypatch):
    holder = {}

    @asynccontextmanager
    async def fake_tenant_connection(tenant_id):
        yield holder["conn"]

    def install(row):
        holder["conn"] = _Conn(row)
        return holder["conn"]

    monkeypatch.setattr(hil_mod, "_tenant_connection", fake_tenant_connection)
    return install


def _required_sets(hil_mod):
    """Every required_roles set the engine can persist: per tier, combined, escalated."""
    tiers = dict(hil_mod.EXPERT_ROLES)
    sets = {f"tier:{name}": sorted(roles) for name, roles in tiers.items()}
    sets["combined:chemical+economic"] = sorted(set(tiers["chemical"]) | set(tiers["economic"]))
    for name, roles in list(sets.items()):
        sets[f"escalated:{name}"] = sorted(set(roles) | {"admin", "regional_manager"})
    return sets


def _approve(hil_mod, conn_factory, required, role, approver_id="7"):
    conn = conn_factory(_row(required))
    result = asyncio.run(
        hil_mod.HumanApprovalWorkflow().approve("SAHOOL-HIL-TEST", approver_id, role, TENANT)
    )
    return result, conn


# ── expert carries exactly the agronomist authority ─────────────────────────────


def test_expert_approves_exactly_what_agronomist_approves(hil_mod, store):
    for label, required in _required_sets(hil_mod).items():
        expert, expert_conn = _approve(hil_mod, store, required, "expert")
        agronomist, _ = _approve(hil_mod, store, required, "agronomist")
        assert expert["status"] == agronomist["status"], label
        if "agronomist" in required:
            assert expert["status"] == "approved", label
            # The audit trail keeps the role auth actually issued, not the mapped name.
            recorded = json.loads(expert_conn.row["approvals"])
            assert recorded[-1]["expert_role"] == "expert", label
        else:
            assert expert["status"] == "unauthorized", label
            assert expert_conn.writes == [], label


def test_expert_is_still_refused_on_economic_tier(hil_mod, store):
    result, conn = _approve(hil_mod, store, hil_mod.EXPERT_ROLES["economic"], "expert")
    assert result["status"] == "unauthorized"
    assert result["error"] == "Expert role not authorized"
    assert conn.writes == []


def test_mapping_reuses_the_existing_table_without_new_tiers(hil_mod):
    assert set(hil_mod.ISSUED_ROLE_AUTHORITY) == {"expert"}
    assert set(hil_mod.ISSUED_ROLE_AUTHORITY.values()) <= hil_mod.APPROVER_ROLES
    assert hil_mod.approver_authority("expert") == "agronomist"
    for role in ("farmer", "viewer", "owner", "admin", "agronomist"):
        assert hil_mod.approver_authority(role) == role
    for bad in (None, 1, ["expert"], {"expert": 1}):
        assert hil_mod.approver_authority(bad) == ""


# ── issued roles without approval authority stay refused ────────────────────────


@pytest.mark.parametrize("role", ["farmer", "viewer", "owner", "", "Expert", "EXPERT"])
def test_unprivileged_issued_roles_refused_at_workflow_gate(hil_mod, store, role):
    for label, required in _required_sets(hil_mod).items():
        result, conn = _approve(hil_mod, store, required, role)
        assert result["status"] == "unauthorized", (role, label)
        assert conn.writes == [], (role, label)
        conn = store(_row(required))
        rejected = asyncio.run(
            hil_mod.HumanApprovalWorkflow().reject("SAHOOL-HIL-TEST", "7", role, "no", TENANT)
        )
        assert rejected["status"] == "unauthorized", (role, label)
        assert conn.writes == [], (role, label)


def _verify(gr_mod, monkeypatch, role, user_id=7):
    from conftest import make_token

    monkeypatch.setattr(gr_mod, "_GR_JWT_SECRET", os.environ["JWT_SECRET"])
    monkeypatch.setattr(gr_mod, "_GR_JWT_ALG", "HS256")
    token = make_token(user_id=user_id, role=role, tenant_id=TENANT)
    return gr_mod._gr_verify(f"Bearer {token}")


@pytest.mark.parametrize("role", ["farmer", "viewer", "owner"])
def test_unprivileged_issued_roles_refused_at_token_gate(gr_mod, monkeypatch, role):
    with pytest.raises(HTTPException) as raised:
        _verify(gr_mod, monkeypatch, role)
    assert raised.value.status_code == 403
    assert raised.value.detail == "الموافقة تتطلّب صلاحيّة خبير أو مدير"


@pytest.mark.parametrize("role", ["expert", "agronomist", "admin"])
def test_approver_roles_pass_token_gate_with_issued_role_kept(gr_mod, monkeypatch, role):
    claims = _verify(gr_mod, monkeypatch, role)
    assert claims["role"] == role  # the gate does not rewrite the claim


# ── admin unchanged ────────────────────────────────────────────────────────────


def test_admin_still_approves_every_tier(hil_mod, store):
    for label, required in _required_sets(hil_mod).items():
        result, _ = _approve(hil_mod, store, required, "admin")
        assert result["status"] == "approved", label


# ── separation of duties ───────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["admin", "agronomist", "expert"])
@pytest.mark.parametrize("approver_id", [str(REQUESTER), f" {REQUESTER}", f"0{REQUESTER}"])
def test_requester_cannot_approve_own_request(hil_mod, store, role, approver_id):
    result, conn = _approve(
        hil_mod, store, hil_mod.EXPERT_ROLES["general"], role, approver_id=approver_id
    )
    assert result == {
        "error": "Requester cannot approve their own request",
        "status": "unauthorized",
    }
    assert conn.writes == []
    assert conn.row["status"] == "pending" and conn.row["approvals"] == "[]"


def test_self_approval_cannot_count_towards_multi_approval(hil_mod, store):
    conn = store(_row(hil_mod.EXPERT_ROLES["general"], risk_level="HIGH"))
    hil = hil_mod.HumanApprovalWorkflow()
    first = asyncio.run(hil.approve("SAHOOL-HIL-TEST", "7", "agronomist", TENANT))
    assert first["status"] == "pending" and first["approvals_received"] == 1
    own = asyncio.run(hil.approve("SAHOOL-HIL-TEST", str(REQUESTER), "admin", TENANT))
    assert own["status"] == "unauthorized"
    assert len(json.loads(conn.row["approvals"])) == 1 and conn.row["status"] == "pending"
    second = asyncio.run(hil.approve("SAHOOL-HIL-TEST", "8", "expert", TENANT))
    assert second["status"] == "approved" and second["approvals_received"] == 2


def test_requester_may_still_reject_own_request(hil_mod, store):
    conn = store(_row(hil_mod.EXPERT_ROLES["general"]))
    result = asyncio.run(
        hil_mod.HumanApprovalWorkflow().reject(
            "SAHOOL-HIL-TEST", str(REQUESTER), "agronomist", "withdrawn", TENANT
        )
    )
    assert result["status"] == "rejected" and conn.row["status"] == "rejected"


def test_unrecorded_requester_does_not_block_distinct_approver(hil_mod, store):
    # Rows written before user_id was enforced have no requester to compare against.
    store(_row(hil_mod.EXPERT_ROLES["general"], user_id=None))
    result = asyncio.run(
        hil_mod.HumanApprovalWorkflow().approve("SAHOOL-HIL-TEST", "7", "agronomist", TENANT)
    )
    assert result["status"] == "approved"


@pytest.mark.parametrize(
    "role,user_id,expected_http,expected_status",
    [
        ("admin", REQUESTER, 403, "unauthorized"),  # self-approval, even by admin
        ("expert", REQUESTER, 403, "unauthorized"),
        ("expert", 7, 200, "approved"),  # expert carries agronomist authority
        ("admin", 7, 200, "approved"),
    ],
)
def test_approval_endpoint_enforces_authority_and_separation(
    gr_mod, hil_mod, store, monkeypatch, role, user_id, expected_http, expected_status
):
    from conftest import make_token

    monkeypatch.setattr(gr_mod, "_GR_JWT_SECRET", os.environ["JWT_SECRET"])
    monkeypatch.setattr(gr_mod, "_GR_JWT_ALG", "HS256")
    conn = store(_row(hil_mod.EXPERT_ROLES["chemical"]))
    token = make_token(user_id=user_id, role=role, tenant_id=TENANT)
    response = TestClient(gr_mod.app).post(
        "/v1/approve/SAHOOL-HIL-TEST",
        params={"approved": "true", "reason": "separation of duties"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == expected_http, response.text
    body = response.json()
    if expected_http == 200:
        assert body["status"] == expected_status
    else:
        assert body["detail"]["status"] == expected_status
        assert body["detail"]["error"] == "Requester cannot approve their own request"
        assert conn.writes == []
