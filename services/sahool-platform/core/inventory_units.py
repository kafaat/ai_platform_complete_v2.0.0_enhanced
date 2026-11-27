"""Totals for inventory lots whose original quantities and unit labels are retained."""

from decimal import Decimal

# Factors are exact. Unlisted units (including a supplier's sack or pack) can
# be added in their own unit but cannot be converted without a product-specific factor.
_METRIC_UNITS = {
    "kg": ("mass", Decimal("1000")),
    "g": ("mass", Decimal("1")),
    "mg": ("mass", Decimal("0.001")),
    "L": ("volume", Decimal("1000")),
    "l": ("volume", Decimal("1000")),
    "mL": ("volume", Decimal("1")),
    "ml": ("volume", Decimal("1")),
}


def stock_in_item_unit(item_unit: str | None, amounts: dict[str | None, Decimal]) -> Decimal | None:
    """None means that some nonzero stock cannot be expressed in the item's unit."""
    total = Decimal(0)
    target = _METRIC_UNITS.get(item_unit)
    for batch_unit, quantity in amounts.items():
        if batch_unit == item_unit or not quantity:
            total += quantity
            continue
        source = _METRIC_UNITS.get(batch_unit)
        if not source or not target or source[0] != target[0]:
            return None
        total += quantity * source[1] / target[1]
    return total
