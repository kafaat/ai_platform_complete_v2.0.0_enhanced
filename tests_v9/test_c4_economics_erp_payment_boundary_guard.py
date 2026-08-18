from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_existing_erp_projection_route_gains_identity_without_route_growth():
    src = _text("services/sahool-platform/api/routers/farm_operations_ledger.py")
    assert src.count('@router.get("/api/v1/farm-ledger/erp-projection/{season_id}")') == 1
    assert "build_projection_envelope" in src
    assert '"projection_digest": envelope["projection_digest"]' in src


def test_reconciliation_no_longer_accepts_outbox_existence_as_proof():
    src = _text("services/sahool-platform/api/routers/operational_truth.py")
    assert "verify_reconciliation_binding" in src
    assert "SELECT provider, payload, status, sent_at FROM farm_ledger_erp_projection_outbox" in src
    assert "SELECT 1 FROM farm_ledger_erp_projection_outbox" not in src
    assert 'stored_status=str(outbox["status"])' in src
    assert 'stored_sent_at=outbox["sent_at"]' in src


def test_payment_bridge_boundary_is_explicit_and_does_not_claim_runtime():
    doc = json.loads(_text("docs/architecture/payment_bridge_accounting_boundary.json"))
    assert doc["implemented_in_this_repository"] is False
    assert doc["posting_policy"]["E2"] == "draft_or_suggest_only"
    assert doc["posting_policy"]["E3"] == "draft_or_suggest_only"
    assert "E4V" in doc["posting_policy"]
    assert doc["required_identity"]["short_code_role"].startswith("routing/channel identity")
