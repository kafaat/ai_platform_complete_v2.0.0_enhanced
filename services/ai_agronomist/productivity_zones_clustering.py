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
    """شبكات ميزات مُتراصفة → متّجهات معياريّة عند خلايا NDVI (السيّد) الصالحة.

    ``grids[0]`` شبكة NDVI (السيّد: يحدّد الصلاحية والتصنيف). كلّ ميزة تُعاير min-max
    إلى [0,1] كي لا يهيمن مقياس واحد (الانحدار 0..90 مقابل NDVI −1..1). القيم المفقودة
    في ميزة مساعدة تُعوَّض بمتوسّط تلك الميزة (محايد) فتبقى تغطية NDVI كاملة. ميزة متدهورة
    (بلا قيم صالحة) ⇒ يُعاد فراغ (سقوط آمن إلى مسار NDVI أحاديّ البُعد لدى المُنادي).
    """
    stats: list[tuple[float, float, float]] = []
    for d, g in enumerate(grids):
        vals: list[float] = []
        for r in range(rows):
            for c in range(cols):
                v = g[r][c]
                if not isinstance(v, (int, float)):
                    continue
                fv = float(v)
                if d == 0:
                    if -1.0 <= fv <= 1.0:
                        vals.append(fv)
                elif math.isfinite(fv):
                    vals.append(fv)
        if not vals:
            return [], []
        stats.append((min(vals), max(vals), sum(vals) / len(vals)))

    positions: list[tuple[int, int]] = []
    vectors: list[list[float]] = []
    for r in range(rows):
        for c in range(cols):
            nd = grids[0][r][c]
            if not (isinstance(nd, (int, float)) and -1.0 <= float(nd) <= 1.0):
                continue
            vec: list[float] = []
            for d, (lo, hi, mean) in enumerate(stats):
                x = grids[d][r][c]
                if d == 0:
                    valid = isinstance(x, (int, float)) and -1.0 <= float(x) <= 1.0
                else:
                    valid = isinstance(x, (int, float)) and math.isfinite(float(x))
                xv = float(x) if valid else mean
                vec.append((xv - lo) / (hi - lo) if hi > lo else 0.5)
            positions.append((r, c))
            vectors.append(vec)
    return positions, vectors


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
                if isinstance(grid[r][c], (int, float))
                else None
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
        score = round((centroids_ndvi[rank] + 1.0) / 2.0, 3)  # NDVI [-1,1] → [0,1]
        for i, p in enumerate(polys):
            zones.append(
                {
                    "zone_id": f"pz-{cls}-{i + 1}",
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


def extract_ndvi_grid(params: dict[str, Any], evidence: dict[str, Any] | None) -> NdviGrid | None:
    """Pull an NDVI grid from params or evidence; None if absent/malformed."""
    for src in (params or {}, evidence or {}):
        grid = src.get("ndvi_grid") if isinstance(src, dict) else None
        if isinstance(grid, list) and grid and all(isinstance(r, list) for r in grid):
            return grid  # type: ignore[return-value]
    return None


def extract_aux_grids(
    params: dict[str, Any],
    evidence: dict[str, Any] | None,
    *,
    ndvi_grid: NdviGrid | None,
) -> dict[str, NdviGrid] | None:
    """Pull co-registered auxiliary feature grids (ndmi/reci/msavi/slope) for V60.3.

    Only grids whose dimensions match the NDVI master are returned; anything malformed
    or mis-sized is silently skipped (fail-safe → NDVI-only clustering). None when no
    aligned aux grid is available, so the caller stays on the pure-NDVI path unchanged.
    """
    if not ndvi_grid:
        return None
    rows = len(ndvi_grid)
    cols = len(ndvi_grid[0]) if rows else 0
    if rows == 0 or cols == 0:
        return None
    out: dict[str, NdviGrid] = {}
    for name, key in _AUX_FEATURE_KEYS:
        for src in (params or {}, evidence or {}):
            grid = src.get(key) if isinstance(src, dict) else None
            if (
                isinstance(grid, list)
                and len(grid) == rows
                and all(isinstance(r, list) and len(r) == cols for r in grid)
            ):
                out[name] = grid  # type: ignore[assignment]
                break
    return out or None
