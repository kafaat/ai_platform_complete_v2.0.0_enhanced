from pathlib import Path
import sys

R = Path(__file__).resolve().parents[2]
required = [
    "services/model-registry-adapter/runtime.py",
    "services/model-registry-adapter/service.py",
    "services/model-registry-adapter/Dockerfile",
    "services/model-registry-adapter/tests/test_runtime.py",
]
missing = [p for p in required if not (R / p).is_file()]
if missing:
    raise SystemExit("missing WX-12 runtime files: " + ", ".join(missing))
text = (R / "services/model-registry-adapter/runtime.py").read_text()
for token in [
    "compare-and-swap",
    "reconcile_active_state",
    "verify_activation",
    "apply_rollout",
    "record_monitoring",
    "dispatch_retraining",
    "MODEL_TRAFFIC_CONTROLLER_URL",
    "MODEL_TRAINING_BACKEND_URL",
]:
    if token not in text:
        raise SystemExit(f"missing contract token: {token}")
for forbidden in ["model.fit(", "optimizer.step(", "mqtt.publish("]:
    if forbidden in text:
        raise SystemExit(f"forbidden hidden side effect: {forbidden}")
print("WX-12 runtime completion gate: PASS")
