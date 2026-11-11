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


def test_ui22_recommendations_are_server_backed_not_fabricated_advice():
    # The panel was a static shell; it now delegates to the server-backed recommendation list.
    # The invariant is unchanged: nothing is invented client-side, each item shows its source,
    # a fetch failure is not shown as "no recommendations", and the screen issues no commands.
    src = read("frontend/src/sections/FieldWorkspaceRecommendationsPanel.tsx")
    rec = read("frontend/src/sections/RecommendationPage.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "<UnifiedRecommendations fieldId={fieldId} />" in src
    assert "لا تنفذ هذه الشاشة أوامر تشغيل" in src
    unified = rec[rec.index("export function UnifiedRecommendations") :]
    assert "useFieldRecommendations(" in unified
    assert "{rec.source}" in unified
    assert 'title="تعذّر جلب توصيات الحقل"' in unified
    assert 'title="لا توصيات متاحة"' in unified
    assert "<FieldWorkspaceRecommendationsPanel fieldId={fieldId} seasonId={seasonId}" in route


def test_ui23_reports_panel_is_a_live_summary_not_a_saved_report():
    # The panel now reads the live field summary. It must say it is not a saved report, keep a
    # failure distinct from an empty result, and never generate PDF/CSV files in the browser.
    src = read("frontend/src/sections/FieldWorkspaceReportsPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "useFieldReport(" in src
    assert "ليس ملفاً محفوظاً أو تقريراً تاريخياً" in src
    assert "<ErrorState" in src and "<EmptyState" in src
    for forbidden in ("new Blob", "createObjectURL", "jspdf", "download="):
        assert forbidden not in src.lower(), forbidden
    assert "<FieldWorkspaceReportsPanel fieldId={fieldId} seasonId={seasonId}" in route
