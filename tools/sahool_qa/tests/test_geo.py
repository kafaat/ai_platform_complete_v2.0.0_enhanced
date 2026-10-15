import math
import unittest

from sahool_qa.geo import (
    E2,
    A,
    Geometry,
    LocalFrame,
    direction_index,
    utm_forward,
    vincenty_inverse,
)


def dms(d, m, s, neg=False):
    v = d + m / 60 + s / 3600
    return -v if neg else v


def quad_area_exact(lon0, lat0, lon1, lat1):
    """Exact ellipsoidal area of a lat/lon quadrangle (authalic formula)."""
    e = math.sqrt(E2)

    def q(phi):
        s = math.sin(phi)
        return s / (1 - E2 * s * s) + (1 / (2 * e)) * math.log((1 + e * s) / (1 - e * s))

    b2 = (A * math.sqrt(1 - E2)) ** 2
    return 0.5 * b2 * math.radians(lon1 - lon0) * (q(math.radians(lat1)) - q(math.radians(lat0)))


class TestGeodesy(unittest.TestCase):
    def test_vincenty_flinders_buninyong(self):
        # Vincenty (1975) / Geoscience Australia reference pair
        d, az = vincenty_inverse(
            dms(144, 25, 29.52440),
            dms(37, 57, 3.72030, True),
            dms(143, 55, 35.38390),
            dms(37, 39, 10.15610, True),
        )
        self.assertAlmostEqual(d, 54972.271, delta=0.01)
        self.assertAlmostEqual(az, dms(306, 52, 5.37), delta=1 / 3600)

    def test_equator_degree(self):
        d, az = vincenty_inverse(0, 0, 1, 0)
        self.assertAlmostEqual(d, 111319.4908, delta=0.01)
        self.assertAlmostEqual(az, 90, delta=1e-6)

    def test_utm_central_meridian_is_scaled_meridian_arc(self):
        e, n = utm_forward(45.0, 16.0, 38)
        self.assertAlmostEqual(e, 500000.0, delta=1e-6)
        steps = 20000
        h = math.radians(16) / steps
        arc = 0.0
        for i in range(steps):  # midpoint integration of the meridional radius
            phi = (i + 0.5) * h
            arc += A * (1 - E2) / (1 - E2 * math.sin(phi) ** 2) ** 1.5 * h
        self.assertAlmostEqual(n, 0.9996 * arc, delta=0.01)

    def test_utm_grid_distance_matches_geodesic(self):
        p, q = (44.9420, 16.0905), (44.9600, 16.1050)
        (e1, n1), (e2, n2) = utm_forward(*p, 38), utm_forward(*q, 38)
        grid = math.hypot(e2 - e1, n2 - n1)
        geo = vincenty_inverse(*p, *q)[0]
        self.assertLess(abs(grid / 0.9996 - geo) / geo, 5e-5)

    def test_quadrangle_area_vs_exact(self):
        lon0, lat0, lon1, lat1 = 44.94, 16.08, 44.95, 16.09
        g = Geometry([[[(lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1)]]])
        exact = quad_area_exact(lon0, lat0, lon1, lat1)
        self.assertLess(abs(g.area_m2 - exact) / exact, 1e-4)

    def test_hole_and_contains(self):
        outer = [(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01)]
        hole = [(0.004, 0.004), (0.006, 0.004), (0.006, 0.006), (0.004, 0.006)]
        g = Geometry([[outer, hole]])
        self.assertTrue(g.contains(0.002, 0.002))
        self.assertFalse(g.contains(0.005, 0.005))
        self.assertFalse(g.contains(0.02, 0.005))
        full = Geometry([[outer]]).area_m2
        self.assertAlmostEqual(g.area_m2 / full, 1 - 0.04, delta=1e-4)

    def test_shapes(self):
        fr = LocalFrame(44.94, 16.09)
        circ = Geometry(
            [
                [
                    [
                        fr.inv(
                            401 * math.sin(2 * math.pi * i / 96),
                            401 * math.cos(2 * math.pi * i / 96),
                        )
                        for i in range(96)
                    ]
                ]
            ]
        )
        self.assertGreater(circ.compactness, 0.99)
        self.assertAlmostEqual(math.sqrt(circ.area_m2 / math.pi), 401, delta=1.0)
        ang = math.radians(25)
        pts = [(-200, -125), (200, -125), (200, 125), (-200, 125)]
        rect = Geometry(
            [
                [
                    [
                        fr.inv(
                            x * math.cos(ang) - y * math.sin(ang),
                            x * math.sin(ang) + y * math.cos(ang),
                        )
                        for x, y in pts
                    ]
                ]
            ]
        )
        area, short, long_ = rect.min_area_rect()
        self.assertAlmostEqual(short, 250, delta=0.5)
        self.assertAlmostEqual(long_, 400, delta=0.5)
        self.assertAlmostEqual(rect.compactness, math.pi * 4 * 100000 / (1300**2), delta=1e-3)

    def test_self_intersection_detected(self):
        bow = Geometry([[[(0, 0), (0.01, 0.01), (0.01, 0), (0, 0.01)]]])
        self.assertTrue(any("self-intersection" in p for p in bow.validity_problems()))

    def test_directions(self):
        self.assertEqual(direction_index(0), 0)
        self.assertEqual(direction_index(359), 0)
        self.assertEqual(direction_index(44), 1)
        self.assertEqual(direction_index(90), 2)
        self.assertEqual(direction_index(200), 4)


if __name__ == "__main__":
    unittest.main()
