#!/usr/bin/env python3
"""Fail closed when vegetation runtime regains synthetic field/provider ownership."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "services" / "vegetation-analysis-service" / "vegetation_runtime.py"
COMPOSES = [ROOT / "docker-compose.v9.yml", ROOT / "docker-compose.fixed.yml"]

text = RUNTIME.read_text(encoding="utf-8")
tree = ast.parse(text)
errors: list[str] = []

for node in ast.walk(tree):
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "FIELD_REGISTRY":
                value = node.value
                if not isinstance(value, ast.Dict) or value.keys:
                    errors.append("FIELD_REGISTRY must remain empty in runtime")

for forbidden in (
    "SH_CLIENT_ID",
    "SH_CLIENT_SECRET",
    "CDSE_CLIENT_ID",
    "CDSE_CLIENT_SECRET",
    "COPERNICUS_USER",
    "COPERNICUS_PASSWORD",
):
    if forbidden in text:
        errors.append(f"provider credential reference found in vegetation runtime: {forbidden}")

if "default=False\n)" not in text and "default=False)" not in text:
    errors.append("legacy field registry must default to disabled")

for compose in COMPOSES:
    ctext = compose.read_text(encoding="utf-8")
    service = ctext.split("sahool-vegetation-analysis:", 1)[1].split(
        "\n  sahool-raster-service:", 1
    )[0]
    for required in (
        "PLATFORM_API_URL:",
        'FEATURE_SENTINEL_DB_FIELDS: "1"',
        'ALLOW_LEGACY_FIELD_REGISTRY: "0"',
        "SAHOOL_AGENT_TOKEN:",
    ):
        if required not in service:
            errors.append(f"{compose.name}: vegetation missing {required}")
    # VEGETATION_REAL_ONLY must be FAIL-CLOSED in production compose. The literal
    # "1" and the env-driven default ${VEGETATION_REAL_ONLY:-1} both satisfy this
    # (dev opts into soft-fail via docker-compose.dev.yml). A soft default (0/false)
    # is rejected — see scripts/ci/vegetation_real_only_posture_guard.py.
    if (
        'VEGETATION_REAL_ONLY: "1"' not in service
        and "VEGETATION_REAL_ONLY: ${VEGETATION_REAL_ONLY:-1}" not in service
    ):
        errors.append(f"{compose.name}: vegetation VEGETATION_REAL_ONLY must default fail-closed (1)")

if errors:
    raise SystemExit("vegetation_runtime_truth_guard failed:\n- " + "\n- ".join(errors))
print("vegetation_runtime_truth_guard_ok")
