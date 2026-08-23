from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")

required = [
    "/v1/learning/calibration-dataset",
    "build_calibration_dataset",
    "read_only",
    "weighted_success_rate",
    "decision_learning_attributions",
    "verified_success",
    "verified_failure",
]
missing = [token for token in required if token not in MAIN + PERSISTENCE]
if missing:
    raise SystemExit(f"WX-11.1 calibration boundary missing: {missing}")

forbidden = ["model.fit(", "optimizer.step(", "partial_fit(", "mqtt.publish(", "redispatch"]
segment = (MAIN + PERSISTENCE).lower()
found = [token for token in forbidden if token.lower() in segment]
if found:
    raise SystemExit(f"WX-11.1 must remain read-only; forbidden tokens: {found}")
print("WX-11.1 calibration dataset boundary: PASS")
