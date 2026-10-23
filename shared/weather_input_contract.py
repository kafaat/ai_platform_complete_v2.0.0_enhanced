"""Shared JSON-safe number contract for weather-service and BFF ET0 inputs.

No framework dependencies: direct callers receive a Pydantic ValidationError.
Strict field annotations still own bool/string/type checks; physical bounds and
ET0 selection remain the weather-service's responsibility.
"""

from __future__ import annotations

import math
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError, model_validator

# Numeric JSON values only: real integer/float zero is accepted; bool and text
# are not observations. Bounds and scientific completeness remain owner policy.
Et0Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]

_WEATHER_FIELDS = frozenset(
    {
        "t_min_c",
        "t_max_c",
        "solar_rad_mj_m2",
        "rh_mean_pct",
        "wind_2m_ms",
        "t_mean_c",
        "lat_deg",
        "latitude_deg",
        "elevation_m",
        "day_of_year",
        "day_of_year_start",
        "daily_t_min",
        "daily_t_max",
        "daily_solar_rad_mj_m2",
        "daily_rh_mean_pct",
        "daily_wind_2m_ms",
    }
)


class Et0WeatherInput(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def reject_nonfinite_weather_values(cls, data):
        # Python's JSON decoder accepts NaN/Infinity. A standard validation
        # error retaining those float inputs cannot itself be serialized by
        # FastAPI, so reject with field locations and safe textual evidence.
        if isinstance(data, dict):
            errors = []

            def inspect(value, location):
                if isinstance(value, list):
                    for index, item in enumerate(value):
                        inspect(item, (*location, index))
                elif isinstance(value, float) and not math.isfinite(value):
                    errors.append({"type": "finite_number", "loc": location, "input": repr(value)})

            for name, value in data.items():
                if name in _WEATHER_FIELDS and name in cls.model_fields:
                    inspect(value, (name,))
            if errors:
                raise ValidationError.from_exception_data(cls.__name__, errors)
        return data
