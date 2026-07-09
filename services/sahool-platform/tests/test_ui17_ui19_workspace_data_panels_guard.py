from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workspace_data_panels_are_real_api_wired_not_placeholders():
    panel = read(FRONTEND / "sections" / "FieldWorkspaceDataPanels.tsx")
    assert "getFieldReadiness" in panel
    assert "getFieldDataCompleteness" in panel
    assert "['field-workspace', fieldId, 'readiness']" in panel
    assert "['field-workspace', fieldId, 'data-completeness']" in panel
    assert "لا تعرض مساحة العمل قيماً بديلة" in panel or "لا تعرض" in panel
    assert "غير معايرة" in panel


def test_workspace_timeline_panel_uses_unified_timeline_contract():
    panel = read(FRONTEND / "sections" / "FieldWorkspaceTimelinePanel.tsx")
    assert "getFieldUnifiedTimeline" in panel
    assert "['field-workspace', fieldId, seasonId ?? 'no-season', 'unified-timeline']" in panel
    assert "limit: 8" in panel
    assert "لا يتم تصنيع أحداث بديلة" in panel
    assert "field_id + season_id" in panel


def test_workspace_priority_panel_uses_priority_queue_without_fabrication():
    panel = read(FRONTEND / "sections" / "FieldWorkspacePriorityPanel.tsx")
    assert "getFieldPriorityQueue" in panel
    assert "['field-workspace', fieldId, 'priority-queue']" in panel
    assert "لا يتم ترتيب عناصر مصطنعة" in panel or "لا يتم عرض أولويات بديلة" in panel
    assert "query.data.degraded" in panel


def test_workspace_route_shell_renders_data_timeline_priority_panels():
    shell = read(FRONTEND / "sections" / "FieldWorkspaceRouteShell.tsx")
    assert "FieldWorkspaceDataPanels" in shell
    assert "FieldWorkspaceTimelinePanel" in shell
    assert "FieldWorkspacePriorityPanel" in shell
    assert "<FieldWorkspaceDataPanels fieldId={fieldId}" in shell
    assert "<FieldWorkspaceTimelinePanel fieldId={fieldId} seasonId={seasonId}" in shell
    assert "<FieldWorkspacePriorityPanel fieldId={fieldId}" in shell
    # Heavy map behavior remains delegated to the existing card.
    assert "<FieldWorkspaceMapCard fieldId={fieldId} showPicker={false}" in shell


def test_field_operating_api_contract_remains_explicit():
    api = read(FRONTEND / "services" / "api" / "fieldOperating.ts")
    assert "FieldReadinessResponse" in api
    assert "FieldDataCompletenessResponse" in api
    assert "FieldUnifiedTimelineResponse" in api
    assert "PriorityQueueResponse" in api
    assert "/api/v1/fields/${fieldId}/readiness" in api
    assert "/api/v1/fields/${fieldId}/data-completeness" in api
    assert "/api/v1/fields/${fieldId}/unified-timeline" in api
    assert "/api/v1/fields/${fieldId}/priority-queue" in api
