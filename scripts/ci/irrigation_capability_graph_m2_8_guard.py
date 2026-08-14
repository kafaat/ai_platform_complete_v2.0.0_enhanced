#!/usr/bin/env python3
"""Repository ratchet for M2.8 unified irrigation capability graph."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {
    "migrations/v175_unified_irrigation_capability_graph.sql": [
        "canonical_irrigation_capability_graphs",
        "irrigation_capability_graph_nodes",
        "irrigation_capability_graph_edges",
        "FORCE ROW LEVEL SECURITY",
        "FOREIGN KEY (controller_id, tenant_id)",
    ],
    "services/sahool-platform/api/canonical_irrigation_capability_graph.py": [
        "REQUIRED_LINKS",
        "weakest_link",
        "NO_FEASIBLE_OPERATING_WINDOW",
        "CONTROLLER_TELEMETRY_STALE",
        "irrigation_capability_graph_to_mpc_constraints",
        "capability_digest",
    ],
}
for file_name, tokens in REQUIRED.items():
    text = (ROOT / file_name).read_text(encoding="utf-8")
    for token in tokens:
        assert token in text, (file_name, token)
print("irrigation capability graph M2.8 guard: PASS")
