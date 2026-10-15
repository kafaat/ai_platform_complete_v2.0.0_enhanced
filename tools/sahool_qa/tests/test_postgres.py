"""Runs the database loader against a throw-away PostgreSQL cluster.

PostGIS is not required here: geometry columns are stored as GeoJSON TEXT,
which the loader supports directly. On a real SAHOOL database the loader uses
ST_AsGeoJSON instead; everything after that point is the same code path.
Skipped automatically when no PostgreSQL server binaries are available.
"""

import copy
import json
import os
import pwd
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

from sahool_qa.config import DEFAULT_RULES, DEFAULT_SCHEMA, load_schema
from sahool_qa.demo import write_demo
from sahool_qa.pipeline import generate
from sahool_qa.raster import load_rasters
from sahool_qa.sources.fixture import load_fixture
from sahool_qa.sources.postgis import Db, SchemaError, TenantScope, introspect, load, qident
from sahool_qa.split import parse_holdout


def _bindir():
    try:
        return subprocess.run(
            ["pg_config", "--bindir"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        for d in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
            return str(d)
    return None


BIN = _bindir()
HAVE_PG = BIN and Path(BIN, "initdb").exists() and shutil.which("psql")

MAP_V8 = Path(__file__).resolve().parents[1] / "examples" / "schema_map.init_v8.json"


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


DDL = """
CREATE TABLE field_boundaries (field_id TEXT, field_name TEXT, area_ha NUMERIC, crop TEXT, soil_type TEXT,
  latitude NUMERIC, longitude NUMERIC, governorate TEXT, tenant_id TEXT, geom TEXT, updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (field_id, tenant_id));
CREATE TABLE soil_readings (field_id TEXT, sensor_id TEXT, ph NUMERIC, ec_ds_m NUMERIC, moisture_pct NUMERIC,
  nitrogen_mg_kg NUMERIC, phosphorus_mg_kg NUMERIC, potassium_mg_kg NUMERIC, organic_matter_pct NUMERIC, depth_cm INT,
  source TEXT, recorded_at TIMESTAMPTZ, tenant_id TEXT, geom TEXT);
CREATE TABLE field_indicators (field_id TEXT, indicator_id TEXT, indicator_cat TEXT, value NUMERIC, unit TEXT,
  status TEXT, source TEXT, recorded_at TIMESTAMPTZ, tenant_id TEXT, geom TEXT);
ALTER TABLE field_boundaries ENABLE ROW LEVEL SECURITY;
"""

# The three tables as SAHOOL's migrations/init_v8.sql declares them, except: geom is TEXT (no
# PostGIS here) and tenant_id is TEXT (the demo tenant is not a UUID). Column names and the
# absence of geom on soil_readings / field_indicators are as in the migration.
DDL_V8 = """
CREATE TABLE field_boundaries (id SERIAL PRIMARY KEY, field_id VARCHAR(50) NOT NULL UNIQUE,
  field_name VARCHAR(100) NOT NULL, geom TEXT, area_ha NUMERIC(10, 2), crop VARCHAR(50),
  soil_type VARCHAR(30), gov VARCHAR(50), lat NUMERIC(10, 6), lon NUMERIC(10, 6), tenant_id TEXT,
  active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (field_id, tenant_id));
CREATE TABLE soil_readings (id BIGSERIAL PRIMARY KEY, field_id VARCHAR(50) NOT NULL, sensor_id VARCHAR(50),
  depth_cm SMALLINT DEFAULT 30, moisture_pct NUMERIC(6, 2), temperature_c NUMERIC(5, 2), ph NUMERIC(4, 2),
  ec_ds_m NUMERIC(6, 3), nitrogen_mg_kg NUMERIC(8, 2), phosphorus_mg_kg NUMERIC(8, 2),
  potassium_mg_kg NUMERIC(8, 2), organic_matter_pct NUMERIC(5, 2), source VARCHAR(30),
  quality VARCHAR(20) DEFAULT 'good', tenant_id TEXT, recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE field_indicators (id BIGSERIAL PRIMARY KEY, field_id VARCHAR(50) NOT NULL,
  indicator_id VARCHAR(50) NOT NULL, category VARCHAR(30) NOT NULL, value NUMERIC(12, 4) NOT NULL,
  unit VARCHAR(20), status VARCHAR(20), source VARCHAR(30), confidence NUMERIC(4, 3), raw_data JSONB,
  tenant_id TEXT, recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), created_at TIMESTAMPTZ DEFAULT NOW());
"""


def v8_rows(fx: dict) -> list[str]:
    def ins(table, cols, vals):
        return (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(lit(x) for x in vals)});"
        )

    rows = [DDL_V8]
    for ft in fx["features"]:
        p, g = ft["properties"], ft["geometry"]
        if p["kind"] == "field":
            cols = [
                "field_id",
                "field_name",
                "geom",
                "area_ha",
                "crop",
                "soil_type",
                "gov",
                "lat",
                "lon",
                "tenant_id",
            ]
            vals = [
                p["id"],
                p["name"],
                json.dumps(g) if g else None,
                p.get("area_ha"),
                p.get("crop"),
                p.get("soil_type"),
                p.get("governorate"),
                p.get("latitude"),
                p.get("longitude"),
                p["tenant"],
            ]
            rows.append(ins("field_boundaries", cols, vals))
        elif p["kind"] == "soil":
            cols = [
                "field_id",
                "sensor_id",
                "ph",
                "ec_ds_m",
                "moisture_pct",
                "nitrogen_mg_kg",
                "phosphorus_mg_kg",
                "potassium_mg_kg",
                "organic_matter_pct",
                "depth_cm",
                "source",
                "recorded_at",
                "tenant_id",
            ]
            vals = [
                p["field_id"],
                p["sample_id"],
                p.get("ph"),
                p.get("ec"),
                p.get("moisture"),
                p.get("n"),
                p.get("p"),
                p.get("k"),
                p.get("om"),
                p.get("depth_cm"),
                p.get("source"),
                p["recorded_at"],
                p["tenant"],
            ]
            rows.append(ins("soil_readings", cols, vals))
        else:
            cols = [
                "field_id",
                "indicator_id",
                "category",
                "value",
                "unit",
                "status",
                "source",
                "recorded_at",
                "tenant_id",
            ]
            vals = [
                p["field_id"],
                p["indicator_id"],
                p.get("category"),
                p.get("value"),
                p.get("unit"),
                p.get("status"),
                p.get("source"),
                p["recorded_at"],
                p["tenant"],
            ]
            rows.append(ins("field_indicators", cols, vals))
    rows.append(
        "INSERT INTO field_boundaries (field_id, field_name, gov, tenant_id) "
        "VALUES ('rival_field', 'حقل مستأجر آخر', 'الجوف', 'other-tenant');"
    )
    return rows


class TestPostgresPresence(unittest.TestCase):
    """CI sets SAHOOL_QA_REQUIRE_PG=1 so a missing server fails instead of skipping."""

    def test_server_present_when_required(self):
        if os.environ.get("SAHOOL_QA_REQUIRE_PG") == "1" and not HAVE_PG:
            self.fail("SAHOOL_QA_REQUIRE_PG=1 but no PostgreSQL server binaries were found")


@unittest.skipUnless(HAVE_PG, "PostgreSQL server binaries not available")
class TestPostgresLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.chmod(cls.tmp, 0o777)
        cls.data, cls.sock = Path(cls.tmp, "data"), Path(cls.tmp, "sock")
        cls.sock.mkdir()
        os.chmod(cls.sock, 0o777)
        as_pg = []
        if os.geteuid() == 0:
            as_pg = ["runuser", "-u", "postgres", "--"]
            pg = pwd.getpwnam("postgres")
            cls.data.mkdir()
            os.chown(cls.data, pg.pw_uid, pg.pw_gid)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        run = lambda *c: subprocess.run([*as_pg, *c], check=True, capture_output=True, text=True)  # noqa: E731
        run(
            f"{BIN}/initdb",
            "-D",
            str(cls.data),
            "-A",
            "trust",
            "-U",
            "postgres",
            "-E",
            "UTF8",
            "--locale=C.UTF-8",
        )
        run(
            f"{BIN}/pg_ctl",
            "-D",
            str(cls.data),
            "-w",
            "-l",
            str(Path(cls.tmp, "log")),
            "-o",
            f"-k {cls.sock} -p {cls.port} -c listen_addresses=''",
            "start",
        )
        cls.as_pg = as_pg
        cls.dsn = f"host={cls.sock} port={cls.port} user=postgres dbname=sahool"
        env = dict(
            os.environ, PGOPTIONS="-c TimeZone=Asia/Aden"
        )  # dates are entered in local time, as in SAHOOL
        psql = lambda db, sql: subprocess.run(  # noqa: E731
            [
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-d",
                f"host={cls.sock} port={cls.port} user=postgres dbname={db}",
            ],
            input=sql,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        psql("postgres", "CREATE DATABASE sahool;")
        cls.fx, cls.rasters = write_demo(str(Path(cls.tmp, "demo")))
        fx = json.loads(Path(cls.fx).read_text(encoding="utf-8"))
        rows = [DDL]
        for ft in fx["features"]:
            p, g = ft["properties"], ft["geometry"]
            gj = json.dumps(g) if g else None
            if p["kind"] == "field":
                rows.append(
                    "INSERT INTO field_boundaries VALUES ("
                    + ",".join(
                        lit(x)
                        for x in [
                            p["id"],
                            p["name"],
                            p.get("area_ha"),
                            p.get("crop"),
                            p.get("soil_type"),
                            p.get("latitude"),
                            p.get("longitude"),
                            p.get("governorate"),
                            p["tenant"],
                            gj,
                        ]
                    )
                    + ");"
                )
            elif p["kind"] == "soil":
                rows.append(
                    "INSERT INTO soil_readings VALUES ("
                    + ",".join(
                        lit(x)
                        for x in [
                            p["field_id"],
                            p["sample_id"],
                            p.get("ph"),
                            p.get("ec"),
                            p.get("moisture"),
                            p.get("n"),
                            p.get("p"),
                            p.get("k"),
                            p.get("om"),
                            p.get("depth_cm"),
                            p.get("source"),
                            p["recorded_at"],
                            p["tenant"],
                            gj,
                        ]
                    )
                    + ");"
                )
            else:
                rows.append(
                    "INSERT INTO field_indicators VALUES ("
                    + ",".join(
                        lit(x)
                        for x in [
                            p["field_id"],
                            p["indicator_id"],
                            p.get("category"),
                            p.get("value"),
                            p.get("unit"),
                            p.get("status"),
                            p.get("source"),
                            p["recorded_at"],
                            p["tenant"],
                            gj,
                        ]
                    )
                    + ");"
                )
        # another tenant: must never leak into demo-tenant results
        rows.append(
            "INSERT INTO field_boundaries (field_id, field_name, governorate, tenant_id) "
            "VALUES ('rival_field', 'حقل مستأجر آخر', 'الجوف', 'other-tenant');"
        )
        rows.append(
            "INSERT INTO soil_readings (field_id, sensor_id, ec_ds_m, recorded_at, tenant_id) "
            "VALUES ('field_alsunaidar', 'LEAK-1', 99, '2025-01-01', 'other-tenant');"
        )
        psql("sahool", "\n".join(rows))
        psql("postgres", "CREATE DATABASE sahool_v8;")
        psql("sahool_v8", "\n".join(v8_rows(fx)))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            [*cls.as_pg, f"{BIN}/pg_ctl", "-D", str(cls.data), "-m", "fast", "stop"],
            capture_output=True,
        )

    def db(self):
        return Db(self.dsn)

    def db_v8(self):
        return Db(self.dsn.replace("dbname=sahool", "dbname=sahool_v8"))

    def test_init_v8_columns_need_the_shipped_map(self):
        rep = introspect(self.db_v8(), DEFAULT_SCHEMA)["tables"]
        self.assertTrue(
            {"governorate", "latitude", "longitude"} <= set(rep["fields"]["missing_optional"])
        )
        self.assertIn("indicator_cat", rep["indicators"]["missing_optional"])
        mapped = introspect(self.db_v8(), load_schema(str(MAP_V8)))["tables"]
        self.assertEqual(mapped["fields"]["missing_optional"], [])
        self.assertEqual(mapped["soil"]["missing_optional"], ["geom"])  # not in init_v8.sql
        self.assertEqual(mapped["indicators"]["missing_optional"], ["geom"])

    def test_init_v8_map_loads_the_same_attributes_and_splits(self):
        from collections import Counter

        from sahool_qa.demo import PROVENANCE

        store, _ = load(
            self.db_v8(), load_schema(str(MAP_V8)), TenantScope("tenant", "demo-tenant")
        )
        ref = load_fixture(str(self.fx), "demo-tenant")
        self.assertEqual(set(store.fields), set(ref.fields))
        for key, f in ref.fields.items():
            g = store.fields[key]
            self.assertEqual(
                (g.governorate, g.crop, g.soil_type), (f.governorate, f.crop, f.soil_type), key
            )
            for a, b in ((g.lat, f.lat), (g.lon, f.lon)):
                self.assertTrue((a is None and b is None) or abs(a - b) < 1e-6, key)
        self.assertEqual(
            Counter((i.field_id, i.indicator_id, i.category) for i in store.indicators),
            Counter((i.field_id, i.indicator_id, i.category) for i in ref.indicators),
        )
        rules = copy.deepcopy(DEFAULT_RULES)
        rules["water"]["well_inventory"] = copy.deepcopy(PROVENANCE["water_well_inventory"])
        m = generate(
            store,
            rules,
            str(Path(self.tmp, "gen_v8")),
            families="water.,soil.",
            images=False,
            holdout=parse_holdout(["test:governorate=الحديدة", "val:governorate=مأرب"]),
            require_well_inventory=True,
        )
        self.assertGreater(m["counts"]["by_split"].get("test", 0), 0)  # gov drives the holdout
        self.assertGreater(m["counts"]["by_split"].get("val", 0), 0)
        self.assertIn("water.stress_status", m["coverage"]["test"])

    def test_loader_matches_fixture(self):
        store, report = load(self.db(), DEFAULT_SCHEMA, TenantScope("tenant", "demo-tenant"))
        ref = load_fixture(str(self.fx), "demo-tenant")
        store.prepare(DEFAULT_RULES)
        ref.prepare(DEFAULT_RULES)
        self.assertEqual(set(store.fields), set(ref.fields))
        self.assertEqual(sorted(s.key for s in store.soil), sorted(s.key for s in ref.soil))
        self.assertEqual(len(store.indicators), len(ref.indicators))
        for fid, f in ref.fields.items():
            g = store.fields[fid]
            if f.geom is None:
                self.assertIsNone(g.geom)
            else:
                self.assertAlmostEqual(g.geom.area_m2, f.geom.area_m2, delta=1e-6 * f.geom.area_m2)
        self.assertIsNone(report["postgis"])
        self.assertTrue(report["rls"]["field_boundaries"]["enabled"])

    def test_tenant_isolation(self):
        store, _ = load(self.db(), DEFAULT_SCHEMA, TenantScope("tenant", "demo-tenant"))
        self.assertNotIn("other-tenant::rival_field", store.fields)
        self.assertTrue(all(k.startswith("demo-tenant::") for k in store.fields))
        self.assertFalse(any(s.sample_id == "LEAK-1" for s in store.soil))
        other, _ = load(self.db(), DEFAULT_SCHEMA, TenantScope("tenant", "other-tenant"))
        self.assertEqual(set(other.fields), {"other-tenant::rival_field"})
        self.assertEqual(other.soil, [])  # LEAK-1 points at a field the other tenant does not own

    def test_session_is_read_only(self):
        with self.assertRaisesRegex(RuntimeError, "read-only"):
            self.db().query(
                "INSERT INTO field_boundaries (field_id, field_name) VALUES ('x', 'y') RETURNING field_id"
            )
        db = Db(self.dsn, ["app.current_tenant=demo-tenant"])
        r = db.query(
            "SELECT current_setting('app.current_tenant') AS v, current_setting('transaction_read_only') AS ro"
        )
        self.assertEqual(r[0], {"v": "demo-tenant", "ro": "on"})
        with self.assertRaises(SchemaError):
            Db(self.dsn, ["default_transaction_read_only=off"])

    def test_identifier_validation(self):
        with self.assertRaises(SchemaError):
            qident("field_boundaries; DROP TABLE soil_readings")
        bad = json.loads(json.dumps(DEFAULT_SCHEMA))
        bad["fields"]["required"]["name"] = 'name"--'
        with self.assertRaises(SchemaError):
            load(self.db(), bad, TenantScope("tenant", "demo-tenant"))

    def test_missing_column_is_reported(self):
        m = json.loads(json.dumps(DEFAULT_SCHEMA))
        m["soil"]["optional"]["ec"] = "ec_typo"
        rep = introspect(self.db(), m)
        self.assertIn("ec_typo", rep["tables"]["soil"]["missing_optional"])
        store, _ = load(self.db(), m, TenantScope("tenant", "demo-tenant"))
        self.assertTrue(all(s.ec is None for s in store.soil))

    def test_generation_parity_db_vs_fixture(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        from sahool_qa.demo import PROVENANCE

        rules["water"]["well_inventory"] = copy.deepcopy(PROVENANCE["water_well_inventory"])
        out = Path(self.tmp, "gen")
        stores = [
            load(self.db(), DEFAULT_SCHEMA, TenantScope("tenant", "demo-tenant"))[0],
            load_fixture(str(self.fx), "demo-tenant"),
        ]
        results = []
        for k, st in enumerate(stores):
            st.rasters = load_rasters(str(self.rasters))
            generate(
                st,
                rules,
                str(out / str(k)),
                holdout=parse_holdout(["test:governorate=الحديدة", "val:governorate=مأرب"]),
            )
            items = []
            for p in sorted((out / str(k)).glob("*.jsonl")):
                if p.name != "data_issues.jsonl" and not p.name.endswith(".public.jsonl"):
                    items += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()]
            results.append(
                sorted((i["id"], i["answer_text"], i["split"], i["family"]) for i in items)
            )
        self.assertEqual(results[0], results[1])
        self.assertGreater(len(results[0]), 150)
        fams = {r[3] for r in results[0]}
        self.assertTrue(
            {"water.stress_status", "water.rain_corroboration", "temporal.divergence_onset"} <= fams
        )


if __name__ == "__main__":
    unittest.main()
