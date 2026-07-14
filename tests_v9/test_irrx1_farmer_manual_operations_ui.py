from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_manual_operations_panel_is_mounted_in_field_workspace():
    panel = (ROOT / "frontend/src/sections/FieldWorkspaceIrrigationPanel.tsx").read_text()
    assert "IrrigationManualOperationsPanel" in panel
    assert "fieldId={fieldId}" in panel
    assert "seasonId={seasonId}" in panel


def test_ui_preserves_legal_lifecycle_distinctions():
    text = (ROOT / "frontend/src/sections/IrrigationManualOperationsPanel.tsx").read_text()
    for label in (
        "اعتماد",
        "بدء الري",
        "إيقاف الري",
        "تأكيد التنفيذ",
        "تحقق مستقل",
        "ترحيل للدفتر",
    ):
        assert label in text
    assert "لا تولّد الواجهة توصيات أو قيماً مصطنعة" in text


def test_read_endpoint_is_tenant_and_field_scoped():
    text = (ROOT / "services/sahool-platform/api/routers/irrigation_engineering.py").read_text()
    assert '@router.get("/manual-executions")' in text
    assert "tenant_id=$1::uuid AND field_id=$2" in text
    assert "LIMIT 100" in text


def test_verifier_actor_is_server_authoritative():
    text = (ROOT / "services/sahool-platform/api/routers/irrigation_engineering.py").read_text()
    assert 'update={"reviewer_id": str(user.user_id)}' in text
    assert "verification_request" in text
