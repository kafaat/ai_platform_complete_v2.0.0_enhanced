"""Read-only harvest-origin balance projection for the marketplace integration.

Market-MCP currently stores UUID batch_id, whereas authoritative harvest_lots
use hl_* text identities. This module deliberately creates NO shadow market
writer or synthetic UUID. It calculates an upper bound, not reservable stock.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _quantity(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def assess_market_origin_preview(
    lot: dict[str, Any],
    custody_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Conservative projection for a tenant-owned lot; never authorizes sale.

    Seller reservations, grading splits, spoilage and allocations have no
    authoritative bridge yet. Even a valid numeric upper bound cannot be
    promoted to market availability until those owners certify it.
    """
    lot_id = lot.get("harvest_lot_id")
    total = _quantity(lot.get("quantity_kg"))
    outgoing = Decimal("0")
    reasons = ["market_listing_identity_bridge_not_implemented",
               "reservations_and_sorting_losses_unavailable"]
    if total is None or not lot_id:
        reasons.append("origin_quantity_or_identity_invalid")
    for event in custody_events:
        if event.get("event_type") != "sales":
            continue
        qty = _quantity(event.get("quantity_kg"))
        if qty is None:
            reasons.append("recorded_sale_quantity_missing_or_invalid")
        else:
            outgoing += qty
    if total is not None and outgoing > total:
        reasons.append("recorded_sales_exceed_harvest_quantity")
    if lot.get("status") in ("sold", "rejected"):
        reasons.append("lot_closed_or_rejected")
    if lot.get("quality_grade") not in ("A", "B", "C"):
        reasons.append("lot_quality_not_declared_for_sale")
    remaining = total - outgoing if total is not None and outgoing <= total else None
    return {
        "schema": "sahool.market-origin-preview/v1",
        "origin_kind": "harvest_lot",
        "origin_id": lot_id,
        "recorded_harvest_kg": float(total) if total is not None else None,
        "recorded_sales_kg": float(outgoing),
        "upper_bound_remaining_kg": float(remaining) if remaining is not None else None,
        "status": "blocked" if any(r not in (
            "market_listing_identity_bridge_not_implemented",
            "reservations_and_sorting_losses_unavailable",
        ) for r in reasons) else "preview_only",
        "decision_usable": False,
        "reasons": reasons,
    }
