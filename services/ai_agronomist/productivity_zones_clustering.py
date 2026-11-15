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

import math
from datetime import date
from typing import Any

NdviGrid = list[list[float]]  # row-major NDVI means; row 0 = north.

# مؤشّرات مساعدة مُتاحة أصلاً (band_math/terrain) لكنّها غير موصولة بالعنقدة قبل V60.3.
# التعيين: اسم الميزة → مفتاح الشبكة في params/evidence. NDVI هو الأساس (السيّد) دائماً.
_AUX_FEATURE_KEYS: tuple[tuple[str, str], ...] = (
    ("ndmi", "ndmi_grid"),  # رطوبة الغطاء (band_math) — يفصل الإجهاد المائيّ عن الحيويّة
    ("reci", "reci_grid"),  # كلوروفيل الحافّة الحمراء (RECI) — حالة التغذية
    ("msavi", "msavi_grid"),  # MSAVI — حيويّة مُصحَّحة للتربة العارية (مناطق متناثرة)
    ("slope", "slope_grid"),  # الانحدار (terrain) — يفسّر تباين الإنتاجيّة الطوبوغرافيّ
)


def _flatten_valid(grid: NdviGrid) -> list[float]:
    vals: list[float] = []
    for row in grid:
        for v in row:
            if _finite_number(v) and -1 <= v <= 1:
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


# ── العنقدة متعدّدة الأبعاد (V60.3): NDVI + مؤشّرات مساعدة + طوبوغرافيا ──────────
def _sqdist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=True))


def _nearest_vec(vec: list[float], centroids: list[list[float]]) -> int:
    return min(range(len(centroids)), key=lambda c: _sqdist(vec, centroids[c]))


def kmeans_nd(vectors: list[list[float]], k: int, *, iters: int = 25) -> list[list[float]]:
    """k-means حتميّ متعدّد الأبعاد (بلا numpy/عشوائيّة).

    البذر عند كوانتايلات البُعد الأوّل (NDVI المعياريّ) المرتّبة — يُبقي NDVI مُوجِّهاً
    للترتيب فيبقى تصنيف low→high ذا معنى بعد العنقدة. تعادل المسافة يُحسَم بأصغر فهرس
    (``min`` حتميّ) فالنتيجة تتكرّر في CI. المراكز الفارغة تُبقي موضعها السابق.
    """
    if not vectors:
        return []
    dim = len(vectors[0])
    k = max(1, min(k, len(vectors)))
    order = sorted(range(len(vectors)), key=lambda i: vectors[i][0])
    centroids = [
        list(vectors[order[min(len(order) - 1, (2 * j + 1) * len(order) // (2 * k))]])
        for j in range(k)
    ]
    for _ in range(iters):
        buckets: list[list[list[float]]] = [[] for _ in range(k)]
        for v in vectors:
            buckets[_nearest_vec(v, centroids)].append(v)
        new = [
            [sum(vec[d] for vec in b) / len(b) for d in range(dim)] if b else list(centroids[i])
            for i, b in enumerate(buckets)
        ]
        if all(_sqdist(a, b) < 1e-18 for a, b in zip(new, centroids, strict=True)):
            centroids = new
            break
        centroids = new
    return centroids


def _feature_vectors(
    grids: list[NdviGrid], rows: int, cols: int
) -> tuple[list[tuple[int, int]], list[list[float]]]:
    """Normalize only jointly observed pixels. Missing values retain their spatial mask."""
    positions = []
    values = []
    for r in range(rows):
        for c in range(cols):
            pixel = [g[r][c] for g in grids]
            if all(_finite_number(v) for v in pixel) and -1 <= pixel[0] <= 1:
                positions.append((r, c))
                values.append(pixel)
    if not positions:
        return [], []
    limits = [(min(column), max(column)) for column in zip(*values, strict=True)]
    vectors = [
        [
            (value - lo) / (hi - lo) if hi > lo else 0.5
            for value, (lo, hi) in zip(pixel, limits, strict=True)
        ]
        for pixel in values
    ]
    return positions, vectors


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _aligned_aux(
    rows: int, cols: int, aux_grids: dict[str, NdviGrid] | None
) -> dict[str, NdviGrid]:
    """يُبقي فقط الشبكات المساعدة المُتراصفة تماماً مع شبكة NDVI (سقوط آمن للبقيّة)."""
    if not isinstance(aux_grids, dict) or rows == 0 or cols == 0:
        return {}
    out: dict[str, NdviGrid] = {}
    for name, g in aux_grids.items():
        if (
            isinstance(g, list)
            and len(g) == rows
            and all(isinstance(row, list) and len(row) == cols for row in g)
        ):
            out[name] = g
    return out


def _multiindex_rank_labels(
    ndvi_grid: NdviGrid,
    aux: dict[str, NdviGrid],
    rows: int,
    cols: int,
    k: int,
) -> tuple[list[list[int | None]], list[float], list[str]] | None:
    """عنقدة N-بُعديّة → (شبكة تصنيف مرتّبة تصاعديّاً بـNDVI، مراكز NDVI الفعليّة، أسماء الميزات).

    المجموعات تُرتَّب بمتوسّط NDVI **الفعليّ** (لا المعياريّ) فيبقى score/التصنيف متّسقاً مع
    المسار الأحاديّ. المجموعات الفارغة تُسقَط. ``None`` عند تعذّر تكوين مجموعتَين.
    """
    feature_names = ["ndvi", *aux.keys()]
    grids = [ndvi_grid, *aux.values()]
    positions, vectors = _feature_vectors(grids, rows, cols)
    if len(vectors) < 2:
        return None
    centroids = kmeans_nd(vectors, k)
    if len(centroids) < 2:
        return None

    assign: list[int] = [_nearest_vec(v, centroids) for v in vectors]
    members_ndvi: list[list[float]] = [[] for _ in range(len(centroids))]
    for (r, c), j in zip(positions, assign, strict=True):
        members_ndvi[j].append(float(ndvi_grid[r][c]))

    used = [j for j in range(len(centroids)) if members_ndvi[j]]
    if len(used) < 2:
        return None
    used.sort(key=lambda j: sum(members_ndvi[j]) / len(members_ndvi[j]))
    rank_of = {j: rank for rank, j in enumerate(used)}
    centroids_ndvi = [sum(members_ndvi[j]) / len(members_ndvi[j]) for j in used]

    labels: list[list[int | None]] = [[None] * cols for _ in range(rows)]
    for (r, c), j in zip(positions, assign, strict=True):
        labels[r][c] = rank_of[j]
    return labels, centroids_ndvi, feature_names


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
    aux_grids: dict[str, NdviGrid] | None = None,
) -> dict[str, Any] | None:
    """NDVI grid → per-class productivity zones (polygons + score), or None if unusable.

    ``k`` fixes the cluster count; pass ``None`` to auto-select the optimal number of
    management zones via FPI/NCE (Management Zone Analyst, V60.2). ``smooth`` applies an
    8-neighbour majority filter to the per-cell class grid first, enforcing spatial
    contiguity (fewer salt-and-pepper zones) — idempotent on already-contiguous fields.

    ``aux_grids`` (V60.3): optional co-registered feature grids (e.g. ``ndmi``/``reci``/
    ``msavi``/``slope``) clustered *together* with NDVI in a normalized N-D feature space
    — the precision-ag Management Zone Analyst approach (multi-variable, not NDVI-only).
    NDVI stays the master (defines validity + class score). Any misaligned aux grid is
    dropped (fail-safe → NDVI-only). Empty/None ⇒ identical to the pure NDVI path.

    Returns None when the grid is empty/degenerate so the caller can fall back to the
    deterministic strip zoning.
    """
    from .field_boundary_backends import mask_to_polygons

    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    if not cols or any(len(row) != cols for row in grid):
        return None
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

    aligned = _aligned_aux(rows, cols, aux_grids)
    feature_names = ["ndvi"]
    labels: list[list[int | None]]
    centroids_ndvi: list[float]

    multi = _multiindex_rank_labels(grid, aligned, rows, cols, k) if aligned else None
    if multi is not None:
        labels, centroids_ndvi, feature_names = multi
        k_eff = len(centroids_ndvi)
    else:
        centroids = kmeans_1d(flat, k)
        if len(centroids) < 2:
            return None
        k_eff = len(centroids)
        centroids_ndvi = list(centroids)
        # Per-cell class label grid (None where invalid).
        labels = [
            [
                _nearest(float(grid[r][c]), centroids)
                if _finite_number(grid[r][c]) and -1 <= grid[r][c] <= 1
                else None
                for c in range(cols)
            ]
            for r in range(rows)
        ]

    if smooth:
        labels = smooth_label_grid(labels)

    zones: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}
    for rank in range(k_eff):
        mask = [[1 if labels[r][c] == rank else 0 for c in range(cols)] for r in range(rows)]
        polys = mask_to_polygons(mask, bbox, min_area_px=1, exact=True)
        if not polys:
            continue
        cls = _class_for_rank(rank, k_eff)
        score = round((centroids_ndvi[rank] + 1.0) / 2.0, 3)  # NDVI [-1,1] → [0,1]
        for p in polys:
            class_counts[cls] = class_counts.get(cls, 0) + 1
            zones.append(
                {
                    "zone_id": f"pz-{cls}-{class_counts[cls]}",
                    "productivity_class": cls,
                    "score": score,
                    "ndvi_centroid": round(centroids_ndvi[rank], 3),
                    "geometry": {"type": p["type"], "coordinates": p["coordinates"]},
                    "pixel_area": p["pixel_area"],
                }
            )
    if not zones:
        return None
    result: dict[str, Any] = {
        "zones": zones,
        "k_effective": k_eff,
        "cluster_separability": cluster_separability(flat, centroids_ndvi),
        "ndvi_centroids": [round(c, 3) for c in centroids_ndvi],
        "spatially_smoothed": smooth,
        "feature_names": feature_names,
    }
    if recommendation is not None:
        result["zone_count_recommendation"] = recommendation
    return result


# Upper bound on either side of an indicator grid. Clustering here is pure Python and
# auto zone-count selection runs fuzzy c-means for several k, so cost grows with cells;
# anything larger is refused (insufficient_data) rather than clustered.
MAX_GRID_SIDE = 128


def _grid_candidate(src: Any) -> list[Any] | None:
    grid = src.get("ndvi_grid") if isinstance(src, dict) else None
    if isinstance(grid, list) and grid and all(isinstance(r, list) for r in grid):
        return grid
    return None


def grid_within_cap(grid: Any) -> bool:
    """True when ``grid`` has at most ``MAX_GRID_SIDE`` rows and columns."""
    return (
        isinstance(grid, list)
        and len(grid) <= MAX_GRID_SIDE
        and all(isinstance(r, list) and len(r) <= MAX_GRID_SIDE for r in grid)
    )


def ndvi_grid_exceeds_cap(params: dict[str, Any], evidence: dict[str, Any] | None) -> bool:
    """True when the grid :func:`extract_ndvi_grid` would pick was refused for its size."""
    for src in (evidence or {}, params or {}):
        grid = _grid_candidate(src)
        if grid is not None:
            return not grid_within_cap(grid)
    return False


def extract_ndvi_grid(params: dict[str, Any], evidence: dict[str, Any] | None) -> NdviGrid | None:
    """Pull an NDVI grid, evidence first; None if absent, malformed or oversized.

    A grid in the evidence context (from the raster pipeline) always wins: caller- or
    model-supplied ``params["ndvi_grid"]`` is only used when the evidence has none, so a
    tool call cannot override the field's real imagery. A grid larger than
    ``MAX_GRID_SIDE`` on either side is refused without falling back to the other source."""
    for src in (evidence or {}, params or {}):
        grid = _grid_candidate(src)
        if grid is not None:
            return grid if grid_within_cap(grid) else None  # type: ignore[return-value]
    return None


def _grid_source(params, evidence):
    return evidence if _grid_candidate(evidence) is not None else params


def _grid_identity(meta, rows, cols):
    identity = meta.get("grid_identity")
    if not isinstance(identity, dict):
        return None
    crs, affine = identity.get("crs"), identity.get("transform")
    revision = identity.get("geometry_revision")
    if not isinstance(crs, str) or not crs.strip() or type(revision) is not int or revision < 0:
        return None
    if (
        type(identity.get("rows")) is not int
        or type(identity.get("cols")) is not int
        or (identity["rows"], identity["cols"]) != (rows, cols)
    ):
        return None
    if (
        not isinstance(affine, (list, tuple))
        or len(affine) != 6
        or not all(map(_finite_number, affine))
    ):
        return None
    if affine[0] * affine[4] == affine[1] * affine[3]:
        return None
    return crs.strip().upper(), tuple(affine), revision


def _source_ref(meta, name):
    if not isinstance(meta, dict):
        return {}
    if name == "slope":
        asset = meta.get("asset_id")
        return (
            {"asset_id": asset} if isinstance(asset, str) and 0 < len(asset.strip()) <= 256 else {}
        )
    scene, day = meta.get("scene_id"), meta.get("acquisition_date")
    if not isinstance(scene, str) or not 0 < len(scene.strip()) <= 256 or not isinstance(day, str):
        return {}
    try:
        day = date.fromisoformat(day[:10]).isoformat()
    except ValueError:
        return {}
    return {"scene_id": scene, "acquisition_date": day}


def indicator_sources(params, evidence, feature_names):
    source = _grid_source(params, evidence)
    metadata = source.get("grid_metadata") or {}
    if not isinstance(metadata, dict):
        return {}
    return {name: ref for name in feature_names if (ref := _source_ref(metadata.get(name), name))}


def extract_aux_grids(params, evidence, *, ndvi_grid):
    """Accept auxiliary layers from the same owner and acquisition on the same native grid."""
    if not ndvi_grid or not ndvi_grid[0]:
        return None
    rows, cols = len(ndvi_grid), len(ndvi_grid[0])
    source = _grid_source(params, evidence)
    metadata = source.get("grid_metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("ndvi"), dict):
        return None
    master = metadata["ndvi"]
    identity = _grid_identity(master, rows, cols)
    ndvi_source = _source_ref(master, "ndvi")
    if not identity or not ndvi_source:
        return None
    result = {}
    for name, key in _AUX_FEATURE_KEYS:
        meta = metadata.get(name)
        if not isinstance(meta, dict) or identity != _grid_identity(meta, rows, cols):
            continue
        ref = _source_ref(meta, name)
        if not ref or (name != "slope" and ref != ndvi_source):
            continue
        candidate = source.get(key)
        if (
            isinstance(candidate, list)
            and len(candidate) == rows
            and all(isinstance(row, list) and len(row) == cols for row in candidate)
        ):
            result[name] = candidate
    return result or None
