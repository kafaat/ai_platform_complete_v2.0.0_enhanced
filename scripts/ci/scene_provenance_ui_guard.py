#!/usr/bin/env python3
"""Static ratchet: scene provenance must remain visible and fail-honest in both imagery UIs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
component = (ROOT / "frontend/src/components/maphub/SceneProvenanceCard.tsx").read_text(
    encoding="utf-8"
)
workspace = (ROOT / "frontend/src/sections/FieldWorkspaceImageryPanel.tsx").read_text(
    encoding="utf-8"
)
maphub = (ROOT / "frontend/src/sections/MapHub.tsx").read_text(encoding="utf-8")
api = (ROOT / "frontend/src/services/api/fieldImagery.ts").read_text(encoding="utf-8")

for token in (
    "scene_id",
    "acquisition_datetime",
    "cloud_pct",
    "بيانات المصدر الناقصة",
    "لا تُعد هذه الصورة كاملة التتبّع",
):
    assert token in component, f"Scene provenance component missing {token}"
assert "<SceneProvenanceCard scene={item} compact />" in workspace
assert "<SceneProvenanceCard scene={selectedScene} />" in maphub
for token in ("scene_id?:", "acquisition_datetime?:", "cloud_pct:"):
    assert token in api, f"Imagery API contract missing {token}"
print("scene provenance UI guard: PASS")
