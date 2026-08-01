from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
persistence = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
migration = (
    ROOT / "services/decision-service/migrations/006_execution_delivery_receipt.sql"
).read_text(encoding="utf-8")
for token in (
    "/v1/execution-requests/{execution_request_id}/claim",
    "/v1/execution-requests/{execution_request_id}/receipt",
):
    assert token in main
for token in (
    "EXECUTION_REQUEST_CLAIMED",
    "EXECUTION_RECEIPT_RECORDED",
    "decision_execution_delivery_attempts",
):
    assert token in persistence or token in migration
for forbidden in ("outcome_record", "online_learning_updates", "MQTT", "actuator"):
    assert forbidden not in main[main.index("class ExecutionDeliveryClaimIn") :]
print("WX-10.11b execution-delivery receipt boundary: LOCKED")
