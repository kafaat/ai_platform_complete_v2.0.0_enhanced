"""Decode tile clip queries. ';' separates positions, '|' rings, and '!' polygons."""

from fastapi import HTTPException


def parse_mask_parts(poly: str | None) -> list | None:
    if not isinstance(poly, str) or not poly:
        return None
    parts = []
    try:
        for polygon in poly.split("!"):
            rings = []
            for ring in polygon.split("|"):
                points = []
                for pair in ring.split(";"):
                    if not pair.strip():
                        continue
                    lng, lat = map(float, pair.split(","))
                    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                        raise ValueError("coordinate out of range")
                    points.append([lng, lat])
                if len({tuple(p) for p in points}) < 3:
                    raise ValueError("ring needs three distinct points")
                if points[-1] != points[0]:
                    points.append(points[0])
                rings.append(points)
            parts.append(rings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid field clip polygon") from exc
    return parts


def parse_poly(poly: str | None) -> dict | None:
    parts = parse_mask_parts(poly)
    if not parts:
        return None
    if len(parts) == 1:
        return {"type": "Polygon", "coordinates": parts[0]}
    return {"type": "MultiPolygon", "coordinates": parts}
