#!/usr/bin/env python3
"""CI guard for edge-inference service runtime/config contracts.

This is intentionally static + import-light. It catches the production issues that
make edge appear healthy while being unreachable or incapable of real inference:
- proxy must remain hidden from OpenAPI but runtime-routable through platform
- edge service must require SAHOOL_AGENT_TOKEN
- compose variants must pass the same token/model path contracts to edge
- all internal URLs must target port 8100, not 8000
- model path resolution must support MODEL_CACHE default paths
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGE = ROOT / "services" / "edge-inference"
PROXY = ROOT / "services" / "sahool-platform" / "api" / "routers" / "service_proxy.py"


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"missing required file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def check_edge_app_import_contract() -> None:
    main = _read(EDGE / "main.py")
    assert 'AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")' in main
    assert 'raise HTTPException(503, "SAHOOL_AGENT_TOKEN' in main
    assert 'PEST_MODEL_PATH' in main and 'pest_detector_int8.onnx' in main
    assert 'YIELD_MODEL_PATH' in main and 'yield_estimator_int8.onnx' in main
    assert '@app.get("/capabilities")' in main
    assert '"status": status' in main and '"degraded"' in main
    ast.parse(main)


def check_no_synthetic_inference_contract() -> None:
    pest = _read(EDGE / "models" / "pest_detector.py")
    yld = _read(EDGE / "models" / "yield_estimator.py")
    assert "raise ModelNotProvisioned" in pest
    assert "raise ModelNotProvisioned" in yld
    assert "_ml_pest_model_path(self.model_path)" in pest
    assert "_ml_yield_model_path(self.model_path)" in yld
    # The old helper may remain for local testing, but production predict() must not call it.
    predict_pest = pest.split("def predict(", 1)[1].split("def _parse_onnx_outputs", 1)[0]
    assert "_simulate_detection(" not in predict_pest


def check_platform_proxy_contract() -> None:
    proxy = _read(PROXY)
    assert '"/api/edge/{path:path}"' in proxy
    assert "include_in_schema=False" in proxy
    assert 'EDGE_INFERENCE_URL", "http://sahool-edge:8100"' in proxy
    assert 'headers["X-Agent-Token"] = _service_token()' in proxy
    assert 'headers["X-Tenant-Id"] = str(user.tenant_id)' in proxy


def check_compose_edge_contracts() -> None:
    compose_names = [
        "docker-compose.v9.yml",
        "docker-compose.light.yml",
    ]
    for name in compose_names:
        text = _read(ROOT / name)
        assert "services/edge-inference/Dockerfile.arm64" in text, name
        assert "SAHOOL_AGENT_TOKEN" in text, name
        assert "PEST_MODEL_PATH" in text, name
        assert "YIELD_MODEL_PATH" in text, name
        # Any reference to the edge service must use its real listener port.
        bad_refs = re.findall(r"http://(?:sahool(?:-unified)?-edge|edge-inference):8000", text)
        assert not bad_refs, f"{name} has bad edge URL(s): {bad_refs}"


def main() -> None:
    check_edge_app_import_contract()
    check_no_synthetic_inference_contract()
    check_platform_proxy_contract()
    check_compose_edge_contracts()
    print("✓ Edge inference service contract gate passed")


if __name__ == "__main__":
    main()
