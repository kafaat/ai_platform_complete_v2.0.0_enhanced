"""
soil_zones.py — مناطق أخذ عيّنات التربة + نقاط العيّنات (من SoilGrids).

يُكدّس خصائص التربة (طين/رمل/pH/كربون عضويّ) على bbox الحقل، يُطبّعها، يُجمّعها (k-means
نقيّ بـnumpy، تهيئة حتميّة)، ثمّ:
  • ``compute_soil_sampling_zones`` → مضلّعات GeoJSON لكلّ منطقة (rasterio.features.shapes).
  • ``compute_soil_sampling_points`` → نقطة/نقاط تمثيليّة لكلّ منطقة (مركز البكسلات) —
    تُجيب «أين آخذ العيّنة» من تجميعٍ فعليّ لخصائص التربة (لا نقاط هندسيّة عشوائيّة).

صدق صارم: يحتاج مصدر SoilGrids. بلا مصدر/تغطية ⇒ ``features:[]`` + ``computed:false`` + سبب —
لا تلفيق. تحذير إلزاميّ: تقديريّ ~250م، توجيه لا بديل عن المختبر.
"""

from __future__ import annotations

_ZONE_PROPERTIES: tuple[str, ...] = ("clay", "sand", "phh2o", "soc")
_ZONE_LETTERS = ["A", "B", "C", "D", "E"]
_LAB_TESTS = ["pH", "EC", "OM", "NPK", "texture"]


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


def _cluster_field_soil(bbox, depth: str, n_zones: int):
    """يقرأ خصائص التربة على bbox ويجمّعها. يُرجِع dict (نجاح) أو ``{"error": <source>}``.

    مصدر واحد للحقيقة للمناطق والنقاط: نفس القراءة/التطبيع/التجميع.
    """
    import soil_render as _soil

    if not _soil.is_source_configured():
        return {"error": "soilgrids-source-not-configured"}
    if not bbox or len(bbox) != 4:
        return {"error": "field-bbox-unavailable"}
    try:
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds as win_from_bounds
    except Exception:  # noqa: BLE001
        return {"error": "runtime-libs-missing"}

    depth = _soil.normalize_depth(depth)
    n_zones = max(2, min(int(n_zones), 5))

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
                real = arr / float(_soil.SOIL_PROPERTIES[prop]["div"])
                if ref_shape is None:
                    ref_shape = real.shape
                    ref_transform = src.window_transform(window)
                if real.shape == ref_shape:
                    layers[prop] = real
        except Exception:  # noqa: BLE001
            continue

    if len(layers) < 2 or ref_shape is None:
        return {"error": "field-outside-source"}

    stack = np.stack([layers[p] for p in layers], axis=-1)
    valid = np.isfinite(stack).all(axis=-1)
    if valid.sum() < n_zones:
        return {"error": "insufficient-soil-pixels"}

    feats = stack[valid]
    mean = feats.mean(axis=0)
    std = feats.std(axis=0)
    std[std == 0] = 1.0
    labels_flat, _ = _kmeans((feats - mean) / std, n_zones)

    label_grid = np.full(ref_shape, -1, dtype="int32")
    label_grid[valid] = labels_flat.astype("int32")
    return {
        "layers": layers,
        "label_grid": label_grid,
        "transform": ref_transform,
        "depth": depth,
        "n_zones": n_zones,
    }


def _zone_props(layers, cell_mask):
    import numpy as np
    import soil_render as _soil

    out: dict[str, float] = {}
    for p in layers:
        vals = layers[p][cell_mask]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            out[p] = round(float(vals.mean()), 2)
    texture = _soil.usda_texture_class(out.get("clay"), out.get("sand"))
    return out, texture


def compute_soil_sampling_zones(
    bbox: list[float] | None, depth: str = "0-5cm", n_zones: int = 3
) -> dict:
    """مناطق تربة متجانسة (GeoJSON MultiPolygon) — لتقسيم أخذ العيّنات."""
    import soil_render as _soil

    empty = {"type": "FeatureCollection", "features": [], "computed": False}
    c = _cluster_field_soil(bbox, depth, n_zones)
    if "error" in c:
        return {**empty, "source": c["error"]}
    from rasterio.features import shapes as rio_shapes

    label_grid = c["label_grid"]
    zone_geoms: dict[int, list] = {z_id: [] for z_id in range(c["n_zones"])}
    for geom, val in rio_shapes(label_grid, mask=(label_grid >= 0), transform=c["transform"]):
        z_id = int(val)
        if 0 <= z_id < c["n_zones"]:
            zone_geoms[z_id].append(geom["coordinates"])

    features = []
    for z_id in range(c["n_zones"]):
        polys = zone_geoms.get(z_id) or []
        if not polys:
            continue
        zprops, texture = _zone_props(c["layers"], label_grid == z_id)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone_id": _ZONE_LETTERS[z_id] if z_id < len(_ZONE_LETTERS) else str(z_id),
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
        "depth": c["depth"],
        "zones": len(features),
        "properties_used": list(c["layers"].keys()),
        "disclaimer": _soil.DISCLAIMER_AR,
    }


def compute_soil_sampling_points(
    bbox: list[float] | None, depth: str = "0-5cm", n_zones: int = 3, samples_per_zone: int = 1
) -> dict:
    """نقاط عيّنات تمثيليّة (GeoJSON Point) — مركز كلّ منطقة k-means + سبب اختيارها.

    تُجيب «أين آخذ العيّنة» من تجميعٍ فعليّ لخصائص التربة. صدق: بلا مصدر ⇒ ``features:[]``
    + ``computed:false`` — لا نقاط مُلفَّقة. (بديل أصدق من نقاط هندسيّة عشوائيّة.)
    """
    import numpy as np
    import soil_render as _soil

    empty = {"type": "FeatureCollection", "features": [], "computed": False}
    c = _cluster_field_soil(bbox, depth, n_zones)
    if "error" in c:
        return {**empty, "source": c["error"]}
    label_grid = c["label_grid"]
    transform = c["transform"]
    samples_per_zone = max(1, min(int(samples_per_zone), 3))

    features = []
    for z_id in range(c["n_zones"]):
        cell_mask = label_grid == z_id
        rr, cc = np.where(cell_mask)
        if rr.size == 0:
            continue
        zprops, texture = _zone_props(c["layers"], cell_mask)
        zone_letter = _ZONE_LETTERS[z_id] if z_id < len(_ZONE_LETTERS) else str(z_id)
        # نقاط ممثّلة: المركز أوّلاً ثمّ أبعد نقاط عن المركز (تباعُد داخل المنطقة).
        cr, cc0 = rr.mean(), cc.mean()
        order = np.argsort(-((rr - cr) ** 2 + (cc - cc0) ** 2))  # الأبعد أوّلاً للتنويع
        picks = [(int(cr), int(cc0))]
        for k in order:
            if len(picks) >= samples_per_zone:
                break
            picks.append((int(rr[k]), int(cc[k])))
        reason = f"منطقة {zone_letter}"
        if texture:
            reason += f" — {texture}"
        if "phh2o" in zprops:
            reason += f" · pH≈{zprops['phh2o']}"
        for i, (r, col) in enumerate(picks[:samples_per_zone], start=1):
            lon, lat = transform * (col + 0.5, r + 0.5)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]},
                    "properties": {
                        "point_id": f"soil_{zone_letter}{i}",
                        "zone_id": zone_letter,
                        "depth_cm": "0-30",
                        "tests": _LAB_TESTS,
                        "soil": zprops,
                        "reason_ar": reason,
                        "confidence": "advisory",
                    },
                }
            )
    return {
        "type": "FeatureCollection",
        "features": features,
        "computed": True,
        "source": "soilgrids-zone-centroids",
        "depth": c["depth"],
        "zones": c["n_zones"],
        "disclaimer": _soil.DISCLAIMER_AR,
    }
