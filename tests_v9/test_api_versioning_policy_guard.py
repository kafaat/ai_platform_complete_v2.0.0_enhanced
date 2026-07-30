from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import api_versioning_policy_guard as guard  # noqa: E402

pytestmark = pytest.mark.unit


def test_api_versioning_policy_guard_inventory_is_current():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/api_versioning_policy_guard.py", "--check"],
        cwd=root,
        check=True,
    )


def test_is_test_file_excludes_by_directory_and_filename():
    root = guard.ROOT
    assert guard._is_test_file(
        root / "services/sahool-platform/tests/test_correlation_middleware.py"
    )
    assert guard._is_test_file(root / "services/soil-service/tests/conftest.py")
    assert guard._is_test_file(root / "services/actuator-service/test_commands.py")
    assert not guard._is_test_file(root / "services/soil-service/main.py")
    assert not guard._is_test_file(root / "services/soil-service/routers/readings.py")


def test_collect_excludes_test_file_routes_structurally():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01 false positive: GET /probe inside
    test_correlation_middleware.py is a test fixture, not a production route."""
    rows = guard.collect()
    test_file_rows = [r for r in rows if guard._is_test_file(guard.ROOT / r["file"])]
    assert test_file_rows == [], f"routes leaked from test files: {test_file_rows}"


def test_runtime_identity_is_infra_not_legacy_business():
    """GET /runtime-identity is grouped with healthz/readyz/metrics as a
    provenance/infrastructure route (CLAUDE.md; platform_route_ownership_guard
    already classifies it this way) and is contract-declared, probe-configured,
    and attestation-tested -- not a genuine unversioned business route."""
    assert guard._classify("/runtime-identity") == "infra"
    rows = guard.collect()
    leaked = [
        r for r in rows if r["path"] == "/runtime-identity" and r["classification"] != "infra"
    ]
    assert leaked == [], f"/runtime-identity leaked into a non-infra classification: {leaked}"
