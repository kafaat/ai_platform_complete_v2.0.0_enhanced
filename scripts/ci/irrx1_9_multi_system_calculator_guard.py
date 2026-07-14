from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
backend = (ROOT / "services/sahool-platform/api/irrigation_engineering_workspace.py").read_text()
frontend = (ROOT / "frontend/src/sections/ReservoirBoosterNetworkCalculator.tsx").read_text()
client = (ROOT / "frontend/src/services/api/irrigationNetworkCalculator.ts").read_text()
required_backend = [
    "class IrrigationMachineInput",
    "IrrigationSystemType.DRIP",
    "IrrigationSystemType.SPRINKLER",
    "IrrigationSystemType.LINEAR_MOVE",
    "IrrigationSystemType.REEL",
    "IrrigationSystemType.VALVE_NETWORK",
    "irrigation_machines",
    "requested_machine_ids",
    "machine_mode",
    "selected_machines",
]
required_frontend = [
    "center_pivot",
    "linear_move",
    "reel",
    "sprinkler",
    "drip",
    "valve_network",
    "نوع نظام الري",
    "إضافة جهاز الري اختيارية",
]
missing = [x for x in required_backend if x not in backend]
missing += [x for x in required_frontend if x not in frontend and x not in client]
if missing:
    raise SystemExit("IRR-X1.9 guard failed; missing: " + ", ".join(missing))
print("IRR-X1.9 multi-system irrigation calculator guard: PASS")
