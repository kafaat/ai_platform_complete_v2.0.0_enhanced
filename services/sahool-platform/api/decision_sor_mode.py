"""sahool-platform decision SoR mode contract.

The platform remains the authoritative writer by default. This module centralizes the
environment gates for the eventual demotion to orchestrator/BFF so individual routers do
not invent their own cutover behavior.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}
_ALLOWED_MODES = {"platform_sor", "shadow", "decision_service_sor"}

# The canonical decision system-of-record tables — kept in lockstep with
# decision-service `cutover._REQUIRED_TABLES`. Direct platform writes to these must
# stop once the platform is demoted (effective_mode == "decision_service_sor").
DECISION_SOR_TABLES = frozenset(
    {
        "decision_record",
        "dispatch_decisions",
        "outcome_record",
        "recommendation_outcomes",
        "online_learning_updates",
        "decision_outbox_events",
    }
)


class PlatformDecisionWriteForbidden(RuntimeError):
    """Raised when the platform attempts a direct decision-SoR write after demotion.

    Fail-closed: prevents a dual-write (platform + decision-service both authoritative)
    in ``decision_service_sor`` mode. Never raised in ``platform_sor``/``shadow`` — where
    ``platform_writes_required`` is True — so it is a strict no-op until an explicit,
    fully-gated cutover.
    """

    def __init__(self, table: str, effective_mode: str) -> None:
        self.table = table
        self.effective_mode = effective_mode
        super().__init__(
            f"platform direct write to decision-SoR table {table!r} is forbidden in "
            f"mode {effective_mode!r}; decision-service is the authoritative writer"
        )


def assert_platform_may_write_decision_sor(table: str) -> None:
    """Fail-closed guard placed before every platform write to a decision-SoR table.

    Consults :func:`get_platform_decision_sor_mode`. No-op while the platform is the
    authoritative writer (``platform_writes_required`` True — the default and shadow
    modes); raises :class:`PlatformDecisionWriteForbidden` once the platform has been
    demoted, closing the dual-write window at the application layer. (DB-level write
    revocation from the platform role is the complementary follow-up.)
    """
    mode = get_platform_decision_sor_mode()
    if not mode.platform_writes_required:
        raise PlatformDecisionWriteForbidden(table, mode.effective_mode)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


@dataclass(frozen=True)
class PlatformDecisionSorMode:
    requested_mode: str
    effective_mode: str
    platform_writes_required: bool
    mirror_required: bool
    strict_decision_service_required: bool
    demotion_allowed: bool
    missing_gates: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["missing_gates"] = list(self.missing_gates)
        return data


def crop_twin_direct_decision_enabled() -> bool:
    """Escape hatch for the crop-twin DIRECT decision side-doors (DECISION-CENTER-UNIFY-01).

    Default **False** = fail-closed / the correct posture: the crop-twin ``/decision``
    and ``/decision/profit-aware`` endpoints are preview/scenario only (they do NOT
    persist a platform-authoritative decision), and ``/decision-candidate`` refuses
    ``submit=true`` (a candidate built from client-supplied inputs must not be pushed to
    the decision center). Set ``CROP_TWIN_DIRECT_DECISION_ENABLED=true`` only to restore
    the legacy direct-write behavior.
    """
    return _truthy("CROP_TWIN_DIRECT_DECISION_ENABLED")


def get_platform_decision_sor_mode() -> PlatformDecisionSorMode:
    requested = os.getenv("SAHOOL_DECISION_WRITE_MODE", "platform_sor").strip().lower()
    if requested not in _ALLOWED_MODES:
        requested = "platform_sor"

    gates = {
        "DECISION_SERVICE_SOR_ENABLED": _truthy("DECISION_SERVICE_SOR_ENABLED"),
        "DECISION_SERVICE_MIGRATIONS_VERIFIED": _truthy("DECISION_SERVICE_MIGRATIONS_VERIFIED"),
        "DECISION_SERVICE_BACKFILL_VERIFIED": _truthy("DECISION_SERVICE_BACKFILL_VERIFIED"),
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED": _truthy(
            "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED"
        ),
        "DECISION_SERVICE_OUTBOX_VERIFIED": _truthy("DECISION_SERVICE_OUTBOX_VERIFIED"),
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED": _truthy(
            "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED"
        ),
    }
    missing = tuple(name for name, ok in gates.items() if not ok)
    demotion_allowed = requested == "decision_service_sor" and not missing

    if requested == "shadow":
        return PlatformDecisionSorMode(
            requested_mode=requested,
            effective_mode="shadow",
            platform_writes_required=True,
            mirror_required=True,
            strict_decision_service_required=False,
            demotion_allowed=False,
            missing_gates=(),
        )
    if demotion_allowed:
        return PlatformDecisionSorMode(
            requested_mode=requested,
            effective_mode="decision_service_sor",
            platform_writes_required=False,
            mirror_required=False,
            strict_decision_service_required=True,
            demotion_allowed=True,
            missing_gates=(),
        )
    return PlatformDecisionSorMode(
        requested_mode=requested,
        effective_mode="platform_sor",
        platform_writes_required=True,
        mirror_required=True,
        strict_decision_service_required=False,
        demotion_allowed=False,
        missing_gates=missing if requested == "decision_service_sor" else (),
    )
