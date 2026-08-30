from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/GATE01_INDEPENDENT_AUTHORITY_AND_IMAGE_SUPPLY_CHAIN.md"
pytestmark = pytest.mark.unit


def test_runbook_requires_real_independent_authority_and_one_time_binding() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for token in (
        "required_approving_review_count >= 1",
        "require_code_owner_review == true",
        "require_last_push_approval == true",
        "dismiss_stale_reviews_on_push == true",
        "canonical patch SHA-256",
        "status=ISSUED",
        "CONSUMED",
    ):
        assert token in text


def test_runbook_preserves_runtime_and_production_honesty_boundaries() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "retain `runtime_verified=false`" in text
    assert "must never\nset `production_certified=true`" in text
    assert "--oci-worker-no-process-sandbox" in text
    assert "not an\napproved workaround" in text
