#!/usr/bin/env python3
"""Static ratchet ensuring real-Postgres soil certification remains wired."""

from pathlib import Path

root = Path(__file__).resolve().parents[2]
test = root / "tests_v9/test_soil_runtime_certification_integration.py"
ci = (root / ".github/workflows/ci.yml").read_text()
assert test.exists(), "real PostgreSQL soil certification test missing"
src = test.read_text()
for token in (
    "pytest.mark.integration",
    "FORCE RLS",
    "NOBYPASSRLS",
    "concurrent_idempotency",
    "rebuild_snapshot_locked",
    "get_cutover_readiness",
):
    assert token in src, f"soil runtime certification lost coverage: {token}"
assert "pytest -v -m integration" in ci, "integration certification is not executed in CI"
print("soil_runtime_certification_guard_ok")
