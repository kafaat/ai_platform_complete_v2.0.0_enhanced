"""Spatial execution contract for SAHOOL field trials.

The statistical RCBD design remains owned by ``field_trial_design``. This module
adds deterministic plot generation from an authoritative field polygon, binds the
plots to the RCBD treatment randomisation, and later binds exact measured outcomes.

Geometry generation is deliberately conservative: it works in a local metre plane
centred on the field, clips every plot to the authoritative field geometry, enforces
implement-width/headland constraints, and fails closed when a requested layout
cannot produce a complete RCBD. It does not silently extend plots outside the field.

Assignments and outcomes carry an immutable ``layout_id``. Legacy evidence without
this identity must be regenerated from its verified trial layout; it is never
silently attached to a new layout. Content digests establish identity, not origin
or authorisation of externally supplied measurements.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Any

EARTH_RADIUS_M = 6_378_137.0
# Numerical slivers only: one square millimetre in the local metre plane.
# Equality/containment is always rejected, even for smaller geometries.
PLOT_OVERLAP_TOLERANCE_M2 = 1e-6
_CONTROL_ALIASES = frozenset({"control", "شاهد"})


@dataclass(frozen=True)
class SpatialTrialPlot:
    plot_id: str
    layout_id: str
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
    layout_id: str
    treatment: str
    outcome_refs: tuple[str, ...]
    measurements: dict[str, float]


def _canonical_value(value: Any) -> Any:
    """Canonical JSON values: numeric/list encodings must not change identity."""
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("layout identity keys must be strings")
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("layout identity requires finite numbers")
        return int(value) if value.is_integer() else value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValueError("layout identity requires JSON-compatible values")


def _content_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()}"


def _normalised_treatments(treatments: list[str], control_names: tuple[str, ...] = ()) -> list[str]:
    """Preserve display names while treating control aliases as one identity.

    Custom control names extend the reserved Arabic/English aliases; they do not
    turn a reserved control label into a treatment.
    """
    if any(not isinstance(treatment, str) for treatment in treatments):
        raise ValueError("treatments must be unique non-empty names")
    if any(not isinstance(name, str) or not name.strip() for name in control_names):
        raise ValueError("control_names must contain non-empty names")
    names = [" ".join(treatment.split()) for treatment in treatments]
    controls = _CONTROL_ALIASES | {" ".join(name.split()).casefold() for name in control_names}
    identities = ["control" if name.casefold() in controls else name.casefold() for name in names]
    if any(not name for name in names) or len(set(identities)) != len(names):
        raise ValueError("treatments must be unique non-empty names")
    return names


def _normalised_heading(heading: float) -> float:
    heading = float(heading)
    if not math.isfinite(heading):
        raise ValueError("machine heading must be finite")
    return heading % 360.0


def _plot_identity(row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the physical assignment identity when accepting measured evidence."""
    try:
        block, slot = row["block_index"], row["plot_slot"]
        if type(block) is not int or type(slot) is not int or block < 1 or slot < 1:
            raise ValueError("invalid block or slot")
        if row["role"] not in {"control", "treatment"}:
            raise ValueError("invalid plot role")
        area = float(row["area_m2"]) if row.get("area_m2") is not None else None
        if area is not None and (not math.isfinite(area) or area <= 0):
            raise ValueError("invalid plot area")
        return {
            "block_index": block,
            "plot_slot": slot,
            "treatment": _normalised_treatments([row["treatment"]])[0],
            "role": row["role"],
            "geometry": _canonical_geometry(row["geometry"]),
            "machine_heading_deg": _normalised_heading(row["machine_heading_deg"]),
            "area_m2": area,
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid spatial plot assignment") from exc


def _stable_plot_id(layout_id: str, row: dict[str, Any]) -> str:
    return _content_id("plot", {"layout_id": layout_id, "assignment": _plot_identity(row)})


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


def _canonical_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    """Validate WGS84 coordinates and normalise polygon winding/start/order."""
    _validate_geojson_polygon(geometry)
    _affinity, _box, mapping, shape, _transform = _shape_dependencies()
    from shapely.errors import GEOSException

    try:
        _canonical_value(geometry.get("coordinates"))
        polygon = shape(geometry)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError("field/plot geometry must be valid and non-empty")
        minx, miny, maxx, maxy = polygon.bounds
        if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
            raise ValueError("field/plot geometry outside WGS84 bounds")
        return mapping(polygon.normalize())
    except (KeyError, TypeError, ValueError, GEOSException) as exc:
        raise ValueError(f"invalid field/plot geometry: {exc}") from exc


def _local_projection(geometry: dict[str, Any]):
    """Project WGS84 field geometry to a local metre plane and return inverse fn."""
    _affinity, _box, _mapping, shape, transform = _shape_dependencies()
    wgs = shape(_canonical_geometry(geometry))
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


def _validate_disjoint_plots(plot_geometries: list[dict[str, Any]]) -> None:
    """Reject physically repeated/overlapping units using an indexed local plane.

    The affine equirectangular plane is shared by all plots, keeps polygon edges
    straight and measures the numerical tolerance in approximate square metres.
    Its domain is a non-polar layout spanning at most one degree per axis. Larger
    or antimeridian-spanning designs need a separately supported projection.
    This is geometric consistency, not proof of biological independence.
    """
    affinity, _box, _mapping, shape, _transform = _shape_dependencies()
    from shapely.strtree import STRtree

    polygons = [shape(_canonical_geometry(geom)) for geom in plot_geometries]
    minx = min(p.bounds[0] for p in polygons)
    miny = min(p.bounds[1] for p in polygons)
    maxx = max(p.bounds[2] for p in polygons)
    maxy = max(p.bounds[3] for p in polygons)
    if maxx - minx > 1 or maxy - miny > 1 or miny < -85 or maxy > 85:
        raise ValueError("trial plots exceed the supported local non-polar projection domain")
    lon0, lat0 = (minx + maxx) / 2, (miny + maxy) / 2
    my = math.pi * EARTH_RADIUS_M / 180.0
    mx = my * math.cos(math.radians(lat0))
    local = [
        affinity.scale(affinity.translate(p, -lon0, -lat0), mx, my, origin=(0, 0)) for p in polygons
    ]
    tree = STRtree(local)
    for i, polygon in enumerate(local):
        for candidate in tree.query(polygon):
            j = int(candidate)
            if j <= i:
                continue
            other = local[j]
            if (
                polygon.covers(other)
                or other.covers(polygon)
                or polygon.intersection(other).area > PLOT_OVERLAP_TOLERANCE_M2
            ):
                raise ValueError(
                    f"duplicate or overlapping trial plots at positions {i + 1}, {j + 1}"
                )


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
    if type(n_blocks) is not int or n_blocks < 1 or len(treatments) < 2:
        raise ValueError("RCBD requires blocks and at least two treatments")
    treatments = _normalised_treatments(treatments)
    implement_width_m = float(implement_width_m)
    headland_m = float(headland_m)
    strip_gap_m = float(strip_gap_m)
    min_plot_area_m2 = float(min_plot_area_m2)
    if (
        not all(
            math.isfinite(value)
            for value in (implement_width_m, headland_m, strip_gap_m, min_plot_area_m2)
        )
        or implement_width_m <= 0
        or headland_m < 0
        or strip_gap_m < 0
        or min_plot_area_m2 <= 0
    ):
        raise ValueError("invalid spatial trial dimensions")
    heading = _normalised_heading(machine_heading_deg)

    affinity, box, mapping, _shape, transform = _shape_dependencies()
    local, to_wgs84 = _local_projection(field_geometry)
    usable = local.buffer(-headland_m) if headland_m else local
    if usable.is_empty or not usable.is_valid:
        raise ValueError("headland removes all usable trial area")

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
    layout_parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Bind one supplied/generated plot geometry to each treatment in every RCBD block."""
    if (
        not isinstance(trial_id, str)
        or not trial_id.strip()
        or trial_id.strip().casefold() == "unbound-trial"
    ):
        raise ValueError("a real non-empty trial_id is required")
    if not isinstance(randomization_seed, str) or not randomization_seed.strip():
        raise ValueError("randomization_seed is required")
    trial_id, randomization_seed = trial_id.strip(), randomization_seed.strip()
    if type(n_blocks) is not int or n_blocks < 1 or len(treatments) < 2:
        raise ValueError("RCBD requires blocks and at least two treatments")
    treatments = _normalised_treatments(treatments, control_names)
    expected = n_blocks * len(treatments)
    if len(plot_geometries) != expected:
        raise ValueError(f"expected {expected} plot geometries, got {len(plot_geometries)}")
    _validate_disjoint_plots(plot_geometries)
    heading = _normalised_heading(machine_heading_deg)
    rng = random.Random(hashlib.sha256(randomization_seed.encode()).digest())
    assignments: list[dict[str, Any]] = []
    cursor = 0
    controls = _CONTROL_ALIASES | {" ".join(name.split()).casefold() for name in control_names}
    for block in range(1, n_blocks + 1):
        block_treatments = list(treatments)
        rng.shuffle(block_treatments)
        for slot, treatment in enumerate(block_treatments, 1):
            geom = plot_geometries[cursor]
            _validate_geojson_polygon(geom)
            if geom.get("_sahool_plot_slot", slot) != slot:
                raise ValueError("plot slot must match the ordered block geometry")
            role = "control" if treatment.casefold() in controls else "treatment"
            assignments.append(
                _plot_identity(
                    {
                        "block_index": block,
                        "treatment": treatment,
                        "role": role,
                        "geometry": geom,
                        "machine_heading_deg": heading,
                        "plot_slot": slot,
                        "area_m2": geom.get("_sahool_area_m2"),
                    }
                )
            )
            cursor += 1
    layout_id = _content_id(
        "layout",
        {
            "schema_version": 1,
            "trial_id": trial_id,
            "randomization_seed": randomization_seed,
            "treatments": treatments,
            "n_blocks": n_blocks,
            "machine_heading_deg": heading,
            "layout_parameters": layout_parameters or {},
            "assignments": assignments,
        },
    )
    return [
        asdict(
            SpatialTrialPlot(
                plot_id=_stable_plot_id(layout_id, row),
                layout_id=layout_id,
                **row,
            )
        )
        for row in assignments
    ]


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
        layout_parameters={
            "field_geometry": _canonical_geometry(field_geometry),
            "implement_width_m": float(implement_width_m),
            "headland_m": float(headland_m),
            "strip_gap_m": float(strip_gap_m),
            "min_plot_area_m2": float(min_plot_area_m2),
        },
    )


def bind_plot_outcomes(
    assignments: list[dict[str, Any]], outcomes: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Bind evidence to the exact supplied plot set and its layout identity.

    Reject missing/extra outcomes, legacy identities and altered assignments. The
    caller must supply the complete registered layout: this helper has no registry
    from which to verify that rows were not removed from both inputs, and does not
    authenticate the origin of externally supplied measurements.
    """
    ids = [str(row.get("plot_id") or "") for row in assignments]
    if not ids or any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("assignments require unique plot_id values")
    layout_ids = [row.get("layout_id") for row in assignments]
    if (
        any(not isinstance(value, str) or not value.strip() for value in layout_ids)
        or len(set(layout_ids)) != 1
    ):
        raise ValueError("assignments require a single layout_id; regenerate legacy assignments")
    layout_id = layout_ids[0]
    missing = [plot_id for plot_id in ids if plot_id not in outcomes]
    extra = sorted(set(outcomes) - set(ids))
    if missing or extra:
        raise ValueError(f"plot outcome identity mismatch: missing={missing} extra={extra}")
    bound: list[PlotOutcomeBinding] = []
    for row in assignments:
        plot_id = str(row["plot_id"])
        if plot_id != _stable_plot_id(layout_id, row):
            raise ValueError(f"plot assignment identity mismatch: {plot_id}")
        outcome = outcomes[plot_id]
        if outcome.get("layout_id") != layout_id:
            raise ValueError(f"plot outcome layout identity mismatch: {plot_id}")
        refs = tuple(str(v) for v in (outcome.get("outcome_refs") or []) if str(v))
        raw_measurements = outcome.get("measurements")
        if not isinstance(raw_measurements, dict) or not raw_measurements:
            raise ValueError(f"plot {plot_id} has invalid outcome measurements")
        try:
            if any(isinstance(value, bool) for value in raw_measurements.values()):
                raise ValueError("boolean measurements are not quantities")
            measurements = {str(key): float(value) for key, value in raw_measurements.items()}
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"plot {plot_id} has invalid outcome measurements") from exc
        if not refs:
            raise ValueError(f"plot {plot_id} has no outcome evidence refs")
        if not measurements or any(not math.isfinite(v) for v in measurements.values()):
            raise ValueError(f"plot {plot_id} has invalid outcome measurements")
        bound.append(
            PlotOutcomeBinding(
                plot_id=plot_id,
                layout_id=layout_id,
                treatment=str(row["treatment"]),
                outcome_refs=refs,
                measurements=measurements,
            )
        )
    # Externally supplied or older assignments can have self-consistent digests
    # while describing the same physical unit more than once.
    _validate_disjoint_plots([row["geometry"] for row in assignments])
    return [asdict(row) for row in bound]
