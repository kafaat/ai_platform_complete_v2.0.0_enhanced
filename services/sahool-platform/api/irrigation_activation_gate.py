"""Live consumer of the ``irr_f01_reservation`` activation gate — the platform-side restricted
adapter (open-ledger #1: enforce activation BEFORE a reservation is created).

This is the SINGLE way platform code is allowed to admit an IRR-F01 reservation. The reservation
coordinator (``irrigation_reservation_adapter.reserve_and_request_dispatch_db``) takes an injected
``activation_guard`` and awaits it before any lock or write; :func:`activation_guard` here is the
production wiring of that seam, and a static guard
(``test_irrigation_activation_gate_no_bypass_static.py``) forbids any other platform module from
reaching the reservation/admission primitives without routing through this adapter.

Contract (a REFUSAL — the gate owns the semantics; we translate its answer, never re-derive it):

    gate enabled     -> admit (return the snapshot)
    gate disabled    -> raise IrrigationActivationNotEnabled  (403 from the server)
    gate revoked     -> raise IrrigationActivationNotEnabled
    gate degraded    -> raise IrrigationActivationNotEnabled
    gate evaluating  -> raise IrrigationActivationNotEnabled
    gate unreachable -> raise IrrigationActivationNotEnabled  (fail-closed on 5xx/timeout/malformed)

The server-side ``POST /v1/activation/irr_f01_reservation/enforce`` runs the gate's
``enforce_enabled`` (a FRESH read, never cached), so TTL expiry / revoke take effect immediately —
we do NOT read ``/current`` and re-interpret ``effective_enabled`` (that would clone the gate
semantics in two places, the exact "parallel readiness" the gate exists to prevent).

Default-off: with ``IRR_F01_RESERVATION_ENFORCE_ACTIVATION`` unset the guard is a no-op and the
reservation flow is unchanged (transitional, same flag the decision-service inbox uses). The
production-profile startup gate makes the flag mandatory in production.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger("platform.irrigation_activation_gate")

GATE_ENFORCE_PATH = "/v1/activation/irr_f01_reservation/enforce"


class IrrigationActivationNotEnabled(Exception):
    """Raised when the irr_f01_reservation gate is not effectively enabled (or unreachable). The
    reservation coordinator lets it propagate; the HTTP caller maps it to a 403."""

    def __init__(self, environment_id: str, reason: str) -> None:
        super().__init__(f"irr_f01_reservation not activated for {environment_id}: {reason}")
        self.environment_id = environment_id
        self.reason = reason


def enforcement_enabled() -> bool:
    """Read the enforcement flag fresh — an operator flip takes effect without a restart."""
    return os.getenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def environment_id() -> str:
    """The activation environment this platform instance belongs to (mirrors the gate side)."""
    return (os.getenv("ACTIVATION_ENVIRONMENT_ID") or os.getenv("SAHOOL_ENV") or "default").strip()


def _decision_url() -> str:
    base = os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160").rstrip("/")
    return f"{base}{GATE_ENFORCE_PATH}"


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("ACTIVATION_GATE_TIMEOUT_SECONDS", "5"))
    except ValueError:
        return 5.0


async def enforce_or_raise(
    *, env: str | None = None, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Refuse the reservation unless the gate is effectively enabled RIGHT NOW.

    Reads the flag fresh; when enforcement is off this is a no-op (returns a not-enforced marker).
    Otherwise it calls the server enforce endpoint and FAILS CLOSED on anything that is not an
    explicit 200 — a 403 (not enabled), a non-200 (mirror 503 / SoR off), or any transport error all
    raise :class:`IrrigationActivationNotEnabled`. Reservation is a resource-protection layer;
    letting it through on gate blindness would run a feature that is not activated.
    """
    e = (env or environment_id()).strip()
    if not enforcement_enabled():
        return {"enforced": False, "environment_id": e, "reason": "enforcement_disabled"}

    headers = {}
    token = os.getenv("DECISION_SERVICE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def _call(c: httpx.AsyncClient) -> dict[str, Any]:
        resp = await c.post(_decision_url(), headers=headers, timeout=_timeout_seconds())
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 403:
            reason = "not_enabled"
            try:
                reason = str(resp.json().get("detail", reason))
            except Exception:  # noqa: BLE001 — a malformed 403 body is still a refusal
                pass
            raise IrrigationActivationNotEnabled(e, reason)
        # 503 in mirror mode / SoR off, or any other non-200 — fail closed.
        raise IrrigationActivationNotEnabled(e, f"gate_unreachable:http_{resp.status_code}")

    try:
        if client is not None:
            return await _call(client)
        async with httpx.AsyncClient() as c:
            return await _call(c)
    except IrrigationActivationNotEnabled:
        raise
    except Exception as exc:  # noqa: BLE001 — any transport failure fails closed
        logger.warning("irr_f01_reservation gate unreachable for env=%s: %s", e, type(exc).__name__)
        raise IrrigationActivationNotEnabled(e, f"gate_unreachable:{type(exc).__name__}") from exc


def activation_guard(
    *, env: str | None = None, client: httpx.AsyncClient | None = None
) -> Callable[[], Awaitable[None]]:
    """Build the ``activation_guard`` thunk to inject into
    ``reserve_and_request_dispatch_db(activation_guard=...)``. Awaited before any lock/write; a
    disabled/revoked/unreachable gate raises and no reservation is created."""

    async def _guard() -> None:
        await enforce_or_raise(env=env, client=client)

    return _guard
