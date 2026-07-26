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
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.canonical_well_capability import DECISION_GRADE_SAMPLE_QUALITIES

# Sorted for a deterministic bound parameter (list, not set — asyncpg binds text[]).
DECISION_GRADE_SAMPLE_QUALITY_LIST = sorted(DECISION_GRADE_SAMPLE_QUALITIES)

# Active bindings for a field at $2 (now), joined to the source for its configured EC limit.
ACTIVE_BINDINGS_SQL = """
SELECT a.water_source_id,
       a.priority,
       a.mixing_ratio,
       s.maximum_allowed_ec_ds_m
FROM field_irrigation_source_assignments a
JOIN irrigation_water_sources s
  ON s.id = a.water_source_id AND s.tenant_id = a.tenant_id
WHERE a.field_id = $1
  AND a.status = 'active'
  AND a.valid_from <= $2
  AND (a.valid_to IS NULL OR a.valid_to > $2)
ORDER BY a.priority ASC, a.water_source_id ASC
"""

# Latest DECISION-GRADE sample for a source ($2 = decision-grade tiers). estimated/measured excluded.
LATEST_DECISION_GRADE_SAMPLE_SQL = """
SELECT ec_ds_m, sampled_at, quality
FROM irrigation_water_quality_samples
WHERE water_source_id = $1 AND quality = ANY($2::text[])
ORDER BY sampled_at DESC
LIMIT 1
"""

# Whether ANY sample exists for a source (to tell "no sample" from "only lower-grade samples").
ANY_SAMPLE_EXISTS_SQL = """
SELECT EXISTS(SELECT 1 FROM irrigation_water_quality_samples WHERE water_source_id = $1)
"""


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


async def resolve_active_bindings(
    conn: Any, field_id: str, *, now: datetime
) -> list[dict[str, Any]]:
    """Resolve the field's active water-source bindings with decision-grade salinity evidence.

    ``conn`` is any object exposing asyncpg's ``fetch``/``fetchrow``/``fetchval`` already scoped
    to the caller's tenant (RLS via ``app.current_tenant``). Returns one dict per active source,
    ordered by priority. Never raises for an empty result — an empty list means "no active binding".
    """
    rows = await conn.fetch(ACTIVE_BINDINGS_SQL, field_id, now)
    bindings: list[dict[str, Any]] = []
    for row in rows:
        source_id = row["water_source_id"]
        sample = await conn.fetchrow(
            LATEST_DECISION_GRADE_SAMPLE_SQL, source_id, DECISION_GRADE_SAMPLE_QUALITY_LIST
        )
        non_decision_grade_present = False
        if sample is None:
            non_decision_grade_present = bool(await conn.fetchval(ANY_SAMPLE_EXISTS_SQL, source_id))
        water_quality: dict[str, Any] | None = None
        if sample is not None:
            sampled_at = sample["sampled_at"]
            water_quality = {
                "ec_ds_m": _float(sample["ec_ds_m"]),
                "sampled_at": sampled_at.isoformat()
                if hasattr(sampled_at, "isoformat")
                else str(sampled_at),
                "quality": sample["quality"],
            }
        bindings.append(
            {
                "water_source_id": str(source_id),
                "priority": int(row["priority"]),
                "mixing_ratio": _float(row["mixing_ratio"]),
                "maximum_allowed_ec_ds_m": _float(row["maximum_allowed_ec_ds_m"]),
                "water_quality": water_quality,
                "non_decision_grade_sample_present": non_decision_grade_present,
            }
        )
    return bindings
