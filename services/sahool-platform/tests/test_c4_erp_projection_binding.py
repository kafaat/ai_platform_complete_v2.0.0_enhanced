from __future__ import annotations

import pytest
from core.erp_projection_contract import (
    build_projection_envelope,
    canonical_digest,
    verify_reconciliation_binding,
)


def test_projection_identity_is_deterministic_and_read_only():
    lines = [{"account": "6000", "debit": 100.0, "credit": 0.0}]
    a = build_projection_envelope(season_id="s1", lines=lines, provider="erpnext", currency="yer")
    b = build_projection_envelope(season_id="s1", lines=lines, provider="erpnext", currency="YER")
    assert a["projection_digest"] == b["projection_digest"]
    assert a["posting_eligible"] is True
    assert a["erp_write"] is False
    assert a["currency"] == "YER"


def test_unconfigured_provider_projection_is_not_posting_eligible():
    result = build_projection_envelope(
        season_id="s1", lines=[{"amount": 10}], provider="none", currency="YER"
    )
    assert result["posting_eligible"] is False


def test_reconciliation_requires_exact_projection_digest_and_provider():
    payload = {
        "schema_version": "farm_ledger_erp_projection.v1",
        "season_id": "s1",
        "provider": "erpnext",
        "currency": "YER",
        "lines": [{"amount": 100}],
    }
    digest = canonical_digest(payload)
    assert (
        verify_reconciliation_binding(
            stored_payload=payload,
            stored_provider="erpnext",
            stored_status="sent",
            stored_sent_at="2026-08-18T00:00:00Z",
            receipt_provider="erpnext",
            evidence={"projection_digest": digest},
        )
        == digest
    )

    with pytest.raises(ValueError, match="projection_digest_mismatch"):
        verify_reconciliation_binding(
            stored_payload=payload,
            stored_provider="erpnext",
            stored_status="sent",
            stored_sent_at="2026-08-18T00:00:00Z",
            receipt_provider="erpnext",
            evidence={"projection_digest": "0" * 64},
        )

    with pytest.raises(ValueError, match="erp_provider_mismatch"):
        verify_reconciliation_binding(
            stored_payload=payload,
            stored_provider="erpnext",
            stored_status="sent",
            stored_sent_at="2026-08-18T00:00:00Z",
            receipt_provider="odoo",
            evidence={"projection_digest": digest},
        )


def test_reconciliation_refuses_unrouted_projection():
    payload = {"season_id": "s1", "lines": [{"amount": 100}]}
    with pytest.raises(ValueError, match="erp_projection_has_no_provider"):
        verify_reconciliation_binding(
            stored_payload=payload,
            stored_provider="none",
            stored_status="sent",
            stored_sent_at="2026-08-18T00:00:00Z",
            receipt_provider="erpnext",
            evidence={"projection_digest": canonical_digest(payload)},
        )


def test_reconciliation_refuses_projection_that_was_not_sent():
    payload = {"season_id": "s1", "provider": "erpnext", "lines": [{"amount": 100}]}
    digest = canonical_digest(payload)
    with pytest.raises(ValueError, match="erp_projection_not_sent"):
        verify_reconciliation_binding(
            stored_payload=payload,
            stored_provider="erpnext",
            stored_status="draft",
            stored_sent_at=None,
            receipt_provider="erpnext",
            evidence={"projection_digest": digest},
        )


def test_reconciliation_refuses_sent_status_without_sent_timestamp():
    payload = {"season_id": "s1", "provider": "erpnext", "lines": [{"amount": 100}]}
    digest = canonical_digest(payload)
    with pytest.raises(ValueError, match="erp_projection_missing_sent_at"):
        verify_reconciliation_binding(
            stored_payload=payload,
            stored_provider="erpnext",
            stored_status="sent",
            stored_sent_at=None,
            receipt_provider="erpnext",
            evidence={"projection_digest": digest},
        )
