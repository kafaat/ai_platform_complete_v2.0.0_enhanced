"""Temporary-table PostGIS experiment. No production tables or extensions mutated."""

import statistics
import time


def percentile(values, fraction):
    return sorted(values)[max(0, __import__("math").ceil(len(values) * fraction) - 1)]


def run(connection, repeats=20):
    if repeats < 20:
        raise ValueError("at least 20 samples required")
    with connection.transaction(force_rollback=True):
        with connection.cursor() as cur:
            cur.execute("SELECT postgis_full_version()")
            version = cur.fetchone()[0]
            cur.execute("""CREATE TEMP TABLE eo_fields ON COMMIT DROP AS
                SELECT i AS id, (i % 2) AS tenant_id,
                ST_Buffer(ST_SetSRID(ST_MakePoint(400000 + (i%10)*2000,
                1772000 + (i/10)*2000),32638),700,128) AS geom
                FROM generate_series(1,100) i""")
            cur.execute("CREATE INDEX ON eo_fields USING gist(geom)")
            cur.execute("""CREATE TEMP TABLE eo_parts ON COMMIT DROP AS
                SELECT id, tenant_id, ST_Subdivide(geom,64) geom FROM eo_fields""")
            cur.execute("CREATE INDEX ON eo_parts USING gist(geom)")
            cur.execute("ANALYZE eo_fields")
            cur.execute("ANALYZE eo_parts")
            query = (
                "SELECT DISTINCT id FROM {table} WHERE tenant_id = %s "
                "AND ST_Intersects(geom,ST_MakeEnvelope(%s,%s,%s,%s,32638)) ORDER BY id"
            )
            # Include boundary touch, empty result and polygons spanning many parts.
            cases = [
                (400000, 1772000, 420000, 1792000),
                (0, 0, 1, 1),
                (401300, 1774000, 402000, 1774700),
            ]
            timings = {"baseline": [], "subdivided": []}
            plans = {}
            for tenant in (0, 1):
                for bbox in cases:
                    params = (tenant, *bbox)
                    outputs = {}
                    for name, table in [("baseline", "eo_fields"), ("subdivided", "eo_parts")]:
                        sql = query.format(table=table)
                        cur.execute(sql, params)
                        outputs[name] = cur.fetchall()
                        if any(row[0] % 2 != tenant for row in outputs[name]):
                            raise AssertionError("tenant predicate leaked another fixture tenant")
                        if len(outputs[name]) != len(set(outputs[name])):
                            raise AssertionError("duplicate field identities")
                        cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
                        plans[f"{tenant}:{bbox}:{name}"] = cur.fetchone()[0]
                    if outputs["baseline"] != outputs["subdivided"]:
                        raise AssertionError("field identities differ")
                    for sample in range(repeats):
                        # Alternate order to reduce cache/order bias; warm measurements only.
                        order = list(timings) if sample % 2 == 0 else list(reversed(timings))
                        for name in order:
                            table = "eo_fields" if name == "baseline" else "eo_parts"
                            start = time.perf_counter()
                            cur.execute(query.format(table=table), params)
                            cur.fetchall()
                            timings[name].append(time.perf_counter() - start)
            cur.execute(
                "SELECT pg_total_relation_size('eo_fields'), pg_total_relation_size('eo_parts')"
            )
            sizes = cur.fetchone()
    summary = {
        name: {"p50": statistics.median(v), "p95": percentile(v, 0.95), "n": len(v)}
        for name, v in timings.items()
    }
    gain = 1 - summary["subdivided"]["p95"] / summary["baseline"]["p95"]
    return {
        "fixture": "synthetic_100_fields_not_production",
        "cache": "warm",
        "postgis": version,
        "correctness_pass": True,
        "timings": summary,
        "p95_gain": gain,
        "adoption_pass": gain >= 0.2,
        "table_and_index_bytes": list(sizes),
        "plans": plans,
        "update_cost_status": "NOT_MEASURED",
        "production_query_status": "NOT_MEASURED",
    }
