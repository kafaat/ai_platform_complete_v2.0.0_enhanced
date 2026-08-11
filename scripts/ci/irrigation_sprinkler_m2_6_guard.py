#!/usr/bin/env python3
"""Repository ratchet for M2.6 sprinkler/runoff capability."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "services/sahool-platform/api/canonical_sprinkler_runoff_capability.py"

required = {
    "migrations/v173_sprinkler_runoff_capability.sql": [
        "canonical_sprinkler_runoff_capabilities",
        "irrigation_sprinkler_packages",
        "FORCE ROW LEVEL SECURITY",
    ],
    str(PRODUCT.relative_to(ROOT)): [
        "RUNOFF_RISK_HIGH",
        "maximum_safe_depth_mm_event",
        "CURRENT_WIND_MEASUREMENT_REQUIRED",
        "root_zone_refill_cap_mm",
        "root_zone_refill_cap_source",
    ],
}
for file, tokens in required.items():
    text = (ROOT / file).read_text(encoding="utf-8")
    for token in tokens:
        assert token in text, (file, token)

tree = ast.parse(PRODUCT.read_text(encoding="utf-8"), filename=str(PRODUCT))
root_zone_keys = set()

for node in ast.walk(tree):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "root_zone_profile"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        root_zone_keys.add(node.args[0].value)

    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "root_zone_profile"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ):
        root_zone_keys.add(node.slice.value)

for required_key in (
    "quality_status",
    "operational_eligible",
    "infiltration_mm_h",
    "root_zone_refill_cap_mm",
    "profile_digest",
):
    assert required_key in root_zone_keys, required_key

for forbidden_key in ("status", "raw_mm", "maximum_safe_event_depth_mm"):
    assert forbidden_key not in root_zone_keys, (
        "canonical root-zone consumer bypass",
        forbidden_key,
    )

contract_test = (ROOT / "tests_v9/test_canonical_root_zone_to_sprinkler_contract.py").read_text(
    encoding="utf-8"
)
for test_name in (
    "test_real_root_zone_product_feeds_m26_without_adapter",
    "test_m26_rejects_legacy_status_alias",
    "test_m26_does_not_rederive_refill_cap_from_raw_mm",
):
    assert test_name in contract_test, test_name

print("irrigation sprinkler M2.6 guard: PASS")
