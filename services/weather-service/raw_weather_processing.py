"""Raw weather-data QA/provenance processing.

This module intentionally does not calculate agricultural operation decisions or
invent weather values. It wraps upstream Open-Meteo payloads with bounded raw
metadata, numeric summaries, and provenance flags so clients can inspect the raw
weather feed before downstream rules derive operation windows or map layers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

RawWeatherSource = Literal["current", "forecast", "historical", "tile_sample"]


class RawWeatherProcessRequest(BaseModel):
    """Request for bounded raw weather payload QA."""

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    source_kind: RawWeatherSource = "current"
    model: str = Field(default="best_match", min_length=1, max_length=64)
    days: int = Field(default=7, ge=1, le=16)
    start_date: str | None = None
    end_date: str | None = None
    time: str = Field(default="now", min_length=1, max_length=64)
    include_payload: bool = False
    max_items: int = Field(default=240, ge=1, le=2000)

    @field_validator("model")
    @classmethod
    def _clean_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model cannot be empty")
        return cleaned

    @model_validator(mode="after")
    def _historical_dates_required(self) -> RawWeatherProcessRequest:
        if self.source_kind == "historical" and (not self.start_date or not self.end_date):
            raise ValueError("start_date and end_date are required for historical raw weather")
        # Fail early on malformed ISO dates while keeping response logic simple.
        for attr in ("start_date", "end_date"):
            value = getattr(self, attr)
            if value:
                date.fromisoformat(value)
        return self


class RawWeatherProcessResponse(BaseModel):
    service: str = "weather-service"
    source_kind: RawWeatherSource
    location: dict[str, float]
    model: str
    source: str | None
    raw_observation_count: int
    numeric_field_count: int
    numeric_summary: dict[str, dict[str, float | int | None]]
    top_level_keys: list[str]
    provenance: dict[str, Any]
    data_quality: dict[str, Any]
    flags: dict[str, bool]
    raw_payload: dict[str, Any] | None = None


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _walk_numeric(payload: Any, prefix: str = "", *, limit: int = 2000) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}

    def visit(node: Any, name: str, budget: list[int]) -> None:
        if budget[0] <= 0:
            return
        budget[0] -= 1
        if _is_number(node):
            values.setdefault(name or "value", []).append(float(node))
            return
        if isinstance(node, Mapping):
            for key, child in node.items():
                child_name = f"{name}.{key}" if name else str(key)
                visit(child, child_name, budget)
            return
        if isinstance(node, Sequence) and not isinstance(node, str | bytes | bytearray):
            for item in node[:limit] if isinstance(node, list) else list(node)[:limit]:
                visit(item, name, budget)

    visit(payload, prefix, [limit])
    return values


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = (len(sorted_values) - 1) * pct
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def summarize_numeric_fields(
    payload: dict[str, Any], *, max_items: int = 240
) -> dict[str, dict[str, float | int | None]]:
    numeric = _walk_numeric(payload, limit=max_items)
    summary: dict[str, dict[str, float | int | None]] = {}
    for name, values in sorted(numeric.items()):
        clipped = values[:max_items]
        ordered = sorted(clipped)
        summary[name] = {
            "count": len(clipped),
            "min": ordered[0] if ordered else None,
            "max": ordered[-1] if ordered else None,
            "mean": sum(ordered) / len(ordered) if ordered else None,
            "p02": _percentile(ordered, 0.02),
            "p50": _percentile(ordered, 0.50),
            "p98": _percentile(ordered, 0.98),
        }
    return summary


def count_raw_observations(payload: dict[str, Any]) -> int:
    for key in ("days", "hours", "hourly", "frames", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 1 if payload else 0


def build_raw_weather_response(
    request: RawWeatherProcessRequest,
    payload: dict[str, Any],
) -> RawWeatherProcessResponse:
    numeric_summary = summarize_numeric_fields(payload, max_items=request.max_items)
    source = payload.get("source") if isinstance(payload, dict) else None
    raw_observation_count = count_raw_observations(payload)
    top_level_keys = sorted(str(k) for k in payload.keys())
    return RawWeatherProcessResponse(
        source_kind=request.source_kind,
        location={"lat": request.lat, "lon": request.lon},
        model=request.model,
        source=str(source) if source is not None else None,
        raw_observation_count=raw_observation_count,
        numeric_field_count=len(numeric_summary),
        numeric_summary=numeric_summary,
        top_level_keys=top_level_keys,
        provenance={
            "provider": source or "open-meteo",
            "source_kind": request.source_kind,
            "model": request.model,
            "bounded_max_items": request.max_items,
            "raw_payload_included": request.include_payload,
        },
        data_quality={
            "has_payload": bool(payload),
            "has_numeric_values": bool(numeric_summary),
            "observation_count": raw_observation_count,
            "truncated_numeric_walk": request.max_items <= 240,
        },
        flags={
            "fabricated_weather": False,
            "operation_window_computed": False,
            "indicator_computed": False,
            "raw_data_processing": True,
        },
        raw_payload=payload if request.include_payload else None,
    )
