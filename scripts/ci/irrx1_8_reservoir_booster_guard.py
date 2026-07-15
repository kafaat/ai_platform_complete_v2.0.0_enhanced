from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    root / "services/sahool-platform/api/irrigation_engineering_workspace.py": [
        "ReservoirBoosterNetworkRequest",
        "calculate_reservoir_booster_network",
        "pivot_mode",
        "pivots: list[PivotMachineInput]",
        "requested_pivot_ids",
    ],
    root / "services/sahool-platform/api/routers/irrigation_engineering.py": ["/network-calculate"],
    root / "frontend/src/sections/ReservoirBoosterNetworkCalculator.tsx": [
        "محوراً",
        "اختيارية",
        "center_pivot",
    ],
    root / "frontend/src/services/api/irrigationNetworkCalculator.ts": [
        "requested_pivot_ids",
        "/network-calculate",
        "center_pivot",
    ],
    root / "tests_v9/test_irrx1_8_reservoir_booster_optional_pivot.py": ["test_pivot_is_optional"],
}
for path, needles in checks.items():
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text, f"{path}: missing {needle}"
print("IRR-X1.8 reservoir/booster optional-pivot compatibility guard: PASS")
