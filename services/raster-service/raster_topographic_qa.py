"""Topographic QA helpers for raster indicator preprocessing.

This module does not fabricate terrain masks. It only reports topographic risk
when real DEM-derived or source-native topographic inputs are supplied. When a
DEM and sun geometry are available, it can compute a conservative hillshade-
based terrain shade risk and slope risk on the indicator grid.
"""

from __future__ import annotations

import math
from typing import Any


def _clamp_pct(value: float | int | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    return max(0.0, min(100.0, float(value)))


def compute_cast_shadow_mask_from_dem(
    dem,
    *,
    pixel_size_m: float,
    sun_azimuth_deg: float,
    sun_altitude_deg: float,
    max_steps: int = 64,
    step_pixels: int = 1,
):
    """Return a conservative cast-shadow mask from an aligned DEM array.

    This is a bounded horizon ray-march along the up-sun direction. For each
    valid DEM pixel, nearby up-sun cells are checked; if an up-sun terrain cell
    rises above the solar altitude line, the pixel is flagged as cast-shadow
    risk. It is intentionally bounded (``max_steps`` and ``step_pixels``) so it
    is safe for indicator preprocessing and CI tests. It is a QA risk mask, not
    a photogrammetric replacement for a full radiative transfer model.
    """

    import numpy as np

    arr = np.asarray(dem, dtype="float32")
    valid = np.isfinite(arr)
    sun_ok = (
        sun_azimuth_deg is not None
        and sun_altitude_deg is not None
        and float(sun_altitude_deg) > 0.0
    )
    if arr.ndim != 2 or arr.size == 0 or not bool(valid.any()) or not sun_ok:
        return {
            "mask": np.zeros(arr.shape if arr.ndim == 2 else (0, 0), dtype=bool),
            "cast_shadow_risk_pct": None,
            "cast_shadow_available": False,
            "cast_shadow_max_steps": int(max_steps),
            "cast_shadow_step_pixels": int(step_pixels),
            "warnings": ["cast_shadow_inputs_unavailable"],
        }

    px = max(float(pixel_size_m or 0.0), 1e-6)
    max_steps = max(1, min(int(max_steps), 512))
    step_pixels = max(1, min(int(step_pixels), 16))
    altitude_tan = math.tan(math.radians(float(sun_altitude_deg)))
    # Azimuth is degrees clockwise from north. In image coordinates: row grows
    # south/down, col grows east/right. Up-sun direction points toward the sun.
    az = math.radians(float(sun_azimuth_deg))
    row_unit = -math.cos(az)
    col_unit = math.sin(az)

    h, w = arr.shape
    shadow = np.zeros((h, w), dtype=bool)

    def shifted_up_sun(values, row_offset: int, col_offset: int):
        shifted = np.full_like(values, np.nan, dtype="float32")
        src_r0 = max(0, -row_offset)
        src_r1 = min(h, h - row_offset)
        dst_r0 = max(0, row_offset)
        dst_r1 = min(h, h + row_offset)
        src_c0 = max(0, -col_offset)
        src_c1 = min(w, w - col_offset)
        dst_c0 = max(0, col_offset)
        dst_c1 = min(w, w + col_offset)
        if src_r1 > src_r0 and src_c1 > src_c0 and dst_r1 > dst_r0 and dst_c1 > dst_c0:
            shifted[dst_r0:dst_r1, dst_c0:dst_c1] = values[src_r0:src_r1, src_c0:src_c1]
        return shifted

    seen_offsets: set[tuple[int, int]] = set()
    for step in range(step_pixels, max_steps + 1, step_pixels):
        dr = int(round(row_unit * step))
        dc = int(round(col_unit * step))
        if (dr, dc) == (0, 0) or (dr, dc) in seen_offsets:
            continue
        seen_offsets.add((dr, dc))
        blocker = shifted_up_sun(arr, dr, dc)
        distance_m = math.hypot(dr, dc) * px
        if distance_m <= 0:
            continue
        required_blocker_height = arr + altitude_tan * distance_m
        step_shadow = np.isfinite(blocker) & valid & (blocker > required_blocker_height)
        shadow |= step_shadow

    cast_shadow_risk_pct = float(np.mean(shadow & valid) * 100.0)
    warnings: list[str] = []
    if max_steps < 32:
        warnings.append("cast_shadow_horizon_limited")
    return {
        "mask": shadow,
        "cast_shadow_risk_pct": _clamp_pct(cast_shadow_risk_pct),
        "cast_shadow_available": True,
        "cast_shadow_max_steps": max_steps,
        "cast_shadow_step_pixels": step_pixels,
        "warnings": warnings,
    }


def compute_topographic_risk_from_dem(
    dem,
    *,
    pixel_size_m: float,
    sun_azimuth_deg: float | None = None,
    sun_altitude_deg: float | None = None,
    slope_risk_threshold_pct: float = 12.0,
    shadow_hillshade_threshold: float = 0.12,
    cast_shadow_enabled: bool = True,
    cast_shadow_max_steps: int = 64,
) -> dict[str, Any]:
    """Compute conservative topographic risk percentages from a DEM array.

    This is a local-terrain QA metric, not a full cast-shadow ray tracing model.
    It estimates:
    - ``slope_risk_pct``: valid DEM pixels with slope >= threshold.
    - ``terrain_shadow_risk_pct``: valid DEM pixels whose hillshade is below a
      low illumination threshold, only when sun azimuth/altitude are supplied.

    The function is intentionally pure and deterministic so it can be tested
    without a live raster service.
    """

    import numpy as np

    arr = np.asarray(dem, dtype="float32")
    valid = np.isfinite(arr)
    if arr.ndim != 2 or arr.size == 0 or not bool(valid.any()):
        return {
            "terrain_shadow_risk_pct": None,
            "slope_risk_pct": None,
            "hillshade_available": False,
            "sun_geometry_available": bool(
                sun_azimuth_deg is not None and sun_altitude_deg is not None
            ),
            "valid_dem_pixel_ratio": 0.0,
            "warnings": ["dem_array_empty_or_invalid"],
        }

    px = max(float(pixel_size_m or 0.0), 1e-6)
    dzdx = np.gradient(arr, px, axis=1)
    dzdy = np.gradient(arr, px, axis=0)
    grad = np.sqrt(dzdx**2 + dzdy**2)
    slope_pct = 100.0 * grad
    slope_risk_pct = float(
        np.nanmean((slope_pct >= float(slope_risk_threshold_pct)) & valid) * 100.0
    )

    sun_ok = (
        sun_azimuth_deg is not None
        and sun_altitude_deg is not None
        and float(sun_altitude_deg) > 0.0
    )
    terrain_shadow_risk_pct: float | None = None
    hillshade_available = False
    warnings: list[str] = []
    if sun_ok:
        slope_rad = np.arctan(grad)
        aspect = np.arctan2(dzdy, -dzdx)
        zenith = math.radians(90.0 - float(sun_altitude_deg))
        az_math = math.radians((360.0 - float(sun_azimuth_deg) + 90.0) % 360.0)
        hillshade = np.cos(zenith) * np.cos(slope_rad) + np.sin(zenith) * np.sin(
            slope_rad
        ) * np.cos(az_math - aspect)
        hillshade = np.clip(hillshade, 0.0, 1.0)
        terrain_shadow_risk_pct = float(
            np.nanmean((hillshade <= float(shadow_hillshade_threshold)) & valid) * 100.0
        )
        hillshade_available = True
    else:
        warnings.append("sun_geometry_unavailable_for_terrain_shadow_model")

    cast_shadow_available = False
    cast_shadow_risk_pct = None
    cast_shadow_max_steps_used = None
    if cast_shadow_enabled and sun_ok:
        cast = compute_cast_shadow_mask_from_dem(
            arr,
            pixel_size_m=px,
            sun_azimuth_deg=sun_azimuth_deg,
            sun_altitude_deg=sun_altitude_deg,
            max_steps=cast_shadow_max_steps,
        )
        cast_shadow_available = bool(cast.get("cast_shadow_available"))
        cast_shadow_risk_pct = cast.get("cast_shadow_risk_pct")
        cast_shadow_max_steps_used = cast.get("cast_shadow_max_steps")
        for warning in cast.get("warnings") or []:
            if warning not in warnings:
                warnings.append(warning)
        if cast_shadow_risk_pct is not None:
            # Use the stricter of local hillshade risk and cast-shadow horizon risk.
            terrain_shadow_risk_pct = max(
                float(terrain_shadow_risk_pct or 0.0), float(cast_shadow_risk_pct)
            )

    valid_ratio = float(np.mean(valid)) if valid.size else 0.0
    return {
        "terrain_shadow_risk_pct": _clamp_pct(terrain_shadow_risk_pct),
        "cast_shadow_risk_pct": _clamp_pct(cast_shadow_risk_pct),
        "slope_risk_pct": _clamp_pct(slope_risk_pct),
        "hillshade_available": hillshade_available,
        "cast_shadow_available": cast_shadow_available,
        "sun_geometry_available": bool(sun_ok),
        "valid_dem_pixel_ratio": valid_ratio,
        "slope_risk_threshold_pct": float(slope_risk_threshold_pct),
        "shadow_hillshade_threshold": float(shadow_hillshade_threshold),
        "cast_shadow_max_steps": cast_shadow_max_steps_used,
        "warnings": warnings,
    }


def build_topographic_qa(
    *,
    dem_configured: bool = False,
    dem_aligned: bool = False,
    terrain_shadow_risk_pct: float | None = None,
    cast_shadow_risk_pct: float | None = None,
    slope_risk_pct: float | None = None,
    hillshade_available: bool = False,
    cast_shadow_available: bool = False,
    sun_geometry_available: bool = False,
    sources: list[str] | None = None,
    valid_dem_pixel_ratio: float | None = None,
    slope_risk_threshold_pct: float | None = None,
    shadow_hillshade_threshold: float | None = None,
    cast_shadow_max_steps: int | None = None,
    method: str | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Return a conservative topographic QA envelope for indicator provenance.

    ``terrain_shadow_risk_pct`` and ``slope_risk_pct`` must come from DEM or
    source-native QA. If absent, the result is explicitly unavailable rather than
    guessed from imagery values.
    """

    sources = list(sources or [])
    terrain_shadow_risk_pct = _clamp_pct(terrain_shadow_risk_pct)
    cast_shadow_risk_pct = _clamp_pct(cast_shadow_risk_pct)
    slope_risk_pct = _clamp_pct(slope_risk_pct)
    available = bool(
        dem_configured
        and dem_aligned
        and (terrain_shadow_risk_pct is not None or slope_risk_pct is not None)
    )
    warnings: list[str] = []
    if not dem_configured:
        warnings.append("dem_not_configured_for_topographic_qa")
    elif not dem_aligned:
        warnings.append("dem_not_aligned_to_indicator_grid")
    if not sun_geometry_available:
        warnings.append("sun_geometry_unavailable_for_terrain_shadow_model")
    if terrain_shadow_risk_pct is None:
        warnings.append("terrain_shadow_risk_unavailable")
    if slope_risk_pct is None:
        warnings.append("slope_risk_unavailable")
    for warning in extra_warnings or []:
        if warning not in warnings:
            warnings.append(warning)

    return {
        "schema": "sahool.raster_topographic_qa/1",
        "available": available,
        "dem_configured": bool(dem_configured),
        "dem_aligned": bool(dem_aligned),
        "hillshade_available": bool(hillshade_available),
        "cast_shadow_available": bool(cast_shadow_available),
        "sun_geometry_available": bool(sun_geometry_available),
        "terrain_shadow_risk_pct": terrain_shadow_risk_pct,
        "cast_shadow_risk_pct": cast_shadow_risk_pct,
        "slope_risk_pct": slope_risk_pct,
        "topographic_qa_applied": available,
        "sources": sources,
        "method": method or ("dem_hillshade_slope" if available else "unavailable"),
        "valid_dem_pixel_ratio": valid_dem_pixel_ratio,
        "slope_risk_threshold_pct": slope_risk_threshold_pct,
        "shadow_hillshade_threshold": shadow_hillshade_threshold,
        "cast_shadow_max_steps": cast_shadow_max_steps,
        "warnings": warnings,
        "fabricated_topographic_mask": False,
    }


def build_topographic_qa_from_dem_array(
    dem,
    *,
    pixel_size_m: float,
    sun_azimuth_deg: float | None = None,
    sun_altitude_deg: float | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Build a topographic QA envelope from an already-aligned DEM array."""

    risk = compute_topographic_risk_from_dem(
        dem,
        pixel_size_m=pixel_size_m,
        sun_azimuth_deg=sun_azimuth_deg,
        sun_altitude_deg=sun_altitude_deg,
    )
    return build_topographic_qa(
        dem_configured=True,
        dem_aligned=True,
        terrain_shadow_risk_pct=risk.get("terrain_shadow_risk_pct"),
        cast_shadow_risk_pct=risk.get("cast_shadow_risk_pct"),
        slope_risk_pct=risk.get("slope_risk_pct"),
        hillshade_available=bool(risk.get("hillshade_available")),
        cast_shadow_available=bool(risk.get("cast_shadow_available")),
        sun_geometry_available=bool(risk.get("sun_geometry_available")),
        sources=list(sources or ["aligned_dem_array"]),
        valid_dem_pixel_ratio=risk.get("valid_dem_pixel_ratio"),
        slope_risk_threshold_pct=risk.get("slope_risk_threshold_pct"),
        shadow_hillshade_threshold=risk.get("shadow_hillshade_threshold"),
        cast_shadow_max_steps=risk.get("cast_shadow_max_steps"),
        method="dem_cast_shadow_hillshade_slope"
        if risk.get("cast_shadow_available")
        else "dem_hillshade_slope",
        extra_warnings=list(risk.get("warnings") or []),
    )
