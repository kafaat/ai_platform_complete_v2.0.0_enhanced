#!/usr/bin/env python3
"""Production honesty guard.

Prevents regression from honest fail-closed services back to mock/stub/fabricated
outputs on production routes. Test files are ignored; explicit 501 or degraded
health-only boundaries are allowed.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGE = ROOT / "services" / "edge-inference"
INDICATORS = ROOT / "services" / "indicators-service"


def fail(msg: str) -> None:
    raise SystemExit("✗ " + msg)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_edge_download_does_not_claim_simulation_fallback() -> None:
    source = text(EDGE / "download_models.py").lower()
    forbidden = [
        "simulation mode",
        '"fallback": "simulation"',
        "will use simulation",
        '"fallback": "regression"',
    ]
    found = [item for item in forbidden if item in source]
    if found:
        fail("edge model downloader still advertises fabricated fallback modes: " + repr(found))


def check_edge_predict_fail_closed_before_simulation() -> None:
    source_path = EDGE / "models" / "pest_detector.py"
    tree = ast.parse(text(source_path))
    predict_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "predict":
            predict_node = node
            break
    if predict_node is None:
        fail("EdgePestDetector.predict missing")
    calls = []
    raises_model_not_provisioned = False
    for node in ast.walk(predict_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.append(node.func.id)
        if isinstance(node, ast.Raise) and node.exc is not None:
            rendered = ast.unparse(node.exc)
            if "ModelNotProvisioned" in rendered:
                raises_model_not_provisioned = True
    if "_simulate_detection" in calls:
        fail("EdgePestDetector.predict calls _simulate_detection on production path")
    if not raises_model_not_provisioned:
        fail("EdgePestDetector.predict must raise ModelNotProvisioned when model is absent")


def check_indicators_contract_boundary_is_honest() -> None:
    source = text(INDICATORS / "main.py")
    required = [
        '"status": "ready"',
        '"implemented_runtime": True',
        # RS2/RS3 cutover: the service is now the canonical-observation adapter
        # (reads observations from raster-service), not a passive contract-only
        # stub. The honest role marker moved accordingly; spectral compute is
        # still disowned (409) and never simulated here.
        '"runtime_role": "canonical-observation-adapter"',
        '"spectral_compute": False',
        "status_code=409",
    ]
    missing = [item for item in required if item not in source]
    if missing:
        fail("indicators-service contract boundary missing honesty markers: " + repr(missing))
    forbidden = ['"health_only": True', '"implemented_runtime": False', "status_code=501"]
    present = [item for item in forbidden if item in source]
    if present:
        fail("indicators-service retains stale health-only markers: " + repr(present))


def main() -> None:
    check_edge_download_does_not_claim_simulation_fallback()
    check_edge_predict_fail_closed_before_simulation()
    check_indicators_contract_boundary_is_honest()
    print("✓ production honesty guard passed")


if __name__ == "__main__":
    main()
