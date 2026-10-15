"""Vegetation-index rasters: per-field coverage computed from pixels, the same
way AgroOmni derives area-ratio answers from segmentation masks — plus a PNG
per question so items can be used as image + question VQA.

Input format (no GDAL needed): a directory of JSON sidecars, each pointing at a
2-D float .npy array:
  {"array": "savi_2026-02-15.npy", "index": "SAVI", "date": "2026-02-15",
   "crs": "EPSG:32638", "transform": [x0, dx, 0, y0, 0, dy],
   "nodata": -9999, "scene_id": "S2B_MSIL2A_...", "synthetic": false}
`transform` is the GDAL geotransform (north-up only).

Images are a two-class threshold map (the exact quantity the question asks
about), the field outline is drawn on the pixels just OUTSIDE the polygon so
no counted pixel is hidden, and north arrow / scale bar / legend sit in bands
outside the map. After writing, the PNG is decoded again and the answer is
recomputed from its pixels; items whose image does not reproduce the answer
are dropped (information-sufficiency check, not a vision test).
"""
from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path

from .facts import RasterLayer, to_date
from .geo import RAD, Geometry, LocalFrame, parse_epsg, utm_forward


def load_rasters(directory: str | None) -> list[RasterLayer]:
    if not directory:
        return []
    out = []
    for side in sorted(Path(directory).glob("*.json")):
        meta = json.loads(side.read_text(encoding="utf-8"))
        if "array" not in meta:
            continue
        tr = tuple(float(v) for v in meta["transform"])
        if len(tr) != 6 or tr[2] != 0 or tr[4] != 0:
            raise ValueError(f"{side.name}: only north-up geotransforms are supported")
        parse_epsg(meta.get("crs", "EPSG:4326"))  # validates
        out.append(RasterLayer(path=str(side.parent / meta["array"]), index_name=str(meta["index"]).upper(),
                               date=to_date(meta["date"]), crs=meta.get("crs", "EPSG:4326"), transform=tr,
                               nodata=meta.get("nodata"), scene_id=meta.get("scene_id"),
                               synthetic=bool(meta.get("synthetic", False)),
                               role=str(meta.get("role", "all")), product_version=meta.get("product_version")))
        if out[-1].role not in ("all", "timeline-only"):
            raise ValueError(f"{side.name}: role must be 'all' or 'timeline-only'")
    return out


def _proj(layer: RasterLayer):
    kind, zone, north = parse_epsg(layer.crs)
    if kind == "geographic":
        return lambda lon, lat: (lon, lat)
    return lambda lon, lat: utm_forward(lon, lat, zone, north)


def pixel_size_m(layer: RasterLayer, geom: Geometry) -> float:
    kind, _, _ = parse_epsg(layer.crs)
    dx = abs(layer.transform[1])
    if kind == "utm":
        return dx
    lon, lat = geom.centroid
    fr = LocalFrame(lon, lat)
    return dx * RAD * fr.N0 * math.cos(lat * RAD)


def _window_mask(layer: RasterLayer, geom: Geometry, pad_frac: float = 0.0):
    """Pixel window around the polygon and a mask of pixel centres strictly inside it."""
    import numpy as np

    proj = _proj(layer)
    polys = [[[proj(lon, lat) for lon, lat in ring] for ring in poly] for poly in geom.polygons]
    xs = [x for poly in polys for ring in poly for x, _ in ring]
    ys = [y for poly in polys for ring in poly for _, y in ring]
    padx, pady = (max(xs) - min(xs)) * pad_frac, (max(ys) - min(ys)) * pad_frac
    x0, dx, _, y0, _, dy = layer.transform
    h, w = layer.array().shape
    c0 = max(0, int(math.floor((min(xs) - padx - x0) / dx)))
    c1 = min(w, int(math.ceil((max(xs) + padx - x0) / dx)) + 1)
    ra, rb = (max(ys) + pady - y0) / dy, (min(ys) - pady - y0) / dy
    r0 = max(0, int(math.floor(min(ra, rb))))
    r1 = min(h, int(math.ceil(max(ra, rb))) + 1)
    if c0 >= c1 or r0 >= r1:
        return None
    X, Y = np.meshgrid(x0 + (np.arange(c0, c1) + 0.5) * dx, y0 + (np.arange(r0, r1) + 0.5) * dy)
    inside = np.zeros(X.shape, dtype=bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        for poly in polys:
            poly_in = np.zeros(X.shape, dtype=bool)
            for ring in poly:
                for i in range(len(ring)):
                    xi, yi = ring[i]
                    xj, yj = ring[i - 1]
                    poly_in ^= ((yi > Y) != (yj > Y)) & (X < (xj - xi) * (Y - yi) / (yj - yi) + xi)
            inside |= poly_in
    full_cover = (min(xs) >= x0 and max(xs) <= x0 + w * dx and
                  min(ys) >= min(y0, y0 + h * dy) and max(ys) <= max(y0, y0 + h * dy))
    return {"r0": r0, "r1": r1, "c0": c0, "c1": c1, "inside": inside, "X": X, "Y": Y,
            "proj": proj, "full_cover": full_cover}


def _valid(layer, vals):
    import numpy as np
    v = np.isfinite(vals)
    if layer.nodata is not None:
        v &= vals != layer.nodata
    return v


def _quadrant_masks(wm, geom):
    cx, cy = wm["proj"](*geom.centroid)
    east, north = wm["X"] >= cx, wm["Y"] >= cy
    return {"NE": east & north, "SE": east & ~north, "SW": ~east & ~north, "NW": ~east & north}


def _fractions(inside, valid, above, quads) -> dict:
    n_valid = int((inside & valid).sum())
    out = {"frac_above": (int((inside & above).sum()) / n_valid) if n_valid else None, "quadrants": {}}
    for name, m in quads.items():
        nv = int((inside & valid & m).sum())
        out["quadrants"][name] = {"valid": nv, "frac_above": (int((inside & above & m).sum()) / nv) if nv else None}
    return out


SECTOR_KEYS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _polar(wm, geom: Geometry, layer: RasterLayer, inside, valid, above, n_rings: int = 5) -> dict:
    """Ring x sector coverage around a pivot's centre.

    Rings: n equal-width radial bands out to the equivalent radius sqrt(A/π)
    (pixels beyond it fall in the outer ring). Sectors: 8 × 45°, centred on
    N, NE, E, … (azimuth clockwise from north). Fractions are of valid pixels.
    """
    import numpy as np
    kind, _, _ = parse_epsg(layer.crs)
    cx, cy = wm["proj"](*geom.centroid)
    dx, dy = wm["X"] - cx, wm["Y"] - cy
    if kind == "geographic":
        lat = geom.centroid[1]
        dx, dy = dx * 111320.0 * math.cos(lat * RAD), dy * 110574.0
    r = np.hypot(dx, dy)
    az = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0
    R = math.sqrt(geom.area_m2 / math.pi)
    ring = np.minimum((r / R * n_rings).astype(int), n_rings - 1)
    sector = (((az + 22.5) % 360.0) // 45.0).astype(int)
    iv = inside & valid

    def frac(mask):
        n_in = int((inside & mask).sum())
        nv = int((iv & mask).sum())
        return {"pixels": n_in, "valid": nv, "valid_frac": (nv / n_in) if n_in else 0.0,
                "frac_above": (int((iv & above & mask).sum()) / nv) if nv else None}
    n_in = int(inside.sum())
    nv = int(iv.sum())
    return {
        "field": {"pixels": n_in, "valid": nv, "valid_frac": (nv / n_in) if n_in else 0.0,
                  "frac_above": (int((iv & above).sum()) / nv) if nv else None},
        "rings": [dict(frac(ring == k), r_from=round(k * R / n_rings, 1), r_to=round((k + 1) * R / n_rings, 1))
                  for k in range(n_rings)],
        "sectors": {SECTOR_KEYS[k]: frac(sector == k) for k in range(8)},
        "rest_of_field": {SECTOR_KEYS[k]: frac(sector != k) for k in range(8)},
        "equivalent_radius_m": round(R, 1),
    }


def polar_stats(layer: RasterLayer, geom: Geometry, threshold: float, n_rings: int = 5) -> dict | None:
    """Ring x sector statistics of a pivot on one layer (None if the layer does not cover it)."""
    wm = _window_mask(layer, geom)
    if wm is None or int(wm["inside"].sum()) == 0 or not wm["full_cover"]:
        return None
    vals = layer.array()[wm["r0"]:wm["r1"], wm["c0"]:wm["c1"]]
    valid = _valid(layer, vals)
    return _polar(wm, geom, layer, wm["inside"], valid, valid & (vals >= threshold), n_rings)


def polygon_stats(layer: RasterLayer, geom: Geometry, threshold: float) -> dict | None:
    """Coverage statistics of a field polygon on one raster layer (None if off-raster)."""
    wm = _window_mask(layer, geom)
    if wm is None or int(wm["inside"].sum()) == 0:
        return None
    inside = wm["inside"]
    vals = layer.array()[wm["r0"]:wm["r1"], wm["c0"]:wm["c1"]]
    valid = _valid(layer, vals)
    fr = _fractions(inside, valid, valid & (vals >= threshold), _quadrant_masks(wm, geom))
    n_poly = int(inside.sum())
    n_valid = int((inside & valid).sum())
    return {"pixels_in_polygon": n_poly, "valid_pixels": n_valid, "valid_frac": n_valid / n_poly,
            "frac_above": fr["frac_above"], "quadrants": fr["quadrants"],
            "mean": float(vals[inside & valid].mean()) if n_valid else None,
            "full_cover": wm["full_cover"], "pixel_size": pixel_size_m(layer, geom)}


# ───────────────────────── PNG rendering + verification ─────────────────────────

def scale_bar_m(layer: RasterLayer, geom: Geometry) -> int:
    """Largest of 10/20/50/100/200/500/1000 m not wider than 30 % of the rendered window."""
    wm = _window_mask(layer, geom, pad_frac=0.15)
    width_m = (wm["c1"] - wm["c0"]) * pixel_size_m(layer, geom) if wm else 0
    fits = [b for b in (10, 20, 50, 100, 200, 500, 1000) if b <= 0.3 * width_m]
    return fits[-1] if fits else 10


GREEN, BROWN, GRAY = (40, 140, 50), (175, 135, 85), (190, 190, 190)
EDGE = (255, 222, 0)        # SAHOOL yellow #FFDE00, drawn outside the polygon
BAND, WHITE = (35, 35, 35), (255, 255, 255)


def _png_bytes(rgb) -> bytes:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[i].tobytes() for i in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def decode_png(data: bytes):
    """Decode an 8-bit RGB, non-interlaced PNG with filter type 0 rows (as written here)."""
    import numpy as np
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat = 8, b""
    w = h = 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = 1 + 3 * w
    rows = [raw[i * stride:(i + 1) * stride] for i in range(h)]
    if any(r[0] != 0 for r in rows):
        raise ValueError("unsupported PNG filter")
    return np.frombuffer(b"".join(r[1:] for r in rows), dtype=np.uint8).reshape(h, w, 3)


def render_threshold_png(layer: RasterLayer, geom: Geometry, threshold: float, path: str, min_size: int = 360) -> dict | None:
    """Write the two-class map and return the fractions recomputed from the decoded PNG."""
    import numpy as np
    wm = _window_mask(layer, geom, pad_frac=0.15)
    if wm is None:
        return None
    vals = layer.array()[wm["r0"]:wm["r1"], wm["c0"]:wm["c1"]].astype(float)
    valid = _valid(layer, vals)
    above = valid & (vals >= threshold)
    ins = wm["inside"]
    mh, mw = ins.shape
    rgb = np.zeros((mh, mw, 3), dtype=np.uint8)
    rgb[:] = BROWN
    rgb[above] = GREEN
    rgb[~valid] = GRAY
    pad = np.pad(ins, 1, constant_values=False)
    dil = np.zeros_like(ins)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            dil |= pad[1 + dr:1 + dr + mh, 1 + dc:1 + dc + mw]
    rgb[dil & ~ins] = EDGE                         # outline on outside pixels only
    s = max(1, int(math.ceil(min_size / max(mh, mw))))
    big = rgb.repeat(s, axis=0).repeat(s, axis=1)
    top = bottom = 30
    W = big.shape[1]
    canvas = np.zeros((big.shape[0] + top + bottom, W, 3), dtype=np.uint8)
    canvas[:] = BAND
    canvas[top:top + big.shape[0]] = big
    for r in range(18):                            # north arrow (white triangle) in the top band
        half = r // 2
        canvas[6 + r, 16 - half:17 + half] = WHITE
    px_m = pixel_size_m(layer, geom)
    bar_m = scale_bar_m(layer, geom)
    bar = int(round(bar_m / px_m * s))             # scale bar in the bottom band
    y = top + big.shape[0] + 12
    canvas[y:y + 6, 10:10 + bar] = WHITE
    for k, col in enumerate((GREEN, BROWN, GRAY)):  # legend swatches
        x = W - 30 - 26 * k
        canvas[y - 4:y + 10, x:x + 16] = col
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(_png_bytes(np.ascontiguousarray(canvas)))

    # re-read and recompute from the image pixels
    img = decode_png(Path(path).read_bytes())[top:top + big.shape[0]:s, ::s][:mh, :mw]
    is_green = np.all(img == GREEN, axis=-1)
    is_brown = np.all(img == BROWN, axis=-1)
    fr = _fractions(ins, is_green | is_brown, is_green, _quadrant_masks(wm, geom))
    polar = _polar(wm, geom, layer, ins, is_green | is_brown, is_green)
    return {"png": str(path), "width": int(W), "height": int(canvas.shape[0]), "scale": s,
            "scale_bar_m": bar_m, "scale_bar_px": bar, "pixel_size_m": px_m, "decoded": fr, "decoded_polar": polar}
