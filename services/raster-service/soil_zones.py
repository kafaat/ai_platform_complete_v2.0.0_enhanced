"""
soil_zones.py — مناطق أخذ عيّنات التربة (تقسيم بصريّ إلى مناطق متجانسة من SoilGrids).

يُكدّس خصائص التربة (طين/رمل/pH/كربون عضويّ) على bbox الحقل، يُطبّعها، يُجمّعها (k-means
نقيّ بـnumpy، تهيئة حتميّة)، ثمّ يُحوّل المناطق إلى مضلّعات GeoJSON عبر
``rasterio.features.shapes``. لكلّ منطقة خصائص متوسّطة تُوجِّه «أين آخذ العيّنة».

صدق صارم: يحتاج مصدر SoilGrids (``SOILGRIDS_DIR``). بلا مصدر/تغطية ⇒ ``features:[]`` +
``computed:false`` + سبب — لا تلفيق مناطق. تحذير إلزاميّ: تقديريّ ~250م، توجيه لا بديل عن المختبر.
"""

from __future__ import annotations

# الخصائص المستعملة في التجميع (متوفّرة غالباً وذات دلالة لأخذ العيّنات).
_ZONE_PROPERTIES: tuple[str, ...] = ("clay", "sand", "phh2o", "soc")


def _kmeans(x, k: int, iters: int = 25):
    """k-means نقيّ بـnumpy بتهيئة حتميّة (بلا عشوائيّة — قابل لإعادة الإنتاج)."""
    import numpy as np

    n = x.shape[0]
    if n <= k:
        return np.arange(n) % k, x.copy()
    idx = np.linspace(0, n - 1, k).astype(int)
    centroids = x[idx].astype("float64").copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d = ((x[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = d.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for j in range(k):
            m = labels == j
            if m.any():
                centroids[j] = x[m].mean(axis=0)
    return labels, centroids


def compute_soil_sampling_zones(
    bbox: list[float] | None, depth: str = "0-5cm", n_zones: int = 3
) -> dict:
    """مناطق تربة متجانسة (GeoJSON) لحقلٍ من SoilGrids — لتقسيم أخذ العيّنات.

    كلّ ``Feature`` منطقة (MultiPolygon) بخصائص: ``zone_id`` وخصائص تربة متوسّطة
    (clay/sand/pH/soc) + صنف قوام إرشاديّ. صدق: بلا مصدر ⇒ ``features:[]`` + سبب.
    """
    import soil_render as _soil

    empty = {"type": "FeatureCollection", "features": [], "computed": False}
    if not _soil.is_source_configured():
        return {**empty, "source": "soilgrids-source-not-configured"}
    if not bbox or len(bbox) != 4:
        return {**empty, "source": "field-bbox-unavailable"}
    try:
        import numpy as np
        import rasterio
        from rasterio.features import shapes as rio_shapes
        from rasterio.windows import from_bounds as win_from_bounds
    except Exception:  # noqa: BLE001
        return {**empty, "source": "runtime-libs-missing"}

    depth = _soil.normalize_depth(depth)
    n_zones = max(2, min(int(n_zones), 5))

    # اقرأ كلّ خاصّيّة على نفس نافذة bbox (شبكة SoilGrids مشتركة ⇒ أشكال متطابقة).
    layers: dict[str, object] = {}
    ref_shape = None
    ref_transform = None
    for prop in _ZONE_PROPERTIES:
        path = _soil.soil_raster_path(prop, depth)
        if path is None:
            continue
        try:
            with rasterio.open(path) as src:
                window = win_from_bounds(*bbox, transform=src.transform)
                arr = src.read(1, window=window, masked=True).filled(np.nan).astype("float32")
                if arr.size == 0:
                    continue
                meta = _soil.SOIL_PROPERTIES[prop]
                real = arr / float(meta["div"])
                if ref_shape is None:
                    ref_shape = real.shape
                    ref_transform = src.window_transform(window)
                if real.shape == ref_shape:
                    layers[prop] = real
        except Exception:  # noqa: BLE001
            continue

    if len(layers) < 2 or ref_shape is None:
        return {**empty, "source": "field-outside-source"}

    rows, cols = ref_shape
    stack = np.stack([layers[p] for p in layers], axis=-1)  # (rows, cols, d)
    valid = np.isfinite(stack).all(axis=-1)
    if valid.sum() < n_zones:
        return {**empty, "source": "insufficient-soil-pixels"}

    feats = stack[valid]  # (m, d)
    mean = feats.mean(axis=0)
    std = feats.std(axis=0)
    std[std == 0] = 1.0
    z = (feats - mean) / std  # تطبيع z لكلّ خاصّيّة (وزن متساوٍ)
    labels_flat, _ = _kmeans(z, n_zones)

    # شبكة تسميات صحيحة (‑1 خارج البيانات) للتحويل إلى مضلّعات.
    label_grid = np.full(ref_shape, -1, dtype="int32")
    label_grid[valid] = labels_flat.astype("int32")

    # اجمع مضلّعات كلّ منطقة + خصائصها المتوسّطة.
    zone_geoms: dict[int, list] = {z_id: [] for z_id in range(n_zones)}
    for geom, val in rio_shapes(label_grid, mask=(label_grid >= 0), transform=ref_transform):
        z_id = int(val)
        if 0 <= z_id < n_zones:
            zone_geoms[z_id].append(geom["coordinates"])

    features = []
    zone_letters = ["A", "B", "C", "D", "E"]
    for z_id in range(n_zones):
        polys = zone_geoms.get(z_id) or []
        if not polys:
            continue
        cell_mask = label_grid == z_id
        zprops: dict[str, float] = {}
        for p in layers:
            vals = layers[p][cell_mask]
            vals = vals[np.isfinite(vals)]
            if vals.size:
                zprops[p] = round(float(vals.mean()), 2)
        texture = _soil.usda_texture_class(zprops.get("clay"), zprops.get("sand"))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone_id": zone_letters[z_id] if z_id < len(zone_letters) else str(z_id),
                    "soil": zprops,
                    "texture_class": texture,
                    "sampling_hint": "خذ عيّنة مركّبة ممثّلة من هذه المنطقة المتجانسة.",
                },
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "computed": True,
        "source": "soilgrids",
        "depth": depth,
        "zones": len(features),
        "properties_used": list(layers.keys()),
        "disclaimer": _soil.DISCLAIMER_AR,
    }
