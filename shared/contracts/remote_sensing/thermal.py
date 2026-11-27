"""Unit carried by a field-scoped Landsat surface temperature observation."""

LANDSAT_ST_KELVIN = "sahool.landsat-c2-l2-st-k/1.0.0"


def observation_unit(indicator: str, algorithm: str | None) -> str | None:
    if indicator == "lst":
        return "K" if algorithm == LANDSAT_ST_KELVIN else None
    return "1"
