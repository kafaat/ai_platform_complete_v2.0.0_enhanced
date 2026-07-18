from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).parents[1]


def test_frontend_contract_exposes_manual_volume():
    api = (ROOT / "frontend/src/services/api/irrigationManualOperations.ts").read_text(
        encoding="utf-8"
    )
    panel = (ROOT / "frontend/src/sections/IrrigationManualOperationsPanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "manual_volume_m3?: number" in api
    assert "manual_volume_m3: form.manual_volume_m3" in panel
    assert "'manual_volume_m3'" in panel


def test_backend_keeps_operator_declared_volume_out_of_ledger():
    backend = (ROOT / "services/sahool-platform/api/irrigation_manual_execution.py").read_text(
        encoding="utf-8"
    )
    assert 'quality = "operator_declared"' in backend
    assert "OPERATOR_DECLARED_VOLUME_REQUIRES_INDEPENDENT_MEASUREMENT" in backend
