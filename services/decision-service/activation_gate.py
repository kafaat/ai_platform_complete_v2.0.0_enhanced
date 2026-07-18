"""IRR-F01 — the irr_f01_reservation ACTIVATION GATE (thin wrapper over the shared core).

A five-state gate (disabled → evaluating → enabled|degraded, plus revoked) governing whether the
irr_f01_reservation capability is ENABLED for an environment. It CONSUMES provenance-bearing
evidence (CI live certification + the decision-service consumer heartbeat) — it never re-runs those
checks, so there is no parallel readiness source of truth.

Phase 3: the state machine / CAS / TTL / append-only evidence / server-derived build_sha / probe
envelope / generation-bound cache now live in ``activation_gate_core.ActivationGateCore`` (shared
with satellite_cdse after both gates proved the machinery). This module keeps ONLY what is specific
to irr_f01_reservation: its identity/evidence config and its enforcement meaning — a REFUSAL
(``enforce_enabled`` raises ``ActivationNotEnabled``). The public function names are unchanged.
"""

from __future__ import annotations

from typing import Any

from activation_gate_core import (
    DEFAULT_STALE_EVALUATION_SECONDS,
    ActivationGateCore,
    ActivationProbeDenied,
    GateConfig,
)
from activation_gate_core import deploy_build_sha as deploy_build_sha

GATE_NAME = "irr_f01_reservation"
# The provenance-bearing evidence this gate consumes (owned by the producers named below).
REQUIRED_CHECKS = frozenset({"ci_live_certification", "consumer_heartbeat"})
KNOWN_PRODUCERS = frozenset({"ci", "decision-service"})
PROBE_ROLE = "activation_probe"

_CORE = ActivationGateCore(
    GateConfig(
        gate_name=GATE_NAME,
        activation_table="irr_f01_reservation_activation",
        events_table="irr_f01_reservation_activation_events",
        required_checks=REQUIRED_CHECKS,
        known_producers=KNOWN_PRODUCERS,
        probe_role=PROBE_ROLE,
        build_sha_namespace="v028",
    )
)

# Public API — bound to the shared core (signatures unchanged from the pre-extraction module).
build_sha = _CORE.build_sha
begin_evaluation = _CORE.begin_evaluation
complete_evaluation = _CORE.complete_evaluation
revoke = _CORE.revoke
reset = _CORE.reset
recover_stale_evaluations = _CORE.recover_stale_evaluations
current = _CORE.current
current_cached = _CORE.current_cached
invalidate_cache = _CORE.invalidate_cache
probe_signature = _CORE.probe_signature
probe_state = _CORE.probe_state

# Re-exported names kept importable for callers/guards.
_evidence_admissible = _CORE._evidence_admissible

__all__ = [
    "ActivationNotEnabled",
    "ActivationProbeDenied",
    "DEFAULT_STALE_EVALUATION_SECONDS",
    "GATE_NAME",
    "KNOWN_PRODUCERS",
    "PROBE_ROLE",
    "REQUIRED_CHECKS",
    "begin_evaluation",
    "build_sha",
    "complete_evaluation",
    "current",
    "current_cached",
    "deploy_build_sha",
    "enforce_enabled",
    "invalidate_cache",
    "probe_signature",
    "probe_state",
    "recover_stale_evaluations",
    "reset",
    "revoke",
]


class ActivationNotEnabled(Exception):
    """Raised by the enforcement point when the gate is not effectively enabled."""

    def __init__(self, environment_id: str, state: str, reason: str) -> None:
        super().__init__(
            f"irr_f01_reservation not enabled for {environment_id}: {state} ({reason})"
        )
        self.environment_id = environment_id
        self.state = state
        self.reason = reason


async def enforce_enabled(environment_id: str) -> dict[str, Any]:
    """The single enforcement point (a REFUSAL — the irr_f01-specific meaning). Raises
    ActivationNotEnabled unless the gate is EFFECTIVELY enabled (state=='enabled' and TTL not
    expired). No internal path may bypass this. Reads fresh — never the cache — so an expired TTL or
    a revoke takes effect immediately."""
    snapshot = await _CORE.current(environment_id)
    if not snapshot["effective_enabled"]:
        reason = "ttl_expired" if snapshot.get("expired") else snapshot["state"]
        raise ActivationNotEnabled(environment_id, snapshot["state"], reason)
    return snapshot
