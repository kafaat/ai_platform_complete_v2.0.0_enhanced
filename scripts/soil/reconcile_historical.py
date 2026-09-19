#!/usr/bin/env python3
"""Backfill legacy soil_readings/device_telemetry into soil_observations.

Idempotency keys are derived from the immutable legacy row identity. The script is
restart-safe, tenant-scoped, batchable and records checkpoints in v157.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass

import asyncpg


@dataclass
class Stats:
    scanned: int = 0
    inserted: int = 0
    # RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01: separate counters, not
    # one. `scanned - inserted` cannot tell a row that was written down from a row that
    # vanished, and that is exactly the difference this slice exists to make visible.
    deferred: int = 0
    reexamined: int = 0
    resolved: int = 0


SOIL_READING_PROPERTIES = (
    ("soil_moisture", "moisture_pct", "%"),
    ("soil_temperature", "temperature_c", "degC"),
    ("ph", "ph", "pH"),
    ("ec", "ec_ds_m", "dS/m"),
    ("nitrogen", "nitrogen_mg_kg", "mg/kg"),
    ("phosphorus", "phosphorus_mg_kg", "mg/kg"),
    ("potassium", "potassium_mg_kg", "mg/kg"),
    ("organic_matter", "organic_matter_pct", "%"),
)
TELEMETRY_MAP = {
    "soil_moisture": ("soil_moisture", "%"),
    "soil_temperature": ("soil_temperature", "degC"),
    "soil_temp": ("soil_temperature", "degC"),
    "soil_ec": ("ec", "dS/m"),
    "soil_ph": ("ph", "pH"),
}


async def _set_tenant(conn, tenant_id: str) -> None:
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)


# ── RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01 ────────────────────
# `last_source_id` is a single high-water mark over a FILTERED stream. Every row the
# scan or the loop skips for a reason that can later disappear — a device with no
# field, a sensor type with no mapping — is passed by the mark as soon as any later
# eligible row in the same batch raises it, and no round returns to it.
#
# The mark is not the thing to fix. One that refuses to pass an unresolved row stalls
# the whole backfill on the first sensor type nobody will ever map: progress becomes
# impossible, which is the defect class closed in #1026. So the mark keeps advancing
# and what it passed is written down, with its reason, and re-examined on every run.
DEFERRAL_REASONS = ("device_field_unbound", "device_not_registered", "sensor_type_unmapped")


async def _defer(conn, source: str, tenant_id: str, source_id: int, reason: str) -> None:
    """Record a passed-over row, or note that it was examined again and still is not
    processable. `examinations` is the honest counter: a deferral seen fifty times with
    the same reason is an operator signal, not a silent retry."""
    if reason not in DEFERRAL_REASONS:  # the CHECK in v231 says the same thing in SQL
        raise ValueError(f"unknown deferral reason {reason!r}")
    await conn.execute(
        """INSERT INTO soil_reconciliation_deferrals(source_name,tenant_id,source_id,reason)
           VALUES ($1,$2::uuid,$3,$4)
           ON CONFLICT (source_name,tenant_id,source_id) DO UPDATE SET
             reason=EXCLUDED.reason,
             last_examined_at=NOW(),
             examinations=soil_reconciliation_deferrals.examinations+1""",
        source,
        tenant_id,
        source_id,
        reason,
    )


async def _resolve_deferral(conn, source: str, tenant_id: str, source_id: int) -> None:
    """Mark a deferral processed. The row is KEPT — deleting it would make a clean
    table mean both "nothing was ever deferred" and "everything was quietly dropped"."""
    await conn.execute(
        """UPDATE soil_reconciliation_deferrals
           SET resolved_at=NOW(), last_examined_at=NOW(),
               examinations=examinations+1
           WHERE source_name=$1 AND tenant_id=$2::uuid AND source_id=$3
             AND resolved_at IS NULL""",
        source,
        tenant_id,
        source_id,
    )


async def _open_deferrals(conn, source: str, tenant_id: str, limit: int) -> list[int]:
    rows = await conn.fetch(
        """SELECT source_id FROM soil_reconciliation_deferrals
           WHERE source_name=$1 AND tenant_id=$2::uuid AND resolved_at IS NULL
           ORDER BY source_id LIMIT $3""",
        source,
        tenant_id,
        limit,
    )
    return [row["source_id"] for row in rows]


async def reconcile_soil_readings(conn, tenant_id: str, batch: int) -> Stats:
    await _set_tenant(conn, tenant_id)
    checkpoint = (
        await conn.fetchval(
            "SELECT COALESCE(last_source_id,0) FROM soil_reconciliation_checkpoints WHERE source_name='soil_readings' AND tenant_id=$1::uuid",
            tenant_id,
        )
        or 0
    )
    rows = await conn.fetch(
        """SELECT id, field_id, sensor_id, depth_cm, moisture_pct, temperature_c, ph,
                  ec_ds_m, nitrogen_mg_kg, phosphorus_mg_kg, potassium_mg_kg,
                  organic_matter_pct, quality, recorded_at
           FROM soil_readings
           WHERE tenant_id=$1::uuid AND id>$2
           ORDER BY id LIMIT $3""",
        tenant_id,
        checkpoint,
        batch,
    )
    stats = Stats(scanned=len(rows))
    last_id = checkpoint
    fields: set[str] = set()
    for row in rows:
        last_id = max(last_id, row["id"])
        fields.add(row["field_id"])
        for prop, column, unit in SOIL_READING_PROPERTIES:
            value = row[column]
            if value is None:
                continue
            result = await conn.execute(
                """INSERT INTO soil_observations(
                       observation_id, contract_version, tenant_id, field_id, property,
                       value_json, unit, depth_from_cm, depth_to_cm, observed_at, received_at,
                       source_type, source_id, procedure_id, quality_status, quality_flags,
                       confidence, idempotency_key, provenance)
                   VALUES ($1,'soil-observation.v1',$2::uuid,$3,$4,to_jsonb($5::numeric),$6,
                           0,$7,$8,$8,'sensor',$9,'legacy_soil_readings_backfill',$10,'[]'::jsonb,
                           0.65,$11,jsonb_build_object('legacy_table','soil_readings','legacy_id',$12))
                   ON CONFLICT (tenant_id,idempotency_key) DO NOTHING""",
                f"obs_legacy_sr_{row['id']}_{prop}",
                tenant_id,
                row["field_id"],
                prop,
                value,
                unit,
                float(row["depth_cm"] or 30),
                row["recorded_at"],
                row["sensor_id"],
                "accepted" if row["quality"] == "good" else "suspect",
                f"soil_readings:{row['id']}:{prop}",
                row["id"],
            )
            stats.inserted += int(result.endswith("1"))
    for field_id in fields:
        await conn.execute(
            """INSERT INTO soil_profile_projection_jobs(tenant_id,field_id,reason)
               VALUES($1::uuid,$2,'historical_reconciliation')
               ON CONFLICT(tenant_id,field_id) WHERE status IN ('pending','running','retry')
               DO UPDATE SET available_at=NOW(), updated_at=NOW()""",
            tenant_id,
            field_id,
        )
    await conn.execute(
        """INSERT INTO soil_reconciliation_checkpoints(source_name,tenant_id,last_source_id,rows_scanned,rows_inserted,last_run_at)
           VALUES ('soil_readings',$1::uuid,$2,$3,$4,NOW())
           ON CONFLICT(source_name,tenant_id) DO UPDATE SET
             last_source_id=EXCLUDED.last_source_id,
             rows_scanned=soil_reconciliation_checkpoints.rows_scanned+EXCLUDED.rows_scanned,
             rows_inserted=soil_reconciliation_checkpoints.rows_inserted+EXCLUDED.rows_inserted,
             last_run_at=NOW(), last_error=NULL, updated_at=NOW()""",
        tenant_id,
        last_id,
        stats.scanned,
        stats.inserted,
    )
    return stats


# The eligibility predicate that used to live in the WHERE clause (`d.field_id IS NOT
# NULL`) is gone, and the JOIN is now LEFT: a row must be SEEN to be recorded, and an
# INNER JOIN hides telemetry whose device was never registered at all. Both passes read
# the same shape so one row-level model decides eligibility, not two.
_TELEMETRY_COLUMNS = """SELECT t.telemetry_id,t.device_id,t.sensor_type,t.value,t.unit,t.recorded_at,t.received_at,
                  d.device_id AS joined_device_id, d.field_id
           FROM device_telemetry t LEFT JOIN iot_devices d ON d.device_id=t.device_id"""


async def _process_telemetry_row(
    conn, tenant_id: str, row, stats: Stats, fields: set
) -> str | None:
    """Insert the observation, or return the reason this row is not processable yet.

    One function for both passes. Two copies of this decision would drift, and the
    forward scan and the re-examination would then disagree about what "eligible"
    means — the failure mode that makes a ledger worse than no ledger.
    """
    if row["joined_device_id"] is None:
        return "device_not_registered"
    if row["field_id"] is None:
        return "device_field_unbound"
    mapping = TELEMETRY_MAP.get(row["sensor_type"])
    if not mapping:
        return "sensor_type_unmapped"
    prop, default_unit = mapping
    fields.add(row["field_id"])
    result = await conn.execute(
        """INSERT INTO soil_observations(
               observation_id,contract_version,tenant_id,field_id,property,value_json,unit,
               depth_from_cm,depth_to_cm,observed_at,received_at,source_type,source_id,
               procedure_id,quality_status,quality_flags,confidence,idempotency_key,provenance)
           VALUES ($1,'soil-observation.v1',$2::uuid,$3,$4,to_jsonb($5::numeric),$6,0,30,$7,$8,
                   'sensor',$9,'device_telemetry_backfill','suspect','["depth_unknown","calibration_unknown"]'::jsonb,
                   0.60,$10,jsonb_build_object('legacy_table','device_telemetry','legacy_id',$11))
           ON CONFLICT(tenant_id,idempotency_key) DO NOTHING""",
        f"obs_legacy_dt_{row['telemetry_id']}_{prop}",
        tenant_id,
        row["field_id"],
        prop,
        row["value"],
        row["unit"] or default_unit,
        row["recorded_at"],
        row["received_at"],
        row["device_id"],
        f"device_telemetry:{row['telemetry_id']}:{prop}",
        row["telemetry_id"],
    )
    stats.inserted += int(result.endswith("1"))
    return None


async def reconcile_device_telemetry(conn, tenant_id: str, batch: int) -> Stats:
    await _set_tenant(conn, tenant_id)
    checkpoint = (
        await conn.fetchval(
            "SELECT COALESCE(last_source_id,0) FROM soil_reconciliation_checkpoints WHERE source_name='device_telemetry' AND tenant_id=$1::uuid",
            tenant_id,
        )
        or 0
    )
    stats = Stats()
    fields: set[str] = set()

    # ── Pass A: re-examine what earlier runs passed over ────────────────────────
    # Before scanning forward, ask whether the reasons recorded earlier have gone. This
    # is the whole point of the ledger: the cursor may pass an unresolved row, but only
    # because something else remembers it.
    deferred_ids = await _open_deferrals(conn, "device_telemetry", tenant_id, batch)
    if deferred_ids:
        for row in await conn.fetch(
            f"""{_TELEMETRY_COLUMNS}
           WHERE t.tenant_id=$1::uuid AND t.telemetry_id = ANY($2::bigint[])
           ORDER BY t.telemetry_id""",
            tenant_id,
            deferred_ids,
        ):
            stats.reexamined += 1
            reason = await _process_telemetry_row(conn, tenant_id, row, stats, fields)
            if reason is None:
                await _resolve_deferral(conn, "device_telemetry", tenant_id, row["telemetry_id"])
                stats.resolved += 1
            else:
                await _defer(conn, "device_telemetry", tenant_id, row["telemetry_id"], reason)

    # ── Pass B: scan forward ────────────────────────────────────────────────────
    rows = await conn.fetch(
        f"""{_TELEMETRY_COLUMNS}
           WHERE t.tenant_id=$1::uuid AND t.telemetry_id>$2
           ORDER BY t.telemetry_id LIMIT $3""",
        tenant_id,
        checkpoint,
        batch,
    )
    stats.scanned = len(rows)
    last_id = checkpoint
    for row in rows:
        last_id = max(last_id, row["telemetry_id"])
        reason = await _process_telemetry_row(conn, tenant_id, row, stats, fields)
        if reason is not None:
            await _defer(conn, "device_telemetry", tenant_id, row["telemetry_id"], reason)
            stats.deferred += 1
    for field_id in fields:
        await conn.execute(
            """INSERT INTO soil_profile_projection_jobs(tenant_id,field_id,reason)
               VALUES($1::uuid,$2,'historical_reconciliation')
               ON CONFLICT(tenant_id,field_id) WHERE status IN ('pending','running','retry')
               DO UPDATE SET available_at=NOW(), updated_at=NOW()""",
            tenant_id,
            field_id,
        )
    await conn.execute(
        """INSERT INTO soil_reconciliation_checkpoints(source_name,tenant_id,last_source_id,rows_scanned,rows_inserted,last_run_at)
           VALUES ('device_telemetry',$1::uuid,$2,$3,$4,NOW())
           ON CONFLICT(source_name,tenant_id) DO UPDATE SET
             last_source_id=EXCLUDED.last_source_id,
             rows_scanned=soil_reconciliation_checkpoints.rows_scanned+EXCLUDED.rows_scanned,
             rows_inserted=soil_reconciliation_checkpoints.rows_inserted+EXCLUDED.rows_inserted,
             last_run_at=NOW(), last_error=NULL, updated_at=NOW()""",
        tenant_id,
        last_id,
        stats.scanned,
        stats.inserted,
    )
    return stats


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--batch", type=int, default=1000)
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL required")
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        async with conn.transaction():
            sr = await reconcile_soil_readings(conn, args.tenant, args.batch)
            dt = await reconcile_device_telemetry(conn, args.tenant, args.batch)
        print({"soil_readings": sr.__dict__, "device_telemetry": dt.__dict__})
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
