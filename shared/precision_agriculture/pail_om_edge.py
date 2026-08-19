"""PAIL/ISO-19156 observation semantics as an interchange projection.

PAIL Part 2 models observations and measurements for agriculture.  This module
projects a SAHOOL measurement into the small semantic subset we can prove from
our own state.  It is intentionally *not* an ISO 7673 conformance claim while
that international standard remains version-sensitive; canonical authority stays
with the originating SAHOOL measurement source.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

SAHOOL_PAIL_OM_MAPPING_VERSION = "sahool.pail-om-edge.v1"
REFERENCE_MODEL = "PAIL Part 2 / ANSI S632-2 (ISO 19156 agricultural observations semantics)"


@dataclass(frozen=True)
class PailObservationProjection:
    mapping_version: str
    reference_model: str
    observation: dict[str, Any]
    content_digest: str
    conformance_claim: bool = False


def project_observation(
    *,
    observation_id: str,
    property_code: str,
    feature_of_interest: str,
    value: float | int | str | bool,
    observed_at: str,
    unit: str | None = None,
    field_id: str | None = None,
    device_id: str | None = None,
    position: dict[str, float] | None = None,
    method_code: str | None = None,
    aggregation_code: str | None = None,
    quality_codes: list[str] | None = None,
    source_ref: str,
) -> PailObservationProjection:
    """Project one value/property/feature observation with explicit provenance.

    PAIL's core observation semantics are preserved: one value for one property on
    one feature of interest, with optional field/device/position context.  We do
    not synthesize missing units, timestamps, or source identity.
    """
    required = {
        "observation_id": observation_id,
        "property_code": property_code,
        "feature_of_interest": feature_of_interest,
        "observed_at": observed_at,
        "source_ref": source_ref,
    }
    missing = [key for key, raw in required.items() if not str(raw).strip()]
    if missing:
        raise ValueError(f"PAIL observation projection missing: {', '.join(missing)}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("observation value must be finite")
    if position is not None:
        lat = float(position.get("lat"))
        lon = float(position.get("lon"))
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise ValueError("observation position outside WGS84 bounds")
        position = {"lat": lat, "lon": lon}

    code_components = {
        "property": property_code,
        "feature_of_interest": feature_of_interest,
        "method": method_code,
        "aggregation": aggregation_code,
    }
    observation = {
        "id": observation_id,
        "time_scopes": [{"observed_at": observed_at}],
        "quality_codes": list(dict.fromkeys(quality_codes or [])),
        "field_id": field_id,
        "device_id": device_id,
        "position": position,
        "code": {key: val for key, val in code_components.items() if val},
        "value": value,
        "value_uom": unit,
        "source_ref": source_ref,
        "authority": "interchange_projection_only",
    }
    raw = json.dumps(
        observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return PailObservationProjection(
        mapping_version=SAHOOL_PAIL_OM_MAPPING_VERSION,
        reference_model=REFERENCE_MODEL,
        observation=observation,
        content_digest=hashlib.sha256(raw).hexdigest(),
    )


def import_observation_projection(
    projection: PailObservationProjection | dict[str, Any],
) -> dict[str, Any]:
    """Validate and round-trip the bounded PAIL/ISO-19156 observation projection."""
    if isinstance(projection, PailObservationProjection):
        mapping_version = projection.mapping_version
        reference_model = projection.reference_model
        observation = dict(projection.observation)
        claimed_digest = projection.content_digest
        conformance_claim = projection.conformance_claim
    elif isinstance(projection, dict):
        mapping_version = str(projection.get("mapping_version") or "")
        reference_model = str(projection.get("reference_model") or "")
        observation = dict(projection.get("observation") or {})
        claimed_digest = str(projection.get("content_digest") or "")
        conformance_claim = bool(projection.get("conformance_claim", False))
    else:
        raise ValueError("invalid PAIL observation projection")
    if mapping_version != SAHOOL_PAIL_OM_MAPPING_VERSION or reference_model != REFERENCE_MODEL:
        raise ValueError("unsupported PAIL observation mapping")
    if conformance_claim:
        raise ValueError("bounded PAIL projection cannot claim full standard conformance")
    if observation.get("authority") != "interchange_projection_only":
        raise ValueError("PAIL projection authority marker missing")
    required = ("id", "time_scopes", "code", "source_ref")
    missing = [key for key in required if not observation.get(key)]
    if missing:
        raise ValueError(f"PAIL observation projection missing: {', '.join(missing)}")
    raw = json.dumps(
        observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    actual_digest = hashlib.sha256(raw).hexdigest()
    if claimed_digest != actual_digest:
        raise ValueError("PAIL observation content_digest mismatch")
    scopes = observation["time_scopes"]
    if not isinstance(scopes, list) or len(scopes) != 1 or not scopes[0].get("observed_at"):
        raise ValueError("PAIL observation requires exactly one observed_at time scope")
    code = observation["code"]
    if (
        not isinstance(code, dict)
        or not code.get("property")
        or not code.get("feature_of_interest")
    ):
        raise ValueError("PAIL observation code requires property and feature_of_interest")
    return {
        "observation_id": str(observation["id"]),
        "property_code": str(code["property"]),
        "feature_of_interest": str(code["feature_of_interest"]),
        "value": observation.get("value"),
        "observed_at": str(scopes[0]["observed_at"]),
        "unit": observation.get("value_uom"),
        "field_id": observation.get("field_id"),
        "device_id": observation.get("device_id"),
        "position": observation.get("position"),
        "method_code": code.get("method"),
        "aggregation_code": code.get("aggregation"),
        "quality_codes": list(observation.get("quality_codes") or []),
        "source_ref": str(observation["source_ref"]),
        "authority": "interchange_roundtrip_only",
    }
