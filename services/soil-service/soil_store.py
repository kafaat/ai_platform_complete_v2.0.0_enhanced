"""Durable canonical soil evidence and snapshot persistence."""

from __future__ import annotations

import json
from typing import Any

from shared.contracts.soil import SoilObservation, SoilProfileSnapshot


async def _tenant_tx(conn, tenant_id: str):
    tx = conn.transaction()
    await tx.start()
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
    return tx


async def persist_observation(pool, observation: SoilObservation) -> bool:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, observation.tenant_id)
        try:
            result = await conn.execute(
                """
                INSERT INTO soil_observations (
                    observation_id, contract_version, tenant_id, field_id, zone_id,
                    property, value_json, unit, depth_from_cm, depth_to_cm,
                    observed_at, received_at, source_type, source_id, procedure_id,
                    calibration_id, quality_status, quality_flags, confidence,
                    idempotency_key, provenance
                ) VALUES (
                    $1,$2,$3::uuid,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12,$13,$14,$15,
                    $16,$17,$18::jsonb,$19,$20,$21::jsonb
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                """,
                observation.observation_id,
                observation.contract_version,
                observation.tenant_id,
                observation.field_id,
                observation.zone_id,
                observation.property,
                json.dumps(observation.value),
                observation.unit,
                observation.depth_from_cm,
                observation.depth_to_cm,
                observation.observed_at,
                observation.received_at,
                observation.source_type.value,
                observation.source_id,
                observation.procedure_id,
                observation.calibration_id,
                observation.quality_status.value,
                json.dumps(observation.quality_flags),
                observation.confidence,
                observation.idempotency_key,
                json.dumps(observation.provenance),
            )
            if result.endswith("1"):
                if observation.supersedes_observation_id:
                    linked = await conn.fetchval(
                        """
                        INSERT INTO soil_observation_supersessions (
                            tenant_id, superseded_observation_id, replacement_observation_id, reason
                        )
                        SELECT $1::uuid, old.observation_id, new.observation_id, $4
                        FROM soil_observations old
                        JOIN soil_observations new ON new.observation_id = $3
                        WHERE old.observation_id = $2
                          AND old.tenant_id = $1::uuid AND new.tenant_id = $1::uuid
                          AND old.field_id = new.field_id
                          AND old.property = new.property
                          AND old.depth_from_cm = new.depth_from_cm
                          AND old.depth_to_cm = new.depth_to_cm
                        ON CONFLICT (tenant_id, superseded_observation_id) DO NOTHING
                        RETURNING replacement_observation_id
                        """,
                        observation.tenant_id,
                        observation.supersedes_observation_id,
                        observation.observation_id,
                        observation.supersession_reason,
                    )
                    if linked is None:
                        raise ValueError(
                            "soil_observation_supersession_target_invalid_or_already_replaced"
                        )
                import projection_jobs

                await projection_jobs.enqueue(
                    conn,
                    tenant_id=observation.tenant_id,
                    field_id=observation.field_id,
                    reason="observation_superseded"
                    if observation.supersedes_observation_id
                    else "observation_ingested",
                )
            await tx.commit()
            return result.endswith("1")
        except Exception:
            await tx.rollback()
            raise


async def list_observations(
    pool,
    *,
    tenant_id: str,
    field_id: str,
    property_name: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            rows = await conn.fetch(
                """
                SELECT o.observation_id, o.contract_version, o.tenant_id::text, o.field_id, o.zone_id,
                       o.property, o.value_json, o.unit, o.depth_from_cm, o.depth_to_cm,
                       o.observed_at, o.received_at, o.source_type, o.source_id, o.procedure_id,
                       o.calibration_id, o.quality_status, o.quality_flags, o.confidence,
                       o.idempotency_key, o.provenance,
                       s.replacement_observation_id IS NOT NULL AS is_superseded,
                       s.replacement_observation_id AS superseded_by_observation_id
                FROM soil_observations o
                LEFT JOIN soil_observation_supersessions s
                  ON s.tenant_id=o.tenant_id AND s.superseded_observation_id=o.observation_id
                WHERE o.tenant_id = $1::uuid AND o.field_id = $2
                  AND ($3::text IS NULL OR o.property = $3)
                ORDER BY o.observed_at DESC, o.received_at DESC
                LIMIT $4
                """,
                tenant_id,
                field_id,
                property_name,
                limit,
            )
            await tx.commit()
            return [dict(row) for row in rows]
        except Exception:
            await tx.rollback()
            raise


async def persist_snapshot(pool, snapshot: SoilProfileSnapshot) -> bool:
    payload = snapshot.model_dump(mode="json")
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, str(snapshot.tenant_id))
        try:
            result = await conn.execute(
                """
                INSERT INTO soil_profile_snapshots (
                    profile_id, profile_hash, contract_version, tenant_id, field_id, zone_id,
                    effective_at, data_available_at, status, evidence_level,
                    completeness_score, quality_passed, executable,
                    selection_policy_version, snapshot
                ) VALUES ($1,$2,$3,$4::uuid,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                ON CONFLICT (profile_hash) DO NOTHING
                """,
                snapshot.profile_id,
                snapshot.profile_hash,
                snapshot.contract_version,
                snapshot.tenant_id,
                snapshot.field_id,
                snapshot.zone_id,
                snapshot.effective_at,
                snapshot.data_available_at,
                snapshot.status.value,
                snapshot.evidence_level.value,
                snapshot.completeness_score,
                snapshot.quality_gate.passed,
                snapshot.quality_gate.executable,
                snapshot.selection_policy_version,
                json.dumps(payload),
            )
            await tx.commit()
            return result.endswith("1")
        except Exception:
            await tx.rollback()
            raise


async def get_current_snapshot(pool, *, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            row = await conn.fetchrow(
                """
                SELECT s.snapshot
                FROM soil_profile_current c
                JOIN soil_profile_snapshots s
                  ON s.tenant_id=c.tenant_id AND s.profile_id=c.current_profile_id
                WHERE c.tenant_id=$1::uuid AND c.field_id=$2
                """,
                tenant_id,
                field_id,
            )
            await tx.commit()
            if not row:
                return None
            raw = row["snapshot"]
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            await tx.rollback()
            raise


async def get_snapshot_history(
    pool, *, tenant_id: str, field_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            rows = await conn.fetch(
                """
                SELECT snapshot
                FROM soil_profile_snapshots
                WHERE tenant_id=$1::uuid AND field_id=$2
                ORDER BY effective_at DESC, created_at DESC
                LIMIT $3
                """,
                tenant_id,
                field_id,
                limit,
            )
            await tx.commit()
            return [
                json.loads(r["snapshot"]) if isinstance(r["snapshot"], str) else dict(r["snapshot"])
                for r in rows
            ]
        except Exception:
            await tx.rollback()
            raise


async def rebuild_snapshot_locked(pool, *, tenant_id: str, field_id: str) -> SoilProfileSnapshot:
    """Build and persist one immutable projection under a per-tenant/field advisory lock.

    The lock prevents duplicate competing projections across workers. The resulting
    profile hash remains the idempotency identity, so retries are logically exactly-once.
    """
    import profile_composer

    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"soil-profile:{tenant_id}:{field_id}",
            )
            rows = await conn.fetch(
                """
                SELECT o.observation_id, o.contract_version, o.tenant_id::text, o.field_id, o.zone_id,
                       o.property, o.value_json, o.unit, o.depth_from_cm, o.depth_to_cm,
                       o.observed_at, o.received_at, o.source_type, o.source_id, o.procedure_id,
                       o.calibration_id, o.quality_status, o.quality_flags, o.confidence,
                       o.idempotency_key, o.provenance,
                       (s.replacement_observation_id IS NOT NULL) AS is_superseded,
                       s.replacement_observation_id AS superseded_by_observation_id
                FROM soil_observations o
                LEFT JOIN soil_observation_supersessions s
                  ON s.tenant_id=o.tenant_id AND s.superseded_observation_id=o.observation_id
                WHERE o.tenant_id=$1::uuid AND o.field_id=$2
                ORDER BY o.observed_at DESC, o.received_at DESC
                LIMIT 5000
                """,
                tenant_id,
                field_id,
            )
            snapshot = profile_composer.compose_snapshot(
                tenant_id=tenant_id, field_id=field_id, observations=[dict(r) for r in rows]
            )
            payload = snapshot.model_dump(mode="json")
            persisted = await conn.fetchval(
                """
                INSERT INTO soil_profile_snapshots (
                    profile_id, profile_hash, contract_version, tenant_id, field_id, zone_id,
                    effective_at, data_available_at, status, evidence_level,
                    completeness_score, quality_passed, executable,
                    selection_policy_version, snapshot
                ) VALUES ($1,$2,$3,$4::uuid,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                ON CONFLICT (profile_hash) DO NOTHING
                RETURNING snapshot
                """,
                snapshot.profile_id,
                snapshot.profile_hash,
                snapshot.contract_version,
                snapshot.tenant_id,
                snapshot.field_id,
                snapshot.zone_id,
                snapshot.effective_at,
                snapshot.data_available_at,
                snapshot.status.value,
                snapshot.evidence_level.value,
                snapshot.completeness_score,
                snapshot.quality_gate.passed,
                snapshot.quality_gate.executable,
                snapshot.selection_policy_version,
                json.dumps(payload),
            )
            if persisted is None:
                persisted = await conn.fetchval(
                    """
                    SELECT snapshot
                    FROM soil_profile_snapshots
                    WHERE tenant_id=$1::uuid AND field_id=$2 AND profile_hash=$3
                    """,
                    tenant_id,
                    field_id,
                    snapshot.profile_hash,
                )
            if persisted is None:
                raise RuntimeError("soil_snapshot_persist_or_load_failed")
            # JSONB decodes as str without a registered codec; normalise before use.
            record = json.loads(persisted) if isinstance(persisted, str) else dict(persisted)
            persisted_profile_id = record.get("profile_id")
            await conn.execute(
                """
                INSERT INTO soil_profile_current (
                    tenant_id, field_id, current_profile_id, projected_at, projection_reason
                ) VALUES ($1::uuid,$2,$3,now(),'rebuild')
                ON CONFLICT (tenant_id, field_id) DO UPDATE SET
                    current_profile_id=EXCLUDED.current_profile_id,
                    projected_at=EXCLUDED.projected_at,
                    projection_reason=EXCLUDED.projection_reason
                """,
                tenant_id,
                field_id,
                persisted_profile_id,
            )
            await tx.commit()
            return SoilProfileSnapshot.model_validate(record)
        except Exception:
            await tx.rollback()
            raise


async def canonical_sensor_readings(
    pool, *, tenant_id: str, field_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    """Compatibility view built from the canonical observation store, not soil_readings."""
    rows = await list_observations(
        pool, tenant_id=tenant_id, field_id=field_id, limit=max(limit * 8, 100)
    )
    by_key: dict[tuple[str, Any], dict[str, Any]] = {}
    mapping = {
        "soil_temperature": "temperature",
        "soil_moisture": "moisture_pct",
        "ph": "ph_level",
        "ec": "ec_level",
        "electrical_conductivity": "ec_level",
        "nitrogen": "n_ppm",
        "phosphorus": "p_ppm",
        "potassium": "k_ppm",
    }
    for row in rows:
        target = mapping.get(row.get("property"))
        if not target or row.get("source_type") != "sensor" or row.get("is_superseded"):
            continue
        key = (row.get("source_id") or "unknown", row.get("observed_at"))
        item = by_key.setdefault(
            key,
            {
                "sensor_id": key[0],
                "recorded_at": key[1],
                "temperature": None,
                "moisture_pct": None,
                "ph_level": None,
                "ec_level": None,
                "n_ppm": None,
                "p_ppm": None,
                "k_ppm": None,
            },
        )
        item[target] = row.get("value_json")
    return sorted(by_key.values(), key=lambda x: x["recorded_at"], reverse=True)[:limit]


async def get_cutover_readiness(pool, *, tenant_id: str) -> dict[str, Any]:
    """Return tenant-scoped readiness for enabling strict soil consumers.

    The denominator is every field that has canonical soil evidence. This avoids claiming
    readiness for unrelated fields while still preventing strict cutover when evidence exists
    but no current governed profile was built.
    """
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            tables = await conn.fetchrow(
                """
                SELECT
                  to_regclass('public.soil_observations') IS NOT NULL AS observations_ready,
                  to_regclass('public.soil_profile_snapshots') IS NOT NULL AS profiles_ready
                """
            )
            if not tables or not tables["observations_ready"] or not tables["profiles_ready"]:
                await tx.commit()
                return {
                    "schema_ready": False,
                    "can_enable_strict_soil": False,
                    "reason": "soil_schema_not_applied",
                    "fields_total": 0,
                    "profiles_ready": 0,
                    "profiles_missing": 0,
                    "invalid_profiles": 0,
                    "coverage_pct": 0.0,
                }

            row = await conn.fetchrow(
                """
                WITH evidence_fields AS (
                    SELECT DISTINCT field_id
                    FROM soil_observations
                    WHERE tenant_id=$1::uuid
                ), current_profiles AS (
                    SELECT c.field_id, s.quality_passed, s.profile_hash,
                           s.snapshot->>'contract_version' AS payload_contract_version
                    FROM soil_profile_current c
                    JOIN soil_profile_snapshots s
                      ON s.tenant_id=c.tenant_id AND s.profile_id=c.current_profile_id
                    WHERE c.tenant_id=$1::uuid
                )
                SELECT
                    (SELECT count(*) FROM evidence_fields) AS fields_total,
                    count(cp.field_id) AS profiles_ready,
                    count(*) FILTER (
                        WHERE cp.field_id IS NOT NULL AND (
                            cp.quality_passed IS NOT TRUE
                            OR cp.profile_hash !~ '^[0-9a-f]{64}$'
                            OR cp.payload_contract_version IS DISTINCT FROM 'soil-profile.v1'
                        )
                    ) AS invalid_profiles
                FROM evidence_fields ef
                LEFT JOIN current_profiles cp USING (field_id)
                """,
                tenant_id,
            )
            await tx.commit()
            total = int(row["fields_total"] or 0)
            ready = int(row["profiles_ready"] or 0)
            invalid = int(row["invalid_profiles"] or 0)
            missing = max(total - ready, 0)
            coverage = round((ready / total * 100.0), 2) if total else 0.0
            can_enable = total > 0 and missing == 0 and invalid == 0
            return {
                "schema_ready": True,
                "can_enable_strict_soil": can_enable,
                "reason": "ready"
                if can_enable
                else ("no_soil_evidence" if total == 0 else "profiles_incomplete_or_invalid"),
                "fields_total": total,
                "profiles_ready": ready,
                "profiles_missing": missing,
                "invalid_profiles": invalid,
                "coverage_pct": coverage,
            }
        except Exception:
            await tx.rollback()
            raise
