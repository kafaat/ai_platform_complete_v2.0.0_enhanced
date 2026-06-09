"""
sahool_core.engines.fuzzy
==========================
Trapezoidal fuzzy membership scoring with an explicit DEAD ZONE.

Why (from the critique): a linear score gives pH=6.0 a score of 0.5 even
when the crop may already be dead at that value. Real agronomic responses
are non-linear with hard cut-offs. We model each factor as a trapezoid:

    score = 0.0   if value < min_acceptable  OR  value > max_acceptable   (DEAD)
    score = 1.0   if optimal_min <= value <= optimal_max                  (PLATEAU)
    score = linear ramp between acceptable and optimal edges              (SHOULDERS)

This is standard fuzzy-logic trapezoidal membership (Zadeh, 1965), applied
to crop-requirement matching per FAO land-suitability framework
(FAO, 1976, "A Framework for Land Evaluation", Soils Bulletin 32).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrapezoidParams:
    """Four corners of the trapezoid. Outside [min_acc, max_acc] => dead zone."""
    min_acceptable: float
    optimal_min: float
    optimal_max: float
    max_acceptable: float

    def __post_init__(self):
        assert (
            self.min_acceptable <= self.optimal_min
            <= self.optimal_max <= self.max_acceptable
        ), "trapezoid corners must be ordered"


def trapezoidal_score(value: float, p: TrapezoidParams) -> float:
    """Return membership score in [0, 1]. Hard 0 outside acceptable range."""
    if value < p.min_acceptable or value > p.max_acceptable:
        return 0.0  # DEAD ZONE — crop fails here
    if p.optimal_min <= value <= p.optimal_max:
        return 1.0  # optimal plateau
    if value < p.optimal_min:
        # rising shoulder
        span = p.optimal_min - p.min_acceptable
        return (value - p.min_acceptable) / span if span > 0 else 1.0
    # falling shoulder (value > optimal_max)
    span = p.max_acceptable - p.optimal_max
    return (p.max_acceptable - value) / span if span > 0 else 1.0


# ── one-sided trapezoids (e.g. salinity: lower is always better) ─────
def descending_score(value: float, optimal_max: float, max_acceptable: float) -> float:
    """For factors where lower is better (salinity, SAR). 1.0 below optimal,
    linear decline to 0 at max_acceptable, dead above."""
    if value <= optimal_max:
        return 1.0
    if value >= max_acceptable:
        return 0.0
    span = max_acceptable - optimal_max
    return (max_acceptable - value) / span if span > 0 else 0.0


def ascending_score(value: float, min_acceptable: float, optimal_min: float) -> float:
    """For factors where higher is better (organic matter, soil depth)."""
    if value >= optimal_min:
        return 1.0
    if value <= min_acceptable:
        return 0.0
    span = optimal_min - min_acceptable
    return (value - min_acceptable) / span if span > 0 else 0.0
