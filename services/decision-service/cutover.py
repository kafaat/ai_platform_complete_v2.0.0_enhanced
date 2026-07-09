"""Decision-service cutover safety contract.

This module intentionally does not perform schema changes or writes. It exposes a
small, deterministic readiness model used by CI and by the runtime `/v1/cutover/readiness`
endpoint so Sahool cannot promote decision-service to SoR merely by setting one flag.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}
_REQUIRED_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
    "decision_outbox_events",
)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


@dataclass(frozen=True)
class CutoverReadiness:
    requested_sor: bool
    database_configured: bool
    migrations_verified: bool
    backfill_verified: bool
    tenant_isolation_verified: bool
    outbox_verified: bool
    staging_approved: bool
    production_approved: bool
    can_enable_sor: bool
    can_demote_platform: bool
    mode: str
    required_tables: tuple[str, ...]
    missing_gates: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_tables"] = list(self.required_tables)
        data["missing_gates"] = list(self.missing_gates)
        return data


def readiness_from_env() -> CutoverReadiness:
    """Return a fail-closed readiness decision for SoR promotion.

    Gates are split deliberately:
    - `can_enable_sor` is allowed only after DB, migrations, backfill, tenant isolation,
      outbox, and staging approval are all verified.
    - `can_demote_platform` additionally requires production approval. This prevents
      accidental removal of sahool-platform writes during staging experiments.
    """
    requested = _truthy("DECISION_SERVICE_SOR_ENABLED")
    db = bool(os.getenv("DATABASE_URL", "").strip())
    migrations = _truthy("DECISION_SERVICE_MIGRATIONS_VERIFIED")
    backfill = _truthy("DECISION_SERVICE_BACKFILL_VERIFIED")
    tenant = _truthy("DECISION_SERVICE_TENANT_ISOLATION_VERIFIED")
    outbox = _truthy("DECISION_SERVICE_OUTBOX_VERIFIED")
    staging = _truthy("DECISION_SERVICE_STAGING_CUTOVER_APPROVED")
    production = _truthy("DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED")

    gates = {
        "DATABASE_URL": db,
        "DECISION_SERVICE_MIGRATIONS_VERIFIED": migrations,
        "DECISION_SERVICE_BACKFILL_VERIFIED": backfill,
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED": tenant,
        "DECISION_SERVICE_OUTBOX_VERIFIED": outbox,
        "DECISION_SERVICE_STAGING_CUTOVER_APPROVED": staging,
    }
    missing = tuple(name for name, ok in gates.items() if not ok)
    can_enable = requested and not missing
    can_demote = can_enable and production
    if can_demote:
        mode = "decision-service-sor-platform-orchestrator"
    elif can_enable:
        mode = "decision-service-sor-staging-shadow"
    elif requested:
        mode = "sor-requested-but-not-ready"
    else:
        mode = "platform-sor-mirror-only"
    return CutoverReadiness(
        requested_sor=requested,
        database_configured=db,
        migrations_verified=migrations,
        backfill_verified=backfill,
        tenant_isolation_verified=tenant,
        outbox_verified=outbox,
        staging_approved=staging,
        production_approved=production,
        can_enable_sor=can_enable,
        can_demote_platform=can_demote,
        mode=mode,
        required_tables=_REQUIRED_TABLES,
        missing_gates=missing,
    )
