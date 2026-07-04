"""CI wiring guard for Backend-to-Frontend coverage gates.

The coverage contracts are only useful if the repository CI runs them on every
pull request, not only when a developer remembers to invoke the scripts locally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CI = REPO / ".github" / "workflows" / "ci.yml"


@pytest.mark.unit
def test_backend_frontend_coverage_gates_are_wired_in_ci() -> None:
    ci = CI.read_text(encoding="utf-8")
    assert "python scripts/ci/endpoint_ui_coverage_gate.py" in ci
    assert "python scripts/ci/service_feature_ui_contract_gate.py" in ci
    assert ci.index("endpoint_ui_coverage_gate.py") > ci.index(
        "service_feature_ui_contract_gate.py"
    )
