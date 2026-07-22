#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
contract = json.loads((ROOT / "shared/contracts/intelligence_governance.json").read_text())
errors = []
if contract["principles"].get("observed_spectral_truth") != "raster-service":
    errors.append("bad spectral owner")
for rel in [
    "services/supervisor-agent/remote_sensing_skill.py",
    "services/supervisor-agent/skills/remote_sensing_skill.py",
]:
    text = (ROOT / rel).read_text()
    if '"compute_ndvi"' in text:
        errors.append(f"legacy compute_ndvi brain call: {rel}")
    if "read_indicator_observation" not in text:
        errors.append(f"missing authoritative read: {rel}")
    if "BRAIN_DIRECT_SATELLITE_FETCH_ENABLED" not in text:
        errors.append(f"direct provider fetch not gated: {rel}")

# Brain/agent services must not directly call actuator or MQTT; physical effects belong to Decision-Service.
for base in ["services/ai_agronomist", "services/agriai-engine", "services/supervisor-agent"]:
    for py in (ROOT / base).rglob("*.py"):
        if py.name.startswith("test_"):
            continue
        text = py.read_text(errors="ignore")
        low = text.lower()
        if "actuator_service_url" in low or "sahool-actuator" in low or "mqtt.publish(" in low:
            errors.append(f"direct physical-effect path in brain: {py.relative_to(ROOT)}")

brain = (ROOT / "sahool-brain/decisions/engine-ownership.md").read_text()
for token in ["Raster-Service", "Decision-Service", "intelligence_governance.json"]:
    if token not in brain:
        errors.append(f"brain ownership drift: {token}")
mcp = (ROOT / "services/mcp_servers/sentinel_hub_server.py").read_text()
if "RASTER_SERVICE_URL" not in mcp or "read_indicator_observation" not in mcp:
    errors.append("MCP not wired to Raster truth")
if errors:
    print("intelligence_governance_gate_failed")
    print("\n".join(f"- {e}" for e in errors))
    sys.exit(1)
print("intelligence_governance_gate_ok")
