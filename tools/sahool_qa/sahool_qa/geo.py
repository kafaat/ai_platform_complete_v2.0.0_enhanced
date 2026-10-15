"""Pure-Python geodesy for field-scale geometry (no shapely / pyproj needed).

* Distances and azimuths: Vincenty inverse on WGS84 (matches PostGIS geography
  ST_Distance to well under a metre).
* Areas, perimeters, centroids, hulls: a local sinusoidal (equal-area) frame
  centred on the geometry. Relative area error is ~1e-4 for farms a few km
  across; geometries wider than ~50 km are flagged by `extent_warning`.
* UTM forward projection (Krüger series, mm-level) so polygons can be matched
  against Sentinel-2 rasters delivered in EPSG:326xx / 327xx.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

A = 6378137.0
F = 1 / 298.257223563
B = A * (1 - F)
E2 = F * (2 - F)
RAD = math.pi / 180.0

Ring = list[tuple[float, float]]  # [(lon, lat), ...] closed or open
PolygonRings = list[Ring]  # exterior first, then holes


# ─────────────────────────── distances ────────────────────────────


def vincenty_inverse(lon1: float, lat1: float, lon2: float, lat2: float) -> tuple[float, float]:
    """Ellipsoidal distance (m) and initial azimuth (deg, 0=N clockwise)."""
    if abs(lon1 - lon2) < 1e-12 and abs(lat1 - lat2) < 1e-12:
        return 0.0, 0.0
    L = (lon2 - lon1) * RAD
    U1 = math.atan((1 - F) * math.tan(lat1 * RAD))
    U2 = math.atan((1 - F) * math.tan(lat2 * RAD))
    sinU1, cosU1, sinU2, cosU2 = math.sin(U1), math.cos(U1), math.sin(U2), math.cos(U2)
    lam = L
    for _ in range(200):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(cosU2 * sin_lam, cosU1 * sinU2 - sinU1 * cosU2 * cos_lam)
        if sin_sigma == 0:
            return 0.0, 0.0
        cos_sigma = sinU1 * sinU2 + cosU1 * cosU2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cosU1 * cosU2 * sin_lam / sin_sigma
        cos2_alpha = 1 - sin_alpha**2
        cos2_sm = cos_sigma - 2 * sinU1 * sinU2 / cos2_alpha if cos2_alpha else 0.0
        C = F / 16 * cos2_alpha * (4 + F * (4 - 3 * cos2_alpha))
        lam_prev = lam
        lam = L + (1 - C) * F * sin_alpha * (
            sigma + C * sin_sigma * (cos2_sm + C * cos_sigma * (-1 + 2 * cos2_sm**2))
        )
        if abs(lam - lam_prev) < 1e-12:
            break
    else:  # near-antipodal: fall back to haversine (never happens at farm scale)
        return haversine(lon1, lat1, lon2, lat2), _planar_bearing(lon1, lat1, lon2, lat2)
    u2 = cos2_alpha * (A**2 - B**2) / B**2
    Ak = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    Bk = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    d_sigma = (
        Bk
        * sin_sigma
        * (
            cos2_sm
            + Bk
            / 4
            * (
                cos_sigma * (-1 + 2 * cos2_sm**2)
                - Bk / 6 * cos2_sm * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos2_sm**2)
            )
        )
    )
    dist = B * Ak * (sigma - d_sigma)
    az = math.atan2(cosU2 * math.sin(lam), cosU1 * sinU2 - sinU1 * cosU2 * math.cos(lam))
    return dist, (math.degrees(az) + 360) % 360


def haversine(lon1, lat1, lon2, lat2, r: float = 6371008.8) -> float:
    p1, p2 = lat1 * RAD, lat2 * RAD
    dp, dl = p2 - p1, (lon2 - lon1) * RAD
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _planar_bearing(lon1, lat1, lon2, lat2) -> float:
    x = (lon2 - lon1) * math.cos((lat1 + lat2) / 2 * RAD)
    y = lat2 - lat1
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ─────────────────────────── local frame ───────────────────────────


class LocalFrame:
    """Equal-area sinusoidal frame around (lon0, lat0) using WGS84 radii."""

    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0 = lon0, lat0
        s = math.sin(lat0 * RAD)
        w = 1 - E2 * s * s
        self.N0 = A / math.sqrt(w)
        self.M0 = A * (1 - E2) / w**1.5

    def fwd(self, lon: float, lat: float) -> tuple[float, float]:
        return (
            (lon - self.lon0) * RAD * self.N0 * math.cos(lat * RAD),
            (lat - self.lat0) * RAD * self.M0,
        )

    def inv(self, x: float, y: float) -> tuple[float, float]:
        lat = self.lat0 + y / (self.M0 * RAD)
        lon = self.lon0 + x / (self.N0 * math.cos(lat * RAD) * RAD)
        return lon, lat


# ─────────────────────────── geometry ──────────────────────────────


@dataclass
class Geometry:
    """Polygon or MultiPolygon in lon/lat (EPSG:4326)."""

    polygons: list[PolygonRings]
    _frame: LocalFrame | None = field(default=None, repr=False)
    _xy: list | None = field(default=None, repr=False)

    # -- construction --
    @staticmethod
    def from_geojson(obj) -> Geometry | None:
        if obj is None:
            return None
        if isinstance(obj, (str, bytes)):
            obj = json.loads(obj)
        if obj.get("type") == "Feature":
            obj = obj.get("geometry")
            if obj is None:
                return None
        t = obj.get("type")
        if t == "Polygon":
            polys = [obj["coordinates"]]
        elif t == "MultiPolygon":
            polys = obj["coordinates"]
        else:
            return None
        clean = []
        for poly in polys:
            rings = []
            for ring in poly:
                pts = [(float(p[0]), float(p[1])) for p in ring]
                if len(pts) >= 2 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                rings.append(pts)
            clean.append(rings)
        return Geometry(clean)

    def to_geojson(self, ndigits: int = 6) -> dict:
        def ring_out(r):
            pts = [[round(x, ndigits), round(y, ndigits)] for x, y in r]
            return pts + [pts[0]] if pts else pts

        if len(self.polygons) == 1:
            return {"type": "Polygon", "coordinates": [ring_out(r) for r in self.polygons[0]]}
        return {
            "type": "MultiPolygon",
            "coordinates": [[ring_out(r) for r in p] for p in self.polygons],
        }

    # -- helpers --
    def all_points(self):
        for poly in self.polygons:
            for ring in poly:
                yield from ring

    @property
    def frame(self) -> LocalFrame:
        if self._frame is None:
            x0, y0, x1, y1 = self.bbox
            self._frame = LocalFrame((x0 + x1) / 2, (y0 + y1) / 2)
        return self._frame

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs, ys = zip(*self.all_points(), strict=False)
        return min(xs), min(ys), max(xs), max(ys)

    def _xy_rings(self):
        if self._xy is None:
            fr = self.frame
            self._xy = [
                [[fr.fwd(lon, lat) for lon, lat in ring] for ring in poly] for poly in self.polygons
            ]
        return self._xy

    @staticmethod
    def _ring_signed_area(r) -> float:
        s = 0.0
        n = len(r)
        for i in range(n):
            x1, y1 = r[i]
            x2, y2 = r[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return s / 2

    # -- metrics --
    @property
    def area_m2(self) -> float:
        total = 0.0
        for poly in self._xy_rings():
            for k, ring in enumerate(poly):
                a = abs(self._ring_signed_area(ring))
                total += a if k == 0 else -a
        return total

    @property
    def perimeter_m(self) -> float:
        p = 0.0
        for poly in self._xy_rings():
            for ring in poly:
                n = len(ring)
                for i in range(n):
                    x1, y1 = ring[i]
                    x2, y2 = ring[(i + 1) % n]
                    p += math.hypot(x2 - x1, y2 - y1)
        return p

    @property
    def centroid(self) -> tuple[float, float]:
        cx = cy = at = 0.0
        for poly in self._xy_rings():
            for k, ring in enumerate(poly):
                a = self._ring_signed_area(ring)
                if a == 0:
                    continue
                sx = sy = 0.0
                n = len(ring)
                for i in range(n):
                    x1, y1 = ring[i]
                    x2, y2 = ring[(i + 1) % n]
                    c = x1 * y2 - x2 * y1
                    sx += (x1 + x2) * c
                    sy += (y1 + y2) * c
                gx, gy = sx / (6 * a), sy / (6 * a)
                w = abs(a) if k == 0 else -abs(a)
                cx += gx * w
                cy += gy * w
                at += w
        if at == 0:
            xs, ys = zip(*self.all_points(), strict=False)
            return sum(xs) / len(xs), sum(ys) / len(ys)
        return self.frame.inv(cx / at, cy / at)

    @property
    def compactness(self) -> float:
        """Polsby–Popper 4πA/P² (1.0 = circle, 0.785 = square)."""
        p = self.perimeter_m
        return 4 * math.pi * self.area_m2 / (p * p) if p else 0.0

    def min_area_rect(self) -> tuple[float, float, float]:
        """(rect_area_m2, short_side_m, long_side_m) of the minimum-area bounding rectangle."""
        pts = [pt for poly in self._xy_rings() for pt in poly[0]]
        hull = convex_hull(pts)
        if len(hull) < 3:
            return 0.0, 0.0, 0.0
        best = None
        n = len(hull)
        for i in range(n):
            x1, y1 = hull[i]
            x2, y2 = hull[(i + 1) % n]
            ang = math.atan2(y2 - y1, x2 - x1)
            c, s = math.cos(-ang), math.sin(-ang)
            rx = [x * c - y * s for x, y in hull]
            ry = [x * s + y * c for x, y in hull]
            w, h = max(rx) - min(rx), max(ry) - min(ry)
            if best is None or w * h < best[0]:
                best = (w * h, min(w, h), max(w, h))
        return best

    def contains(self, lon: float, lat: float) -> bool:
        """ST_Contains semantics: a point on an edge, a vertex or a hole ring is NOT contained."""
        if self.on_boundary(lon, lat):
            return False
        return any(_point_in_rings(lon, lat, poly) for poly in self.polygons)

    def on_boundary(self, lon: float, lat: float, eps_deg: float = 1e-12) -> bool:
        for poly in self.polygons:
            for ring in poly:
                n = len(ring)
                for i in range(n):
                    (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
                    dx, dy = bx - ax, by - ay
                    seg2 = dx * dx + dy * dy
                    cross = dx * (lat - ay) - dy * (lon - ax)
                    dot = (lon - ax) * dx + (lat - ay) * dy
                    if (
                        abs(cross) <= eps_deg * math.sqrt(seg2)
                        and -eps_deg <= dot <= seg2 + eps_deg
                    ):
                        return True
        return False

    def boundary_distance_m(self, lon: float, lat: float) -> float:
        """Distance in metres from a point to the nearest edge (any ring)."""
        px, py = self.frame.fwd(lon, lat)
        best = math.inf
        for poly in self._xy_rings():
            for ring in poly:
                n = len(ring)
                for i in range(n):
                    (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
                    dx, dy = bx - ax, by - ay
                    seg2 = dx * dx + dy * dy
                    t = (
                        0.0
                        if seg2 == 0
                        else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                    )
                    best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
        return best

    def extent_warning(self) -> bool:
        x0, y0, x1, y1 = self.bbox
        return vincenty_inverse(x0, y0, x1, y1)[0] > 50_000

    def validity_problems(self) -> list[str]:
        probs = []
        for pi, poly in enumerate(self.polygons):
            for ri, ring in enumerate(poly):
                if len(ring) < 3:
                    probs.append(f"polygon {pi} ring {ri}: fewer than 3 distinct vertices")
                    continue
                if abs(self._ring_signed_area([self.frame.fwd(*p) for p in ring])) < 1e-6:
                    probs.append(f"polygon {pi} ring {ri}: zero area")
                if len(ring) <= 400 and _self_intersects(ring):
                    probs.append(f"polygon {pi} ring {ri}: self-intersection")
        return probs


def _point_in_rings(x: float, y: float, rings: PolygonRings) -> bool:
    inside = False
    for ring in rings:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


def _segments_cross(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-18 else (1 if v > 0 else -1)

    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def _self_intersects(ring: Ring) -> bool:
    n = len(ring)
    edges = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # adjacent through the closing vertex
            if _segments_cross(*edges[i], *edges[j]):
                return True
    return False


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def parse_point(obj) -> tuple[float, float] | None:
    if obj is None:
        return None
    if isinstance(obj, (str, bytes)):
        obj = json.loads(obj)
    if obj.get("type") == "Feature":
        obj = obj.get("geometry") or {}
    if obj.get("type") != "Point":
        return None
    lon, lat = obj["coordinates"][:2]
    return float(lon), float(lat)


# ─────────────────────────── directions ────────────────────────────

DIRECTIONS_AR = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"]


def direction_index(azimuth_deg: float) -> int:
    return int(((azimuth_deg + 22.5) % 360) // 45)


def direction_ambiguity(azimuth_deg: float) -> float:
    """Degrees from the nearest sector boundary (0 = exactly on a boundary)."""
    off = (azimuth_deg + 22.5) % 45
    return min(off, 45 - off)


# ─────────────────────────── UTM ───────────────────────────────────

_N = F / (2 - F)
_AK = A / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64)
_ALPHA = (
    _N / 2 - 2 / 3 * _N**2 + 5 / 16 * _N**3,
    13 / 48 * _N**2 - 3 / 5 * _N**3,
    61 / 240 * _N**3,
)


def utm_forward(lon: float, lat: float, zone: int, north: bool = True) -> tuple[float, float]:
    """WGS84 lon/lat -> UTM easting/northing (Krüger series, ~mm accuracy)."""
    k0 = 0.9996
    lam0 = (zone * 6 - 183) * RAD
    phi, lam = lat * RAD, lon * RAD - lam0
    c = 2 * math.sqrt(_N) / (1 + _N)
    sphi = math.sin(phi)
    t = math.sinh(math.atanh(sphi) - c * math.atanh(c * sphi))
    xi = math.atan2(t, math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    e = eta + sum(
        a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(_ALPHA, 1)
    )
    nn = xi + sum(
        a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(_ALPHA, 1)
    )
    return 500000 + k0 * _AK * e, (0 if north else 10_000_000) + k0 * _AK * nn


def parse_epsg(crs: str) -> tuple[str, int | None, bool]:
    """'EPSG:4326' -> ('geographic', None, True); 'EPSG:32638' -> ('utm', 38, True)."""
    code = int(str(crs).upper().replace("EPSG:", "").strip())
    if code == 4326:
        return "geographic", None, True
    if 32601 <= code <= 32660:
        return "utm", code - 32600, True
    if 32701 <= code <= 32760:
        return "utm", code - 32700, False
    raise ValueError(f"unsupported CRS {crs}: use EPSG:4326 or WGS84/UTM (326xx/327xx)")
