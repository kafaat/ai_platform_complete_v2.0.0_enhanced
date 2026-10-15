"""Water investigation (0.4.0).

The recompute classes below parse the demo fixture rows themselves and use their
own polygon area and their own transcription of the FAO-56 values; they import
nothing from sahool_qa.waterbal or the water generator."""

import datetime as dt
import json
import math
import re
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from sahool_qa.config import ABSTAIN_TEXT, DEFAULT_RULES
from sahool_qa.demo import write_demo
from sahool_qa.facts import Indicator
from sahool_qa.pipeline import generate
from sahool_qa.raster import load_rasters
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.split import parse_holdout
from sahool_qa.waterbal import Series, balance, daily_increments, stress_class, window_delta

# ── independent transcription of FAO-56 (Table 19 midpoints, Table 22 low Zr and p) ──
SOIL = {
    "sandy_loam": (0.23, 0.11),
    "loamy_sand": (0.15, 0.065),
    "loam": (0.25, 0.12),
    "silt_loam": (0.29, 0.15),
}
CROP = {"قمح": (1.0, 0.55), "ذرة رفيعة": (1.0, 0.55), "شعير": (1.0, 0.55), "سمسم": (1.0, 0.60)}
LINEAGE = {"station": {"gauge"}, "chirps_v3_rnl": {"era5"}, "era5land": {"era5"}}
PRIORITY = ["station", "chirps_v3_rnl", "era5land"]
EA, MAX_H = 0.80, 10.0
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def area_m2(ring):
    """Shoelace on a local equirectangular frame with WGS84 radii at the centroid."""
    a, e2 = 6378137.0, 0.00669437999014
    lon0 = sum(p[0] for p in ring) / len(ring)
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    w = 1 - e2 * math.sin(lat0) ** 2
    M, N = a * (1 - e2) / w**1.5, a / w**0.5
    xy = [
        (math.radians(lon - lon0) * N * math.cos(lat0), math.radians(lat) * M) for lon, lat in ring
    ]
    return (
        abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1], strict=False)))
        / 2
    )


class Rows:
    """The fixture's water rows: field -> indicator id -> {date: [(time, value, unit)]}."""

    def __init__(self, fx_path):
        fx = json.loads(Path(fx_path).read_text(encoding="utf-8"))
        self.fields, self.rows = {}, defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for ft in fx["features"]:
            p = ft["properties"]
            if p.get("kind") == "field" and p.get("tenant") == "demo-tenant":
                ring = ft["geometry"]["coordinates"][0][:-1] if ft["geometry"] else None
                self.fields[p["id"]] = {
                    "area": area_m2(ring) if ring else None,
                    "soil": p.get("soil_type"),
                    "crop": p.get("crop"),
                }
            elif p.get("kind") == "indicator" and p.get("tenant") == "demo-tenant":
                d, t = p["recorded_at"][:10], p["recorded_at"][11:16]
                self.rows[p["field_id"]][p["indicator_id"]][d].append(
                    (t, p["value"], p.get("unit"))
                )

    def ids(self, fid, prefix):
        return sorted(i for i in self.rows[fid] if i.startswith(prefix))

    def day(self, fid, iid, d):
        v = self.rows[fid][iid].get(d)
        if not v:
            return None
        return (
            max(v)[1]
            if iid.startswith(("meter_total_", "pump_hours_"))
            else sum(x[1] for x in v) / len(v)
        )

    def owners(self, iid):
        return sorted(f for f in self.rows if iid in self.rows[f])


def days(a, b):
    a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return [str(a + dt.timedelta(days=k)) for k in range((b - a).days + 1)]


def recompute_balance(R: Rows, fid, d0, D):
    f = R.fields[fid]
    fc, wp = SOIL[f["soil"]]
    zr, pt = CROP[f["crop"]]
    taw = 1000 * (fc - wp) * zr
    (sm,) = R.ids(fid, "soil_moisture_vol")
    theta0 = R.day(fid, sm, d0) / 100
    dr = min(max(1000 * (fc - theta0) * zr, 0), taw)
    span = days(d0, D)[1:]
    src = next(
        s
        for s in PRIORITY
        if f"rain_mm_{s}" in R.rows[fid]
        and all(R.day(fid, f"rain_mm_{s}", d) is not None for d in span)
    )
    kc_days = sorted(R.rows[fid]["kc"])
    p = None
    for prev, d in zip(days(d0, D), span, strict=False):
        kc = R.day(fid, "kc", max(x for x in kc_days if x <= d))
        etc = kc * R.day(fid, "et0_mm", d)
        p = min(0.8, max(0.1, pt + 0.04 * (5 - etc)))
        ks = 1.0 if dr <= p * taw else (taw - dr) / ((1 - p) * taw)
        irr = (
            sum(R.day(fid, m, d) - R.day(fid, m, prev) for m in R.ids(fid, "meter_total_"))
            / f["area"]
            * 1000
        )
        dr = min(max(dr - R.day(fid, f"rain_mm_{src}", d) - EA * irr + ks * etc, 0.0), taw)
    raw = p * taw
    if dr <= raw:
        return "no_stress", dr
    ks = (taw - dr) / ((1 - p) * taw)
    return ("moderate" if ks >= 0.5 else "severe"), dr


class WaterDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        fx, rasters = write_demo(str(cls.tmp))
        cls.R = Rows(fx)
        store = load_fixture(str(fx), "demo-tenant")
        store.rasters = load_rasters(str(rasters))
        cls.m = generate(
            store,
            DEFAULT_RULES,
            str(cls.tmp / "qa"),
            holdout=parse_holdout(["test:governorate=الحديدة", "val:governorate=مأرب"]),
        )
        cls.items = []
        for p in sorted((cls.tmp / "qa").glob("*.jsonl")):
            if p.name != "data_issues.jsonl" and not p.name.endswith(".public.jsonl"):
                cls.items += [
                    json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
                ]
        cls.issues = [
            json.loads(line)
            for line in (cls.tmp / "qa" / "data_issues.jsonl").read_text("utf-8").splitlines()
        ]

    def fam(self, name):
        return [i for i in self.items if i["family"] == name]

    @staticmethod
    def fid(it):
        return next(
            r["field_id"] for r in it["evidence"]["records"] if r["table"] == "field_boundaries"
        )


class TestWaterCoverage(WaterDemo):
    def test_every_split_has_every_water_family_with_answers_and_abstentions(self):
        fams = [
            f
            for f in self.m["coverage"]["train"]
            if f.startswith("water.") and f != "water.salinity_class"
        ]
        self.assertEqual(len(fams), 6)
        for split in ("train", "val", "test"):
            for f in fams:
                self.assertIn(f, self.m["coverage"][split], (split, f))
        for f in fams:
            items = self.fam(f)
            self.assertTrue(any(i["answerable"] for i in items), f)
            self.assertTrue(any(not i["answerable"] for i in items), f)
            self.assertTrue(all(i["evidence"]["kind"] == "derived" for i in items))

    def test_answer_classes_are_spread(self):
        def classes(f):
            return {i["answer_value"] for i in self.fam(f) if i["answerable"]}

        self.assertEqual(classes("water.stress_status"), {"no_stress", "moderate", "severe"})
        self.assertEqual(classes("water.plan_vs_measured"), {"below", "within", "above"})
        self.assertEqual(classes("water.refill_feasibility"), {"one", "few", "many", "unavailable"})
        self.assertEqual(classes("water.rain_corroboration"), {"confirmed", "contradicted"})


class TestPlantedTraps(WaterDemo):
    def problem(self, family, fid, day=None):
        out = []
        for it in self.fam(family):
            if self.fid(it) == fid and (day is None or day in it["question"]):
                v = it["evidence"]["values"]
                out.append(
                    None
                    if it["answerable"]
                    else v.get("problem") or v.get("balance", {}).get("problem") or "abstain"
                )
        return out

    def test_missing_records_become_abstentions(self):
        self.assertEqual(self.problem("water.applied_depth", "demo_flood"), ["no_meter"])
        marib = {
            tuple(it["evidence"]["values"]["window"]): it["evidence"]["values"].get("problem")
            for it in self.fam("water.applied_depth")
            if self.fid(it) == "demo_marib_pivot"
        }
        self.assertEqual(
            marib,
            {
                ("2026-01-10", "2026-02-07"): "meter_decrease",  # MP1 replaced on 01-25
                ("2026-01-10", "2026-01-17"): None,
                ("2026-01-17", "2026-01-24"): None,
                ("2026-01-24", "2026-01-31"): "meter_decrease",
                ("2026-01-31", "2026-02-07"): None,
            },
        )
        self.assertEqual(self.problem("water.applied_depth", "demo_tihama_farm"), ["no_polygon"])
        self.assertEqual(self.problem("water.applied_depth", "demo_tihama_1"), ["shared_meter"])
        self.assertEqual(self.problem("water.applied_depth", "demo_tihama_2"), ["shared_meter"])
        self.assertEqual(
            self.problem("water.plan_vs_measured", "demo_tihama_2"), ["missing_plan_week"]
        )
        self.assertEqual(
            self.problem("water.stress_status", "demo_flood"), ["no_meter"]
        )  # asked once
        self.assertEqual(self.problem("water.stress_status", "demo_marib_1"), ["theta0_unusable"])
        self.assertEqual(self.problem("water.stress_status", "demo_tihama_1"), ["shared_meter"])
        self.assertEqual(
            self.problem("water.stress_status", "demo_marib_pivot", "2026-01-31"),
            ["meter_decrease"],
        )
        self.assertEqual(
            self.problem("water.refill_feasibility", "demo_pivot_1", "2026-02-02"),
            ["pump_hours_not_increasing"],
        )  # pumps idle: flow unknown

    def test_cumulative_meter_gap_total_known_daily_split_unknown(self):
        # demo_pivot_2: P2A readings missing on 01-21..01-23
        self.assertEqual(self.problem("water.applied_depth", "demo_pivot_2"), [None] * 5)
        self.assertEqual(self.problem("water.plan_vs_measured", "demo_pivot_2"), [None])
        self.assertEqual(
            self.problem("water.stress_status", "demo_pivot_2", "2026-01-26"),
            ["missing_daily_reading"],
        )
        self.assertEqual(self.problem("water.stress_status", "demo_pivot_2", "2026-01-19"), [None])

    def test_gauge_gap_falls_back_to_next_source(self):
        src = {
            DATE.findall(it["question"])[1]: it["evidence"]["values"]["rain_source"]
            for it in self.fam("water.stress_status")
            if self.fid(it) == "demo_tihama_pivot" and it["answerable"]
        }
        self.assertEqual(
            src,
            {
                "2026-07-08": "station",
                "2026-07-15": "station",
                "2026-07-22": "chirps_v3_rnl",
                "2026-07-29": "chirps_v3_rnl",
            },
        )

    def test_careless_answer_is_among_the_options(self):
        for it in self.fam("water.applied_depth"):
            if (
                it["evidence"]["values"].get("problem") == "no_meter"
            ):  # "no irrigation" is the careless reading
                self.assertTrue(any(o["text"].startswith("0-") for o in it["options"]))
        for it in self.fam("water.applied_depth") + self.fam("water.rain_total"):
            bins = [
                tuple(map(float, o["text"].split()[0].split("-")))
                for o in it["options"]
                if o["text"] != ABSTAIN_TEXT
            ]
            bins.sort()
            self.assertEqual(len(bins), 3)
            self.assertTrue(
                all(x[1] == y[0] for x, y in zip(bins, bins[1:], strict=False)), it["id"]
            )  # consecutive: no isolated range
        for it in self.fam("water.rain_total"):
            if not it["answerable"]:
                naive = it["evidence"]["values"]["sum_of_recorded_days_mm"]
                bins = [o["text"] for o in it["options"] if o["text"] != ABSTAIN_TEXT]
                lohi = [tuple(map(float, b.split()[0].split("-"))) for b in bins]
                self.assertTrue(any(lo <= naive < hi for lo, hi in lohi), (naive, bins))
        for f in (
            "water.rain_corroboration",
            "water.stress_status",
            "water.plan_vs_measured",
            "water.refill_feasibility",
            "water.applied_depth",
            "water.rain_total",
        ):
            for it in self.fam(f):  # always offered: its presence never gives the answer away
                self.assertIn(ABSTAIN_TEXT, [o["text"] for o in it["options"]])
                self.assertEqual(
                    len(it["options"]),
                    3
                    if f == "water.rain_corroboration"
                    else 5
                    if f == "water.refill_feasibility"
                    else 4,
                    it["id"],
                )

    def test_same_day_records_are_aggregated(self):
        it = next(
            i
            for i in self.fam("water.stress_status")
            if self.fid(i) == "demo_pivot_1" and "2026-01-19" in i["question"]
        )
        day = next(r for r in it["evidence"]["values"]["daily"] if r["date"] == "2026-01-18")
        self.assertAlmostEqual(day["rain"], 8.3)  # two gauge entries: daily mean
        self.assertIn("8.4 (23:30) / 8.2 (23:45)", it["context"])
        it = next(
            i
            for i in self.fam("water.stress_status")
            if self.fid(i) == "demo_tihama_pivot" and i["answerable"]
        )
        day = next(r for r in it["evidence"]["values"]["daily"] if r["date"] == "2026-07-05")
        self.assertAlmostEqual(
            day["irr_gross"], (840 + 800) / 282566 * 1000, delta=0.01
        )  # TP1 from its 21:00 reading, + TP2

    def test_polygons_follow_rfc7946_winding(self):
        fx = json.loads((self.tmp / "demo_fixture.geojson").read_text("utf-8"))
        for ft in fx["features"]:
            if ft["geometry"] and ft["geometry"]["type"] == "Polygon":
                r = ft["geometry"]["coordinates"][0]
                self.assertGreater(
                    sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:], strict=False)), 0
                )

    def test_audit_lists_water_faults(self):
        codes = defaultdict(list)
        for i in self.issues:
            codes[i["code"]].append(i)
        self.assertEqual([i["indicator_id"] for i in codes["unknown_unit"]], ["soil_moisture_vol"])
        self.assertEqual(codes["meter_shared_between_fields"][0]["indicator_id"], "meter_total_T12")
        self.assertEqual(
            [i["recorded_at"] for i in codes["cumulative_meter_decrease"]], ["2026-01-25"]
        )


class TestIndependentRecompute(WaterDemo):
    def test_stress_classes(self):
        n = 0
        for it in self.fam("water.stress_status"):
            if not it["answerable"]:
                continue
            d0, D = DATE.findall(it["question"])
            cls, dr = recompute_balance(self.R, self.fid(it), d0, D)
            self.assertEqual(cls, it["answer_value"], (self.fid(it), D))
            self.assertAlmostEqual(dr, it["evidence"]["values"]["dr_end_mm"], delta=0.05)
            n += 1
        self.assertEqual(n, 12)

    def test_refill_classes(self):
        n = 0
        for it in self.fam("water.refill_feasibility"):
            if not it["answerable"]:
                continue
            a, D, d0 = DATE.findall(
                it["question"]
            )  # flow window a..D, balance from the reading on d0
            self.assertEqual(a, str(dt.date.fromisoformat(D) - dt.timedelta(days=7)))
            _, dr = recompute_balance(self.R, fid := self.fid(it), d0, D)
            pumping = days(a, D)[1:]
            q = 0.0
            for m in self.R.ids(fid, "meter_total_"):
                well = m[len("meter_total_") :]
                st = self.R.rows[fid].get("well_status_" + well, {})
                in_force = [
                    st[max(x for x in st if x <= d)][0][1] if any(x <= d for x in st) else None
                    for d in pumping
                ]
                if in_force and all(
                    v == 0 for v in in_force
                ):  # logged out of service: a known zero
                    continue
                h = "pump_hours_" + well
                q += (self.R.day(fid, m, D) - self.R.day(fid, m, a)) / (
                    self.R.day(fid, h, D) - self.R.day(fid, h, a)
                )
            if q == 0:
                want = "unavailable"
            else:
                pump_days = dr * self.R.fields[fid]["area"] / 1000 / EA / (q * MAX_H)
                want = "one" if pump_days <= 2 else "few" if pump_days <= 5 else "many"
            self.assertEqual(want, it["answer_value"], (fid, D))
            n += 1
        self.assertGreaterEqual(n, 5)

    def test_applied_depth_and_plan(self):
        for it in self.fam("water.applied_depth") + self.fam("water.plan_vs_measured"):
            if not it["answerable"]:
                continue
            fid = self.fid(it)
            a, b = it["evidence"]["values"]["window"]
            if (
                it["family"] == "water.plan_vs_measured"
            ):  # planned days start..start+6, read from the evening before
                weeks = sorted(self.R.rows[fid]["irrigation_plan_week"])
                self.assertEqual(
                    [a, b],
                    [
                        str(dt.date.fromisoformat(weeks[0]) - dt.timedelta(days=1)),
                        str(dt.date.fromisoformat(weeks[-1]) + dt.timedelta(days=6)),
                    ],
                )
                self.assertIn(f"من {weeks[0]} إلى {b} شاملةً", it["question"])
            vol = sum(
                self.R.day(fid, m, b) - self.R.day(fid, m, a)
                for m in self.R.ids(fid, "meter_total_")
            )
            depth = vol / self.R.fields[fid]["area"] * 1000
            if it["family"] == "water.applied_depth":
                lo, hi = map(float, it["answer_text"].split()[0].split("-"))
                self.assertTrue(lo <= depth < hi, (fid, depth, it["answer_text"]))
            else:
                plan = sum(v[0][1] for v in self.R.rows[fid]["irrigation_plan_week"].values())
                r = depth / plan
                self.assertEqual(
                    "below" if r < 0.9 else "above" if r > 1.1 else "within", it["answer_value"]
                )

    def test_rain_totals_and_corroboration(self):
        for it in self.fam("water.rain_total"):
            fid, iid = self.fid(it), it["question"].split("سجلات ")[-1].rstrip("؟")
            a, b = DATE.findall(it["question"])
            vals = [self.R.day(fid, iid, d) for d in days(a, b)]
            self.assertEqual(it["answerable"], None not in vals)
            if it["answerable"]:
                lo, hi = map(float, it["answer_text"].split()[0].split("-"))
                self.assertTrue(lo <= sum(vals) < hi)
        for it in self.fam("water.rain_corroboration"):
            fid = self.fid(it)
            src = it["question"].split()[1][len("rain_mm_") :]
            d = DATE.findall(it["question"])[0]
            win = days(
                str(dt.date.fromisoformat(d) - dt.timedelta(days=1)),
                str(dt.date.fromisoformat(d) + dt.timedelta(days=1)),
            )
            totals = []
            for other, lin in LINEAGE.items():
                if other == src or lin & LINEAGE[src] or f"rain_mm_{other}" not in self.R.rows[fid]:
                    continue
                vals = [self.R.day(fid, f"rain_mm_{other}", x) for x in win]
                if None not in vals:
                    totals.append(sum(vals))
            want = None if not totals else "confirmed" if max(totals) >= 2.0 else "contradicted"
            self.assertEqual(want, it["answer_value"], (fid, src, d))
            self.assertEqual(it["answerable"], want is not None)


class TestWaterCore(unittest.TestCase):
    def test_fao_values_pinned(self):
        w = DEFAULT_RULES["water"]
        self.assertEqual(
            w["soil_water"]["sandy_loam"], {"fc": [0.18, 0.28], "wp": [0.06, 0.16]}
        )  # FAO-56 Table 19
        self.assertEqual(w["soil_water"]["clay"], {"fc": [0.32, 0.40], "wp": [0.20, 0.24]})
        self.assertEqual(w["crops"]["قمح"]["zr"], [1.0, 1.5])  # Table 22
        self.assertEqual(
            (w["crops"]["سمسم"]["p"], w["crops"]["بطاطس"]["p"], w["crops"]["قطن"]["p"]),
            (0.60, 0.35, 0.65),
        )
        for soil, (fc, wp) in SOIL.items():  # independent transcription
            self.assertAlmostEqual(sum(w["soil_water"][soil]["fc"]) / 2, fc)
            self.assertAlmostEqual(sum(w["soil_water"][soil]["wp"]) / 2, wp)

    def test_balance_by_hand(self):
        prm = {"fc": 0.23, "wp": 0.11, "zr": 1.0, "p_table": 0.55, "ea": 0.8, "taw": 120.0}
        ds = [dt.date(2026, 1, k) for k in (2, 3, 4, 5)]
        dr0, rows = balance(
            prm,
            0.17,
            ds,
            {d: 5.0 for d in ds},
            {d: 1.0 for d in ds},
            dict(zip(ds, [0, 0, 0, 100.0], strict=False)),
            {d: 0.0 for d in ds},
        )
        self.assertAlmostEqual(dr0, 60.0)
        self.assertAlmostEqual(rows[0]["dr_end"], 65.0)  # Dr0 60 <= RAW 66: Ks 1
        self.assertAlmostEqual(rows[1]["dr_end"], 70.0)  # start 65 <= 66: Ks 1
        self.assertAlmostEqual(rows[2]["ks_start"], 50 / 54)  # start 70 > 66: (120-70)/(0.45*120)
        self.assertAlmostEqual(rows[2]["dr_end"], 70 + 5 * 50 / 54)
        self.assertEqual(rows[3]["dr_end"], 0.0)  # 100 mm: back to field capacity
        self.assertAlmostEqual(rows[3]["dp"], 100 - rows[2]["dr_end"] - rows[3]["eta"])
        self.assertEqual(
            stress_class(rows[2]["dr_end"], 66.0, 120.0, 0.55, DEFAULT_RULES)[0], "moderate"
        )
        self.assertEqual(
            stress_class(100.0, 66.0, 120.0, 0.55, DEFAULT_RULES)[0], "severe"
        )  # Ks 0.37

    def test_cumulative_meter_rules(self):
        def series(vals):
            s = Series("meter", "meter_total_X")
            for k, v in vals.items():
                d = dt.date(2026, 1, k)
                rec = Indicator(
                    field_id="f",
                    indicator_id="meter_total_X",
                    value=v,
                    recorded_ts=dt.datetime(2026, 1, k, 21),
                    unit="m3",
                    tenant="t",
                )
                rec.conv = v
                s.records[d] = [rec]
            return s

        d = lambda k: dt.date(2026, 1, k)  # noqa: E731
        gap = series({1: 100.0, 2: 150.0, 5: 300.0, 6: 320.0})
        self.assertEqual(
            window_delta(gap, d(1), d(6)), (220.0, None)
        )  # total across a gap is known
        self.assertEqual(daily_increments(gap, d(1), d(6))[1], "missing_daily_reading")
        self.assertEqual(window_delta(gap, d(1), d(7)), (None, "missing_endpoint"))
        reset = series({1: 100.0, 2: 150.0, 3: 4.0, 4: 60.0})
        self.assertEqual(window_delta(reset, d(1), d(4)), (None, "meter_decrease"))
        self.assertEqual(
            window_delta(reset, d(3), d(4)), (56.0, None)
        )  # after the replacement: fine


if __name__ == "__main__":
    unittest.main()
