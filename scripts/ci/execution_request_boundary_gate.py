from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    ROOT
    / "services/decision-service/main.py": "/v1/dispatch-authorizations/{dispatch_authorization_id}/execute",
    ROOT
    / "services/decision-service/migrations/005_execution_request.sql": "decision_execution_requests",
    ROOT / "services/sahool-platform/core/authorization.py": "DECISION_EXECUTE",
}
for p, token in checks.items():
    text = p.read_text(encoding="utf-8")
    assert token in text, f"{token} missing in {p}"
body = (
    (ROOT / "services/decision-service/persistence.py")
    .read_text(encoding="utf-8")
    .split("async def create_execution_request", 1)[1]
)
for forbidden in (
    "mqtt.publish",
    "actuator_runtime",
    "create_task(",
    "record_outcome",
    "learning_update",
):
    assert forbidden not in body, f"forbidden execution side effect: {forbidden}"
print("WX-10.11a execution-request boundary: LOCKED")
