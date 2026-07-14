from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    root / "services/sahool-platform/api/irrigation_engineering_workspace.py": [
        "InteractiveIrrigationCalculationRequest",
        "calculate_interactive_irrigation_engineering",
        "required_pressure_bar",
        "INSTALLED_MOTOR_POWER_INSUFFICIENT",
        'execution_authorized": False',
    ],
    root / "services/sahool-platform/api/routers/irrigation_engineering.py": [
        "/interactive-calculate",
        "calculate_interactive_irrigation_engineering",
    ],
    root / "frontend/src/sections/IrrigationEngineeringCalculator.tsx": [
        "حاسبة الري والهيدروليك",
        "احسب الكمية والضغط",
        "لا يمنح تفويض تشغيل آلي",
    ],
    root / "frontend/src/sections/FieldWorkspaceIrrigationPanel.tsx": [
        "IrrigationEngineeringCalculator",
    ],
    root / "frontend/src/services/api/irrigationEngineeringCalculator.ts": [
        "/api/v1/irrigation/engineering/interactive-calculate",
    ],
}
missing = []
for path, needles in checks.items():
    if not path.exists():
        missing.append(str(path.relative_to(root)))
        continue
    text = path.read_text(encoding="utf-8")
    missing.extend(
        f"{path.relative_to(root)}::{needle}" for needle in needles if needle not in text
    )
if missing:
    raise SystemExit("IRR-X1.7 guard failed: " + ", ".join(missing))
print("IRR-X1.7 interactive irrigation calculator guard: PASS")
