"""End-to-end checks on the demo fixture, with answers re-derived independently
of the generator code paths where that is possible."""
import json
import math
import random
import statistics
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from sahool_qa.config import ABSTAIN_TEXT, DEFAULT_RULES
from sahool_qa.demo import SOIL_2022, SOIL_2025, write_demo
from sahool_qa.pipeline import generate
from sahool_qa.raster import decode_png, load_rasters
from sahool_qa.score import score
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.split import parse_holdout

HOLDOUT = ["test:governorate=الحديدة", "val:governorate=مأرب"]


def read_items(out):
    items = []
    for p in sorted(Path(out).glob("*.jsonl")):
        if p.name != "data_issues.jsonl" and not p.name.endswith(".public.jsonl"):
            items += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    return items


def run(out, seed=7, **kw):
    fx, rasters = write_demo(out)
    store = load_fixture(str(fx), "demo-tenant")
    store.rasters = load_rasters(str(rasters))
    m = generate(store, DEFAULT_RULES, str(Path(out) / "qa"), seed=seed, holdout=parse_holdout(HOLDOUT), **kw)
    return m, read_items(Path(out) / "qa"), store


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.m, cls.items, cls.store = run(cls.tmp)
        cls.out = Path(cls.tmp) / "qa"

    def test_structure(self):
        self.assertEqual(len(self.items), self.m["counts"]["items_total"])
        self.assertGreater(len(self.items), 300)
        for it in self.items:
            keys = [o["key"] for o in it["options"]]
            texts = [o["text"] for o in it["options"]]
            self.assertIn(it["answer"], keys)
            self.assertEqual(dict(zip(keys, texts))[it["answer"]], it["answer_text"])
            self.assertEqual(len(set(texts)), len(texts), it["id"])
            self.assertGreaterEqual(len(texts), 3, it["id"])
            if not it["answerable"]:
                self.assertEqual(it["answer_text"], ABSTAIN_TEXT)
            self.assertTrue(it["synthetic"])
            self.assertTrue(it["evidence"].get("computation"), it["family"])
            self.assertTrue(all(fk in self.store.fields for fk in it["field_refs"]))
        self.assertEqual(len({it["id"] for it in self.items}), len(self.items))
        self.assertEqual(self.m["family_errors"], {})

    def test_every_family_in_every_split(self):
        from sahool_qa.generators import FAMILIES
        for split in ("train", "val", "test"):
            self.assertEqual(set(self.m["coverage"][split]), set(FAMILIES), split)
        test_cov = self.m["coverage"]["test"]
        self.assertGreater(sum(v["with_image"] for v in test_cov.values()), 0)
        abst_families = {f for f, v in test_cov.items() if v["abstention"]}
        self.assertGreaterEqual(len(abst_families), 4, abst_families)   # not only soil.nutrient

    def test_public_files_hide_answers(self):
        for split in ("train", "val", "test"):
            rows = [json.loads(l) for l in (self.out / f"{split}.public.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            for r in rows:
                for k in ("answer", "answer_text", "answer_value", "evidence", "answerable", "abstain_offered"):
                    self.assertNotIn(k, r)

    def test_no_record_owner_in_two_splits(self):
        owner = defaultdict(set)
        for it in self.items:
            for fk in it["field_refs"]:
                owner[fk].add(it["split"])
            for r in it["evidence"].get("records", []):
                owner[r["field_key"]].add(it["split"])
        self.assertTrue(all(len(s) == 1 for s in owner.values()), {k: v for k, v in owner.items() if len(v) > 1})
        tihama = [it for it in self.items if any("الحديدة" in u for u in it["split_units"])]
        self.assertTrue(tihama and all(it["split"] == "test" for it in tihama))

    def test_salinity_answers_from_raw_seed_values(self):
        ec = {sid: e for sid, _, e, _ in SOIL_2022} | {sid: e for sid, _, e, *_ in SOIL_2025}
        n = 0
        for it in self.items:
            if it["family"] != "soil.salinity_class" or not it["answerable"]:
                continue
            sid = it["evidence"]["records"][0]["sample_id"]
            if sid not in ec:
                continue
            v = ec[sid]
            expect = "غير ملحية" if v < 2 else "ملوحة خفيفة" if v < 4 else "ملوحة متوسطة" if v < 8 else "ملحية"
            self.assertEqual(it["answer_text"], expect, sid)
            n += 1
        self.assertEqual(n, 16)

    def test_ec_change_real_numbers(self):
        it = next(i for i in self.items if i["family"] == "temporal.ec_change" and "السنيدار" in i["question"])
        m22 = statistics.fmean(e for _, _, e, _ in SOIL_2022)
        m25 = statistics.fmean(r[2] for r in SOIL_2025)
        self.assertAlmostEqual(it["evidence"]["values"]["relative_change"], (m25 - m22) / m22, places=3)
        self.assertEqual(it["answer_text"], "ارتفع بأكثر من 100%")

    def test_area_bins_contain_independent_area(self):
        # Jawf pivots are regular 96-gons of radius 401 m: A = n/2 r^2 sin(2π/n)
        expect = 96 / 2 * 401 ** 2 * math.sin(2 * math.pi / 96) / 1e4
        hits = 0
        for it in self.items:
            if it["family"] == "scene.area" and "«المحور" in it["question"]:
                lo, hi = [float(x.replace(",", "")) for x in it["answer_text"].split()[0].split("-")]
                self.assertTrue(lo <= expect < hi, (it["answer_text"], expect))
                self.assertAlmostEqual(it["answer_value"], expect, delta=expect * 2e-3)
                hits += 1
        self.assertEqual(hits, 2)

    def test_weak_quadrants_are_the_planted_gaps(self):
        want = {"المحور 1": "الربع الشمالي الشرقي", "محور مأرب": "الربع الشمالي الغربي", "محور تهامة": "الربع الجنوبي الغربي"}
        got = {}
        for it in self.items:
            if it["family"] == "reasoning.pivot_weak_quadrant":
                name = next(k for k in want if f"«{k}" in it["question"])
                got[name] = it["answer_text"]
                png = (self.out / it["image"]).read_bytes()
                self.assertTrue(png.startswith(b"\x89PNG"))
                decode_png(png)
        self.assertEqual(got, want)

    def test_images_reproduce_answers(self):
        self.assertEqual(self.m["images"].get("dropped_not_reproducible_from_png", 0), 0)
        self.assertEqual(self.m["images"]["verified"], self.m["counts"]["with_image"])

    def test_audit_catches_planted_problems(self):
        issues = [json.loads(l) for l in (self.out / "data_issues.jsonl").read_text(encoding="utf-8").splitlines()]
        codes = {i["code"] for i in issues}
        for c in ("area_mismatch", "duplicate_sample_location", "sample_outside_country", "field_no_polygon",
                  "unknown_ec_unit", "ec_out_of_range", "ph_out_of_range", "value_not_finite",
                  "sample_near_boundary", "rejected_out_of_scope_tenant"):
            self.assertIn(c, codes)
        self.assertTrue(any(i["code"] == "sample_outside_country" and "مقلوب" in i["message"] for i in issues))
        self.assertFalse(any("FOREIGN-1" in json.dumps(it, ensure_ascii=False) for it in self.items))

    def test_no_area_question_for_mismatched_field(self):
        self.assertFalse(any(i["family"] == "scene.area" and "تهامة 2" in i["question"] for i in self.items))

    def test_qc_failures_become_abstentions(self):
        bad = [i for i in self.items if "«T1-BAD (2026)»" in i["question"]]
        self.assertTrue(bad)
        self.assertTrue(all(not i["answerable"] for i in bad))

    def test_scoring(self):
        gold = self.items
        perfect = score(gold, [{"id": i["id"], "prediction": i["answer"]} for i in gold])
        self.assertEqual(perfect["accuracy"], 1.0)
        self.assertEqual(perfect["abstention"]["hallucination_rate"], 0.0)
        rng = random.Random(0)
        rand = score(gold, [{"id": i["id"], "prediction": rng.choice(i["options"])["key"]} for i in gold])
        self.assertLess(abs(rand["accuracy"] - rand["chance_accuracy"]), 0.08)
        always_abstain = score(gold, [{"id": i["id"], "prediction": ABSTAIN_TEXT} for i in gold])
        self.assertEqual(always_abstain["abstention"]["correct_abstention_rate"], 1.0)
        self.assertEqual(always_abstain["abstention"]["false_abstention_rate"], 1.0)
        as_text = score(gold, [{"id": i["id"], "prediction": i["answer_text"]} for i in gold])
        self.assertEqual(as_text["accuracy"], 1.0)

    def test_determinism_and_seed_independence_of_splits(self):
        tmp2 = tempfile.mkdtemp()
        _, items2, _ = run(tmp2)
        strip = lambda rows: [{k: v for k, v in r.items() if k != "image_ref"} for r in rows]  # noqa: E731
        self.assertEqual(strip(sorted(self.items, key=lambda r: r["id"])), strip(sorted(items2, key=lambda r: r["id"])))
        _, items3, _ = run(tempfile.mkdtemp(), seed=99)
        s1 = {i["id"]: i["split"] for i in self.items}
        s3 = {i["id"]: i["split"] for i in items3}
        common = set(s1) & set(s3)
        self.assertGreater(len(common), 0.9 * len(s1))
        self.assertTrue(all(s1[k] == s3[k] for k in common))

    def test_preview_is_self_contained(self):
        html = (self.out / "preview.html").read_text(encoding="utf-8")
        self.assertIn('dir="rtl"', html)
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn('src="images/', html)
        from html.parser import HTMLParser

        class Nesting(HTMLParser):          # every element closed, in order
            VOID = {"meta", "link", "br", "img", "hr", "input"}

            def __init__(self):
                super().__init__()
                self.stack, self.errors = [], []

            def handle_starttag(self, tag, attrs):
                if tag not in self.VOID:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if not self.stack or self.stack[-1] != tag:
                    self.errors.append((tag, list(self.stack[-3:])))
                else:
                    self.stack.pop()
        n = Nesting()
        n.feed(html)
        self.assertEqual(n.errors, [])
        self.assertEqual(n.stack, [])
        self.assertIn('<span class="v" dir="ltr">[', html)   # coordinate lists are laid out LTR

    def test_cap_and_digits(self):
        m, items, _ = run(tempfile.mkdtemp(), max_per_family=5, arabic_digits=True, images=False)
        self.assertLessEqual(max(Counter(i["family"] for i in items).values()), 5)
        self.assertFalse(any(i.get("image_ref") for i in items))   # image questions need their image
        area = next(i for i in items if i["family"] == "scene.area" and i["answerable"])
        self.assertTrue(any("٠" <= ch <= "٩" for ch in area["answer_text"]))
        self.assertFalse(any(ch.isascii() and ch.isdigit() for ch in area["answer_text"]))
        for i in items:  # identifiers survive: sample ids, USSL classes, ISO dates
            if i["family"] in ("spatial.point_in_field", "soil.max_ec"):   # sample ids keep Western digits
                self.assertFalse(any("٠" <= c <= "٩" for o in i["options"] for c in o["text"].split()[0]))
            if i["family"] == "water.salinity_class":
                self.assertTrue(any(o["text"].startswith("C1") for o in i["options"]))
            if i["family"] == "temporal.index_trend":
                self.assertRegex(i["question"], r"\d{4}-\d{2}-\d{2}")
        self.assertEqual(score(items, [{"id": i["id"], "prediction": i["answer_text"]} for i in items])["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
