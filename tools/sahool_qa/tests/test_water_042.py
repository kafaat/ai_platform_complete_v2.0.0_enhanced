"""0.4.2: the two meters of a well must agree, zero flow needs a status record, a missing well
inventory is announced, and the rule wording a blind checker could read two ways is fixed."""
import copy
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sahool_qa.audit import audit
from sahool_qa.config import ABSTAIN_TEXT, DEFAULT_RULES
from sahool_qa.demo import build_fixture, write_demo
from sahool_qa.generators import water
from sahool_qa.items import GenContext
from sahool_qa.pipeline import generate
from sahool_qa.preview import evidence_line
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.split import parse_holdout

DAY = dt.timedelta(days=1)
HOLD = ["test:governorate=الحديدة", "val:governorate=مأرب"]


def d(s):
    return dt.date.fromisoformat(s)


class Demo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fx, _ = write_demo(cls.tmp.name)
        store = load_fixture(str(cls.fx), "demo-tenant")
        cls.m = generate(store, DEFAULT_RULES, str(Path(cls.tmp.name) / "qa"), families="water.", images=False,
                         holdout=parse_holdout(HOLD))
        qa = Path(cls.tmp.name) / "qa"
        cls.items = [json.loads(l) for s in ("train", "val", "test") for l in (qa / f"{s}.jsonl").read_text("utf-8").splitlines()]
        cls.issues = [json.loads(l) for l in (qa / "data_issues.jsonl").read_text("utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def of(self, family, field):
        return [i for i in self.items if i["family"] == family
                and any(r.get("field_id") == field for r in i["evidence"]["records"] if r["table"] == "field_boundaries")]

    def ctx(self):
        s = load_fixture(str(self.fx), "demo-tenant")
        rules = copy.deepcopy(DEFAULT_RULES)
        s.prepare(rules)
        return GenContext(s, rules)

    @staticmethod
    def fw(ctx, fid):
        return next(w for w in water._fw(ctx).values() if w.field.id == fid)


class StalledVolumeMeter(Demo):
    def test_windows_with_a_stall_are_unknown_others_answered(self):
        for field, stalled_week in (("demo_orchard", ("2026-01-12", "2026-01-19")),
                                    ("demo_tihama_strip", ("2026-07-15", "2026-07-22"))):
            got = {tuple(i["evidence"]["values"]["window"]): (i["answerable"], i["evidence"]["values"].get("problem"))
                   for i in self.of("water.applied_depth", field)}
            whole = max(got, key=lambda w: d(w[1]) - d(w[0]))
            self.assertEqual(got.pop(whole), (False, "volume_meter_stalled"), field)
            self.assertEqual(got.pop(stalled_week), (False, "volume_meter_stalled"), field)
            self.assertTrue(got and all(v == (True, None) for v in got.values()), (field, got))

    def test_stall_reading_is_offered_as_the_careless_answer(self):
        for it in self.of("water.applied_depth", "demo_orchard"):
            if not it["answerable"]:
                naive = it["evidence"]["values"]["naive"]             # the stalled meter taken at face value
                bins = [tuple(map(float, o["text"].split()[0].split("-"))) for o in it["options"] if o["text"] != ABSTAIN_TEXT]
                self.assertTrue(any(lo <= naive < hi for lo, hi in bins), (naive, bins))

    def test_audit_flags_each_stalled_meter(self):
        flagged = {i["indicator_id"] for i in self.issues if i["code"] == "volume_meter_stalled"}
        self.assertEqual(flagged, {"meter_total_OR1", "meter_total_TS1"})
        # a reset is a decrease, not a stall
        self.assertFalse([i for i in self.issues if i["code"] == "volume_meter_stalled" and "MP1" in i["indicator_id"]])

    def test_flat_volume_below_threshold_is_still_not_zero_flow(self):
        c = self.ctx()
        fw = self.fw(c, "demo_pivot_2")
        for kind, fn in (("meter", lambda k: 5000.0), ("pump_hours", lambda k: 100 + 0.1 * k)):   # 0.7 h a week
            for s in fw.of(kind).values():
                start = s.days()[0]
                for day, rs in s.records.items():
                    for r in rs:
                        r.value = r.conv = fn((day - start).days)
        c.cache["water"].pop("stress", None)
        items = [i for i in water.gen_refill_feasibility(c) if i["field_refs"][0].endswith("demo_pivot_2")]
        self.assertFalse([i for i in items if i["answer_value"] == "unavailable"])


class WellStatus(Demo):
    def test_logged_outage_is_a_known_zero_flow(self):
        got = {i["question"].split("نهاية يوم ")[2][:10]: (i["answerable"], i["answer_value"])
               for i in self.of("water.refill_feasibility", "demo_tihama_pivot")}
        self.assertEqual(got["2026-07-08"], (True, "few"))
        for day in ("2026-07-15", "2026-07-22", "2026-07-29"):
            self.assertEqual(got[day], (True, "unavailable"), day)

    def test_logged_failure_counts_zero_but_unlogged_idle_well_stays_unknown(self):
        got = {i["question"].split("نهاية يوم ")[2][:10]: i for i in self.of("water.refill_feasibility", "demo_pivot_1")}
        flows = got["2026-01-26"]["evidence"]["values"]["flows"]
        self.assertEqual(flows["meter_total_P1B"]["status"], "out_of_service")
        self.assertEqual(flows["meter_total_P1B"]["flow_m3_h"], 0.0)
        self.assertEqual(got["2026-01-26"]["answer_value"], "many")
        self.assertFalse(got["2026-02-02"]["answerable"])           # P1A diesel cut not logged
        self.assertEqual(got["2026-02-02"]["evidence"]["values"]["problem"], "pump_hours_not_increasing")

    def test_volume_while_out_of_service_is_a_conflict(self):
        c = self.ctx()
        fw = self.fw(c, "demo_tihama_pivot")
        for day, rs in fw.of("meter")["tp1"].records.items():
            if day >= d("2026-07-20"):                                # water while the log says out of service
                for r in rs:
                    r.value = r.conv = r.conv + 500.0
        c.cache["water"].pop("stress", None)
        res = water.irrigation_window(c, fw, d("2026-07-15"), d("2026-07-22"))
        self.assertEqual(res["problem"], "well_status_conflict")
        self.assertIn("well_status_conflict", [i["code"] for i in audit(c.store, c.rules)])

    def test_stalled_hour_meter_blocks_flow_not_volume(self):
        c = self.ctx()
        fw = self.fw(c, "demo_pivot_2")
        hs = fw.of("pump_hours")["p2a"]
        frozen = hs.value(d("2026-01-08"))
        for day in (d("2026-01-09"), d("2026-01-10"), d("2026-01-11")):
            for r in hs.records[day]:
                r.value = r.conv = frozen
        c.cache["water"].pop("stress", None)
        self.assertIn("depth", water.irrigation_window(c, fw, d("2026-01-05"), d("2026-01-12")))
        items = [i for i in water.gen_refill_feasibility(c) if i["field_refs"][0].endswith("demo_pivot_2")]
        first = next(i for i in items if "نهاية يوم 2026-01-12" in i["question"])
        self.assertEqual((first["answerable"], first["evidence"]["values"]["problem"]), (False, "hour_meter_stalled"))


class EvidenceIsInTheContext(Demo):
    """A blind checker could not see the hour meters or the status log in 0.4.2-rc: every record a
    meter rule reads must be in the question context and in the evidence references."""

    def test_meter_contexts_show_both_meters_and_status_log(self):
        for it in self.items:
            if it["family"] in ("water.applied_depth", "water.plan_vs_measured", "water.stress_status",
                                "water.refill_feasibility"):
                ids = {r["indicator_id"] for r in it["evidence"]["records"] if r["table"] == "field_indicators"}
                for iid in ids:
                    if iid.startswith(("meter_total_", "pump_hours_", "well_status_")):
                        self.assertIn(iid, it["context"], (it["id"], iid))
                wells = {i[len("meter_total_"):] for i in ids if i.startswith("meter_total_")}
                hours = {i[len("pump_hours_"):] for i in ids if i.startswith("pump_hours_")}
                self.assertEqual(wells, hours, it["id"])            # every demo well has both meters

    def test_status_records_reach_the_refill_context(self):
        it = next(i for i in self.items if i["family"] == "water.refill_feasibility" and i["answer_value"] == "unavailable")
        self.assertIn("well_status_TP1", it["context"])
        self.assertIn("2026-07-09: 0", it["context"])


class InventoryAnnounced(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        fx = build_fixture()
        fx["sahool_qa"]["provenance"].pop("water_well_inventory")
        self.fx = Path(self.tmp.name) / "fx.geojson"
        self.fx.write_text(json.dumps(fx, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixture_provenance_is_not_shared_between_builds(self):
        self.assertIn("water_well_inventory", build_fixture()["sahool_qa"]["provenance"])

    def test_manifest_warns_and_lists_fields(self):
        m = generate(load_fixture(str(self.fx), "demo-tenant"), DEFAULT_RULES, str(Path(self.tmp.name) / "qa"),
                     families="water.applied_depth", images=False)
        self.assertEqual(len(m["water_inventory"]["without_inventory"]), m["water_inventory"]["metered_fields"])
        self.assertTrue(any("no declared well inventory" in w for w in m["warnings"]))

    def test_require_flag_refuses_to_generate(self):
        with self.assertRaisesRegex(ValueError, "well inventory"):
            generate(load_fixture(str(self.fx), "demo-tenant"), DEFAULT_RULES, str(Path(self.tmp.name) / "qa"),
                     families="water.", images=False, require_well_inventory=True)
        self.assertFalse((Path(self.tmp.name) / "qa").exists())
        p = subprocess.run([sys.executable, "-m", "sahool_qa", "generate", "--fixture", str(self.fx), "--tenant",
                            "demo-tenant", "--out", str(Path(self.tmp.name) / "qa2"), "--families", "water.",
                            "--no-images", "--require-well-inventory"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("well inventory", p.stderr)


class Wording(Demo):
    def test_refill_question_names_the_flow_window(self):
        for it in self.items:
            if it["family"] == "water.refill_feasibility":
                a, D, _ = __import__("re").findall(r"\d{4}-\d{2}-\d{2}", it["question"])
                self.assertEqual(d(D) - d(a), 7 * DAY)
                self.assertIn("قراءة نهاية اليوم الذي يسبق اليوم المسؤول عنه", it["context"])

    def test_probe_rule_and_valid_reading_are_stated(self):
        it = next(i for i in self.items if i["family"] == "water.stress_status")
        self.assertIn("تُعامل متوسطاً للمنطقة الجذرية كلها أياً كان عمق المجس", it["context"])
        self.assertIn("القراءة الصالحة = سجل اجتاز فحص الجودة", it["context"])
        depth = next(i for i in self.items if i["family"] == "water.applied_depth")
        self.assertIn("«x-y» يشمل x ولا يشمل y", depth["context"])
        self.assertIn("ما لم يتقدم عداد ساعات البئر نفسها", depth["context"])

    def test_pumping_days_ranges_and_no_dangling_reference(self):
        it = next(i for i in self.items if i["family"] == "water.refill_feasibility")
        self.assertIn("فيوم القراءة الأولى نفسه ليس منها", it["context"])
        self.assertIn("بقيمة 0 في كل أيام الضخ بينهما", it["context"])
        for i in self.items:
            self.assertNotIn("انظر التحفظات", i["context"])
        depth = next(i for i in self.items if i["family"] == "water.applied_depth")
        self.assertIn("الرطوبة 0 إلى 0.6 m3/m3", depth["context"])

    def test_parameter_lines_render_as_ltr_blocks(self):
        it = next(i for i in self.items if i["family"] == "water.stress_status" and i["answerable"])
        lines = [l for l in it["evidence"]["rule"].split("\n") if l.startswith(("θFC = ", "θWP = ", "Zr = ", "fao_crop = "))]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertTrue(evidence_line(line).startswith('<div class="formula" dir="ltr">'), line)


if __name__ == "__main__":
    unittest.main()
