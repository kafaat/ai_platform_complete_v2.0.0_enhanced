"""levelling_design.py — bounded cut/fill levelling DESIGN PROPOSAL on a supplied elevation grid.

Scope and honesty rules:
- Input is a caller-supplied elevation grid; nothing is read from a DEM here and nothing is
  invented. Missing CRS, vertical datum, cell size, polygon or valid coverage => refusal
  (``computed: False`` with a ``source`` code), the same envelope as ``terrain_analysis``.
- CRS must be projected with metre units (volumes from degrees are meaningless).
- Polygon exterior/holes use cell-centre even-odd tests in the grid CRS; holes are not field area.
- nodata / NaN cells are excluded and reported, never treated as zero elevation.
- Output is never construction authority: ``execution_authorized`` is always False.
- RTK points are evidence only (checked against the grid); they never change the design.
- Costs: quantities always; money only when the caller supplies unit prices (no defaults).
Not modelled (declared gaps): haul distance / mass-haul, swell vs shrink split by soil layer,
drainage-grade validation, compaction of topsoil, rounding of cell-centre sampling error.
"""

from __future__ import annotations

import math

MAX_CELLS = 1_000_000
MIN_VALID_COVERAGE = 0.95
MAX_SLOPE_PCT = 5.0
MAX_TOPSOIL_M = 1.0
MAX_SHRINK = 2.0
RTK_MIN_FIXED = 5
RTK_RMSE_TOL_M = 0.10
_NOT_FOR_CONSTRUCTION = "design_proposal_not_for_construction"


def _refuse(code: str, reason: str) -> dict:
    return {
        "computed": False,
        "source": code,
        "reason": reason,
        "execution_authorized": False,
    }


def _num(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _ring(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    out = []
    for p in raw:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        x, y = _num(p[0]), _num(p[1])
        if x is None or y is None:
            return None
        out.append((x, y))
    return out


def _inside(np, ring, px, py):
    """Even-odd point-in-ring for arrays of points."""
    inside = np.zeros(px.shape, dtype=bool)
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if y1 == y2:
            continue
        cond = (y1 > py) != (y2 > py)
        xint = (x2 - x1) * (py - y1) / (y2 - y1) + x1
        inside ^= cond & (px < xint)
    return inside


def _crs_ok(epsg) -> str | None:
    if isinstance(epsg, bool) or not isinstance(epsg, int):
        return "crs-missing"
    try:
        from rasterio.crs import CRS

        crs = CRS.from_epsg(epsg)
        if not crs.is_projected:
            return "crs-not-projected-metric"
        units = crs.linear_units_factor
        if abs(units[1] - 1.0) > 1e-9:
            return "crs-not-projected-metric"
    except Exception:  # noqa: BLE001 - unknown EPSG is a refusal, not a guess
        return "crs-not-projected-metric"
    return None


def _validate_design(d):
    if not isinstance(d, dict):
        return None
    mode = d.get("mode")
    shrink = d.get("shrink_factor", 1.0)
    shrink = _num(shrink)
    if mode not in ("flat", "plane") or shrink is None or not 1.0 <= shrink <= MAX_SHRINK:
        return None
    sx = _num(d.get("slope_x_pct", 0.0)) if mode == "plane" else 0.0
    sy = _num(d.get("slope_y_pct", 0.0)) if mode == "plane" else 0.0
    if sx is None or sy is None or abs(sx) > MAX_SLOPE_PCT or abs(sy) > MAX_SLOPE_PCT:
        return None
    return mode, shrink, sx / 100.0, sy / 100.0


def _rtk_evidence(np, pts, datum, cell, origin, shape, z, valid, ring_sets):
    ev = {
        "points": 0,
        "fixed_points": 0,
        "outside_field": 0,
        "rmse_m": None,
        "max_abs_residual_m": None,
        "rmse_tolerance_m": RTK_RMSE_TOL_M,
        "min_fixed_points": RTK_MIN_FIXED,
    }
    if pts is None:
        return ev, "dem_only_indicative", None
    if not isinstance(pts, list):
        return None, None, _refuse("rtk-invalid", "rtk_points must be a list")
    resid = []
    ev["points"] = len(pts)
    for p in pts:
        if not isinstance(p, dict):
            return None, None, _refuse("rtk-invalid", "rtk point must be an object")
        x, y, pz = _num(p.get("x")), _num(p.get("y")), _num(p.get("z"))
        if x is None or y is None or pz is None:
            return None, None, _refuse("rtk-invalid", "rtk point needs finite x, y, z")
        if p.get("vertical_datum") != datum:
            return (
                None,
                None,
                _refuse("rtk-datum-mismatch", "RTK vertical datum differs from the grid datum"),
            )
        col = int(math.floor((x - origin[0]) / cell[0]))
        row = int(math.floor((origin[1] - y) / cell[1]))
        if not (0 <= row < shape[0] and 0 <= col < shape[1]) or not valid[row, col]:
            ev["outside_field"] += 1
            continue
        if p.get("fix") != "fixed":
            continue
        ev["fixed_points"] += 1
        resid.append(pz - float(z[row, col]))
    if resid:
        r = np.array(resid)
        ev["rmse_m"] = float(np.sqrt(np.mean(r**2)))
        ev["max_abs_residual_m"] = float(np.max(np.abs(r)))
    if ev["fixed_points"] < RTK_MIN_FIXED:
        return ev, "dem_only_indicative", None
    if ev["rmse_m"] <= RTK_RMSE_TOL_M:
        return ev, "rtk_checked", None
    return ev, "rtk_disagrees_with_dem", None


def compute_levelling_design(req: dict) -> dict:
    """Cut/fill design proposal. See module docstring; returns result or refusal envelope."""
    try:
        import numpy as np
    except ImportError:
        return _refuse("runtime-libs-missing", "numpy unavailable")
    if not isinstance(req, dict):
        return _refuse("request-invalid", "request must be an object")

    epsg = req.get("crs_epsg")
    bad = _crs_ok(epsg)
    if bad:
        return _refuse(bad, "explicit projected metre CRS (EPSG) is required")
    datum = req.get("vertical_datum")
    if not isinstance(datum, str) or not datum.strip():
        return _refuse("vertical-datum-missing", "explicit vertical datum is required")

    cs = req.get("cell_size_m")
    if (
        not isinstance(cs, (list, tuple))
        or len(cs) != 2
        or any(_num(v) is None or _num(v) <= 0 for v in cs)
    ):
        return _refuse("cell-size-invalid", "cell_size_m must be [dx, dy] metres > 0")
    cell = (float(cs[0]), float(cs[1]))
    org = req.get("origin_xy")
    if not isinstance(org, (list, tuple)) or len(org) != 2 or any(_num(v) is None for v in org):
        return _refuse("origin-invalid", "origin_xy must be [x_min, y_max] of the grid")
    origin = (float(org[0]), float(org[1]))

    grid = req.get("elevation_m")
    if (
        not isinstance(grid, (list, tuple))
        or not grid
        or not all(isinstance(r, (list, tuple)) and len(r) == len(grid[0]) and r for r in grid)
    ):
        return _refuse("elevation-grid-invalid", "elevation_m must be a non-empty rectangle")
    rows, cols = len(grid), len(grid[0])
    if rows * cols > MAX_CELLS:
        return _refuse("grid-too-large", f"grid exceeds {MAX_CELLS} cells")
    try:
        z = np.array(grid, dtype="float64")
    except (TypeError, ValueError):
        return _refuse("elevation-grid-invalid", "elevation_m must be numeric")
    nodata = req.get("nodata")
    nd = _num(nodata) if nodata is not None else None
    if nodata is not None and nd is None:
        return _refuse("elevation-grid-invalid", "nodata must be a finite number or null")
    if nd is None and np.isinf(z).any():
        return _refuse("elevation-grid-invalid", "infinite elevation without a nodata value")
    nodata_mask = ~np.isfinite(z)
    if nd is not None:
        nodata_mask |= z == nd

    poly = req.get("polygon")
    ext = _ring(poly.get("exterior")) if isinstance(poly, dict) else None
    if ext is None:
        return _refuse("polygon-invalid", "polygon.exterior needs >= 4 finite [x, y] points")
    holes = []
    for h in (poly.get("holes") or []) if isinstance(poly, dict) else []:
        hr = _ring(h)
        if hr is None:
            return _refuse("polygon-invalid", "a polygon hole is malformed")
        holes.append(hr)

    design = _validate_design(req.get("design"))
    if design is None:
        return _refuse(
            "design-invalid",
            f"design: mode flat|plane, shrink_factor in [1,{MAX_SHRINK}], |slope| <= {MAX_SLOPE_PCT}%",
        )
    mode, shrink, sx, sy = design

    topsoil = req.get("topsoil")
    strip = 0.0
    if topsoil is not None:
        strip = _num(topsoil.get("strip_depth_m")) if isinstance(topsoil, dict) else None
        if strip is None or not 0.0 <= strip <= MAX_TOPSOIL_M:
            return _refuse("topsoil-invalid", f"strip_depth_m must be in [0, {MAX_TOPSOIL_M}] m")

    prices = req.get("unit_prices")
    if prices is not None:
        ok = (
            isinstance(prices, dict)
            and isinstance(prices.get("currency"), str)
            and prices["currency"]
        )
        if ok:
            for k in ("earthwork_per_m3", "topsoil_handling_per_m3"):
                if k in prices and (_num(prices[k]) is None or _num(prices[k]) < 0):
                    ok = False
            ok = ok and any(k in prices for k in ("earthwork_per_m3", "topsoil_handling_per_m3"))
        if not ok:
            return _refuse("unit-prices-invalid", "currency and non-negative unit prices required")

    # Cell centres in the grid CRS.
    cx = origin[0] + (np.arange(cols) + 0.5) * cell[0]
    cy = origin[1] - (np.arange(rows) + 0.5) * cell[1]
    px, py = np.meshgrid(cx, cy)
    in_field = _inside(np, ext, px, py)
    for h in holes:
        in_field &= ~_inside(np, h, px, py)
    if not in_field.any():
        return _refuse("polygon-outside-grid", "no grid cell centre lies inside the field")
    valid = in_field & ~nodata_mask
    n_field, n_valid = int(in_field.sum()), int(valid.sum())
    coverage = n_valid / n_field
    if coverage < MIN_VALID_COVERAGE:
        return _refuse(
            "insufficient-valid-coverage",
            f"valid elevation covers {coverage:.1%} of the field, need {MIN_VALID_COVERAGE:.0%}",
        )

    cell_area = cell[0] * cell[1]
    ez = z[valid]
    xc, yc = float(px[valid].mean()), float(py[valid].mean())
    # Plane rises toward +x (east) and +y (north) with positive slopes.
    tilt = sx * (px[valid] - xc) + sy * (py[valid] - yc)

    def net(z0: float) -> float:
        d = (z0 + tilt) - ez
        return float(np.maximum(-d, 0).sum() - shrink * np.maximum(d, 0).sum())

    # Raising z0 lowers cut and raises fill: net (cut - shrink*fill) decreases monotonically.
    lo, hi = float(ez.min() - tilt.max()) - 1.0, float(ez.max() - tilt.min()) + 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if net(mid) > 0:
            lo = mid
        else:
            hi = mid
    z0 = (lo + hi) / 2
    target = z0 + tilt
    d = target - ez
    cut_m3 = float(np.maximum(-d, 0).sum() * cell_area)
    fill_m3 = float(np.maximum(d, 0).sum() * cell_area)
    area_m2 = n_valid * cell_area
    cut_depth = np.maximum(-d, 0)

    rtk_ev, grade, err = _rtk_evidence(
        np, req.get("rtk_points"), datum, cell, origin, z.shape, z, valid, None
    )
    if err:
        return err

    earthwork = cut_m3 + fill_m3
    topsoil_out = None
    topsoil_m3 = 0.0
    if topsoil is not None:
        topsoil_m3 = area_m2 * strip
        topsoil_out = {
            "strip_depth_m": strip,
            "strip_m3": topsoil_m3,
            "respread_m3": topsoil_m3,
            "stockpile_required": topsoil_m3 > 0,
            "subsoil_exposed_area_m2": float((cut_depth > strip).sum() * cell_area),
            "note": "topsoil is stripped before earthwork and respread after; excluded from cut/fill",
        }
    cost = {
        "priced": False,
        "currency": None,
        "total": None,
        "quantities": {"earthwork_m3": earthwork, "topsoil_handling_m3": 2 * topsoil_m3},
    }
    if prices is not None:
        cost["priced"] = True
        cost["currency"] = prices["currency"]
        cost["total"] = float(
            prices.get("earthwork_per_m3", 0.0) * earthwork
            + prices.get("topsoil_handling_per_m3", 0.0) * 2 * topsoil_m3
        )

    return {
        "computed": True,
        "source": "levelling-design",
        "status": _NOT_FOR_CONSTRUCTION,
        "execution_authorized": False,
        "crs_epsg": epsg,
        "vertical_datum": datum,
        "units": {"horizontal": "m", "vertical": "m", "volume": "m3"},
        "area_m2": float(area_m2),
        "coverage": {
            "field_cells": n_field,
            "valid_cells": n_valid,
            "nodata_cells": n_field - n_valid,
            "valid_fraction": coverage,
        },
        "design": {
            "mode": mode,
            "shrink_factor": shrink,
            "slope_x_pct": sx * 100.0,
            "slope_y_pct": sy * 100.0,
            "target_elevation_mean_m": float(target.mean()),
            "max_cut_depth_m": float(cut_depth.max()),
            "max_fill_depth_m": float(np.maximum(d, 0).max()),
        },
        "quantities": {
            "cut_m3": cut_m3,
            "fill_m3": fill_m3,
            "net_m3": cut_m3 - fill_m3,
            "cut_area_m2": float((d < 0).sum() * cell_area),
            "fill_area_m2": float((d > 0).sum() * cell_area),
        },
        "topsoil": topsoil_out,
        "evidence": {"grade": grade, "rtk": rtk_ev, "source_grid": "caller-supplied"},
        "cost": cost,
        "gaps": [
            "no haul distance or mass-haul",
            "cell-centre sampling; no TIN/prismoidal refinement",
            "no drainage-grade validation of the finished surface",
            "design is a proposal; survey stake-out and engineer sign-off required",
        ],
    }
