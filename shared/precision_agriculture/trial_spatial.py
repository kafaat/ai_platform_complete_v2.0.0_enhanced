"""Spatial execution contract for SAHOOL field trials.

The statistical RCBD design remains owned by ``field_trial_design``. This module
adds deterministic plot generation from an authoritative field polygon, binds the
plots to the RCBD treatment randomisation, and later binds exact measured outcomes.

Geometry generation is deliberately conservative: it works in a local metre plane
centred on the field, clips every plot to the authoritative field geometry, enforces
implement-width/headland constraints, and fails closed when a requested layout
cannot produce a complete RCBD. It does not silently extend plots outside the field.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import asdict, dataclass
from typing import Any

EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class SpatialTrialPlot:
    plot_id: str
    block_index: int
    treatment: str
    role: str
    geometry: dict[str, Any]
    machine_heading_deg: float
    plot_slot: int | None = None
    area_m2: float | None = None


@dataclass(frozen=True)
class PlotOutcomeBinding:
    plot_id: str
    treatment: str
    outcome_refs: tuple[str, ...]
    measurements: dict[str, float]


def _stable_plot_id(trial_id: str, block: int, treatment: str) -> str:
    raw = f"{trial_id}:{block}:{treatment}".encode()
    return f"plot_{hashlib.sha256(raw).hexdigest()[:14]}"


def _shape_dependencies():
    try:
        from shapely import affinity
        from shapely.geometry import box, mapping, shape
        from shapely.ops import transform
    except ImportError as exc:  # pragma: no cover - production dependency guard
        raise RuntimeError("spatial trial generation requires shapely>=2") from exc
    return affinity, box, mapping, shape, transform


def _validate_geojson_polygon(geometry: dict[str, Any]) -> None:
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("field/plot geometry must be Polygon or MultiPolygon")


def _local_projection(geometry: dict[str, Any]):
    """Project WGS84 field geometry to a local metre plane and return inverse fn."""
    _affinity, _box, _mapping, shape, transform = _shape_dependencies()
    _validate_geojson_polygon(geometry)
    wgs = shape(geometry)
    if wgs.is_empty or not wgs.is_valid or wgs.area <= 0:
        raise ValueError("field geometry must be valid and non-empty")
    lon0 = float(wgs.centroid.x)
    lat0 = float(wgs.centroid.y)
    if not (-180 <= lon0 <= 180 and -90 <= lat0 <= 90):
        raise ValueError("field geometry centroid outside WGS84 bounds")
    cos_lat = math.cos(math.radians(lat0))
    if abs(cos_lat) < 1e-9:
        raise ValueError("field geometry too close to pole for local projection")
    mx = math.pi * EARTH_RADIUS_M * cos_lat / 180.0
    my = math.pi * EARTH_RADIUS_M / 180.0

    def to_local(x, y, z=None):
        return ((x - lon0) * mx, (y - lat0) * my)

    def to_wgs84(x, y, z=None):
        return (x / mx + lon0, y / my + lat0)

    return transform(to_local, wgs), to_wgs84


def generate_rcbd_plot_geometries(
    *,
    field_geometry: dict[str, Any],
    treatments: list[str],
    n_blocks: int,
    machine_heading_deg: float,
    implement_width_m: float,
    headland_m: float = 0.0,
    strip_gap_m: float = 0.0,
    min_plot_area_m2: float = 20.0,
) -> list[dict[str, Any]]:
    """Generate one clipped plot per treatment per block from a field polygon.

    In the machine-aligned local frame, Y follows travel and X crosses the implement.
    Blocks are successive travel segments; treatment strips are side-by-side across
    travel. Every generated cell is intersected with the usable field polygon, so
    irregular/concave fields remain inside their authoritative boundary.
    """
    if n_blocks < 1 or len(treatments) < 2:
        raise ValueError("RCBD requires blocks and at least two treatments")
    if len(set(treatments)) != len(treatments) or any(not str(t).strip() for t in treatments):
        raise ValueError("treatments must be unique non-empty names")
    implement_width_m = float(implement_width_m)
    headland_m = float(headland_m)
    strip_gap_m = float(strip_gap_m)
    min_plot_area_m2 = float(min_plot_area_m2)
    if implement_width_m <= 0 or headland_m < 0 or strip_gap_m < 0 or min_plot_area_m2 <= 0:
        raise ValueError("invalid spatial trial dimensions")

    affinity, box, mapping, _shape, transform = _shape_dependencies()
    local, to_wgs84 = _local_projection(field_geometry)
    usable = local.buffer(-headland_m) if headland_m else local
    if usable.is_empty or not usable.is_valid:
        raise ValueError("headland removes all usable trial area")

    heading = float(machine_heading_deg) % 360.0
    # In XY coordinates, heading h from North has angle 90-h from +X. Rotating by
    # +h aligns the travel vector with +Y, leaving X as the cross-track axis.
    aligned = affinity.rotate(usable, heading, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = aligned.bounds
    cross_width = maxx - minx
    travel_length = maxy - miny
    n_treatments = len(treatments)
    cell_width = cross_width / n_treatments
    block_length = travel_length / n_blocks
    if cell_width + 1e-9 < implement_width_m:
        raise ValueError(
            f"field cross-track width cannot fit {n_treatments} implement-width strips: "
            f"cell={cell_width:.2f}m implement={implement_width_m:.2f}m"
        )
    if strip_gap_m >= min(cell_width, block_length):
        raise ValueError("strip_gap_m is too large for generated plot cells")

    generated: list[dict[str, Any]] = []
    for block_index in range(n_blocks):
        y0 = miny + block_index * block_length + strip_gap_m / 2
        y1 = miny + (block_index + 1) * block_length - strip_gap_m / 2
        for slot in range(n_treatments):
            x0 = minx + slot * cell_width + strip_gap_m / 2
            x1 = minx + (slot + 1) * cell_width - strip_gap_m / 2
            clipped = aligned.intersection(box(x0, y0, x1, y1))
            if clipped.is_empty or clipped.area < min_plot_area_m2:
                raise ValueError(
                    f"generated plot block={block_index + 1} slot={slot + 1} "
                    f"has insufficient clipped area"
                )
            # Keep only polygonal output and reject pathological disconnected cells
            # that machinery cannot treat as one deterministic plot.
            if clipped.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError("generated trial cell is not polygonal")
            unrotated = affinity.rotate(clipped, -heading, origin=(0, 0), use_radians=False)
            wgs = transform(to_wgs84, unrotated)
            geom = mapping(wgs)
            generated.append(
                {
                    "type": geom["type"],
                    "coordinates": geom["coordinates"],
                    "_sahool_plot_slot": slot + 1,
                    "_sahool_area_m2": round(float(clipped.area), 3),
                }
            )
    expected = n_blocks * n_treatments
    if len(generated) != expected:
        raise ValueError(
            f"spatial trial generation incomplete: expected {expected}, got {len(generated)}"
        )
    return generated


def assign_rcbd_geometries(
    *,
    trial_id: str,
    treatments: list[str],
    n_blocks: int,
    plot_geometries: list[dict[str, Any]],
    machine_heading_deg: float,
    randomization_seed: str,
    control_names: tuple[str, ...] = ("شاهد", "control"),
) -> list[dict[str, Any]]:
    """Bind one supplied/generated plot geometry to each treatment in every RCBD block."""
    if not trial_id or not randomization_seed:
        raise ValueError("trial_id and randomization_seed are required")
    if n_blocks < 1 or len(treatments) < 2:
        raise ValueError("RCBD requires blocks and at least two treatments")
    expected = n_blocks * len(treatments)
    if len(plot_geometries) != expected:
        raise ValueError(f"expected {expected} plot geometries, got {len(plot_geometries)}")
    heading = float(machine_heading_deg) % 360.0
    for geom in plot_geometries:
        _validate_geojson_polygon(geom)
    rng = random.Random(hashlib.sha256(randomization_seed.encode()).digest())
    out: list[SpatialTrialPlot] = []
    cursor = 0
    controls = {x.lower() for x in control_names}
    for block in range(1, n_blocks + 1):
        block_treatments = list(treatments)
        rng.shuffle(block_treatments)
        for treatment in block_treatments:
            geom = plot_geometries[cursor]
            role = "control" if treatment.strip().lower() in controls else "treatment"
            out.append(
                SpatialTrialPlot(
                    plot_id=_stable_plot_id(trial_id, block, treatment),
                    block_index=block,
                    treatment=treatment,
                    role=role,
                    geometry={k: v for k, v in geom.items() if not k.startswith("_sahool_")},
                    machine_heading_deg=heading,
                    plot_slot=int(geom.get("_sahool_plot_slot"))
                    if geom.get("_sahool_plot_slot")
                    else None,
                    area_m2=float(geom.get("_sahool_area_m2"))
                    if geom.get("_sahool_area_m2")
                    else None,
                )
            )
            cursor += 1
    return [asdict(row) for row in out]


def design_spatial_rcbd(
    *,
    trial_id: str,
    treatments: list[str],
    n_blocks: int,
    field_geometry: dict[str, Any],
    machine_heading_deg: float,
    implement_width_m: float,
    randomization_seed: str,
    headland_m: float = 0.0,
    strip_gap_m: float = 0.0,
    min_plot_area_m2: float = 20.0,
) -> list[dict[str, Any]]:
    """Generate legal plot geometry then apply deterministic RCBD randomisation."""
    geoms = generate_rcbd_plot_geometries(
        field_geometry=field_geometry,
        treatments=treatments,
        n_blocks=n_blocks,
        machine_heading_deg=machine_heading_deg,
        implement_width_m=implement_width_m,
        headland_m=headland_m,
        strip_gap_m=strip_gap_m,
        min_plot_area_m2=min_plot_area_m2,
    )
    return assign_rcbd_geometries(
        trial_id=trial_id,
        treatments=treatments,
        n_blocks=n_blocks,
        plot_geometries=geoms,
        machine_heading_deg=machine_heading_deg,
        randomization_seed=randomization_seed,
    )


def bind_plot_outcomes(
    assignments: list[dict[str, Any]], outcomes: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Bind raster/as-applied/yield evidence to exact plot IDs; reject partial sets."""
    ids = [str(row.get("plot_id") or "") for row in assignments]
    if not ids or any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("assignments require unique plot_id values")
    missing = [plot_id for plot_id in ids if plot_id not in outcomes]
    extra = sorted(set(outcomes) - set(ids))
    if missing or extra:
        raise ValueError(f"plot outcome identity mismatch: missing={missing} extra={extra}")
    bound: list[PlotOutcomeBinding] = []
    for row in assignments:
        plot_id = str(row["plot_id"])
        outcome = outcomes[plot_id]
        refs = tuple(str(v) for v in (outcome.get("outcome_refs") or []) if str(v))
        measurements = {str(k): float(v) for k, v in (outcome.get("measurements") or {}).items()}
        if not refs:
            raise ValueError(f"plot {plot_id} has no outcome evidence refs")
        if not measurements or any(not math.isfinite(v) for v in measurements.values()):
            raise ValueError(f"plot {plot_id} has invalid outcome measurements")
        bound.append(
            PlotOutcomeBinding(
                plot_id=plot_id,
                treatment=str(row["treatment"]),
                outcome_refs=refs,
                measurements=measurements,
            )
        )
    return [asdict(row) for row in bound]
