#!/usr/bin/env python3
"""WX-10.13 ratchet: outcome attribution must not mutate models or restart execution."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
files = [
    ROOT / "services/decision-service/main.py",
    ROOT / "services/decision-service/persistence.py",
    ROOT / "services/decision-service/migrations/008_learning_attribution.sql",
]
text = "\n".join(p.read_text() for p in files)
required = [
    "decision_learning_attributions", "LEARNING_ATTRIBUTION_CREATED",
    "evidence_snapshot_id", "execution_request_id", "learning_state",
]
for token in required:
    if token not in text:
        print(f"WX-10.13 gate: missing {token}")
        sys.exit(1)
for forbidden in ("model.fit(", "optimizer.step(", "automatic_redispatch", "actuator.call(", "mqtt.publish("):
    if forbidden in text:
        print(f"WX-10.13 gate: forbidden side effect {forbidden}")
        sys.exit(1)
print("WX-10.13 learning attribution boundary: PASS")
