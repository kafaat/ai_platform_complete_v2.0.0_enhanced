from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _connection(role: str):
    return {
        "current_user": role,
        "session_user": role,
        "role_attributes": {
            "rolsuper": False,
            "rolbypassrls": False,
            "rolcreaterole": False,
            "rolcreatedb": False,
            "rolcanlogin": True,
            "rolinherit": False,
        },
        "membership_closure": [],
        "memberships_can_set_role_to": [],
        "table_owners": {},
        "table_grants": {},
        "effective_table_privileges": {},
        "sequences": {},
        "security_definer_writers": [],
    }


def test_decision_role_preflight_rejects_membership_sequence_owner_and_shared_role():
    m = _load(
        "decision_role_certify_s5_test", "services/decision-service/decision_sor_role_certify.py"
    )
    platform = _connection("sahool_app")
    service = _connection("decision_service_app")
    for conn in (platform, service):
        conn["table_owners"] = {table: "decision_schema_owner" for table in m.SOR_TABLES}
    result = {
        "platform": platform,
        "decision_service": service,
        "role_separation_confirmed": True,
    }
    assert m._preflight_blockers(result) == []

    shared = {**result, "role_separation_confirmed": False}
    assert "platform_and_decision_service_roles_must_be_distinct" in m._preflight_blockers(shared)

    member = {**result, "platform": {**platform, "membership_closure": [{"role": "writer_parent"}]}}
    assert "platform_role_membership_closure_must_be_empty" in m._preflight_blockers(member)

    sequence = {
        **result,
        "platform": {
            **platform,
            "sequences": {
                "decision_record_id_seq": {
                    "effective": {"USAGE": True, "SELECT": False, "UPDATE": False}
                }
            },
        },
    }
    assert "platform_sequence_privilege_present:decision_record_id_seq" in m._preflight_blockers(
        sequence
    )

    owner = {
        **result,
        "platform": {
            **platform,
            "table_owners": {**platform["table_owners"], "decision_record": "sahool_app"},
        },
    }
    assert any("app_role_owns_table:sahool_app" in x for x in m._preflight_blockers(owner))


def _revoked_state(m):
    return {
        table: {"INSERT": False, "UPDATE": False, "DELETE": False, "SELECT": True}
        for table in m.PLATFORM_SOR_TABLES
    }


def test_platform_revoke_postcondition_uses_effective_privileges_fail_closed():
    m = _load("platform_sor_revoke_s5_test", "services/decision-service/platform_sor_revoke.py")
    state = _revoked_state(m)
    assert m.privilege_closure_findings(state, action="revoke") == []

    inherited = {table: dict(privs) for table, privs in state.items()}
    inherited["decision_record"]["INSERT"] = True
    findings = m.privilege_closure_findings(inherited, action="revoke")
    assert "decision_record:INSERT:effective_write_still_allowed" in findings

    lost_read = {table: dict(privs) for table, privs in state.items()}
    lost_read["outcome_record"]["SELECT"] = False
    assert "outcome_record:SELECT:read_facade_privilege_missing" in m.privilege_closure_findings(
        lost_read, action="revoke"
    )

    rollback = {
        table: {"INSERT": True, "UPDATE": True, "DELETE": True, "SELECT": True}
        for table in m.PLATFORM_SOR_TABLES
    }
    assert m.privilege_closure_findings(rollback, action="grant") == []
    rollback["dispatch_decisions"]["DELETE"] = False
    assert "dispatch_decisions:DELETE:rollback_privilege_missing" in m.privilege_closure_findings(
        rollback, action="grant"
    )


def test_revoke_mutation_and_effective_verification_share_one_outer_transaction():
    source = (ROOT / "services/decision-service/platform_sor_revoke.py").read_text(encoding="utf-8")
    run = source.split("async def _run(action: str)", 1)[1].split("def main", 1)[0]
    assert "async with conn.transaction():" in run
    assert "after = await privilege_state" in run
    assert "privilege_closure_findings(after" in run
    assert "raise PrivilegeClosureError" in run


def test_role_certification_catalogue_query_is_transitive_not_direct_only():
    source = (ROOT / "services/decision-service/decision_sor_role_certify.py").read_text(
        encoding="utf-8"
    )
    assert "WITH RECURSIVE walk AS" in source
    assert "JOIN walk w ON m.member = w.roleid" in source
    assert "platform_role_membership_closure_must_be_empty" in source
