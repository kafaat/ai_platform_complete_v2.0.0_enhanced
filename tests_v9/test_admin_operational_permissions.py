"""Administrative operation permission regression tests."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _handler(path, name):
    source = (ROOT / path).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name == name:
                return ast.unparse(node)
    raise AssertionError("missing endpoint: " + name)


def test_task_completion_uses_execution_permission():
    source = _handler("services/sahool-platform/api/routers/tasks.py", "update_task")
    assert "require_permission(Permission.ACTIVITY_EXECUTE)" in source


def test_financial_writes_require_finance_permission():
    path = "services/sahool-platform/api/routers/farm_operations_ledger.py"
    for name in ("upsert_season_budget_lines", "create_revenue_record"):
        source = _handler(path, name)
        assert "require_permission(Permission.FINANCE_MANAGE)" in source


def test_requeue_writes_separate_from_audit_reads():
    path = "services/sahool-platform/api/routers/admin.py"
    writers = (
        "admin_requeue_dead_letter",
        "admin_requeue_all_dead_letter",
        "admin_outbox_requeue_dead_letter",
    )
    for name in writers:
        source = _handler(path, name)
        assert "require_permission(Permission.EVENT_REQUEUE)" in source
    reader = _handler(path, "admin_events_dead_letter")
    assert "require_permission(Permission.AUDIT_VIEW)" in reader


def test_finance_and_requeue_granted_to_managers_only():
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema

    for role in UserRole:
        actor = UserSchema(user_id="1", tenant_id="t", role=role, name_ar="x")
        expected = role in (UserRole.OWNER, UserRole.MANAGER)
        assert has_permission(actor, Permission.FINANCE_MANAGE) == expected
        assert has_permission(actor, Permission.EVENT_REQUEUE) == expected


def test_tenant_provisioning_ui_matches_auth_contract():
    ts_path = ROOT / "frontend/src/services/api/auth.ts"
    ui_path = ROOT / "frontend/src/sections/ManagerConsolePage.tsx"
    ts = ts_path.read_text(encoding="utf-8")
    ui = ui_path.read_text(encoding="utf-8")
    for field in ("owner_user_id", "owner_email", "owner_role", "setup_link"):
        assert field in ts
    for field in ("owner_email", "owner_role", "setup_link"):
        assert "tenantM.data." + field in ui
