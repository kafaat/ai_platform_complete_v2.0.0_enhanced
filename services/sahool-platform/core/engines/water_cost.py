"""
sahool_core.engines.water_cost
===============================
Water cost model — the factor the critique called "ROI-flipping".

In arid regions, pumping cost (diesel) can be 60% of total cost and turn a
profitable crop into a loss. Solar is cheap to run but encourages aquifer
depletion (near-zero marginal cost). We compute cost PER m3 as a RANGE,
never a single fabricated number.

Physics:
  Energy to lift 1 m3 by 1 m = rho*g*h / efficiency
  rho*g = 9.81 kN/m3 ; 1 kWh = 3.6 MJ
  => 0.002725 kWh per m3 per metre at 100% efficiency
  Divide by pump+motor efficiency.

Sources:
  - Hydraulic power: standard pump engineering (P = rho*g*Q*H).
  - Yemen SPIS context: solar pumping spread widely due to diesel scarcity;
    near-zero marginal cost drives over-abstraction (well-documented in
    Yemen groundwater literature). We DO NOT hardcode a $/m3 — caller
    supplies depth, pump type, fuel price.
"""

from __future__ import annotations

from dataclasses import dataclass

# kWh needed to lift 1 m3 of water 1 metre (100% efficiency)
KWH_PER_M3_PER_M = 0.002725


@dataclass
class WaterCostInputs:
    well_depth_m: float
    pump_type: str  # "diesel" | "solar" | "grid"
    pump_efficiency: float = 0.55  # diesel pump+motor typical 0.5-0.6
    # diesel
    diesel_price_usd_per_liter: float | None = None
    diesel_kwh_per_liter: float = 3.4  # usable shaft energy, not raw LHV
    # solar (amortised)
    solar_capital_usd: float | None = None
    solar_lifetime_years: int = 10
    solar_maintenance_annual_pct: float = 0.05
    solar_m3_per_year: float | None = None
    solar_dust_derate_pct: float = 0.25  # dust cuts output 20-30% in arid zones
    # grid
    grid_price_usd_per_kwh: float | None = None
    grid_efficiency: float = 0.80


def _energy_kwh_per_m3(depth_m: float, efficiency: float) -> float:
    return KWH_PER_M3_PER_M * depth_m / max(0.1, efficiency)


def water_cost_per_m3(inp: WaterCostInputs) -> dict:
    """Return {low, high, mid, basis} in USD/m3. Range, not a fake point."""
    if inp.pump_type == "diesel":
        if inp.diesel_price_usd_per_liter is None:
            return {"error": "diesel_price_usd_per_liter required (volatile, daily)"}
        kwh = _energy_kwh_per_m3(inp.well_depth_m, inp.pump_efficiency)
        liters = kwh / inp.diesel_kwh_per_liter
        cost = liters * inp.diesel_price_usd_per_liter
        # +/-20% band for efficiency degradation & price swings
        return {
            "mid": round(cost, 4),
            "low": round(cost * 0.8, 4),
            "high": round(cost * 1.3, 4),
            "basis": "diesel; volatile fuel price drives the wide upper band",
        }

    if inp.pump_type == "solar":
        if not (inp.solar_capital_usd and inp.solar_m3_per_year):
            return {"error": "solar_capital_usd and solar_m3_per_year required"}
        eff_m3 = inp.solar_m3_per_year * (1.0 - inp.solar_dust_derate_pct)
        annual_capital = inp.solar_capital_usd / inp.solar_lifetime_years
        annual_maint = inp.solar_capital_usd * inp.solar_maintenance_annual_pct
        base_cost = (annual_capital + annual_maint) / max(1.0, eff_m3)
        # depth scales the energy (hence panel sizing) needed per m3.
        # normalise to a 100 m reference well so depth genuinely matters.
        depth_factor = inp.well_depth_m / 100.0
        cost = base_cost * depth_factor
        return {
            "mid": round(cost, 4),
            "low": round(cost * 0.7, 4),
            "high": round(cost * 1.4, 4),
            "basis": "solar; amortised capital scaled by well depth, dust-derated. "
            "Near-zero marginal cost — WARN: encourages over-abstraction",
            "depletion_warning": True,
        }

    if inp.pump_type == "grid":
        if inp.grid_price_usd_per_kwh is None:
            return {"error": "grid_price_usd_per_kwh required"}
        kwh = _energy_kwh_per_m3(inp.well_depth_m, inp.grid_efficiency)
        cost = kwh * inp.grid_price_usd_per_kwh
        return {
            "mid": round(cost, 4),
            "low": round(cost * 0.9, 4),
            "high": round(cost * 1.2, 4),
            "basis": "grid electricity; outages add hidden cost not modelled",
        }

    return {"error": f"unknown pump_type: {inp.pump_type}"}


def seasonal_water_cost(inp: WaterCostInputs, etc_m3_per_ha: float, area_ha: float) -> dict:
    """Total seasonal water cost for a field as a range."""
    per_m3 = water_cost_per_m3(inp)
    if "error" in per_m3:
        return per_m3
    total_m3 = etc_m3_per_ha * area_ha
    return {
        "total_m3": round(total_m3, 0),
        "cost_low_usd": round(total_m3 * per_m3["low"], 0),
        "cost_mid_usd": round(total_m3 * per_m3["mid"], 0),
        "cost_high_usd": round(total_m3 * per_m3["high"], 0),
        "per_m3": per_m3,
    }
