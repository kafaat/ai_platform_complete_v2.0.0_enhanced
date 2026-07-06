"""Productivity-zone clustering (V60.1) — real NDVI-driven zoning, gated + fail-safe.

Replaces the v60 vertical-strip placeholder with **k-means clustering on an NDVI grid**
when one is available, so zones follow actual vegetation vigour instead of arbitrary
slices. If no NDVI grid is supplied (the offline/agent default), the caller keeps the
deterministic strip proposal unchanged.

Pure Python + stdlib (no numpy/sklearn): a deterministic 1-D k-means (sorted seeding,
fixed iterations) clusters per-cell NDVI means; connected components per class then
become zone polygons via the shared ``field_boundary_backends.mask_to_polygons``.

Everything remains a *proposal* — saving zones is a separate high-risk approval.
"""

from __future__ import annotations

from typing import Any

NdviGrid = list[list[float]]  # row-major NDVI means; row 0 = north.


def _flatten_valid(grid: NdviGrid) -> list[float]:
    vals: list[float] = []
    for row in grid:
        for v in row:
            if isinstance(v, (int, float)) and -1.0 <= float(v) <= 1.0:
                vals.append(float(v))
    return vals


def kmeans_1d(values: list[float], k: int, *, iters: int = 25) -> list[float]:
    """Deterministic 1-D k-means centroids (ascending). Sorted-quantile seeding.

    No randomness (reproducible in CI). Empty/edge inputs degrade gracefully.
    """
    vals = sorted(v for v in values if isinstance(v, (int, float)))
    if not vals:
        return []
    k = max(1, min(k, len(set(vals)) or 1))
    # Seed centroids at evenly-spaced quantiles of the sorted data.
    centroids = [vals[min(len(vals) - 1, (2 * i + 1) * len(vals) // (2 * k))] for i in range(k)]
    for _ in range(iters):
        buckets: list[list[float]] = [[] for _ in range(k)]
        for v in vals:
            j = min(range(k), key=lambda c: abs(v - centroids[c]))
            buckets[j].append(v)
        new = [sum(b) / len(b) if b else centroids[i] for i, b in enumerate(buckets)]
        if all(abs(a - b) < 1e-9 for a, b in zip(new, centroids, strict=True)):
            centroids = new
            break
        centroids = new
    return sorted(centroids)


def _nearest(value: float, centroids: list[float]) -> int:
    return min(range(len(centroids)), key=lambda c: abs(value - centroids[c]))


def smooth_label_grid(
    labels: list[list[int | None]],
    *,
    iters: int = 1,
) -> list[list[int | None]]:
    """مرشّح الأغلبيّة (8-جوار) لفرض تجاور مكانيّ على شبكة تصنيف المناطق (V60.2).

    التخصيص لكلّ بكسل على حِدة يُنتج «ملح-وفلفل» (مناطق مبعثرة غير قابلة للإدارة).
    مرشّح الأغلبيّة يُسنِد لكلّ خليّة صالحة أكثر تصنيفات جيرانها (مع نفسها) شيوعاً؛
    التعادل يُبقي التصنيف الحالي. الخلايا غير الصالحة (``None``) لا تصوّت وتبقى كما هي.
    idempotent على المناطق المتّصلة أصلاً (لا يغيّر حقلاً نظيفاً).
    """
    if not labels or not labels[0]:
        return labels
    rows, cols = len(labels), len(labels[0])
    cur = labels
    for _ in range(max(1, iters)):
        nxt = [row[:] for row in cur]
        for r in range(rows):
            for c in range(cols):
                if cur[r][c] is None:
                    continue
                counts: dict[int, int] = {}
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < rows and 0 <= cc < cols and cur[rr][cc] is not None:
                            lbl = cur[rr][cc]
                            counts[lbl] = counts.get(lbl, 0) + 1
                if not counts:
                    continue
                best = max(counts.values())
                # التعادل: أبقِ الحالي إن كان ضمن الأكثر شيوعاً؛ وإلّا أصغر تصنيف (حتميّ).
                if counts.get(cur[r][c], 0) == best:
                    nxt[r][c] = cur[r][c]
                else:
                    nxt[r][c] = min(lbl for lbl, n in counts.items() if n == best)
        if nxt == cur:
            break
        cur = nxt
    return cur


def cluster_separability(values: list[float], centroids: list[float]) -> float:
    """Between-cluster / total variance in [0,1] — higher = cleaner clusters."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2 or len(centroids) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    total = sum((v - mean) ** 2 for v in vals)
    if total <= 0:
        return 0.0
    within = sum((v - centroids[_nearest(v, centroids)]) ** 2 for v in vals)
    return round(max(0.0, min(1.0, 1.0 - within / total)), 3)


# Cluster index (ascending NDVI) → productivity class label, for k∈{2,3,4,5}.
def _class_for_rank(rank: int, k: int) -> str:
    if k <= 2:
        return "low" if rank == 0 else "high"
    if rank == 0:
        return "low"
    if rank == k - 1:
        return "high"
    return "medium"


def zones_from_ndvi_grid(
    grid: NdviGrid,
    bbox: list[float],
    k: int | None,
    *,
    smooth: bool = False,
) -> dict[str, Any] | None:
    """NDVI grid → per-class productivity zones (polygons + score), or None if unusable.

    ``k`` fixes the cluster count; pass ``None`` to auto-select the optimal number of
    management zones via FPI/NCE (Management Zone Analyst, V60.2). ``smooth`` applies an
    8-neighbour majority filter to the per-cell class grid first, enforcing spatial
    contiguity (fewer salt-and-pepper zones) — idempotent on already-contiguous fields.

    Returns None when the grid is empty/degenerate so the caller can fall back to the
    deterministic strip zoning.
    """
    from .field_boundary_backends import mask_to_polygons

    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    flat = _flatten_valid(grid)
    if rows == 0 or cols == 0 or len(set(flat)) < 2:
        return None

    recommendation: dict[str, Any] | None = None
    if k is None:
        from .management_zone_count import recommend_zone_count

        recommendation = recommend_zone_count(flat)
        if recommendation is None:
            return None
        k = recommendation["recommended_k"]

    centroids = kmeans_1d(flat, k)
    if len(centroids) < 2:
        return None
    k_eff = len(centroids)

    # Per-cell class label grid (None where invalid), optionally contiguity-smoothed.
    labels: list[list[int | None]] = [
        [
            _nearest(float(grid[r][c]), centroids) if isinstance(grid[r][c], (int, float)) else None
            for c in range(cols)
        ]
        for r in range(rows)
    ]
    if smooth:
        labels = smooth_label_grid(labels)

    zones: list[dict[str, Any]] = []
    for rank in range(k_eff):
        mask = [[1 if labels[r][c] == rank else 0 for c in range(cols)] for r in range(rows)]
        polys = mask_to_polygons(mask, bbox, min_area_px=1)
        if not polys:
            continue
        cls = _class_for_rank(rank, k_eff)
        score = round((centroids[rank] + 1.0) / 2.0, 3)  # NDVI [-1,1] → [0,1]
        for i, p in enumerate(polys):
            zones.append(
                {
                    "zone_id": f"pz-{cls}-{i + 1}",
                    "productivity_class": cls,
                    "score": score,
                    "ndvi_centroid": round(centroids[rank], 3),
                    "geometry": {"type": p["type"], "coordinates": p["coordinates"]},
                    "pixel_area": p["pixel_area"],
                }
            )
    if not zones:
        return None
    result: dict[str, Any] = {
        "zones": zones,
        "k_effective": k_eff,
        "cluster_separability": cluster_separability(flat, centroids),
        "ndvi_centroids": [round(c, 3) for c in centroids],
        "spatially_smoothed": smooth,
    }
    if recommendation is not None:
        result["zone_count_recommendation"] = recommendation
    return result


def extract_ndvi_grid(params: dict[str, Any], evidence: dict[str, Any] | None) -> NdviGrid | None:
    """Pull an NDVI grid from params or evidence; None if absent/malformed."""
    for src in (params or {}, evidence or {}):
        grid = src.get("ndvi_grid") if isinstance(src, dict) else None
        if isinstance(grid, list) and grid and all(isinstance(r, list) for r in grid):
            return grid  # type: ignore[return-value]
    return None
