"""satellite_cdse — the CDSE-active-source ACTIVATION GATE (thin wrapper over the shared core).

Governs whether CDSE is the ACTIVE imagery source for an environment, from provenance-bearing
evidence it CONSUMES (raster-service: CDSE credentials present + a successful live scene probe). It
never re-runs those checks (no parallel readiness source of truth).

Phase 3: the state machine / CAS / TTL / append-only evidence / server-derived build_sha / probe
envelope / generation-bound cache now live in ``activation_gate_core.ActivationGateCore`` (shared
with irr_f01_reservation). This module keeps ONLY what is specific to satellite_cdse: its
identity/evidence config and its enforcement meaning — a SOURCE SELECTION, not a refusal:
``active_imagery_source`` returns 'cdse' when enabled and safely falls back to 'element84'
otherwise (Category A, no physical effect). The public function names are unchanged.
"""

from __future__ import annotations

from typing import Any

from activation_gate_core import (
    ActivationGateCore,
    ActivationProbeDenied,
    GateConfig,
)
from activation_gate_core import deploy_build_sha as deploy_build_sha

GATE_NAME = "satellite_cdse"
REQUIRED_CHECKS = frozenset({"cdse_credentials_present", "cdse_live_probe"})
KNOWN_PRODUCERS = frozenset({"raster-service"})
PRIMARY_SOURCE = "cdse"
FALLBACK_SOURCE = "element84"
PROBE_ROLE = "activation_probe"

_CORE = ActivationGateCore(
    GateConfig(
        gate_name=GATE_NAME,
        activation_table="satellite_cdse_activation",
        events_table="satellite_cdse_activation_events",
        required_checks=REQUIRED_CHECKS,
        known_producers=KNOWN_PRODUCERS,
        probe_role=PROBE_ROLE,
        build_sha_namespace="v029",
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

__all__ = [
    "ActivationProbeDenied",
    "FALLBACK_SOURCE",
    "GATE_NAME",
    "KNOWN_PRODUCERS",
    "PRIMARY_SOURCE",
    "PROBE_ROLE",
    "REQUIRED_CHECKS",
    "active_imagery_source",
    "begin_evaluation",
    "build_sha",
    "complete_evaluation",
    "current",
    "current_cached",
    "deploy_build_sha",
    "invalidate_cache",
    "probe_signature",
    "probe_state",
    "recover_stale_evaluations",
    "reset",
    "revoke",
]


async def active_imagery_source(environment_id: str) -> dict[str, Any]:
    """Enforcement for satellite_cdse — a SOURCE SELECTION, not a refusal. Returns 'cdse' when the
    gate is effectively enabled, otherwise the safe 'element84' fallback. Reads fresh (never the
    cache) so an expired TTL or a revoke re-routes to the fallback immediately.

    generation + build_sha travel with the decision so a live consumer can BIND a long-running job
    to the exact activation generation it started beneath (detecting a mid-job revoke/expiry as a
    generation change) and record non-repudiable provenance in its own evidence."""
    snapshot = await _CORE.current(environment_id)
    common = {
        "environment_id": environment_id,
        "gate_state": snapshot["state"],
        "generation": snapshot["generation"],
        "build_sha": snapshot.get("build_sha"),
    }
    if snapshot["effective_enabled"]:
        return {"source": PRIMARY_SOURCE, "fallback": False, **common}
    return {
        "source": FALLBACK_SOURCE,
        "fallback": True,
        "reason": "ttl_expired" if snapshot.get("expired") else snapshot["state"],
        **common,
    }
