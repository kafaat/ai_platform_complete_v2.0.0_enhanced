"""Live consumer of the ``satellite_cdse`` activation gate (Phase 2 P2-c).

This is the SINGLE restricted adapter through which raster-service is allowed to decide that
CDSE is the active imagery source. Nothing else may select CDSE: scene search and index
processing consult :func:`resolve_active_source` first, and a static guard
(``test_imagery_source_gate_no_bypass_static.py``) forbids any other module from reaching the
raw CDSE selection primitives without routing through here.

Contract (mirrors the operator's ratified P2-c mapping — the decision-service ``/source`` endpoint
already collapses the gate state machine into a source selection, and this adapter treats every
non-``cdse`` answer, and every error, as the safe ``element84`` fallback):

    gate enabled    -> cdse
    gate degraded   -> element84   (CDSE not trusted; result semantics unchanged)
    gate disabled   -> element84
    gate revoked    -> element84   (a new CDSE selection is blocked immediately)
    gate evaluating -> element84   (fail-closed: never speculate CDSE mid-evaluation)
    gate unreachable-> element84   (fail-closed on 503/timeout/malformed — never silently CDSE)

Default-off: with ``RASTER_ACTIVATION_GATE_ENFORCE`` unset the module never contacts the gate and
callers keep their existing static ``HISTORICAL_SEARCH_PROVIDER`` behaviour unchanged. The gate
only governs provider selection once an operator turns enforcement on for the environment.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger("raster.imagery_source_gate")

PRIMARY_SOURCE = "cdse"
FALLBACK_SOURCE = "element84"
GATE_SOURCE_PATH = "/v1/activation/satellite_cdse/source"
_KNOWN_SOURCES = {PRIMARY_SOURCE, FALLBACK_SOURCE}


def enforce_enabled() -> bool:
    """Read the enforcement flag fresh — an operator flip must take effect without a restart."""
    return os.getenv("RASTER_ACTIVATION_GATE_ENFORCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def environment_id() -> str:
    """The activation environment this raster-service instance belongs to (mirrors the gate side)."""
    return (os.getenv("ACTIVATION_ENVIRONMENT_ID") or os.getenv("SAHOOL_ENV") or "default").strip()


def _decision_url() -> str:
    base = os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160").rstrip("/")
    return f"{base}{GATE_SOURCE_PATH}"


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("ACTIVATION_GATE_TIMEOUT_SECONDS", "5"))
    except ValueError:
        return 5.0


@dataclass(frozen=True)
class ImagerySourceDecision:
    """The provider raster-service is allowed to use, plus the provenance that decision was made
    under. ``generation`` binds a long-running job to the exact activation generation it started
    beneath so a mid-job revoke/expiry (which bumps the generation) is detectable."""

    provider: str
    gate_state: str
    generation: int | None
    build_sha: str | None
    fallback: bool
    reason: str | None
    environment_id: str
    decided_at: str
    enforced: bool
    degraded: bool  # True when the answer came from a fail-closed error path, not the live gate

    @property
    def use_cdse(self) -> bool:
        return self.provider == PRIMARY_SOURCE

    def evidence(self) -> dict[str, Any]:
        """Non-repudiable provenance a consumer attaches to its own output (proof #5)."""
        return {
            "gate": "satellite_cdse",
            "gate_generation": self.generation,
            "selected_provider": self.provider,
            "decision_timestamp": self.decided_at,
            "gate_state": self.gate_state,
            "environment_id": self.environment_id,
            "fallback": self.fallback,
            "reason": self.reason,
            "enforced": self.enforced,
            "degraded_decision": self.degraded,
        }


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).isoformat()


def _static_decision(env: str, now: datetime | None) -> ImagerySourceDecision:
    """Enforcement off: no override — the caller keeps its static provider selection."""
    return ImagerySourceDecision(
        provider=FALLBACK_SOURCE,
        gate_state="not_enforced",
        generation=None,
        build_sha=None,
        fallback=False,
        reason="enforcement_disabled",
        environment_id=env,
        decided_at=_now_iso(now),
        enforced=False,
        degraded=False,
    )


def _fail_closed(env: str, reason: str, now: datetime | None) -> ImagerySourceDecision:
    """Any error contacting the gate routes to the safe fallback — never speculatively CDSE."""
    logger.warning(
        "satellite_cdse gate unreachable for env=%s: %s — falling back to %s",
        env,
        reason,
        FALLBACK_SOURCE,
    )
    return ImagerySourceDecision(
        provider=FALLBACK_SOURCE,
        gate_state="unreachable",
        generation=None,
        build_sha=None,
        fallback=True,
        reason=f"gate_unreachable:{reason}",
        environment_id=env,
        decided_at=_now_iso(now),
        enforced=True,
        degraded=True,
    )


def decision_from_source_payload(
    payload: dict[str, Any], *, env: str, now: datetime | None = None
) -> ImagerySourceDecision:
    """Pure mapping of a ``/source`` response into a decision. The server already collapses the
    state machine into a source; we defensively treat any unknown source as the safe fallback so a
    contract drift can never upgrade the consumer to CDSE."""
    raw = str(payload.get("source", "")).strip().lower()
    provider = raw if raw in _KNOWN_SOURCES else FALLBACK_SOURCE
    unknown = raw not in _KNOWN_SOURCES
    return ImagerySourceDecision(
        provider=provider,
        gate_state=str(payload.get("gate_state", "unknown")),
        generation=payload.get("generation"),
        build_sha=payload.get("build_sha"),
        fallback=bool(payload.get("fallback", provider != PRIMARY_SOURCE)),
        reason=("unknown_source" if unknown else payload.get("reason")),
        environment_id=str(payload.get("environment_id", env)),
        decided_at=_now_iso(now),
        enforced=True,
        degraded=unknown,
    )


async def resolve_active_source(
    *, env: str | None = None, now: datetime | None = None, client: httpx.AsyncClient | None = None
) -> ImagerySourceDecision:
    """Resolve which imagery source is active for this environment RIGHT NOW.

    Reads the gate fresh on every call (the decision-service ``/source`` endpoint never caches), so
    a revoke or TTL expiry re-routes to the fallback immediately. Returns a non-enforced decision
    unchanged when enforcement is off; fails closed to the fallback on any transport/gate error.
    """
    e = (env or environment_id()).strip()
    if not enforce_enabled():
        return _static_decision(e, now)

    headers = {}
    token = os.getenv("DECISION_SERVICE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def _call(c: httpx.AsyncClient) -> ImagerySourceDecision:
        resp = await c.get(_decision_url(), headers=headers, timeout=_timeout_seconds())
        if resp.status_code != 200:
            # 503 in mirror mode / SoR off, or any non-200 — fail closed, never speculate CDSE.
            return _fail_closed(e, f"http_{resp.status_code}", now)
        return decision_from_source_payload(resp.json(), env=e, now=now)

    try:
        if client is not None:
            return await _call(client)
        async with httpx.AsyncClient() as c:
            return await _call(c)
    except Exception as exc:  # noqa: BLE001 — any transport failure is a fail-closed fallback
        return _fail_closed(e, type(exc).__name__, now)
