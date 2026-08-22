#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
contract = json.loads((ROOT / "shared/contracts/intelligence_governance.json").read_text(encoding="utf-8"))
errors = []
if contract["principles"].get("observed_spectral_truth") != "raster-service":
    errors.append("bad spectral owner")
# الموضع القانونيّ الوحيد بعد حذف نسخة الجذر الميتة
# (SUPERVISOR-ROOT-SKILLS-DEAD-CODE-01): main.py يستورد skills.* حصراً.
for rel in [
    "services/supervisor-agent/skills/remote_sensing_skill.py",
]:
    text = (ROOT / rel).read_text(encoding="utf-8")
    if '"compute_ndvi"' in text:
        errors.append(f"legacy compute_ndvi brain call: {rel}")
    if "read_indicator_observation" not in text:
        errors.append(f"missing authoritative read: {rel}")
    if "BRAIN_DIRECT_SATELLITE_FETCH_ENABLED" not in text:
        errors.append(f"direct provider fetch not gated: {rel}")

# قاعدة «الدماغ لا يصل فيزيائيّاً» انتقلت إلى موضعها القانونيّ الواحد:
# scripts/ci/physical_effect_boundary_guard.py + عقد
# docs/architecture/physical_effect_boundary_contract.json (P0-7).
# كانت هنا ثلاث كلمات مفتاحيّة تغطّي المسار الأصرح وحده وتترك موضوع أمر NATS
# واستيراد العميل والغلاف المُرحِّل مفتوحةً؛ والحارس الجديد يغطّي الأربعة ومنطقتين
# إضافيّتين (mcp_servers · agents). تُركت نسخة هنا كانت تعني مصدرَي حقيقة لقاعدة واحدة.

brain = (ROOT / "sahool-brain/decisions/engine-ownership.md").read_text(encoding="utf-8")
for token in ["Raster-Service", "Decision-Service", "intelligence_governance.json"]:
    if token not in brain:
        errors.append(f"brain ownership drift: {token}")
mcp = (ROOT / "services/mcp_servers/sentinel_hub_server.py").read_text(encoding="utf-8")
if "RASTER_SERVICE_URL" not in mcp or "read_indicator_observation" not in mcp:
    errors.append("MCP not wired to Raster truth")
if errors:
    print("intelligence_governance_gate_failed")
    print("\n".join(f"- {e}" for e in errors))
    sys.exit(1)
print("intelligence_governance_gate_ok")
