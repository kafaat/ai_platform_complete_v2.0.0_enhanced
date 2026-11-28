"""H5.1 server-authoritative field↔water-source binding resolution (pure DB logic).

The salinity gate must derive the water source from SoR, never from client input. This module
owns the exact SQL and the decision-grade sample-selection policy, and is imported by BOTH the
served MPC recommendation route (which wraps it in a tenant-scoped connection) and the real-PG
certification test (which drives it against a live database as a restricted NOBYPASSRLS role).
Keeping the SQL here — not inlined in the router — means the certification test exercises the
REAL query, not a copy.

Resolution rule: for a field at instant ``now``, the active bindings are the rows with
``status='active'`` whose validity window covers ``now``, ordered by ``priority`` (lower = primary).
Every active source is returned so a sensitive gate can fail closed on the worst of a blend. For
each source, the latest DECISION-GRADE water-quality sample is selected (estimated/measured are
excluded — see canonical_well_capability.DECISION_GRADE_SAMPLE_QUALITIES); when only lower-grade
samples exist that fact is surfaced so the verdict can distinguish "no sample" from "unvalidated".

The blend actually applied to the field is summarised by ``summarize_blend_water_quality``: EC of
the blend from the declared mixing ratios, and SAR only from blended ion concentrations. It is
advisory provenance — the gate above still fails closed on the worst active source.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.irrigation_water_analysis import BLEND_ION_FIELDS, compute_blend_water_quality

from api.canonical_well_capability import (
    AQUIFER_ALLOCATION_UNVERIFIED,
    DECISION_GRADE_SAMPLE_QUALITIES,
)

# Sorted for a deterministic bound parameter (list, not set — asyncpg binds text[]).
DECISION_GRADE_SAMPLE_QUALITY_LIST = sorted(DECISION_GRADE_SAMPLE_QUALITIES)

# Resolve active bindings and their evidence in one tenant-scoped statement. The lateral lookup
# can use the (tenant_id, water_source_id, sampled_at) index and retains the latest eligible sample
# even if its EC is missing. Equal sample times have no policy-defined precedence.
ACTIVE_BINDINGS_SQL = """
SELECT a.water_source_id,
       a.priority,
       a.mixing_ratio,
       s.maximum_allowed_ec_ds_m,
       latest.ec_ds_m,
       latest.sampled_at,
       latest.quality,
       CASE WHEN latest.quality IS NULL THEN EXISTS (
           SELECT 1 FROM irrigation_water_quality_samples any_sample
           WHERE any_sample.tenant_id = a.tenant_id AND any_sample.water_source_id = a.water_source_id
       ) ELSE false END AS non_decision_grade_sample_present
FROM field_irrigation_source_assignments a
JOIN irrigation_water_sources s
  ON s.id = a.water_source_id AND s.tenant_id = a.tenant_id
LEFT JOIN LATERAL (
    SELECT q.ec_ds_m, q.sampled_at, q.quality
    FROM irrigation_water_quality_samples q
    WHERE q.tenant_id = a.tenant_id AND q.water_source_id = a.water_source_id
      AND q.quality = ANY($3::text[])
    ORDER BY q.sampled_at DESC
    LIMIT 1
) latest ON true
WHERE a.field_id = $1
  AND a.status = 'active'
  AND a.valid_from <= $2
  AND (a.valid_to IS NULL OR a.valid_to > $2)
ORDER BY a.priority, a.water_source_id
"""


async def aquifer_allocation_blocker(
    conn: Any,
    field_id: str,
    *,
    tenant_id: str,
    start: datetime,
    end: datetime,
    season_id: str | None = None,
) -> str | None:
    """Block unresolved well allocation, including a current-season persisted well graph."""
    import asyncpg

    try:
        has_well = await conn.fetchval(
            """
            SELECT CASE WHEN current_setting('app.current_tenant', true) = $4::text
            THEN EXISTS (
                SELECT 1 FROM field_irrigation_source_assignments a
                JOIN irrigation_water_sources s
                  ON (s.id, s.tenant_id) = (a.water_source_id, a.tenant_id)
                WHERE a.tenant_id = ($4::text)::uuid AND a.field_id = $1
                  AND a.status = 'active' AND s.source_type = 'well'
                  AND a.valid_from < $3 AND (a.valid_to IS NULL OR a.valid_to > $2)
            ) END
            """,
            field_id,
            start,
            end,
            str(tenant_id),
        )
        if has_well is False and season_id is not None:
            # A well graph survives missing/expired source assignments. Daily MPC
            # must not regain eligibility by losing that separate binding row.
            has_well = await conn.fetchval(
                """
                SELECT COALESCE((
                    SELECT well_id IS NOT NULL
                    FROM canonical_irrigation_capability_graphs
                    WHERE tenant_id::text = $1 AND field_id = $2 AND season_id = $3
                    ORDER BY created_at DESC
                    LIMIT 1
                ), FALSE)
                """,
                str(tenant_id),
                field_id,
                season_id,
            )
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
        return "water_source_binding_unresolved"
    if has_well is None:
        return "water_source_binding_unresolved"
    return AQUIFER_ALLOCATION_UNVERIFIED if has_well else None


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


async def resolve_active_bindings(
    conn: Any, field_id: str, *, now: datetime
) -> list[dict[str, Any]]:
    """Resolve the field's active water-source bindings with decision-grade salinity evidence.

    ``conn`` is any object exposing asyncpg's ``fetch`` already scoped
    to the caller's tenant (RLS via ``app.current_tenant``). Returns one dict per active source,
    ordered by priority. Never raises for an empty result — an empty list means "no active binding".
    """
    rows = await conn.fetch(ACTIVE_BINDINGS_SQL, field_id, now, DECISION_GRADE_SAMPLE_QUALITY_LIST)
    bindings: list[dict[str, Any]] = []
    for row in rows:
        water_quality: dict[str, Any] | None = None
        if row["quality"] is not None:
            sampled_at = row["sampled_at"]
            water_quality = {
                "ec_ds_m": _float(row["ec_ds_m"]),
                "sampled_at": sampled_at.isoformat()
                if hasattr(sampled_at, "isoformat")
                else str(sampled_at),
                "quality": row["quality"],
            }
        bindings.append(
            {
                "water_source_id": str(row["water_source_id"]),
                "priority": int(row["priority"]),
                "mixing_ratio": _float(row["mixing_ratio"]),
                "maximum_allowed_ec_ds_m": _float(row["maximum_allowed_ec_ds_m"]),
                "water_quality": water_quality,
                "non_decision_grade_sample_present": row["non_decision_grade_sample_present"],
            }
        )
    return bindings


def summarize_blend_water_quality(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """EC/SAR of the water actually applied: the active sources blended by ``mixing_ratio``.

    EC is the volume-weighted mean of each source's decision-grade EC. SAR is computed only from
    blended Na/Ca/Mg (meq/L) — never as a weighted mean of per-source SARs, which is a different
    and wrong number. ``irrigation_water_quality_samples`` records no ion concentrations today, so
    a live blend reports SAR ``not_computable`` (``source_ions_missing``) rather than a guess; the
    ion keys are read from ``water_quality`` the moment a producer supplies them.

    Advisory only: it does NOT relax the per-source gate (``gate_effect`` says so explicitly).
    """
    components = []
    for b in bindings:
        wq = b.get("water_quality") or {}
        components.append(
            {
                "source_id": b.get("water_source_id"),
                "mixing_ratio": b.get("mixing_ratio"),
                "ec_ds_m": wq.get("ec_ds_m"),
                **{k: wq.get(k) for k in BLEND_ION_FIELDS},
            }
        )
    out = compute_blend_water_quality(components)
    out["gate_effect"] = "advisory_worst_source_gate_unchanged"
    return out
