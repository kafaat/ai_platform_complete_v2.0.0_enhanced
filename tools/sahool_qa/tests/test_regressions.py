"""Regression tests for review findings F01–F12 (review of sahool-qa 0.1.0,
13 Oct 2026). Each test reproduces the counter-case from the review and
asserts the corrected behaviour."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from sahool_qa.config import ABSTAIN_TEXT, DEFAULT_RULES
from sahool_qa.demo import circle, poly_geojson, rect
from sahool_qa.geo import Geometry
from sahool_qa.pipeline import fingerprint, generate
from sahool_qa.score import score
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.split import parse_holdout


def feat(geom, **p):
    return {"type": "Feature", "geometry": geom, "properties": p}


def pt(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


def write_fx(features, tmp, name="fx.geojson"):
    p = Path(tmp) / name
    p.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(p)


def read_items(out):
    rows = []
    for p in sorted(Path(out).glob("*.jsonl")):
        if p.name == "data_issues.jsonl" or p.name.endswith(".public.jsonl"):
            continue
        rows += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()]
    return rows


A = (44.9420, 16.0905)


class F01_FixtureTenantIsolation(unittest.TestCase):
    def test_foreign_rows_on_own_field_are_not_loaded(self):
        tmp = tempfile.mkdtemp()
        fx = write_fx(
            [
                feat(
                    poly_geojson(rect(*A, 300, 300)),
                    kind="field",
                    id="fa",
                    name="A",
                    tenant="tenant-a",
                    governorate="الجوف",
                ),
                feat(
                    pt(*A),
                    kind="soil",
                    field_id="fa",
                    sample_id="S1",
                    ec=1.0,
                    recorded_at="2025-01-01",
                    tenant="tenant-a",
                ),
                feat(
                    pt(*A),
                    kind="soil",
                    field_id="fa",
                    sample_id="X1",
                    ec=9.0,
                    recorded_at="2025-01-01",
                    tenant="tenant-b",
                ),
                feat(
                    None,
                    kind="indicator",
                    field_id="fa",
                    indicator_id="savi",
                    value=0.5,
                    recorded_at="2025-01-01",
                    tenant="tenant-b",
                ),
            ],
            tmp,
        )
        store = load_fixture(fx, "tenant-a")
        self.assertEqual({s.tenant for s in store.soil}, {"tenant-a"})
        self.assertEqual(store.indicators, [])
        self.assertEqual(store.rejected.get("out_of_scope_tenant"), 2)


class F02_AssociationRespectsTenant(unittest.TestCase):
    def test_spatial_and_id_association_never_cross_tenants(self):
        tmp = tempfile.mkdtemp()
        fx = write_fx(
            [
                feat(
                    poly_geojson(rect(*A, 400, 400)),
                    kind="field",
                    id="f1",
                    name="A",
                    tenant="tenant-a",
                    governorate="الجوف",
                ),
                feat(
                    poly_geojson(rect(A[0] + 0.01, A[1], 400, 400)),
                    kind="field",
                    id="f1",
                    name="B",
                    tenant="tenant-b",
                    governorate="الجوف",
                ),
                # tenant-b sample located inside tenant-a's polygon, same field_id string
                feat(
                    pt(*A),
                    kind="soil",
                    field_id="f1",
                    sample_id="B-1",
                    ec=5.0,
                    recorded_at="2025-01-01",
                    tenant="tenant-b",
                ),
                feat(
                    pt(*A),
                    kind="soil",
                    field_id="f1",
                    sample_id="A-1",
                    ec=1.0,
                    recorded_at="2025-01-01",
                    tenant="tenant-a",
                ),
            ],
            tmp,
        )
        store = load_fixture(fx, None, all_tenants=True)
        self.assertEqual(len(store.fields), 2)  # composite (tenant, field_id) keys
        fa = next(f for f in store.fields.values() if f.tenant == "tenant-a")
        fb = next(f for f in store.fields.values() if f.tenant == "tenant-b")
        self.assertEqual([s.sample_id for s, _ in store.samples_for(fa)], ["A-1"])
        self.assertEqual([s.sample_id for s, _ in store.samples_for(fb)], [])


def _heldout_fixture(tmp):
    """train-0 has a polygon; 'heldout' has none but its records sit inside train-0."""
    feats = [
        feat(
            poly_geojson(rect(*A, 600, 600)),
            kind="field",
            id="train-0",
            name="T0",
            crop="قمح",
            tenant="t",
            governorate="الجوف",
        ),
        feat(
            poly_geojson(rect(A[0] + 0.02, A[1], 300, 300)),
            kind="field",
            id="train-1",
            name="T1",
            crop="قمح",
            tenant="t",
            governorate="الجوف",
        ),
        feat(
            None, kind="field", id="heldout", name="H", crop="شعير", tenant="t", governorate="الجوف"
        ),
    ]
    for i, (dx, ec) in enumerate(((-0.001, 1.2), (0.001, 1.5), (0.0, 2.2))):
        feats.append(
            feat(
                pt(A[0] + dx, A[1]),
                kind="soil",
                field_id="train-0",
                sample_id=f"T{i}",
                ec=ec,
                ph=7.8,
                recorded_at="2025-03-01",
                tenant="t",
            )
        )
        feats.append(
            feat(
                pt(A[0] + dx, A[1] + 0.0005),
                kind="soil",
                field_id="heldout",
                sample_id=f"H{i}",
                ec=ec + 3,
                ph=8.0,
                recorded_at="2026-03-01",
                tenant="t",
            )
        )
    for k in range(8):
        feats.append(
            feat(
                pt(A[0], A[1] + 0.0004),
                kind="indicator",
                field_id="heldout",
                indicator_id="savi",
                value=0.1 + 0.05 * k,
                recorded_at=f"2026-0{1 + k // 4}-{1 + 7 * (k % 4):02d}",
                tenant="t",
            )
        )
    return write_fx(feats, tmp)


class F03_F04_RecordsFromHeldoutNeverInTrain(unittest.TestCase):
    def test_no_train_item_sees_heldout_records(self):
        tmp = tempfile.mkdtemp()
        store = load_fixture(_heldout_fixture(tmp), "t")
        out = Path(tmp, "qa")
        generate(
            store,
            DEFAULT_RULES,
            str(out),
            split_unit="field",
            holdout=parse_holdout(["field=heldout"]),
            images=False,
        )
        items = read_items(out)
        self.assertTrue(items)
        for it in items:
            recs = {r.get("field_id") for r in it["evidence"].get("records", [])}
            if it["split"] != "test":
                self.assertNotIn("heldout", recs, it["id"])
                self.assertNotIn("field_id=heldout", it["context"], it["id"])
        dropped = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["split"][
            "dropped"
        ]
        self.assertGreater(dropped.get("cross_split", 0), 0)


class F05_InvalidPredictionsAreNotHallucinations(unittest.TestCase):
    def test_missing_and_unparsed(self):
        gold = [
            {
                "id": f"q{i}",
                "level": "object_understanding",
                "family": "soil.nutrient",
                "answerable": False,
                "answer": "أ",
                "options": [
                    {"key": "أ", "text": ABSTAIN_TEXT},
                    {"key": "ب", "text": "1–2 mg/kg"},
                    {"key": "ج", "text": "2–3 mg/kg"},
                ],
            }
            for i in range(15)
        ]
        for preds in ([], [{"id": f"q{i}", "prediction": "???"} for i in range(15)]):
            rep = score(gold, preds)
            ab = rep["abstention"]
            self.assertEqual(ab["valid_predictions"], 0)
            self.assertIsNone(ab["hallucination_rate"])
            self.assertEqual(ab["invalid_predictions"], 15)
            self.assertEqual(ab["abstention_failure_incl_invalid"], 1.0)
            self.assertEqual(rep["coverage"], 0.0)
        rep = score(gold, [{"id": "q0", "prediction": "ب"}, {"id": "q1", "prediction": "أ"}])
        self.assertEqual(rep["abstention"]["hallucination_rate"], 0.5)
        self.assertEqual(rep["abstention"]["valid_predictions"], 2)


class F06_RepublishReplacesWholeOutput(unittest.TestCase):
    def test_mode_change_leaves_no_stale_files(self):
        tmp = tempfile.mkdtemp()
        store = load_fixture(_heldout_fixture(tmp), "t")
        out = Path(tmp, "qa")
        generate(
            store,
            DEFAULT_RULES,
            str(out),
            split_unit="field",
            holdout=parse_holdout(["field=heldout"]),
            images=False,
        )
        self.assertTrue((out / "train.jsonl").exists())
        m = generate(store, DEFAULT_RULES, str(out), split_mode="none", images=False)
        names = sorted(p.name for p in out.iterdir())
        self.assertNotIn("train.jsonl", names)
        self.assertNotIn("test.jsonl", names)
        self.assertEqual(len(read_items(out)), m["counts"]["items_total"])
        self.assertEqual(sorted(m["outputs"]), sorted(n for n in names if n != "manifest.json"))

    def test_refuses_foreign_directory(self):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "notes.txt").write_text("keep me")
        store = load_fixture(_heldout_fixture(tempfile.mkdtemp()), "t")
        with self.assertRaises(RuntimeError):
            generate(store, DEFAULT_RULES, tmp, split_mode="none", images=False)
        self.assertEqual((Path(tmp) / "notes.txt").read_text(), "keep me")


class F07_InvalidPolygonDoesNotStopTheRun(unittest.TestCase):
    def test_bowtie_zero_area_with_stored_area(self):
        tmp = tempfile.mkdtemp()
        bow = {
            "type": "Polygon",
            "coordinates": [
                [[44.94, 16.09], [44.95, 16.10], [44.95, 16.09], [44.94, 16.10], [44.94, 16.09]]
            ],
        }
        zero = {
            "type": "Polygon",
            "coordinates": [[[44.94, 16.09], [44.95, 16.09], [44.96, 16.09], [44.94, 16.09]]],
        }
        fx = write_fx(
            [
                feat(
                    bow,
                    kind="field",
                    id="bow",
                    name="Bow",
                    area_ha=12.0,
                    tenant="t",
                    governorate="الجوف",
                ),
                feat(
                    zero,
                    kind="field",
                    id="zero",
                    name="Zero",
                    area_ha=5.0,
                    tenant="t",
                    governorate="الجوف",
                ),
                feat(
                    poly_geojson(rect(*A, 300, 300)),
                    kind="field",
                    id="ok",
                    name="OK",
                    crop="قمح",
                    tenant="t",
                    governorate="الجوف",
                ),
            ],
            tmp,
        )
        out = Path(tmp, "qa")
        m = generate(
            load_fixture(fx, "t"), DEFAULT_RULES, str(out), split_mode="none", images=False
        )
        issues = [
            json.loads(ln)
            for ln in (out / "data_issues.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            {i["field_id"] for i in issues if i["code"] == "invalid_polygon"}, {"t::bow", "t::zero"}
        )
        self.assertEqual(m["family_errors"], {})
        items = read_items(out)
        self.assertTrue(any(i["family"] == "scene.area" and "«OK»" in i["question"] for i in items))
        self.assertFalse(
            any(
                i["family"] in ("scene.area", "field.shape")
                and ("«Bow»" in i["question"] or "«Zero»" in i["question"])
                and i["answerable"]
                for i in items
            )
        )


class F08_InvalidMeasurementsBecomeAbstention(unittest.TestCase):
    def test_out_of_range_ec_and_ph(self):
        tmp = tempfile.mkdtemp()
        fx = write_fx(
            [
                feat(None, kind="field", id="f", name="F", tenant="t", governorate="الجوف"),
                feat(
                    None,
                    kind="soil",
                    field_id="f",
                    sample_id="BAD",
                    ec=-1,
                    ph=99,
                    n=200.0,
                    recorded_at="2025-01-01",
                    tenant="t",
                ),
                feat(
                    None,
                    kind="soil",
                    field_id="f",
                    sample_id="INF",
                    ec="Infinity",
                    ph=7.5,
                    recorded_at="2025-01-01",
                    tenant="t",
                ),
            ],
            tmp,
        )
        out = Path(tmp, "qa")
        generate(load_fixture(fx, "t"), DEFAULT_RULES, str(out), split_mode="none", images=False)
        items = read_items(out)
        for it in items:
            if "«BAD (2025)»" in it["question"] and it["family"] in (
                "soil.salinity_class",
                "soil.ph_class",
                "reasoning.ec_rule_class",
            ):
                self.assertFalse(it["answerable"], it["family"])
                self.assertEqual(it["answer_text"], ABSTAIN_TEXT)
        self.assertFalse(
            any(
                i["family"] == "reasoning.ec_rule_class"
                and "BAD" in i["question"]
                and i["answerable"]
                for i in items
            )
        )
        self.assertFalse(
            any(i["family"] == "soil.mean_ec" for i in items)
        )  # no valid EC pair left to average
        issues = (out / "data_issues.jsonl").read_text(encoding="utf-8")
        for code in ("ec_out_of_range", "ph_out_of_range", "value_not_finite"):
            self.assertIn(code, issues)


class F09_BoundaryFollowsStContains(unittest.TestCase):
    def test_edges_vertices_and_holes_are_outside(self):
        outer = [(0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01)]
        hole = [(0.004, 0.004), (0.006, 0.004), (0.006, 0.006), (0.004, 0.006)]
        g = Geometry([[outer, hole]])
        for p in [
            (0.0, 0.005),
            (0.01, 0.005),
            (0.005, 0.0),
            (0.005, 0.01),  # west, east, south, north edges
            (0.0, 0.0),
            (0.01, 0.01),  # vertices
            (0.004, 0.005),
            (0.005, 0.006),
        ]:  # hole boundary
            self.assertFalse(g.contains(*p), p)
        self.assertTrue(g.contains(0.002, 0.002))
        self.assertLess(g.boundary_distance_m(0.002, 0.0), 1e-6)
        self.assertAlmostEqual(g.boundary_distance_m(0.002, 0.002), 0.002 * 110_650, delta=5)

    def test_near_boundary_samples_are_not_associated(self):
        tmp = tempfile.mkdtemp()
        g = rect(*A, 200, 200)
        west = min(x for x, _ in g)
        fx = write_fx(
            [
                feat(
                    poly_geojson(g), kind="field", id="p", name="P", tenant="t", governorate="الجوف"
                ),
                feat(None, kind="field", id="farm", name="Farm", tenant="t", governorate="الجوف"),
                feat(
                    pt(west + 0.000003, A[1]),
                    kind="soil",
                    field_id="farm",
                    sample_id="EDGE",
                    ec=1.0,
                    recorded_at="2025-01-01",
                    tenant="t",
                ),  # ~0.3 m inside the west edge
                feat(
                    pt(*A),
                    kind="soil",
                    field_id="farm",
                    sample_id="MID",
                    ec=1.0,
                    recorded_at="2025-01-01",
                    tenant="t",
                ),
            ],
            tmp,
        )
        store = load_fixture(fx, "t")
        f = next(x for x in store.fields.values() if x.id == "p")
        self.assertEqual([s.sample_id for s, _ in store.samples_for(f)], ["MID"])


class F10_ReadOnlyCannotBeOverridden(unittest.TestCase):
    def test_option_allowlist(self):
        from sahool_qa.sources.postgis import Db, SchemaError

        for bad in (
            "default_transaction_read_only=off",
            "transaction_read_only=off",
            "session_replication_role=replica",
            "statement_timeout=0",
            "search_path=evil",
        ):
            with self.assertRaises(SchemaError, msg=bad):
                Db("host=/nonexistent", [bad], verify=False)
        from unittest.mock import patch

        with patch.dict("sys.modules", {"psycopg": object()}):
            db = Db(
                "host=/nonexistent",
                ["app.current_tenant=abc-123", "TimeZone=Asia/Aden"],
                verify=False,
            )
        self.assertIn("app.current_tenant=abc-123", db.options)
        self.assertTrue(
            db.options.index("default_transaction_read_only=on")
            > db.options.index("app.current_tenant")
        )


class F11_FingerprintCoversEveryInput(unittest.TestCase):
    def test_changes_detected_and_order_ignored(self):
        tmp = tempfile.mkdtemp()
        path = _heldout_fixture(tmp)
        base = load_fixture(path, "t")
        fp0 = fingerprint(base)
        s = load_fixture(path, "t")
        s.soil[0].depth_cm = 99
        self.assertNotEqual(fingerprint(s), fp0)
        s = load_fixture(path, "t")
        next(iter(s.fields.values())).soil_type = "clay"
        self.assertNotEqual(fingerprint(s), fp0)
        s = load_fixture(path, "t")
        random.Random(1).shuffle(s.soil)
        random.Random(2).shuffle(s.indicators)
        self.assertEqual(fingerprint(s), fp0)

    def test_raster_metadata(self):
        import numpy as np
        from sahool_qa.facts import RasterLayer

        tmp = tempfile.mkdtemp()
        np.save(Path(tmp, "a.npy"), np.zeros((4, 4), dtype="float32"))
        store = load_fixture(_heldout_fixture(tmp), "t")

        def mk(tr):
            return RasterLayer(
                path=str(Path(tmp, "a.npy")),
                index_name="SAVI",
                date=None,
                crs="EPSG:32638",  # noqa: E731
                transform=tr,
                nodata=-9999.0,
            )

        store.rasters = [mk((0, 10, 0, 0, 0, -10))]
        fp1 = fingerprint(store)
        store.rasters = [mk((5, 10, 0, 0, 0, -10))]
        self.assertNotEqual(fingerprint(store), fp1)


class F12_SameDayReadingsAreOrderIndependent(unittest.TestCase):
    def test_reordering_rows_does_not_change_answers(self):
        feats = [
            feat(
                poly_geojson(circle(*A, 300)),
                kind="field",
                id="p",
                name="P",
                tenant="t",
                governorate="الجوف",
            )
        ]
        days = ["2026-01-01", "2026-01-15", "2026-01-29", "2026-02-12", "2026-02-26", "2026-03-12"]
        vals = [0.2, 0.35, 0.5, 0.45, 0.3, 0.25]
        for d, v in zip(days, vals, strict=False):
            feats.append(
                feat(
                    None,
                    kind="indicator",
                    field_id="p",
                    indicator_id="savi",
                    value=v,
                    recorded_at=f"{d}T10:00:00",
                    tenant="t",
                )
            )
        feats.append(
            feat(
                None,
                kind="indicator",
                field_id="p",
                indicator_id="savi",
                value=0.1,
                recorded_at="2026-03-12T08:00:00",
                tenant="t",
            )
        )
        feats.append(
            feat(
                None,
                kind="indicator",
                field_id="p",
                indicator_id="savi",
                value=0.8,
                recorded_at="2026-03-12T16:00:00",
                tenant="t",
            )
        )
        answers = []
        for order in (feats, feats[:1] + feats[1:][::-1]):
            sub = tempfile.mkdtemp()
            fx = write_fx(order, sub)
            store = load_fixture(fx, "t")
            self.assertEqual(len(store.indicators), 8)  # nothing silently dropped
            out = Path(sub, "qa")
            generate(store, DEFAULT_RULES, str(out), split_mode="none", images=False)
            answers.append(
                sorted(
                    (i["id"], i["answer_text"], json.dumps(i["evidence"]["values"], sort_keys=True))
                    for i in read_items(out)
                    if i["family"].startswith("temporal.index")
                )
            )
        self.assertTrue(answers[0])
        self.assertEqual(answers[0], answers[1])


if __name__ == "__main__":
    unittest.main()


class BlindCheck_UnitsAndRules(unittest.TestCase):
    """Follow-ups from the independent blind solve of 0.2.0 (47/48 agreement)."""

    def _water(self, value, unit):
        tmp = tempfile.mkdtemp()
        fx = write_fx(
            [
                feat(None, kind="field", id="f", name="F", tenant="t", governorate="الجوف"),
                feat(
                    None,
                    kind="indicator",
                    field_id="f",
                    indicator_id="water_ec_X",
                    category="water",
                    value=value,
                    unit=unit,
                    recorded_at="2026-01-01",
                    tenant="t",
                ),
            ],
            tmp,
        )
        out = Path(tmp, "qa")
        generate(
            load_fixture(fx, "t"),
            DEFAULT_RULES,
            str(out),
            split_mode="none",
            images=False,
            families="water.salinity_class",
        )
        return read_items(out)

    def test_tds_ppm_is_converted_with_fao_factor(self):
        items = self._water(900.0, "ppm")  # 900/640 = 1.41 dS/m -> C3
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["answer_text"].startswith("C3"))
        self.assertTrue(any("640" in c for c in items[0]["evidence"]["caveats"]))

    def test_tds_near_class_boundary_is_not_asked(self):
        self.assertEqual(self._water(500.0, "ppm"), [])  # 0.78 dS/m: within 10 % of the 0.75 edge

    def test_non_ec_unit_is_abstention(self):
        items = self._water(9.5, "meq/L")
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["answerable"])

    def test_shape_rule_is_in_the_context(self):
        tmp = tempfile.mkdtemp()
        fx = write_fx(
            [
                feat(
                    poly_geojson(rect(*A, 300, 200)),
                    kind="field",
                    id="r",
                    name="R",
                    tenant="t",
                    governorate="الجوف",
                )
            ],
            tmp,
        )
        out = Path(tmp, "qa")
        generate(
            load_fixture(fx, "t"),
            DEFAULT_RULES,
            str(out),
            split_mode="none",
            images=False,
            families="field.shape",
        )
        it = read_items(out)[0]
        self.assertIn("قاعدة الشكل", it["context"])
        self.assertEqual(it["answer_text"], "مستطيل أو قريب من المستطيل")
