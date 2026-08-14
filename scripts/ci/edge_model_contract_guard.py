#!/usr/bin/env python3
"""Guard the edge-inference model contract.

The service must not silently package opaque ONNX weights in the repo, and the manifest
must stay aligned with the runtime defaults in main.py/docker-compose.v9.yml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "services" / "edge-inference" / "models_manifest" / "edge_models.required.json"
MAIN = ROOT / "services" / "edge-inference" / "main.py"
COMPOSE = ROOT / "docker-compose.v9.yml"
EDGE_DIR = ROOT / "services" / "edge-inference"


def main() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    main_text = MAIN.read_text(encoding="utf-8")
    compose_text = COMPOSE.read_text(encoding="utf-8")
    errors: list[str] = []

    if "EDGE_READINESS_MODE" not in main_text or "EDGE_READINESS_MODE" not in compose_text:
        errors.append(
            "EDGE_READINESS_MODE must be supported in main.py and exposed in docker-compose.v9.yml"
        )
    if (
        "EDGE_PRODUCTION_REQUIRED" not in main_text
        or "EDGE_PRODUCTION_REQUIRED" not in compose_text
    ):
        errors.append(
            "EDGE_PRODUCTION_REQUIRED must be supported in main.py and exposed in docker-compose.v9.yml"
        )

    for model in payload.get("required_models", []):
        env = model["env"]
        default_path = model["default_path"]
        filename = Path(default_path).name
        if env not in main_text:
            errors.append(f"{env} is missing from edge main.py")
        if default_path not in compose_text:
            errors.append(f"{default_path} is missing from docker-compose.v9.yml")
        packaged = list(EDGE_DIR.rglob(filename))
        packaged = [p for p in packaged if "models_manifest" not in p.parts]
        if packaged:
            rel = ", ".join(str(p.relative_to(ROOT)) for p in packaged)
            errors.append(f"ONNX model must be operator-provisioned, not committed: {rel}")

    if errors:
        raise SystemExit("Edge model contract guard failed:\n" + "\n".join(errors))
    print("✓ edge model contract guard passed")


if __name__ == "__main__":
    main()
