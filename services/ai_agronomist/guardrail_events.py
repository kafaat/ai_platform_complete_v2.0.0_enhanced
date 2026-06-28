from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class GuardrailEvent:
    tenant_id: str
    field_id: str
    action: str
    reason: str
    confidence: float
    timestamp: str = datetime.utcnow().isoformat()

    def to_event(self) -> dict[str, Any]:
        return asdict(self)


NATS_SUBJECTS = {
    "guardrail": "SAHOOL.AI.GUARDRAIL",
    "human_review": "SAHOOL.AI.REVIEW",
    "feedback": "SAHOOL.AI.FEEDBACK",
}
