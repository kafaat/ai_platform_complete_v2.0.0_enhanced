#!/usr/bin/env python3
"""Static ratchet for M2.9 controller/edge framework."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
req = {
    "services/sahool-platform/api/controller_edge_adapter.py": [
        "TELEMETRY_REPLAY_OR_OUT_OF_ORDER",
        'dispatch_allowed": False',
        "READ_ONLY_NO_COMMAND_EXECUTION",
        "controller_capability_to_graph_input",
    ],
    "migrations/v176_controller_edge_adapter_framework.sql": [
        "irrigation_controller_handshakes",
        "irrigation_controller_telemetry",
        "canonical_controller_capabilities",
        "irrigation_controller_command_requests",
        "FORCE ROW LEVEL SECURITY",
        "dispatch_allowed = FALSE",
    ],
}
for f, toks in req.items():
    s = (ROOT / f).read_text()
    for x in toks:
        assert x in s, (f, x)
print("irrigation controller/edge M2.9 guard: PASS")
