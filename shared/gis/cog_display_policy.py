"""Display-only scalar COG policy; never infer science from tile-local statistics."""

from __future__ import annotations

import math
import re

from fastapi import HTTPException

DISPLAY_POLICY_VERSION = "scalar-cog-v1"
# These normalized differences have a common dimensionless range. EVI, MSI,
# thermal and categorical products deliberately do not inherit an NDVI scale.
NORMALIZED_DIFFERENCES = frozenset({"ndvi", "ndmi", "ndwi", "gndvi"})


def validate_rescale(value: str) -> str:
    """Accept the existing two-decimal-number API, with finite ordered bounds."""
    if len(value) > 96 or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?,-?[0-9]+(?:\.[0-9]+)?", value):
        raise HTTPException(422, "invalid_tile_rescale")
    lower, upper = map(float, value.split(","))
    if not (math.isfinite(lower) and math.isfinite(upper) and lower < upper):
        raise HTTPException(422, "invalid_tile_rescale")
    return value


def display_for_cog(index: str | None, rescale: str | None = None) -> dict:
    """Resolve a reproducible default or a declared caller override, never a guess.

    There is no trusted persisted display-statistics producer in the current
    registry. Arbitrary metadata min/max therefore cannot establish a default.
    Unknown products require an explicit range until that contract exists.
    """
    normalized_index = str(index or "").lower()
    if normalized_index == "truecolor":
        return {
            "policy": DISPLAY_POLICY_VERSION,
            "mode": "rgba",
            "rescale": validate_rescale(rescale) if rescale is not None else None,
            "source": "explicit_request" if rescale is not None else "encoded_channels",
            "units": None,
            "clips_display_only": rescale is not None,
        }
    known = normalized_index in NORMALIZED_DIFFERENCES
    if rescale is None:
        if not known:
            raise HTTPException(422, "tile_display_range_required")
        rescale, source = "-1,1", "normalized_difference"
    else:
        rescale, source = validate_rescale(rescale), "explicit_request"
    return {
        "policy": DISPLAY_POLICY_VERSION,
        "mode": "scalar",
        "rescale": rescale,
        "source": source,
        "units": "dimensionless" if known else None,
        "clips_display_only": True,
    }
