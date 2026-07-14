#!/usr/bin/env python3
"""IRR-X1.4 guard: farmer manual operations UI and read path remain wired."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
required = {
    "frontend/src/sections/IrrigationManualOperationsPanel.tsx": [
        "اعتماد",
        "بدء الري",
        "إيقاف الري",
        "تأكيد التنفيذ",
        "تحقق مستقل",
        "ترحيل للدفتر",
        "listManualExecutions",
        "transitionManualExecution",
        "confirmManualExecution",
        "verifyManualExecution",
        "reconcileManualExecution",
    ],
    "frontend/src/services/api/irrigationManualOperations.ts": [
        "/api/v1/irrigation/engineering/manual-executions",
        "manual_measured",
        "as_applied_digest",
    ],
    "frontend/src/sections/FieldWorkspaceIrrigationPanel.tsx": ["IrrigationManualOperationsPanel"],
    "services/sahool-platform/api/routers/irrigation_engineering.py": [
        '@router.get("/manual-executions")',
        "tenant_id=$1::uuid",
        "field_id=$2",
        'update={"reviewer_id": str(user.user_id)}',
    ],
}
for rel, needles in required.items():
    path = ROOT / rel
    assert path.exists(), f"missing {rel}"
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text, f"{rel}: missing {needle}"
print("IRR-X1.4 farmer manual operations UI guard: PASS")
