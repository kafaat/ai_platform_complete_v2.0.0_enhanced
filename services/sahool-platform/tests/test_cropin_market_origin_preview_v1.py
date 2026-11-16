"""Read-only origin projection must never turn a harvest estimate into saleable stock."""

from core.engines.harvest_traceability import assess_market_origin_preview


def _lot(**kw):
    return {
        "harvest_lot_id": "hl_0123456789abcdef",
        "quantity_kg": 1000,
        "status": "stored",
        "quality_grade": "A",
        **kw,
    }


def test_upper_bound_subtracts_only_recorded_sales_without_authorizing_listing():
    out = assess_market_origin_preview(_lot(), [{"event_type": "sales", "quantity_kg": 200}])
    assert out["upper_bound_remaining_kg"] == 800
    assert out["status"] == "preview_only"
    assert out["decision_usable"] is False
    assert "market_listing_identity_bridge_not_implemented" in out["reasons"]


def test_missing_sale_quantity_fails_closed():
    out = assess_market_origin_preview(_lot(), [{"event_type": "sales", "quantity_kg": None}])
    assert out["status"] == "blocked"
    assert out["decision_usable"] is False


def test_cannot_exceed_recorded_harvest_quantity():
    out = assess_market_origin_preview(_lot(), [{"event_type": "sales", "quantity_kg": 1001}])
    assert out["status"] == "blocked"
    assert out["upper_bound_remaining_kg"] is None


def test_rejected_lot_is_not_eligible_for_listing():
    out = assess_market_origin_preview(_lot(status="rejected"), [])
    assert out["status"] == "blocked"


def test_non_finite_harvest_quantity_has_no_balance():
    out = assess_market_origin_preview(_lot(quantity_kg=float("nan")), [])
    assert out["status"] == "blocked"
    assert out["upper_bound_remaining_kg"] is None
