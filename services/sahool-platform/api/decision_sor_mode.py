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
