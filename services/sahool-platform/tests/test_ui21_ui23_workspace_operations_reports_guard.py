from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_ui21_field_tasks_api_contract_exists_and_uses_real_tasks_endpoint():
    src = read("frontend/src/services/api/fieldTasks.ts")
    assert "getFieldTasks" in src
    assert "/api/v1/tasks" in src
    assert "field_id" in src
    assert "FieldTaskListResponse" in src
    assert "kongApi.get" in src
    facade = read("frontend/src/services/api.ts")
    assert "export * from './api/fieldTasks'" in facade


def test_ui21_operations_tab_combines_priority_and_tasks_without_fake_writes():
    panel = read("frontend/src/sections/FieldWorkspaceOperationsPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "FieldWorkspacePriorityPanel" in panel
    assert "FieldWorkspaceTasksPanel" in panel
    assert "endpoint كتابة صريح" in panel or "evidence" in panel
    assert "<FieldWorkspaceOperationsPanel fieldId={fieldId} seasonId={seasonId}" in route
    assert "activeTab === 'operations'" in route


def test_ui21_tasks_panel_has_empty_degraded_permission_states():
    src = read("frontend/src/sections/FieldWorkspaceTasksPanel.tsx")
    assert "DegradedState" in src
    assert "EmptyState" in src
    assert "ErrorState" in src
    assert "502 || status === 503 || status === 504" in src
    assert "status === 401 || status === 403" in src
    assert "لا يتم إنشاء مهام وهمية" in src


def test_ui22_recommendations_are_evidence_only_shell_not_fabricated_advice():
    src = read("frontend/src/sections/FieldWorkspaceRecommendationsPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "evidence lineage" in src
    assert "recommendation_id" in src
    assert "confidence" in src
    assert "لا توجد توصيات موثقة" in src
    assert "<FieldWorkspaceRecommendationsPanel fieldId={fieldId} seasonId={seasonId}" in route


def test_ui23_reports_shell_requires_saved_server_side_reports():
    src = read("frontend/src/sections/FieldWorkspaceReportsPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "report_id" in src
    assert "download_url" in src
    assert "لا توجد تقارير محفوظة" in src
    assert "لا تُولد PDF/CSV" in src
    assert "<FieldWorkspaceReportsPanel fieldId={fieldId} seasonId={seasonId}" in route
