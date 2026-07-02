"""Runtime evidence wiring (V62.2) — derive real imagery/NDVI signals for the tools.

Bridges the AI-context pack (imagery timeline, per-indicator stats, NDVI grid) into the
inputs the v59.1/v60.1 engines actually consume, so boundary/zoning quality reflects real
imagery instead of defaults. Pure, fail-safe (missing keys → conservative defaults), and
never fabricates data — it only forwards what the pack already carries.
"""

from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _imagery(pack: dict[str, Any] | None) -> dict[str, Any]:
    p = pack if isinstance(pack, dict) else {}
    tl = p.get("imagery_timeline")
    return tl if isinstance(tl, dict) else {}


def derive_cloud_risk(pack: dict[str, Any] | None) -> float | None:
    """Cloud risk in [0,1] from the imagery timeline, or None when unknown.

    Prefers an explicit ``cloud_risk``/``mean_cloud_pct``; else infers from the
    ready/total ratio (few ready dates ⇒ higher cloud risk). None ⇒ unknown (treated
    as usable by the boundary guard) so we never over-claim clouds we can't see.
    """
    im = _imagery(pack)
    explicit = _num(im.get("cloud_risk"))
    if explicit is not None:
        return round(max(0.0, min(explicit, 1.0)), 2)
    pct = _num(im.get("mean_cloud_pct"))
    if pct is not None:
        return round(max(0.0, min(pct / 100.0, 1.0)), 2)
    total = _num(im.get("total_dates")) or 0.0
    ready = _num(im.get("ready_dates"))
    if total > 0 and ready is not None:
        return round(max(0.0, min(1.0 - ready / total, 1.0)), 2)
    return None


def extract_pack_ndvi_grid(pack: dict[str, Any] | None) -> list[list[float]] | None:
    """Forward an NDVI grid from the pack if the raster pipeline provided one."""
    p = pack if isinstance(pack, dict) else {}
    for src in (p, _imagery(p)):
        grid = src.get("ndvi_grid") if isinstance(src, dict) else None
        if isinstance(grid, list) and grid and all(isinstance(r, list) for r in grid):
            return grid  # type: ignore[return-value]
    return None


def boundary_imagery_context(pack: dict[str, Any] | None) -> dict[str, Any]:
    """Enriched imagery_context for ``propose_boundaries`` (adds cloud_risk + ready_dates)."""
    im = dict(_imagery(pack))
    cloud = derive_cloud_risk(pack)
    if cloud is not None:
        im.setdefault("cloud_risk", cloud)
    return im


def zoning_evidence_context(pack: dict[str, Any] | None) -> dict[str, Any]:
    """Evidence for ``propose_productivity_zones`` — pass the pack through, plus a real
    NDVI grid when present so the k-means path (not strips) is taken."""
    p = dict(pack) if isinstance(pack, dict) else {}
    grid = extract_pack_ndvi_grid(pack)
    if grid is not None and "ndvi_grid" not in p:
        p["ndvi_grid"] = grid
    return p


def pack_ndvi_grid_evidence(pack: dict[str, Any] | None) -> dict[str, Any] | None:
    """Assemble the v62.3 ``ndvi_grid_evidence`` contract object from the pack's NDVI
    grid + quality metadata (as plumbed by field_ai_context v62.3-C). Returns None when
    the pack carries no grid, so zoning/VRA fall back exactly as before.

    Fail-safe and non-fabricating: quality metadata is optional; missing metrics stay
    None inside the contract. The ``evidence_contract`` import is done locally to keep
    that dependency scoped to ai_agronomist and avoid an import cycle (evidence_contract
    imports zoning_is_evidence_backed from this module).
    """
    grid = extract_pack_ndvi_grid(pack)
    if grid is None:
        return None
    p = pack if isinstance(pack, dict) else {}
    im = _imagery(p)
    quality = im.get("ndvi_grid_quality")
    quality = quality if isinstance(quality, dict) else {}
    # cloud_cover expected as a ratio in [0,1]; convert cloud_pct/100 when only that is given.
    cloud_cover = quality.get("cloud_cover")
    if cloud_cover is None:
        pct = _num(quality.get("cloud_pct"))
        if pct is not None:
            cloud_cover = pct / 100.0

    try:  # relative import in-service; absolute fallback for direct-spec unit guards
        from .evidence_contract import build_ndvi_grid_evidence
    except ImportError:  # pragma: no cover - mirrors evidence_contract's own shim
        from services.ai_agronomist.evidence_contract import (  # type: ignore
            build_ndvi_grid_evidence,
        )

    return build_ndvi_grid_evidence(
        field_id=p.get("field_id"),
        tenant_id=p.get("tenant_id"),
        source="raster-service",
        index="ndvi",
        scene_id=quality.get("scene_id"),
        acquisition_date=quality.get("acquisition_date"),
        grid=grid,
        cloud_cover=cloud_cover,
        valid_pixel_ratio=quality.get("valid_pixel_ratio"),
        coverage_ratio=quality.get("coverage_ratio"),
        source_resolution_m=quality.get("source_resolution_m"),
        asset_id=quality.get("asset_id"),
    )


# ── provenance: distinguish real-evidence zoning from geometry-only fallback ──
_REAL_ZONING_METHODS = {"ndvi_kmeans_clustering", "multi_index_quantile_zoning_fallback"}


def zoning_is_evidence_backed(zoning_method: str | None) -> bool:
    return str(zoning_method or "").strip() in _REAL_ZONING_METHODS
