"""Canonical field-state contract shared by intelligence consumers.

This module validates, fingerprints and combines owner-produced state products.  It
never computes weather, water, soil or spectral facts and never accepts an
unversioned dictionary as canonical truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_field_state.v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _schema_of(value: dict[str, Any]) -> str | None:
    return value.get("schema_version") or value.get("schema")


def _require_product(
    name: str, value: dict[str, Any] | None, accepted_prefixes: tuple[str, ...]
) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, f"{name}_missing"
    if not isinstance(value, dict):
        return None, f"{name}_not_object"
    schema = _schema_of(value)
    if not isinstance(schema, str) or not schema.startswith(accepted_prefixes):
        return None, f"{name}_noncanonical_schema"
    return value, None


@dataclass(frozen=True)
class CanonicalFieldState:
    schema_version: str
    field_id: str
    season_id: str | None
    as_of_time: str
    weather: dict[str, Any] | None
    water: dict[str, Any] | None
    soil: dict[str, Any] | None
    spectral: dict[str, Any] | None
    availability: dict[str, bool]
    limitations: list[str]
    evidence_digests: dict[str, str]
    state_digest: str
    operational_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compose_canonical_field_state(
    *,
    field_id: str,
    season_id: str | None,
    as_of_time: str,
    weather: dict[str, Any] | None = None,
    water: dict[str, Any] | None = None,
    soil: dict[str, Any] | None = None,
    spectral: dict[str, Any] | None = None,
    required: tuple[str, ...] = ("weather", "water", "soil"),
) -> CanonicalFieldState:
    if not field_id or not as_of_time:
        raise ValueError("field_id and as_of_time are required")
    specs = {
        "weather": (weather, ("wx10/canonical-weather-state/", "canonical_weather_state")),
        "water": (water, ("canonical_water_state.",)),
        "soil": (soil, ("canonical_soil_state.", "soil-profile.")),
        "spectral": (spectral, ("canonical_spectral_state.", "validated-raster-product.")),
    }
    accepted: dict[str, dict[str, Any] | None] = {}
    limitations: list[str] = []
    availability: dict[str, bool] = {}
    evidence: dict[str, str] = {}
    for name, (value, prefixes) in specs.items():
        product, limitation = _require_product(name, value, prefixes)
        accepted[name] = product
        availability[name] = product is not None
        if limitation:
            limitations.append(limitation)
        elif product is not None:
            evidence[name] = _digest(product)
    missing_required = [name for name in required if not availability.get(name, False)]
    limitations.extend(f"required_{name}_unavailable" for name in missing_required)
    body = {
        "schema_version": SCHEMA_VERSION,
        "field_id": field_id,
        "season_id": season_id,
        "as_of_time": as_of_time,
        **accepted,
        "availability": availability,
        "limitations": list(dict.fromkeys(limitations)),
        "evidence_digests": evidence,
    }
    digest = _digest(body)
    return CanonicalFieldState(
        **body, state_digest=digest, operational_eligible=not missing_required
    )
