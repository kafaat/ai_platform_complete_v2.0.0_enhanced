import random
import unittest

from sahool_qa.arabic import normalize, to_arabic_digits
from sahool_qa.config import ABSTAIN_TEXT, DEFAULT_RULES, classify
from sahool_qa.facts import FactStore, Field
from sahool_qa.items import GenContext, bin_options, make_item, numeric_bins
from sahool_qa.score import parse_prediction


class TestBins(unittest.TestCase):
    def test_value_always_inside_with_margin(self):
        rng = random.Random(1)
        for _ in range(3000):
            w = rng.choice([0.25, 0.5, 1, 2.5, 5, 10, 25, 50, 100])
            v = rng.uniform(0, 40 * w)
            bins, idx = numeric_bins(v, w, 4, random.Random(rng.random()), floor=0)
            self.assertTrue(bins[idx][0] <= v < bins[idx][1])
            self.assertGreaterEqual(bins[0][0], -1e-9)
            for (_a, b), (c, _d) in zip(bins, bins[1:], strict=False):
                self.assertAlmostEqual(b, c)
            if v > 2 * w:  # far from the floor the value is never hugging an edge
                self.assertGreaterEqual(min(v - bins[idx][0], bins[idx][1] - v), 0.2 * w - 1e-9)

    def test_percent_bounds(self):
        for v in (0.0, 3.0, 50.0, 99.9, 100.0):
            bins, idx = numeric_bins(v, 10, 4, random.Random(int(v)), floor=0, ceil=100)
            self.assertGreaterEqual(bins[0][0], 0)
            self.assertLessEqual(bins[-1][1], 100 + 1e-9)
            self.assertTrue(bins[idx][0] <= min(v, 100 - 1e-6) < bins[idx][1])

    def test_display_has_no_misleading_rounding(self):
        correct, others, meta = bin_options(401.3, 0.06, "م", random.Random(3), min_width=25)
        for a, _b in meta["bins"]:
            self.assertEqual(a, round(a))  # integer edges when the width is an integer
        self.assertIn("م", correct)


class TestItems(unittest.TestCase):
    def ctx(self):
        store = FactStore()
        store.add_field(Field(id="f", name="F", tenant="t"))
        return GenContext(store=store, rules=dict(DEFAULT_RULES, abstain_option_rate=0.5), seed=3)

    def test_answer_key_points_at_correct_text(self):
        ctx = self.ctx()
        for k in range(200):
            it = make_item(
                ctx,
                family="t",
                level="scene_understanding",
                question="س",
                correct=f"صحيح {k}",
                distractors=["خطأ 1", "خطأ 2", "خطأ 3"],
                evidence={"kind": "derived"},
                context="",
                field_refs=["t::f"],
                key={"k": k},
            )
            opt = {o["key"]: o["text"] for o in it["options"]}
            self.assertEqual(opt[it["answer"]], f"صحيح {k}")
            self.assertEqual(len(set(opt.values())), len(opt))

    def test_unknown_dependency_is_refused(self):
        it = make_item(
            self.ctx(),
            family="t",
            level="object_understanding",
            question="س",
            correct="x",
            distractors=["y", "z"],
            evidence={"kind": "derived"},
            context="",
            field_refs=["t::missing"],
            key={},
        )
        self.assertIsNone(it)

    def test_abstain_never_duplicated(self):
        ctx = GenContext(
            store=self.ctx().store, rules=dict(DEFAULT_RULES, abstain_option_rate=1.0), seed=1
        )
        it = make_item(
            ctx,
            family="t",
            level="scene_reasoning",
            question="س",
            correct="x",
            distractors=["y", ABSTAIN_TEXT],
            evidence={"kind": "derived"},
            context="",
            field_refs=["t::f"],
            key={},
        )
        texts = [o["text"] for o in it["options"]]
        self.assertEqual(len(texts), len(set(texts)))

    def test_unanswerable_correct_is_abstain(self):
        it = make_item(
            self.ctx(),
            family="t",
            level="object_understanding",
            question="س",
            correct=None,
            distractors=["أ", "ب", "ج"],
            evidence={"kind": "derived"},
            context="",
            field_refs=["t::f"],
            key={},
            answerable=False,
        )
        self.assertEqual(it["answer_text"], ABSTAIN_TEXT)
        self.assertFalse(it["answerable"])

    def test_ids_are_deterministic(self):
        a = make_item(
            self.ctx(),
            family="t",
            level="scene_reasoning",
            question="س",
            correct="x",
            distractors=["y", "z"],
            evidence={"kind": "derived"},
            context="",
            field_refs=["t::f"],
            key={"f": 1},
        )
        b = make_item(
            self.ctx(),
            family="t",
            level="scene_reasoning",
            question="س",
            correct="x",
            distractors=["y", "z"],
            evidence={"kind": "derived"},
            context="",
            field_refs=["t::f"],
            key={"f": 1},
        )
        self.assertEqual(a, b)

    def test_classify_conventions(self):
        cls = DEFAULT_RULES["soil_salinity_classes"]
        self.assertEqual(classify(2.0, cls), "ملوحة خفيفة")  # [2, 4)
        self.assertEqual(classify(1.999, cls), "غير ملحية")
        suit = DEFAULT_RULES["soil_suitability_classes"]
        self.assertEqual(
            classify(8.0, suit, True), "حدّية (تحتاج غسيلاً وصرفاً)"
        )  # Excel: IF(x>8,...)
        self.assertEqual(classify(8.01, suit, True), "ضعيفة (تحتاج استصلاحاً)")
        self.assertEqual(classify(4.0, suit, True), "مناسبة")


class TestScoringParse(unittest.TestCase):
    item = {
        "options": [
            {"key": "أ", "text": "45–55 هكتار"},
            {"key": "ب", "text": "ارتفع بأكثر من 100%"},
            {"key": "ج", "text": "قمح"},
            {"key": "د", "text": ABSTAIN_TEXT},
        ],
        "answer": "أ",
    }

    def test_letters(self):
        for p, k in [
            ("أ", "أ"),
            ("ا", "أ"),
            ("(ب)", "ب"),
            ("ج)", "ج"),
            ("د. لا تتوفر", "د"),
            ("A", "أ"),
            ("b)", "ب"),
            ("D", "د"),
            ("الإجابة", None),
        ]:
            self.assertEqual(parse_prediction(p, self.item), k, p)

    def test_text_and_digits(self):
        self.assertEqual(parse_prediction("٤٥–٥٥ هكتار", self.item), "أ")
        self.assertEqual(parse_prediction("الإجابة: قمح", self.item), "ج")
        self.assertEqual(parse_prediction(ABSTAIN_TEXT, self.item), "د")
        self.assertIsNone(parse_prediction("شعير", self.item))

    def test_arabic_digits_roundtrip(self):
        s = "المساحة 1,234.5 هكتار"
        self.assertEqual(normalize(to_arabic_digits(s)), normalize(s))


if __name__ == "__main__":
    unittest.main()
