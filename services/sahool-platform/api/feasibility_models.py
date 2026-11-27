"""api/feasibility_models.py — نماذج الجدوى الاقتصاديّة (Feasibility)
==================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): نموذج طلب الجدوى الاقتصاديّة
مُستخرَج حرفيّاً ليُستورَد من ``api/routers/economics.py``.

النموذج مكتفٍ ذاتيّاً (pydantic فقط) — لا يعتمد على رموز ``api.main`` الخاصّة.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ─── ٤١. دراسة الجدوى الاقتصاديّة (هل سأربح؟) ─────────────────────


class WaterCostScenario(BaseModel):
    """Caller-supplied seasonal pumping scenario, not measured costs or ledger data."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    input_basis: Literal["synthetic", "operator_estimate"]
    source_ref: str = Field(min_length=1, max_length=512, pattern=r"\S")
    pumped_m3_per_ha: float = Field(ge=0)
    well_depth_m: float = Field(gt=0)
    pump_type: Literal["diesel", "grid", "solar"]
    pump_efficiency: float | None = Field(default=None, ge=0.1, le=1)
    diesel_price_usd_per_liter: float | None = Field(default=None, ge=0)
    diesel_kwh_per_liter: float | None = Field(default=None, gt=0)
    grid_price_usd_per_kwh: float | None = Field(default=None, ge=0)
    grid_efficiency: float | None = Field(default=None, ge=0.1, le=1)
    solar_capital_usd: float | None = Field(default=None, gt=0)
    solar_lifetime_years: int | None = Field(default=None, gt=0)
    solar_maintenance_annual_pct: float | None = Field(default=None, ge=0)
    solar_m3_per_year: float | None = Field(
        default=None,
        gt=0,
        description="Annual pumped volume in m³ at the 100 m reference depth, before dust losses.",
    )
    solar_dust_derate_pct: float | None = Field(default=None, ge=0, lt=1)

    @model_validator(mode="after")
    def require_matching_pump_inputs(self) -> WaterCostScenario:
        groups = {
            "diesel": ("pump_efficiency", "diesel_price_usd_per_liter", "diesel_kwh_per_liter"),
            "grid": ("grid_price_usd_per_kwh", "grid_efficiency"),
            "solar": (
                "solar_capital_usd",
                "solar_lifetime_years",
                "solar_maintenance_annual_pct",
                "solar_m3_per_year",
                "solar_dust_derate_pct",
            ),
        }
        for pump_type, names in groups.items():
            for name in names:
                present = getattr(self, name) is not None
                if present != (pump_type == self.pump_type):
                    raise ValueError(f"{name}: required for {pump_type}, otherwise omit")
        return self


EnergySource = Literal["grid", "diesel", "solar"]
Money = Annotated[float, Field(ge=0, le=1e15)]
Description = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]


class QuotedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    item: Description
    unit: Description
    quantity: float = Field(gt=0, le=1e12)
    unit_price: Money
    service_life_years: int = Field(ge=1, le=200)


class SupplyOption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    source: EnergySource
    source_ref: Description
    boq: list[QuotedItem] = Field(min_length=1, max_length=100)
    annual_maintenance: Money
    annual_delivered_m3: float = Field(gt=0, le=1e12)
    annual_energy_kwh: float = Field(gt=0, le=1e12)
    energy_price_per_kwh: Money


class LifecycleScenario(BaseModel):
    """Constant-price scenario, equal delivered water required to compare options."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    currency: str = Field(pattern="^[A-Z]{3}$")
    horizon_years: int = Field(ge=1, le=100)
    discount_rate: float = Field(ge=0, le=1)
    baseline: EnergySource
    options: list[SupplyOption] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def sources_unique(self):
        if len({o.source for o in self.options}) != 3:
            raise ValueError("all three distinct power sources are required")
        return self

    def evaluate(self):
        results = []
        for o in self.options:
            capex = sum(i.quantity * i.unit_price for i in o.boq)
            opex = o.annual_maintenance + o.annual_energy_kwh * o.energy_price_per_kwh
            discounted = capex
            replacements = 0.0
            for year in range(1, self.horizon_years + 1):
                # Replace at end of useful life only if another service year follows.
                renewal = sum(
                    i.quantity * i.unit_price
                    for i in o.boq
                    if year < self.horizon_years and year % i.service_life_years == 0
                )
                replacements += renewal
                discounted += (opex + renewal) / (1 + self.discount_rate) ** year
            results.append(
                {
                    "source": o.source,
                    "assumptions": o.model_dump(),
                    "capex": capex,
                    "annual_opex": opex,
                    "replacement_total": replacements,
                    "undiscounted_cost": capex + replacements + opex * self.horizon_years,
                    "discounted_cost": discounted,
                }
            )
        base = next(r for r in results if r["source"] == self.baseline)
        for row in results:
            same = (
                row["assumptions"]["annual_delivered_m3"]
                == base["assumptions"]["annual_delivered_m3"]
            )
            incremental = row["capex"] - base["capex"]
            row["comparable_water_service"] = same
            row["incremental_roi_pct"] = (
                100 * (base["undiscounted_cost"] - row["undiscounted_cost"]) / incremental
                if same and incremental > 0
                else None
            )
            if row["incremental_roi_pct"] is not None and not math.isfinite(
                row["incremental_roi_pct"]
            ):
                row["incremental_roi_pct"] = None
        return {
            "currency": self.currency,
            "horizon_years": self.horizon_years,
            "discount_rate": self.discount_rate,
            "baseline": self.baseline,
            "basis": "quoted_scenario_constant_annual_service",
            "includes_terminal_salvage": False,
            "options": results,
        }


class FeasibilityRequest(BaseModel):
    area_ha: float
    yield_t_per_ha: float
    price_per_t: float
    costs: dict[str, float] | None = None
    total_cost: float | None = None
    water_cost_scenario: WaterCostScenario | None = None
    lifecycle_scenario: LifecycleScenario | None = None
