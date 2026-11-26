"""api/feasibility_models.py — نماذج الجدوى الاقتصاديّة (Feasibility)
==================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): نموذج طلب الجدوى الاقتصاديّة
مُستخرَج حرفيّاً ليُستورَد من ``api/routers/economics.py``.

النموذج مكتفٍ ذاتيّاً (pydantic فقط) — لا يعتمد على رموز ``api.main`` الخاصّة.
"""

from __future__ import annotations

from typing import Literal

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
    solar_m3_per_year: float | None = Field(default=None, gt=0)
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


class FeasibilityRequest(BaseModel):
    area_ha: float
    yield_t_per_ha: float
    price_per_t: float
    costs: dict[str, float] | None = None
    total_cost: float | None = None
    water_cost_scenario: WaterCostScenario | None = None
