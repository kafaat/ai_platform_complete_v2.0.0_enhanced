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


async def reconcile_soil_readings(conn, tenant_id: str, batch: int) -> Stats:
    await _set_tenant(conn, tenant_id)
    checkpoint = await conn.fetchval(
        "SELECT COALESCE(last_source_id,0) FROM soil_reconciliation_checkpoints WHERE source_name='soil_readings' AND tenant_id=$1::uuid",
        tenant_id,
    ) or 0
    rows = await conn.fetch(
        """SELECT id, field_id, sensor_id, depth_cm, moisture_pct, temperature_c, ph,
                  ec_ds_m, nitrogen_mg_kg, phosphorus_mg_kg, potassium_mg_kg,
                  organic_matter_pct, quality, recorded_at
           FROM soil_readings
           WHERE tenant_id=$1::uuid AND id>$2
           ORDER BY id LIMIT $3""",
        tenant_id, checkpoint, batch,
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
                f"obs_legacy_sr_{row['id']}_{prop}", tenant_id, row["field_id"], prop,
                value, unit, float(row["depth_cm"] or 30), row["recorded_at"],
                row["sensor_id"], "accepted" if row["quality"] == "good" else "suspect",
                f"soil_readings:{row['id']}:{prop}", row["id"],
            )
            stats.inserted += int(result.endswith("1"))
    for field_id in fields:
        await conn.execute(
            """INSERT INTO soil_profile_projection_jobs(tenant_id,field_id,reason)
               VALUES($1::uuid,$2,'historical_reconciliation')
               ON CONFLICT(tenant_id,field_id) WHERE status IN ('pending','running','retry')
               DO UPDATE SET available_at=NOW(), updated_at=NOW()""",
            tenant_id, field_id,
        )
    await conn.execute(
        """INSERT INTO soil_reconciliation_checkpoints(source_name,tenant_id,last_source_id,rows_scanned,rows_inserted,last_run_at)
           VALUES ('soil_readings',$1::uuid,$2,$3,$4,NOW())
           ON CONFLICT(source_name,tenant_id) DO UPDATE SET
             last_source_id=EXCLUDED.last_source_id,
             rows_scanned=soil_reconciliation_checkpoints.rows_scanned+EXCLUDED.rows_scanned,
             rows_inserted=soil_reconciliation_checkpoints.rows_inserted+EXCLUDED.rows_inserted,
             last_run_at=NOW(), last_error=NULL, updated_at=NOW()""",
        tenant_id, last_id, stats.scanned, stats.inserted,
    )
    return stats


async def reconcile_device_telemetry(conn, tenant_id: str, batch: int) -> Stats:
    await _set_tenant(conn, tenant_id)
    checkpoint = await conn.fetchval(
        "SELECT COALESCE(last_source_id,0) FROM soil_reconciliation_checkpoints WHERE source_name='device_telemetry' AND tenant_id=$1::uuid",
        tenant_id,
    ) or 0
    rows = await conn.fetch(
        """SELECT t.telemetry_id,t.device_id,t.sensor_type,t.value,t.unit,t.recorded_at,t.received_at,d.field_id
           FROM device_telemetry t JOIN iot_devices d ON d.device_id=t.device_id
           WHERE t.tenant_id=$1::uuid AND t.telemetry_id>$2 AND d.field_id IS NOT NULL
           ORDER BY t.telemetry_id LIMIT $3""",
        tenant_id, checkpoint, batch,
    )
    stats = Stats(scanned=len(rows))
    last_id = checkpoint
    fields: set[str] = set()
    for row in rows:
        last_id = max(last_id, row["telemetry_id"])
        mapping = TELEMETRY_MAP.get(row["sensor_type"])
        if not mapping:
            continue
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
            f"obs_legacy_dt_{row['telemetry_id']}_{prop}", tenant_id, row["field_id"], prop,
            row["value"], row["unit"] or default_unit, row["recorded_at"], row["received_at"],
            row["device_id"], f"device_telemetry:{row['telemetry_id']}:{prop}", row["telemetry_id"],
        )
        stats.inserted += int(result.endswith("1"))
    for field_id in fields:
        await conn.execute(
            """INSERT INTO soil_profile_projection_jobs(tenant_id,field_id,reason)
               VALUES($1::uuid,$2,'historical_reconciliation')
               ON CONFLICT(tenant_id,field_id) WHERE status IN ('pending','running','retry')
               DO UPDATE SET available_at=NOW(), updated_at=NOW()""",
            tenant_id, field_id,
        )
    await conn.execute(
        """INSERT INTO soil_reconciliation_checkpoints(source_name,tenant_id,last_source_id,rows_scanned,rows_inserted,last_run_at)
           VALUES ('device_telemetry',$1::uuid,$2,$3,$4,NOW())
           ON CONFLICT(source_name,tenant_id) DO UPDATE SET
             last_source_id=EXCLUDED.last_source_id,
             rows_scanned=soil_reconciliation_checkpoints.rows_scanned+EXCLUDED.rows_scanned,
             rows_inserted=soil_reconciliation_checkpoints.rows_inserted+EXCLUDED.rows_inserted,
             last_run_at=NOW(), last_error=NULL, updated_at=NOW()""",
        tenant_id, last_id, stats.scanned, stats.inserted,
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
