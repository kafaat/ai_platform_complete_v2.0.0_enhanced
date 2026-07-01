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
