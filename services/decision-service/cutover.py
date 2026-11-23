"""Decision-service cutover safety contract.

This module intentionally does not perform schema changes or writes. It exposes a
small, deterministic readiness model used by CI and by the runtime `/v1/cutover/readiness`
endpoint so Sahool cannot promote decision-service to SoR merely by setting one flag.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
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


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
SOR_CAPABILITY_CONTRACT = "decision-sor-capability/v1"

# F-D01: what DECISION_SERVICE_OUTBOX_VERIFIED proves. The operator sets it after one persisted
# write left its ``pending`` row in ``decision_outbox_events`` (staging runbook step 4c). No relay
# reads that table or sets ``published_at``, so the gate never means the event was delivered.
OUTBOX_GATE_PROVES = "pending row recorded, not delivered"
OUTBOX_RELAY_IMPLEMENTED = False


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
    outbox_gate_proves: str
    outbox_relay_implemented: bool
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
      outbox, and staging approval are all verified. The outbox gate proves only that a
      pending row was recorded, not that it was delivered: there is no relay (F-D01).
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
        outbox_gate_proves=OUTBOX_GATE_PROVES,
        outbox_relay_implemented=OUTBOX_RELAY_IMPLEMENTED,
        staging_approved=staging,
        production_approved=production,
        can_enable_sor=can_enable,
        can_demote_platform=can_demote,
        mode=mode,
        required_tables=_REQUIRED_TABLES,
        missing_gates=missing,
    )


def code_migration_versions() -> list[str]:
    """Migration identifiers shipped with this image (file names only, sorted)."""
    return sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))


def _migration_level(db: Mapping[str, Any]) -> dict[str, Any]:
    code_versions = code_migration_versions()
    known = [str(v) for v in (db.get("known_migrations") or code_versions)]
    pending = {str(v) for v in (db.get("pending_migrations") or [])}
    reachable = db.get("db_reachable") is True
    applied = [v for v in known if v not in pending] if reachable else []
    return {
        "code_head": code_versions[-1] if code_versions else None,
        "known_count": len(known),
        "applied_head": applied[-1] if applied else None,
        "pending_count": len(pending) if reachable else None,
        "current": db.get("migrations_current"),
    }


def sor_capability_signal(
    db: Mapping[str, Any],
    *,
    sor_enabled: bool,
    ready: bool,
    readiness: CutoverReadiness | None = None,
) -> dict[str, Any]:
    """W2-01: the SoR capability block that ``/readyz`` exposes to the BFF and to operators.

    Booleans and identifiers only. It never carries a connection string, a token or an error
    text, so it is safe on an unauthenticated probe. ``mode`` is what the runtime actually does
    (``persisted`` once ``DECISION_SERVICE_SOR_ENABLED`` and ``DATABASE_URL`` are both set,
    else ``mirror``). ``review_available`` is the switch a client uses to show or hide the
    review queue: it is true only when writes persist *and* the service is ready (database
    reachable, every migration applied). The signal is conservative, not an exact mirror of
    the endpoint: ``/v1/decisions/review-queue`` answers 503 only in mirror mode (it checks
    ``sor_enabled()`` alone), so ``review_available: true`` implies the queue is served, while
    ``false`` with ``persisted: true`` means the service is not ready and the queue may still
    answer, or fail on the database. The cutover gates come from :func:`readiness_from_env`, the same
    model as ``/v1/cutover/readiness``, so the two endpoints cannot disagree.
    ``persisted_without_verified_gates`` makes an operator shortcut visible: the flag was set
    before the verification gates were recorded.
    """
    r = readiness if readiness is not None else readiness_from_env()
    persisted = bool(sor_enabled)
    gates = {
        "DATABASE_URL": r.database_configured,
        "DECISION_SERVICE_MIGRATIONS_VERIFIED": r.migrations_verified,
        "DECISION_SERVICE_BACKFILL_VERIFIED": r.backfill_verified,
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED": r.tenant_isolation_verified,
        "DECISION_SERVICE_OUTBOX_VERIFIED": r.outbox_verified,
        "DECISION_SERVICE_STAGING_CUTOVER_APPROVED": r.staging_approved,
    }
    return {
        "contract": SOR_CAPABILITY_CONTRACT,
        "mode": "persisted" if persisted else "mirror",
        "persisted": persisted,
        "review_available": persisted and bool(ready),
        "requested_sor": r.requested_sor,
        "cutover_mode": r.mode,
        "gates": gates,
        "gates_complete": not r.missing_gates,
        "missing_gates": list(r.missing_gates),
        "production_approved": r.production_approved,
        "can_enable_sor": r.can_enable_sor,
        "can_demote_platform": r.can_demote_platform,
        "persisted_without_verified_gates": persisted and bool(r.missing_gates),
        "outbox_gate_proves": r.outbox_gate_proves,
        "outbox_relay_implemented": r.outbox_relay_implemented,
        "migration_level": _migration_level(db),
    }
