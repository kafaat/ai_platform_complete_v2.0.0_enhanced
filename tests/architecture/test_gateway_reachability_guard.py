import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "gateway_guard", ROOT / "scripts/ci/gateway_reachability_guard.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_gateway_payload_has_no_runtime_claim():
    data = MOD.payload()
    assert data["runtime_verified"] is False
    assert data["production_certified"] is False


def test_gateway_outputs_match_tree():
    data = MOD.payload()
    assert json.loads(MOD.JSON_PATH.read_text(encoding="utf-8")) == data


def test_every_proxy_upstream_is_declared_in_same_config():
    data = MOD.payload()
    assert data["hard_configuration_errors"] == []


def test_sensitive_findings_are_review_only():
    data = MOD.payload()
    assert all(
        "note" in item
        for f in data["files"]
        for item in f["review_findings"]
        if item["kind"] == "sensitive_route_without_gateway_auth"
    )
