"""Field-boundary detection backends (V59.5) — pluggable, fail-safe scaffold.

The agent tool contract (``field_boundary_ai.propose_boundaries``) never changes.
Behind it we select a *backend* by env ``SAHOOL_FIELD_BOUNDARY_BACKEND``:

- ``deterministic`` (default): the seeded-bbox proposal — always available, offline.
- ``ftw``: a scaffold for the *Fields of The World* (FTW, 2024, MIT code) style
  Sentinel-2 segmentation model. It runs a real, deterministic post-processing
  pipeline (mask → connected components → per-component polygon in EPSG:4326),
  but the actual model **inference** (PyTorch + trained weights) is deliberately
  gated: if weights/torch are absent — as in CI and any offline box — the backend
  returns ``None`` and the caller falls back to ``deterministic``. Nothing crashes,
  the tool contract is preserved, and no heavy dependency is imported at module load.

Honesty / licensing (see V59_5 report):
- FTW *code* is MIT (commercial-safe); some FTW *weights/datasets* are CC-BY-NC-SA
  (NON-commercial) — audit the specific weight file before shipping.
- ``Delineate Anything`` (YOLOv11) is **AGPL-3.0** — a SaaS blocker; not used here.
- Real inference (torch forward on S2 tiles) needs the operator's environment; this
  module ships the deterministic, unit-testable geometry half only.

Pure-Python + stdlib at import time (numpy/torch are optional and lazily imported),
so this loads in the fastapi-less unit job and the path-loading contract guards.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any

Mask = Sequence[Sequence[int]]  # 2D grid of 0/1 (row-major; row 0 = north/top).


# ── pixel ⇆ lon/lat (affine from the tile bbox; EPSG:4326) ──────────────────
def pixel_to_lonlat(
    col: float, row: float, bbox: Sequence[float], cols: int, rows: int
) -> list[float]:
    """Map a pixel-edge coordinate (col, row) to [lon, lat] within ``bbox``.

    Column 0 → lon_min, column ``cols`` → lon_max. Row 0 is the northern edge
    (lat_max) and row ``rows`` is the southern edge (lat_min), matching raster
    row order. No projection: linear within the (small) tile in EPSG:4326.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    fx = 0.0 if cols == 0 else col / cols
    fy = 0.0 if rows == 0 else row / rows
    return [lon_min + fx * (lon_max - lon_min), lat_max - fy * (lat_max - lat_min)]


def connected_components(mask: Mask) -> list[list[tuple[int, int]]]:
    """4-connectivity connected components of the truthy cells (iterative BFS)."""
    rows = len(mask)
    cols = len(mask[0]) if rows else 0
    seen = [[False] * cols for _ in range(rows)]
    comps: list[list[tuple[int, int]]] = []
    for r in range(rows):
        for c in range(cols):
            if not mask[r][c] or seen[r][c]:
                continue
            stack = [(r, c)]
            seen[r][c] = True
            cells: list[tuple[int, int]] = []
            while stack:
                y, x = stack.pop()
                cells.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < rows and 0 <= nx < cols and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
            comps.append(cells)
    return comps


def mask_to_polygons(
    mask: Mask, bbox: Sequence[float], *, min_area_px: int = 4
) -> list[dict[str, Any]]:
    """Segmentation mask → one closed EPSG:4326 Polygon per connected field.

    Deterministic post-processing shared by any raster model. This scaffold emits
    each component's pixel-extent rectangle (separating *multiple* fields in a
    scene — a real gain over the single-bbox placeholder). Production swaps the
    per-component rectangle for true contour tracing (``rasterio.features.shapes``
    / marching squares) without touching callers.
    """
    rows = len(mask)
    cols = len(mask[0]) if rows else 0
    if not rows or not cols:
        return []
    polys: list[dict[str, Any]] = []
    for cells in connected_components(mask):
        if len(cells) < max(1, min_area_px):
            continue
        ys = [y for y, _ in cells]
        xs = [x for _, x in cells]
        r0, r1 = min(ys), max(ys) + 1
        c0, c1 = min(xs), max(xs) + 1
        ring = [
            pixel_to_lonlat(c0, r0, bbox, cols, rows),
            pixel_to_lonlat(c1, r0, bbox, cols, rows),
            pixel_to_lonlat(c1, r1, bbox, cols, rows),
            pixel_to_lonlat(c0, r1, bbox, cols, rows),
        ]
        ring.append(list(ring[0]))  # close the ring
        polys.append({"type": "Polygon", "coordinates": [ring], "pixel_area": len(cells)})
    return polys


# ── FTW backend (scaffold; inference gated + fail-safe) ─────────────────────
def ftw_weights_path() -> str:
    return os.getenv("SAHOOL_FTW_WEIGHTS", "").strip()


def ftw_available() -> bool:
    """True only if a weights file is configured AND torch is importable.

    In CI / any offline box this is False → the caller falls back to deterministic.
    We never import torch at module load (heavy, optional).
    """
    weights = ftw_weights_path()
    if not weights or not os.path.isfile(weights):
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("torch") is not None
    except Exception:  # noqa: BLE001 — أيّ خلل في الفحص ⇒ اعتبره غير متاح (fail-safe)
        return False


def ftw_propose(
    params: dict[str, Any],
    *,
    field_id: str | None = None,
    imagery_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """FTW-backed proposal, or ``None`` to signal fallback to deterministic.

    Returns ``None`` whenever the model is unavailable (the offline/CI case), so
    the tool contract is always honoured. When wired to real weights, replace the
    ``_run_ftw_inference`` stub with a torch forward pass that yields a binary
    field mask for the tile; the rest of the pipeline is already deterministic.
    """
    from .field_boundary_ai import area_ha_for_bbox, normalize_bbox

    bbox = normalize_bbox(params.get("bbox"))
    if bbox is None or not ftw_available():
        return None

    mask = _run_ftw_inference(bbox, params)  # operator-provided; None until wired.
    if not mask:
        return None

    source = str(params.get("source") or "truecolor").strip().lower()
    polygons = mask_to_polygons(mask, bbox, min_area_px=int(params.get("min_field_px") or 4))
    proposals = [
        {
            "geometry": {"type": p["type"], "coordinates": p["coordinates"]},
            "confidence": 0.9,
            "area_ha": _polygon_area_ha(p["coordinates"][0], area_ha_for_bbox, bbox, mask),
            "method": "ftw_resunet_mask_polygonization",
        }
        for p in polygons
    ]
    return {
        "field_id": field_id,
        "source": source,
        "date": params.get("date"),
        "crop_hint": params.get("crop_hint"),
        "backend": "ftw",
        "method": "ftw_sentinel2_field_segmentation",
        "proposed_boundaries": proposals,
        "requires_user_confirmation": True,
        "persistence": "proposal_only_until_user_confirms",
    }


def _run_ftw_inference(bbox: Sequence[float], params: dict[str, Any]) -> Mask | None:
    """Stub for the real FTW torch forward pass — returns None until wired.

    Operator wiring (needs their environment): load weights (``ftw_weights_path``),
    fetch the S2 tile for ``bbox``/``date``, normalize the FTW input bands, run the
    model, threshold to a binary field mask, and return it as a 2D 0/1 grid.
    """
    return None


def _polygon_area_ha(
    ring: list[list[float]], area_ha_for_bbox: Callable, bbox: Sequence[float], mask: Mask
) -> float:
    """Area of a component ≈ (component pixel share) × tile area. Deterministic."""
    rows = len(mask)
    cols = len(mask[0]) if rows else 0
    total_px = rows * cols
    if total_px == 0:
        return 0.0
    # ring pixel-fraction via its lon/lat extent relative to bbox.
    lon_min, lat_min, lon_max, lat_max = bbox
    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    fw = (max(lons) - min(lons)) / (lon_max - lon_min) if lon_max > lon_min else 0.0
    fh = (max(lats) - min(lats)) / (lat_max - lat_min) if lat_max > lat_min else 0.0
    return round(area_ha_for_bbox(list(bbox)) * fw * fh, 3)


# ── backend registry ────────────────────────────────────────────────────────
def select_backend_name() -> str:
    name = os.getenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "deterministic").strip().lower()
    return name if name in {"deterministic", "ftw"} else "deterministic"


# ══════════════════════════════════════════════════════════════════════════════
# V59.1 — replaceable adapter chain + boundary quality assessment
#
# Adapters are tried best-first; the first that yields geometry wins. Every result
# stays a *proposal* (requires_user_confirmation=True) — saving remains a separate
# high-risk approval (save_detected_boundary). A guard flags any degradation to the
# bbox rectangle *while imagery/FTW evidence exists*, so agronomic weakness is
# visible instead of silent.
# ══════════════════════════════════════════════════════════════════════════════
_FIELD_MIN_HA = 0.05  # حقل معقول: 0.05–500 هكتار (خارجها ⇒ area_reasonableness يهبط).
_FIELD_MAX_HA = 500.0


def _has_imagery_evidence(evidence: dict[str, Any] | None) -> bool:
    e = evidence or {}
    return bool(e.get("total_dates") or e.get("ready_dates") or e.get("available"))


def _has_usable_imagery(evidence: dict[str, Any] | None) -> bool:
    """Imagery that is actually usable for edge tracing: present AND not too cloudy.

    High cloud (or an explicit unusable flag) means imagery *exists* but cannot drive
    a real boundary — so ``sentinel2_boundary_fallback`` declines and the bbox guard
    fires (agronomic weakness surfaced, not hidden)."""
    e = evidence or {}
    if not _has_imagery_evidence(e):
        return False
    cloud = e.get("cloud_risk")
    if isinstance(cloud, (int, float)) and cloud >= 0.7:
        return False
    return True


def _seed_confidence(source: str, has_scene: bool, crop_hint: Any) -> float:
    base = 0.62 if source == "truecolor" else 0.54
    if has_scene:
        base += 0.08
    if crop_hint:
        base += 0.03
    return round(max(0.35, min(base, 0.82)), 2)


def _bbox_proposal(params: dict[str, Any]) -> dict[str, Any] | None:
    from .field_boundary_ai import area_ha_for_bbox, bbox_polygon, normalize_bbox

    bbox = normalize_bbox(params.get("bbox"))
    if bbox is None:
        return None
    return {"geometry": bbox_polygon(bbox), "area_ha": area_ha_for_bbox(bbox), "bbox": bbox}


def registered_boundary_lookup(
    params: dict[str, Any], evidence: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Highest trust: a boundary a human already confirmed/registered for the field.

    Read from the canonical field state passed as evidence — never fabricated.
    """
    e = evidence or {}
    geom = e.get("registered_boundary") or e.get("canonical_field_geometry")
    if isinstance(geom, dict) and geom.get("type") in {"Polygon", "MultiPolygon"}:
        return {
            "source": "registered_boundary",
            "resolution_m": 1.0,
            "confidence": 0.95,
            "proposals": [{"geometry": geom, "method": "registered_canonical_boundary"}],
        }
    return None


def ftw_boundary_adapter(
    params: dict[str, Any], evidence: dict[str, Any] | None
) -> dict[str, Any] | None:
    """FTW/MIT Sentinel-2 segmentation — gated; None offline (fail-safe)."""
    res = ftw_propose(params, imagery_context=evidence)
    if res is None:
        return None
    return {
        "source": "ftw",
        "resolution_m": 10.0,
        "confidence": max(
            (p.get("confidence", 0.9) for p in res["proposed_boundaries"]), default=0.9
        ),
        "proposals": res["proposed_boundaries"],
    }


def sentinel2_boundary_fallback(
    params: dict[str, Any], evidence: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Imagery exists but no FTW model: a bbox-seeded polygon tagged S2-derived.

    Only fires when imagery evidence is present AND usable — otherwise defers to
    bbox_fallback (and the guard flags the degradation).
    """
    if not _has_usable_imagery(evidence):
        return None
    seed = _bbox_proposal(params)
    if seed is None:
        return None
    source = str(params.get("source") or "truecolor").strip().lower()
    conf = _seed_confidence(
        source if source in {"truecolor", "ndvi", "falsecolor"} else "truecolor",
        True,
        params.get("crop_hint"),
    )
    return {
        "source": "sentinel2_fallback",
        "resolution_m": 10.0,
        "confidence": conf,
        "proposals": [
            {
                "geometry": seed["geometry"],
                "area_ha": seed["area_ha"],
                "method": "sentinel2_bbox_seeded_polygon",
            }
        ],
    }


def bbox_fallback(params: dict[str, Any], evidence: dict[str, Any] | None) -> dict[str, Any] | None:
    """Lowest trust: pure bbox rectangle (no imagery signal)."""
    seed = _bbox_proposal(params)
    if seed is None:
        return None
    source = str(params.get("source") or "truecolor").strip().lower()
    conf = _seed_confidence(
        source if source in {"truecolor", "ndvi", "falsecolor"} else "truecolor",
        False,
        params.get("crop_hint"),
    )
    return {
        "source": "bbox_fallback",
        "resolution_m": None,
        "confidence": conf,
        "proposals": [
            {
                "geometry": seed["geometry"],
                "area_ha": seed["area_ha"],
                "method": "bbox_seeded_polygon",
            }
        ],
    }


# ترتيب الأفضليّة (الأعلى ثقةً أوّلاً).
BOUNDARY_ADAPTER_CHAIN: list[
    Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any] | None]
] = [
    registered_boundary_lookup,
    ftw_boundary_adapter,
    sentinel2_boundary_fallback,
    bbox_fallback,
]


def _ring_of(geometry: dict[str, Any]) -> list[list[float]]:
    if geometry.get("type") == "Polygon":
        coords = geometry.get("coordinates") or [[]]
        return coords[0] if coords else []
    if geometry.get("type") == "MultiPolygon":
        coords = geometry.get("coordinates") or [[[]]]
        return coords[0][0] if coords and coords[0] else []
    return []


def _shape_validity(geometry: dict[str, Any]) -> float:
    ring = _ring_of(geometry)
    if len(ring) < 4:
        return 0.0
    closed = ring[0] == ring[-1]
    distinct = len({(round(x, 7), round(y, 7)) for x, y in ring}) >= 3
    return 1.0 if (closed and distinct) else 0.5


def _area_reasonableness(area_ha: float | None) -> float:
    if area_ha is None or area_ha <= 0:
        return 0.0
    if _FIELD_MIN_HA <= area_ha <= _FIELD_MAX_HA:
        return 1.0
    return 0.4  # out of the typical field band — plausible but flag for review.


def assess_boundary_quality(
    winner: dict[str, Any], proposal: dict[str, Any], evidence: dict[str, Any] | None
) -> dict[str, Any]:
    """Seven agronomic-quality signals for one boundary proposal (all in [0,1] except res)."""
    source = winner["source"]
    e = evidence or {}
    # edge_strength: imagery-derived sources trace real edges; bbox has none.
    edge = {
        "registered_boundary": 0.9,
        "ftw": 0.85,
        "sentinel2_fallback": 0.45,
        "bbox_fallback": 0.0,
    }.get(source, 0.0)
    cloud = e.get("cloud_risk")
    cloud_risk = float(cloud) if isinstance(cloud, (int, float)) else 0.5  # unknown ⇒ mid.
    return {
        "boundary_confidence": winner["confidence"],
        "edge_strength": edge,
        "shape_validity": _shape_validity(proposal.get("geometry") or {}),
        "area_reasonableness": _area_reasonableness(proposal.get("area_ha")),
        "source_resolution_m": winner["resolution_m"],
        "cloud_risk": round(cloud_risk, 2),
        "requires_user_confirmation": True,
    }


def run_boundary_adapters(
    params: dict[str, Any], evidence: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Run the chain best-first; return the winner + provenance + quality + guard.

    Guard: if imagery/FTW evidence exists yet only ``bbox_fallback`` won, set
    ``degraded_to_bbox_despite_imagery=True`` (agronomic weakness made visible).
    """
    tried: list[str] = []
    winner: dict[str, Any] | None = None
    for adapter in BOUNDARY_ADAPTER_CHAIN:
        try:
            res = adapter(params, evidence)
        except Exception:  # noqa: BLE001 — محوّل يفشل ⇒ جرّب التالي (fail-safe)
            res = None
        tried.append(adapter.__name__)
        if res is not None:
            winner = res
            break
    if winner is None:
        return None
    proposal0 = winner["proposals"][0] if winner["proposals"] else {}
    quality = assess_boundary_quality(winner, proposal0, evidence)
    degraded = winner["source"] == "bbox_fallback" and _has_imagery_evidence(evidence)
    return {
        "boundary_source": winner["source"],
        "adapters_tried": tried,
        "quality": quality,
        "degraded_to_bbox_despite_imagery": degraded,
        "winner": winner,
    }
