"""Season-investigator families (0.3.0): pattern, next measurement, divergence
onset, green-up window, and the mandatory evidence kind."""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from sahool_qa.config import ABSTAIN_TEXT, DEFAULT_RULES
from sahool_qa.demo import TIMELINES, write_demo
from sahool_qa.facts import FactStore, Field
from sahool_qa.generators.investigation import (
    MEASUREMENTS,
    NO_DIVERGENCE,
    PATTERNS,
    classify_pattern,
)
from sahool_qa.geo import utm_forward
from sahool_qa.items import GenContext, make_item
from sahool_qa.pipeline import generate
from sahool_qa.raster import load_rasters
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.split import parse_holdout


def polar(field, rings, sectors, valid=1.0, n=500):
    keys = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    b = lambda fr: {"pixels": n, "valid": n, "valid_frac": 1.0, "frac_above": fr}  # noqa: E731
    return {
        "field": {"pixels": 8 * n, "valid": 8 * n, "valid_frac": valid, "frac_above": field},
        "rings": [dict(b(r), r_from=80.0 * i, r_to=80.0 * (i + 1)) for i, r in enumerate(rings)],
        "sectors": {k: b(s) for k, s in zip(keys, sectors, strict=False)},
    }


class TestClassifyPattern(unittest.TestCase):
    R = DEFAULT_RULES

    def test_classes(self):
        self.assertEqual(
            classify_pattern(polar(0.72, [1, 1, 1, 0.0, 1], [0.72] * 8), self.R)[0], "ring"
        )
        c, d = classify_pattern(polar(0.875, [0.875] * 5, [1, 1, 0.0, 1, 1, 1, 1, 1]), self.R)
        self.assertEqual((c, d["weak_sector"]), ("sector", "E"))
        self.assertEqual(
            classify_pattern(polar(0.05, [0.05] * 5, [0.05] * 8), self.R)[0], "field_wide"
        )
        self.assertEqual(classify_pattern(polar(0.99, [0.99] * 5, [0.99] * 8), self.R)[0], "none")

    def test_ambiguous_cases_are_not_asked(self):
        self.assertIsNone(
            classify_pattern(polar(0.65, [0.65] * 5, [0.65] * 8), self.R)[0]
        )  # intermediate
        self.assertIsNone(
            classify_pattern(polar(0.6, [1, 1, 0.3, 0.2, 1], [1, 0, 1, 1, 1, 0.5, 1, 1]), self.R)[0]
        )  # mixed
        self.assertIsNone(
            classify_pattern(polar(0.80, [0.80] * 5, [0.80] * 8), self.R)[0]
        )  # on the edge
        self.assertIsNone(
            classify_pattern(polar(0.9, [0.9] * 5, [0.9] * 8, valid=0.5), self.R)[0]
        )  # mostly cloud


class TestEvidenceKind(unittest.TestCase):
    def test_kind_is_required_without_default(self):
        store = FactStore()
        store.add_field(Field(id="f", name="F", tenant="t"))
        ctx = GenContext(store=store, rules=DEFAULT_RULES)
        for ev in ({}, {"kind": "measured"}):
            with self.assertRaises(ValueError):
                make_item(
                    ctx,
                    family="t",
                    level="scene_reasoning",
                    question="س",
                    correct="x",
                    distractors=["y", "z"],
                    evidence=ev,
                    context="",
                    field_refs=["t::f"],
                    key={},
                )


class TestInvestigationOnDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        fx, rasters = write_demo(str(cls.tmp))
        cls.fx, cls.rasters = fx, rasters
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
                cls.items += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()]

    def fam(self, name):
        return [i for i in self.items if i["family"] == name]

    def test_every_item_has_a_kind(self):
        kinds = {i["evidence"]["kind"] for i in self.items}
        self.assertEqual(kinds, {"observed", "derived", "inferred"})
        self.assertTrue(
            all(i["evidence"]["kind"] == "inferred" for i in self.fam("reasoning.next_measurement"))
        )
        self.assertEqual(sum(self.m["counts"]["by_evidence_kind"].values()), len(self.items))

    def test_planted_patterns(self):
        want = {
            ("المحور 1", "2026-02-15"): "sector",
            ("المحور 2", "2026-02-15"): "none",
            ("المحور 1", "2026-03-21"): "insufficient_valid",
            ("المحور 2", "2026-03-21"): "ring",
            ("محور مأرب", "2026-01-20"): "sector",
            ("محور مأرب", "2026-02-25"): "field_wide",
            ("محور تهامة", "2026-08-20"): "sector",
            ("محور تهامة", "2026-09-05"): "ring",
            ("محور تهامة", "2026-09-15"): "insufficient_valid",
        }
        got = {}
        for it in self.fam("reasoning.pivot_anomaly_pattern"):
            name = next(n for n, _ in want if f"«{n} (عرض)»" in it["question"])
            date = next(d for _, d in want if d in it["question"])
            got[(name, date)] = it["answer_value"]
            if it["answer_value"] == "insufficient_valid":  # half the pivot under cloud: abstain
                self.assertFalse(it["answerable"])
                self.assertEqual(it["answer_text"], ABSTAIN_TEXT)
                self.assertIn(
                    PATTERNS["none"], [o["text"] for o in it["options"]]
                )  # not solvable by elimination
            else:
                self.assertEqual(it["answer_text"], PATTERNS[it["answer_value"]])
            self.assertTrue((self.tmp / "qa" / it["image"]).exists())
        self.assertEqual(got, want)
        groups = {}
        for it in self.fam("reasoning.next_measurement"):
            self.assertEqual(it["answer_text"], MEASUREMENTS[it["answer_value"]])
            if it["answer_value"] == "insufficient_valid":
                self.assertIn(MEASUREMENTS["none"], [o["text"] for o in it["options"]])
            groups[it["related_group"]] = it["answer_value"]
        for it in self.fam(
            "reasoning.pivot_anomaly_pattern"
        ):  # image and table items of one scene share a group
            self.assertEqual(groups[it["related_group"]], it["answer_value"])
        self.assertEqual(len(self.fam("reasoning.next_measurement")), len(want))
        self.assertEqual(self.m["images"].get("dropped"), [])

    def test_onset_windows(self):
        got = {}
        for it in self.fam("temporal.divergence_onset"):
            name = it["question"].split("«")[1].split(" (")[0]
            got[name] = it["answer_value"] if it["answerable"] else ABSTAIN_TEXT
            if it["answerable"] and it["answer_value"] is None:
                got[name] = it["answer_text"]
        self.assertEqual(
            got,
            {
                "المحور 1": ["2025-03-11", "2025-03-31"],
                "المحور 2": NO_DIVERGENCE,
                "محور مأرب": ABSTAIN_TEXT,
                "محور تهامة": ["2025-08-22", "2025-09-11"],
            },
        )
        it = next(i for i in self.fam("temporal.divergence_onset") if "«المحور 1" in i["question"])
        self.assertIn("المتجه نحو الشرق من مركز المحور", it["question"])
        self.assertIn(
            "بين مشهد 2025-03-11 ومشهد 2025-03-21", [o["text"] for o in it["options"]]
        )  # window ending at the cloud

    def test_onset_independent_recompute(self):
        """Recompute pivot 1's east-sector deficit straight from the arrays, with a simple disc
        instead of the polygon and without the generator's polar code."""
        layers = [
            ln
            for ln in load_rasters(str(self.rasters))
            if ln.scene_id.startswith("TL_demo_pivot_1_")
        ]
        fx = json.loads(Path(self.fx).read_text(encoding="utf-8"))
        ring = next(
            ft["geometry"]["coordinates"][0]
            for ft in fx["features"]
            if ft["properties"].get("id") == "demo_pivot_1"
        )
        xy = [utm_forward(lon, lat, 38) for lon, lat in ring[:-1]]
        cx, cy = sum(x for x, _ in xy) / len(xy), sum(y for _, y in xy) / len(xy)
        out = []
        for ln in sorted(layers, key=lambda ln: ln.date):
            a = ln.array()
            x0, dx, _, y0, _, dy = ln.transform
            X, Y = np.meshgrid(
                x0 + (np.arange(a.shape[1]) + 0.5) * dx, y0 + (np.arange(a.shape[0]) + 0.5) * dy
            )
            r = np.hypot(X - cx, Y - cy)
            az = (np.degrees(np.arctan2(X - cx, Y - cy)) + 360) % 360
            disc = r < 390
            east = disc & (az >= 67.5) & (az < 112.5)
            rest = disc & ~east
            ok = a != -9999
            if (ok & east).sum() < 0.8 * east.sum() or (ok & disc).sum() < 0.9 * disc.sum():
                out.append(None)
                continue
            out.append(float((a[rest & ok] >= 0.2).mean() - (a[east & ok] >= 0.2).mean()))
        flags = [None if d is None else d >= 0.25 for d in out]
        self.assertEqual(
            flags, [True, False, None, True, True, True]
        )  # one-off, normal, cloud, onset, persist

    def test_green_up(self):
        got = {}
        for it in self.fam("temporal.green_up_window"):
            name = it["question"].split("«")[1].split("»")[0]
            got[name] = (
                it["answer_value"]
                if it["answer_value"]
                else (ABSTAIN_TEXT if not it["answerable"] else "never")
            )
        self.assertEqual(got["البستان (عرض)"], "never")
        self.assertEqual(got["حقل مأرب 1 (عرض)"], ABSTAIN_TEXT)
        self.assertEqual(got["حقل تهامة 2 (عرض)"], ABSTAIN_TEXT)
        fx = json.loads(
            Path(self.fx).read_text(encoding="utf-8")
        )  # independent recompute from the raw rows
        series = {}
        names = {
            ft["properties"]["id"]: ft["properties"]["name"]
            for ft in fx["features"]
            if ft["properties"]["kind"] == "field"
        }
        for ft in fx["features"]:
            p = ft["properties"]
            if p["kind"] == "indicator" and p["indicator_id"] == "savi":
                series.setdefault(names[p["field_id"]], []).append(
                    (p["recorded_at"][:10], p["value"])
                )
        for name, val in got.items():
            if isinstance(val, list):
                s = sorted(series[name])
                k = next(i for i in range(len(s) - 1) if s[i][1] >= 0.2 and s[i + 1][1] >= 0.2)
                self.assertEqual(val, [s[k - 1][0], s[k][0]], name)

    def test_revision_tracks_content(self):
        """Same question identity, changed scene pixels -> same id, new revision."""
        import shutil

        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(self.rasters, tmp / "r")
        side = tmp / "r" / "savi_S2B_20260905_TIHAMA_DEMO.json"
        arr = np.load(tmp / "r" / json.loads(side.read_text())["array"])
        arr[arr > 0.2] = 0.9  # same scene id, different values
        np.save(tmp / "r" / json.loads(side.read_text())["array"], arr)
        store = load_fixture(str(self.fx), "demo-tenant")
        store.rasters = load_rasters(str(tmp / "r"))
        generate(
            store,
            DEFAULT_RULES,
            str(tmp / "qa"),
            holdout=parse_holdout(["test:governorate=الحديدة"]),
            images=True,
        )
        new = {}
        for p in (tmp / "qa").glob("*.jsonl"):
            if p.name != "data_issues.jsonl" and not p.name.endswith(".public.jsonl"):
                for ln in p.read_text(encoding="utf-8").splitlines():
                    it = json.loads(ln)
                    new[it["id"]] = it["revision"]
        old = {i["id"]: i["revision"] for i in self.items}
        changed = [i for i in self.items if i["id"] in new and new[i["id"]] != old[i["id"]]]
        self.assertTrue(changed)
        self.assertTrue(
            all("2026-09-05" in i["question"] or "2026-09-05" in i["context"] for i in changed)
        )
        self.assertTrue(
            all(
                new[k] == v
                for k, v in old.items()
                if k in new and k not in {i["id"] for i in changed}
            )
        )

    def test_timeline_layers_stay_out_of_single_scene_families(self):
        for it in self.items:
            ref = it.get("image_ref")
            if ref:
                self.assertFalse(ref["scene_id"].startswith("TL_"), it["id"])

    def test_new_families_in_every_split(self):
        for split in ("train", "val", "test"):
            for fam in (
                "reasoning.pivot_anomaly_pattern",
                "reasoning.next_measurement",
                "temporal.divergence_onset",
                "temporal.green_up_window",
            ):
                self.assertIn(fam, self.m["coverage"][split], (split, fam))
        self.assertGreater(self.m["coverage"]["test"]["temporal.green_up_window"]["abstention"], 0)
        self.assertGreater(self.m["coverage"]["val"]["temporal.divergence_onset"]["abstention"], 0)


if __name__ == "__main__":
    unittest.main()
