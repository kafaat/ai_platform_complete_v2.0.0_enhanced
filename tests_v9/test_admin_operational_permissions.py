"""Distinct permissions for task progress, financial writes and DLQ mutations."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _handler(path, name):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.unparse(fn)

def test_worker_task_update():
    assert "require_permission(Permission.ACTIVITY_EXECUTE)" in _handler("services/sahool-platform/api/routers/tasks.py", "update_task")

def test_financial_writes_are_not_activity_execution():
    path = "services/sahool-platform/api/routers/farm_operations_ledger.py"
    for fn in ("upsert_season_budget_lines", "create_revenue_record"):
        assert "require_permission(Permission.FINANCE_MANAGE)" in _handler(path, fn)

def test_dlq_mutations_require_write_grant():
    path = "services/sahool-platform/api/routers/admin.py"
    for fn in ("admin_requeue_dead_letter", "admin_requeue_all_dead_letter", "admin_outbox_requeue_dead_letter"):
        assert "require_permission(Permission.EVENT_REQUEUE)" in _handler(path, fn)
    assert "require_permission(Permission.AUDIT_VIEW)" in _handler(path, "admin_events_dead_letter")

def test_only_owner_and_manager_get_new_write_grants():
    from core.authorization import Permission, has_permission
    from core.canonical_schemas import UserRole, UserSchema
    for role in UserRole:
        actor = UserSchema(user_id="1", tenant_id="t", role=role, name_ar="x")
        for perm in (Permission.FINANCE_MANAGE, Permission.EVENT_REQUEUE):
            assert has_permission(actor, perm) == (role in (UserRole.OWNER, UserRole.MANAGER))

def test_tenant_provision_result_contract_matches_ui():
    ts = (ROOT / "frontend/src/services/api/auth.ts").read_text()
    ui = (ROOT / "frontend/src/sections/ManagerConsolePage.tsx").read_text()
    assert all(f in ts for f in ("owner_user_id","owner_email","owner_role","setup_token","setup_link"))
    assert all(f"tenantM.data.{f}" in ui for f in ("owner_email","owner_role","setup_link"))
