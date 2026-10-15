"""Read-only loader for the SAHOOL PostGIS database.

Safety properties (the platform has had cross-tenant leaks before, so these are
not optional):
  * every session runs with default_transaction_read_only=on;
  * a tenant scope is mandatory: --tenant <id>, --tenant-null or --all-tenants;
  * soil / indicator rows are additionally restricted to field_ids of the fields
    loaded for that tenant;
  * identifiers from the schema map are validated before being quoted.

Driver: psycopg 3 when installed, otherwise the `psql` client over stdin with
psql variables (:'name') for every value. Geometry is fetched as GeoJSON and
measured in Python, so PostGIS is only needed for ST_AsGeoJSON / ST_Transform.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from ..facts import FactStore, Field, Indicator, SoilSample, parse_ts, to_float, to_float_raw
from ..geo import Geometry, parse_point

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PARAM = re.compile(r"%\((\w+)\)s")
_SEP = "\x1f"


class SchemaError(RuntimeError):
    pass


def qident(name: str) -> str:
    parts = name.split(".")
    for p in parts:
        if not _IDENT.match(p):
            raise SchemaError(f"invalid SQL identifier in schema map: {name!r}")
    return ".".join(f'"{p}"' for p in parts)


@dataclass
class TenantScope:
    mode: str  # "tenant" | "null" | "all"
    value: str | None = None

    def describe(self) -> str:
        return {
            "tenant": f"tenant_id = {self.value}",
            "null": "tenant_id IS NULL",
            "all": "ALL TENANTS",
        }[self.mode]


_CUSTOM_GUC = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_.]+$")  # e.g. app.current_tenant
_BUILTIN_ALLOWED = {"timezone": "TimeZone"}
_VALUE = re.compile(r"^[\w\-.:/@+]+$")


class Db:
    """Read-only database access.

    Read-only is enforced three ways: the session default is set *after* any
    user option (so it cannot be overridden), only custom dotted settings
    (RLS context such as app.current_tenant) and TimeZone may be passed, and
    every query runs inside an explicit READ ONLY transaction. The session is
    verified on first use. Use a read-only database role as well.
    """

    def __init__(
        self,
        dsn: str,
        pg_options: list[str] | None = None,
        timeout_s: int = 120,
        verify: bool = True,
    ):
        self.dsn = dsn
        opts = []
        for o in pg_options or []:
            name, sep, value = o.partition("=")
            if not sep or not _VALUE.match(value):
                raise SchemaError(f"--pg-option must look like name=value, got {o!r}")
            if _CUSTOM_GUC.match(name):
                opts.append(f"-c {name}={value}")
            elif name.lower() in _BUILTIN_ALLOWED:
                opts.append(f"-c {_BUILTIN_ALLOWED[name.lower()]}={value}")
            else:
                raise SchemaError(
                    f"--pg-option {name!r} is not allowed: only custom settings such as "
                    "app.current_tenant and TimeZone may be set"
                )
        opts += ["-c default_transaction_read_only=on", f"-c statement_timeout={timeout_s * 1000}"]
        self.options = " ".join(opts)
        self.driver = None
        try:
            import psycopg  # noqa: F401

            self.driver = "psycopg"
        except ImportError:
            if shutil.which("psql"):
                self.driver = "psql"
        if self.driver is None:
            raise RuntimeError("neither psycopg nor the psql client is available")
        self._conn = None
        self._verified = not verify

    def verify_read_only(self):
        r = self._raw(
            "SELECT current_setting('default_transaction_read_only') AS d, "
            "current_setting('transaction_read_only') AS t",
            {},
        )
        if not r or r[0]["d"] != "on" or r[0]["t"] != "on":
            raise SchemaError(f"database session is not read-only: {r}")
        self._verified = True

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        if not self._verified:
            self.verify_read_only()
        return self._raw(sql, params)

    def _raw(self, sql, params):
        params = {k: (None if v is None else str(v)) for k, v in (params or {}).items()}
        return (
            self._q_psycopg(sql, params) if self.driver == "psycopg" else self._q_psql(sql, params)
        )

    def _q_psycopg(self, sql, params):
        import psycopg
        from psycopg.rows import dict_row

        if self._conn is None:
            self._conn = psycopg.connect(self.dsn, options=self.options, autocommit=False)
            self._conn.read_only = True
        try:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
        finally:
            self._conn.rollback()

    def _q_psql(self, sql, params):
        used = set(_PARAM.findall(sql))
        missing = used - set(params)
        if missing:
            raise SchemaError(f"missing SQL parameters: {sorted(missing)}")
        text = _PARAM.sub(lambda m: f":'{m.group(1)}'", sql)
        script = (
            "BEGIN TRANSACTION READ ONLY;\n"
            f"COPY ({text}) TO STDOUT WITH (FORMAT csv, HEADER true, NULL '\\N');\n"
            "ROLLBACK;\n"
        )
        cmd = ["psql", "-d", self.dsn, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", "-"]
        for k in sorted(used):
            if params[k] is None:
                raise SchemaError(f"NULL parameter {k} not supported by the psql driver")
            cmd[1:1] = ["-v", f"{k}={params[k]}"]
        env = dict(os.environ, PGOPTIONS=self.options)
        res = subprocess.run(cmd, input=script, capture_output=True, text=True, env=env)
        if res.returncode != 0:
            raise RuntimeError(f"psql failed: {res.stderr.strip()}")
        reader = csv.DictReader(io.StringIO(res.stdout))
        return [{k: (None if v == "\\N" else v) for k, v in row.items()} for row in reader]

    def close(self):
        if self._conn is not None:
            self._conn.close()


# ───────────────────────── introspection ─────────────────────────


def _split_table(name: str) -> tuple[str | None, str]:
    return tuple(name.split(".", 1)) if "." in name else (None, name)  # type: ignore[return-value]


def table_columns(db: Db, table: str) -> dict[str, str]:
    """column_name -> udt_name for a table on the search path (or schema-qualified)."""
    schema, tname = _split_table(table)
    if schema:
        rows = db.query(
            "SELECT column_name, udt_name FROM information_schema.columns "
            "WHERE table_schema = %(s)s AND table_name = %(t)s",
            {"s": schema, "t": tname},
        )
    else:
        rows = db.query(
            "SELECT column_name, udt_name FROM information_schema.columns "
            "WHERE table_name = %(t)s AND table_schema = ANY (current_schemas(false))",
            {"t": tname},
        )
    return {r["column_name"]: r["udt_name"] for r in rows}


def introspect(db: Db, schema: dict, scope: TenantScope | None = None) -> dict:
    report: dict = {"driver": db.driver, "tables": {}, "postgis": None, "rls": {}}
    rows = db.query("SELECT extversion FROM pg_extension WHERE extname = %(e)s", {"e": "postgis"})
    report["postgis"] = rows[0]["extversion"] if rows else None
    for key, spec in schema.items():
        cols = table_columns(db, spec["table"])
        req = spec["required"]
        opt = spec["optional"]
        report["tables"][key] = {
            "table": spec["table"],
            "exists": bool(cols),
            "missing_required": [c for c in req.values() if c not in cols],
            "missing_optional": [c for c in opt.values() if c not in cols],
            "geometry_type": cols.get(opt.get("geom", ""), None),
        }
        _, tname = _split_table(spec["table"])
        r = db.query(
            "SELECT relrowsecurity::text AS rls, relforcerowsecurity::text AS force "
            "FROM pg_class WHERE relname = %(t)s AND relkind = 'r' LIMIT 1",
            {"t": tname},
        )
        if r:
            report["rls"][spec["table"]] = {
                "enabled": r[0]["rls"] in ("true", "t", True),
                "forced": r[0]["force"] in ("true", "t", True),
            }
    ind = schema["indicators"]
    icols = table_columns(db, ind["table"])
    if icols:
        id_col = qident(ind["required"]["indicator_id"])
        cat = ind["optional"].get("category")
        cat_expr = qident(cat) if cat and cat in icols else "NULL"
        where, params = "TRUE", {}
        tcol = ind["optional"].get("tenant")
        if scope and tcol in icols:
            where, params = _tenant_clause(qident(tcol), scope)
        rows = db.query(
            f"SELECT {cat_expr}::text AS category, "
            f"regexp_replace(lower({id_col}::text), '_?[a-z]*[0-9]+[a-z0-9-]*$', '') AS stem, count(*)::text AS n "
            f"FROM {qident(ind['table'])} WHERE {where} GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 60",
            params,
        )
        report["indicator_stems"] = rows
    return report


# ───────────────────────── loading ─────────────────────────


def _tenant_clause(col: str, scope: TenantScope) -> tuple[str, dict]:
    if scope.mode == "tenant":
        return f"{col}::text = %(tenant)s", {"tenant": scope.value}
    if scope.mode == "null":
        return f"{col} IS NULL", {}
    return "TRUE", {}


def _geom_expr(col: str, udt: str | None, postgis: bool) -> str:
    if udt is None:
        return "NULL"
    q = qident(col)
    if udt == "geometry" and postgis:
        return f"ST_AsGeoJSON(CASE WHEN ST_SRID({q}) IN (0, 4326) THEN {q} ELSE ST_Transform({q}, 4326) END)"
    if udt == "geography" and postgis:
        return f"ST_AsGeoJSON({q})"
    if udt in ("text", "varchar", "json", "jsonb"):
        return f"{q}::text"
    return "NULL"


def _area_expr(col: str, udt: str | None, postgis: bool) -> str:
    q = qident(col)
    if postgis and udt == "geometry":
        return f"ST_Area((CASE WHEN ST_SRID({q}) IN (0, 4326) THEN ST_SetSRID({q}, 4326) ELSE ST_Transform({q}, 4326) END)::geography)"
    if postgis and udt == "geography":
        return f"ST_Area({q})"
    return "NULL"


def _select_list(spec: dict, cols: dict[str, str], postgis: bool, with_area: bool = False) -> str:
    parts = []
    for logical, col in {**spec["required"], **spec["optional"]}.items():
        if col not in cols:
            parts.append(f"NULL AS {logical}")
        elif logical == "geom":
            parts.append(f"{_geom_expr(col, cols[col], postgis)} AS geom")
            if with_area:
                parts.append(f"{_area_expr(col, cols[col], postgis)} AS db_area_m2")
        else:
            parts.append(f"{qident(col)}::text AS {logical}")
    return ", ".join(parts)


def load(
    db: Db, schema: dict, scope: TenantScope, crosscheck_area: bool = True
) -> tuple[FactStore, dict]:
    report = introspect(db, schema, scope)
    for key, info in report["tables"].items():
        if key == "fields" and (not info["exists"] or info["missing_required"]):
            raise SchemaError(
                f"{info['table']}: missing required columns {info['missing_required'] or 'table not found'}"
            )
    postgis = report["postgis"] is not None
    store = FactStore(source=f"postgres ({db.driver})", tenant_scope=scope.describe())

    # fields
    fs = schema["fields"]
    fcols = table_columns(db, fs["table"])
    tcol = fs["optional"].get("tenant")
    if scope.mode != "all" and tcol not in fcols:
        raise SchemaError(
            f"{fs['table']} has no tenant column '{tcol}'; use --all-tenants explicitly"
        )
    where, params = _tenant_clause(qident(tcol), scope) if tcol in fcols else ("TRUE", {})
    sel = _select_list(fs, fcols, postgis, with_area=crosscheck_area and postgis)
    for r in db.query(f"SELECT {sel} FROM {qident(fs['table'])} WHERE {where}", params):
        store.add_field(
            Field(
                id=str(r["id"]),
                name=r.get("name") or str(r["id"]),
                tenant=r.get("tenant"),
                governorate=r.get("governorate"),
                crop=r.get("crop"),
                soil_type=r.get("soil_type"),
                area_ha_stored=to_float(r.get("area_ha")),
                lat=to_float(r.get("latitude")),
                lon=to_float(r.get("longitude")),
                geom=Geometry.from_geojson(r.get("geom")),
                db_area_m2=to_float(r.get("db_area_m2")),
            )
        )
    field_ids = _SEP.join(sorted({f.id for f in store.fields.values()}))

    # soil + indicators: tenant clause (when the table has a tenant column) AND
    # field_id in the loaded fields; ownership is then checked on (tenant, field_id)
    for key in ("soil", "indicators"):
        spec = schema[key]
        info = report["tables"][key]
        if not info["exists"] or info["missing_required"] or not store.fields:
            continue
        cols = table_columns(db, spec["table"])
        conds = [
            f"{qident(spec['required']['field_id'])}::text = ANY (string_to_array(%(fids)s, chr(31)))"
        ]
        params = {"fids": field_ids}
        tcol = spec["optional"].get("tenant")
        has_tenant = tcol in cols
        if has_tenant and scope.mode != "all":
            c, p = _tenant_clause(qident(tcol), scope)
            conds.append(c)
            params.update(p)
        rows = db.query(
            f"SELECT {_select_list(spec, cols, postgis)} FROM {qident(spec['table'])} "
            f"WHERE {' AND '.join(conds)}",
            params,
        )
        for r in rows:
            if has_tenant:
                tenant = r.get("tenant")
            else:  # no tenant column: inherit only from an unambiguous owner
                ok, tenant = store.inherit_tenant(str(r["field_id"]))
                if not ok:
                    store.rejected["ambiguous_owner"] += 1
                    continue
            common = dict(
                field_id=str(r["field_id"]),
                recorded_ts=parse_ts(r.get("recorded_at")),
                source=r.get("source"),
                point=parse_point(r.get("geom")),
                tenant=tenant,
                record_id=r.get("record_id"),
            )
            if key == "soil":
                rec = SoilSample(
                    sample_id=str(r["sample_id"]),
                    **{a: to_float_raw(r.get(a)) for a in SoilSample.MEASURES},
                    **common,
                )
            else:
                rec = Indicator(
                    indicator_id=str(r["indicator_id"]),
                    value=to_float_raw(r.get("value")),
                    category=r.get("category"),
                    unit=r.get("unit"),
                    status=r.get("status"),
                    **common,
                )
            store.admit(rec)
    return store, report
