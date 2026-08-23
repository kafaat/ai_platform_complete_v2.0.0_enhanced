#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
persist = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
sql = (ROOT / "services/decision-service/migrations/014_wx11_closed_loop_completion.sql").read_text(
    encoding="utf-8"
)
required = [
    "/v1/learning/rollback-commands/{rollback_command_id}/claim",
    "/v1/learning/rollback-commands/{rollback_command_id}/receipt",
    "/v1/learning/models/{model_id}/active-state",
    "/v1/learning/activation-receipts/{activation_receipt_id}/verification",
    "/v1/learning/activation-receipts/{activation_receipt_id}/rollout-plan",
    "/v1/learning/monitoring-snapshots",
    "/v1/learning/retraining-requests",
    "MODEL_REGISTRY_ROLLBACK_RECEIPT_RECORDED",
    "MODEL_POST_ACTIVATION_VERIFIED",
    "MODEL_ROLLOUT_PLAN_CREATED",
    "MODEL_MONITORING_SNAPSHOT_RECORDED",
    "MODEL_RETRAINING_REQUEST_CREATED",
]
blob = main + persist + sql
missing = [x for x in required if x not in blob]
for forbidden in ["model.fit(", "optimizer.step(", "mqtt.publish(", "active_alias ="]:
    if forbidden in persist:
        missing.append("forbidden:" + forbidden)
if missing:
    raise SystemExit("WX-11 completion gate FAILED: " + ", ".join(missing))
print("WX-11 completion gate PASS")
