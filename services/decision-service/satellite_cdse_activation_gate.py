"""Phase 2 — the satellite_cdse ACTIVATION GATE (the SECOND, independent Category-A reference).

Governs whether CDSE is the ACTIVE imagery source for an environment, from provenance-bearing
evidence it CONSUMES (raster-service: CDSE credentials present + a successful live scene probe). It
never re-runs those checks (no parallel readiness source of truth).

This is a DELIBERATELY SEPARATE, DUPLICATED implementation from activation_gate.py
(irr_f01_reservation) — ACTIVATION-GATE-PROD-07 anti-premature-abstraction: only after TWO
independent Category-A gates exist do we extract the proven-shared machinery (Phase 3). The state
machine/CAS/TTL/evidence/stale/probe shape mirrors gate 1 on purpose, so a side-by-side comparison
reveals the true seams. The DIFFERENCES are the point:
  * evidence: cdse_credentials_present + cdse_live_probe (producer: raster-service), and
  * enforcement: NOT a refusal — ``active_imagery_source`` returns 'cdse' when enabled and safely
    falls back to 'element84' otherwise (Category A, no physical effect).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from persistence import database_url

GATE_NAME = "satellite_cdse"
REQUIRED_CHECKS = frozenset({"cdse_credentials_present", "cdse_live_probe"})
KNOWN_PRODUCERS = frozenset({"raster-service"})
PRIMARY_SOURCE = "cdse"
FALLBACK_SOURCE = "element84"
DEFAULT_STALE_EVALUATION_SECONDS = 900
PROBE_ROLE = "activation_probe"


class ActivationProbeDenied(Exception):
    """Raised when a probe_only read is attempted without the probe role + valid signature."""


def _now() -> datetime:
    return datetime.now(UTC)


async def _connect():
    import asyncpg  # type: ignore

    return await asyncpg.connect(database_url(), statement_cache_size=0)


def _rowcount(status: str) -> int:
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


def _evidence_admissible(item: dict[str, Any], environment_id: str, now: datetime) -> bool:
    valid_until = _parse_ts(item.get("valid_until"))
    return bool(
        item.get("producer") in KNOWN_PRODUCERS
        and item.get("check_name") in REQUIRED_CHECKS
        and str(item.get("environment_id")) == str(environment_id)
        and item.get("result") == "pass"
        and valid_until is not None
        and valid_until > now
    )


def deploy_build_sha() -> str:
    return os.getenv("DEPLOY_BUILD_SHA", "").strip()


def build_sha(evidence_items: list[dict[str, Any]]) -> str:
    canon = json.dumps(
        sorted(
            f"{e.get('producer')}|{e.get('check_name')}|{e.get('provenance')}|{e.get('valid_until')}"
            for e in evidence_items
        ),
        separators=(",", ":"),
    )
    return hashlib.sha256(f"{GATE_NAME}:v029:{deploy_build_sha()}:{canon}".encode()).hexdigest()


def _evidence_digest(evidence_items: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(evidence_items, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


CACHE_TTL_SECONDS = float(os.getenv("ACTIVATION_CACHE_TTL_SECONDS", "3") or 3)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_cache(environment_id: str) -> None:
    _CACHE.pop(environment_id, None)


async def _ensure_row(conn: Any, environment_id: str) -> None:
    await conn.execute(
        "INSERT INTO satellite_cdse_activation (environment_id) VALUES ($1) "
        "ON CONFLICT (environment_id) DO NOTHING",
        environment_id,
    )


async def _log(
    conn: Any,
    *,
    environment_id: str,
    from_state: str | None,
    to_state: str,
    generation: int,
    build_sha_value: str | None,
    evidence: list[dict[str, Any]] | None,
    actor: str,
    reason: str,
) -> None:
    await conn.execute(
        """INSERT INTO satellite_cdse_activation_events
             (environment_id, from_state, to_state, activation_generation, build_sha, evidence,
              actor, reason)
           VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8)
           ON CONFLICT (environment_id, activation_generation) DO NOTHING""",
        environment_id,
        from_state,
        to_state,
        generation,
        build_sha_value,
        json.dumps(evidence or []),
        actor,
        reason,
    )
    invalidate_cache(environment_id)


async def begin_evaluation(environment_id: str, *, actor: str) -> dict[str, Any]:
    conn = await _connect()
    try:
        async with conn.transaction():
            await _ensure_row(conn, environment_id)
            row = await conn.fetchrow(
                "SELECT state, activation_generation FROM satellite_cdse_activation "
                "WHERE environment_id=$1 FOR UPDATE",
                environment_id,
            )
            if row["state"] == "revoked":
                return {"status": "conflict", "reason": "revoked"}
            if row["state"] == "evaluating":
                return {"status": "conflict", "reason": "already_evaluating"}
            expected = row["activation_generation"]
            status = await conn.execute(
                "UPDATE satellite_cdse_activation "
                "SET state='evaluating', activation_generation=$2+1, evaluated_at=now(), "
                "    state_expires_at=NULL, last_reason='evaluation_started', updated_at=now() "
                "WHERE environment_id=$1 AND activation_generation=$2",
                environment_id,
                expected,
            )
            if _rowcount(status) != 1:
                return {"status": "conflict", "reason": "cas_conflict"}
            await _log(
                conn,
                environment_id=environment_id,
                from_state=row["state"],
                to_state="evaluating",
                generation=expected + 1,
                build_sha_value=None,
                evidence=None,
                actor=actor,
                reason="evaluation_started",
            )
            return {"status": "evaluating", "generation": expected + 1}
    finally:
        await conn.close()


async def complete_evaluation(
    environment_id: str,
    *,
    expected_generation: int,
    evidence: list[dict[str, Any]],
    actor: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    now = _now()
    admitted = {
        e.get("check_name") for e in evidence if _evidence_admissible(e, environment_id, now)
    }
    enabled = REQUIRED_CHECKS <= admitted
    to_state = "enabled" if enabled else "degraded"
    sha = build_sha(evidence) if enabled else None
    digest = _evidence_digest(evidence)
    expires = now + timedelta(seconds=max(1, int(ttl_seconds)))
    reason = (
        "evidence_complete" if enabled else f"missing_checks:{sorted(REQUIRED_CHECKS - admitted)}"
    )
    conn = await _connect()
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT state, activation_generation FROM satellite_cdse_activation "
                "WHERE environment_id=$1 FOR UPDATE",
                environment_id,
            )
            if row is None or row["state"] != "evaluating":
                return {"status": "conflict", "reason": "not_evaluating"}
            if row["activation_generation"] != expected_generation:
                return {"status": "conflict", "reason": "cas_conflict"}
            status = await conn.execute(
                "UPDATE satellite_cdse_activation "
                "SET state=$3, activation_generation=$2+1, build_sha=$4, evidence_digest=$5, "
                "    state_expires_at=$6, last_reason=$7, updated_at=now() "
                "WHERE environment_id=$1 AND activation_generation=$2",
                environment_id,
                expected_generation,
                to_state,
                sha,
                digest,
                expires,
                reason,
            )
            if _rowcount(status) != 1:
                return {"status": "conflict", "reason": "cas_conflict"}
            await _log(
                conn,
                environment_id=environment_id,
                from_state="evaluating",
                to_state=to_state,
                generation=expected_generation + 1,
                build_sha_value=sha,
                evidence=evidence,
                actor=actor,
                reason=reason,
            )
            return {
                "status": to_state,
                "generation": expected_generation + 1,
                "build_sha": sha,
                "state_expires_at": expires.isoformat(),
            }
    finally:
        await conn.close()


async def revoke(environment_id: str, *, actor: str, reason: str) -> dict[str, Any]:
    conn = await _connect()
    try:
        async with conn.transaction():
            await _ensure_row(conn, environment_id)
            row = await conn.fetchrow(
                "SELECT state, activation_generation FROM satellite_cdse_activation "
                "WHERE environment_id=$1 FOR UPDATE",
                environment_id,
            )
            if row["state"] == "revoked":
                return {
                    "status": "revoked",
                    "generation": row["activation_generation"],
                    "replay": True,
                }
            expected = row["activation_generation"]
            status = await conn.execute(
                "UPDATE satellite_cdse_activation "
                "SET state='revoked', activation_generation=$2+1, state_expires_at=NULL, "
                "    build_sha=NULL, last_reason=$3, updated_at=now() "
                "WHERE environment_id=$1 AND activation_generation=$2",
                environment_id,
                expected,
                reason,
            )
            if _rowcount(status) != 1:
                return {"status": "conflict", "reason": "cas_conflict"}
            await _log(
                conn,
                environment_id=environment_id,
                from_state=row["state"],
                to_state="revoked",
                generation=expected + 1,
                build_sha_value=None,
                evidence=None,
                actor=actor,
                reason=reason,
            )
            return {"status": "revoked", "generation": expected + 1}
    finally:
        await conn.close()


async def reset(environment_id: str, *, actor: str) -> dict[str, Any]:
    conn = await _connect()
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT state, activation_generation FROM satellite_cdse_activation "
                "WHERE environment_id=$1 FOR UPDATE",
                environment_id,
            )
            if row is None or row["state"] != "revoked":
                return {"status": "conflict", "reason": "not_revoked"}
            expected = row["activation_generation"]
            status = await conn.execute(
                "UPDATE satellite_cdse_activation "
                "SET state='disabled', activation_generation=$2+1, last_reason='reset', updated_at=now() "
                "WHERE environment_id=$1 AND activation_generation=$2",
                environment_id,
                expected,
            )
            if _rowcount(status) != 1:
                return {"status": "conflict", "reason": "cas_conflict"}
            await _log(
                conn,
                environment_id=environment_id,
                from_state="revoked",
                to_state="disabled",
                generation=expected + 1,
                build_sha_value=None,
                evidence=None,
                actor=actor,
                reason="reset",
            )
            return {"status": "disabled", "generation": expected + 1}
    finally:
        await conn.close()


async def recover_stale_evaluations(
    *, stale_seconds: int = DEFAULT_STALE_EVALUATION_SECONDS, actor: str = "stale-recovery"
) -> list[str]:
    conn = await _connect()
    recovered: list[str] = []
    try:
        async with conn.transaction():
            rows = await conn.fetch(
                "UPDATE satellite_cdse_activation "
                "SET state='disabled', activation_generation=activation_generation+1, "
                "    last_reason='stale_evaluation_recovered', updated_at=now() "
                "WHERE state='evaluating' AND evaluated_at < now() - ($1 || ' seconds')::interval "
                "RETURNING environment_id, activation_generation",
                str(int(stale_seconds)),
            )
            for r in rows:
                recovered.append(r["environment_id"])
                await _log(
                    conn,
                    environment_id=r["environment_id"],
                    from_state="evaluating",
                    to_state="disabled",
                    generation=r["activation_generation"],
                    build_sha_value=None,
                    evidence=None,
                    actor=actor,
                    reason="stale_evaluation_recovered",
                )
        return recovered
    finally:
        await conn.close()


def _effective(row: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    if row is None:
        return {"state": "disabled", "effective_enabled": False, "expired": False, "generation": 0}
    state = row["state"]
    expires = row["state_expires_at"]
    expired = state in ("enabled", "degraded") and expires is not None and expires <= now
    return {
        "state": state,
        "effective_enabled": state == "enabled" and not expired,
        "expired": expired,
        "generation": row["activation_generation"],
        "build_sha": row["build_sha"],
        "state_expires_at": expires.isoformat() if expires else None,
    }


async def current(environment_id: str) -> dict[str, Any]:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT state, activation_generation, build_sha, state_expires_at "
            "FROM satellite_cdse_activation WHERE environment_id=$1",
            environment_id,
        )
        return {"environment_id": environment_id, **_effective(dict(row) if row else None, _now())}
    finally:
        await conn.close()


async def current_cached(environment_id: str) -> dict[str, Any]:
    entry = _CACHE.get(environment_id)
    if entry is not None and (time.monotonic() - entry[0]) < CACHE_TTL_SECONDS:
        return {**entry[1], "cached": True}
    snapshot = await current(environment_id)
    _CACHE[environment_id] = (time.monotonic(), snapshot)
    return {**snapshot, "cached": False}


async def active_imagery_source(environment_id: str) -> dict[str, Any]:
    """Enforcement for satellite_cdse — a SOURCE SELECTION, not a refusal. Returns 'cdse' when the
    gate is effectively enabled, otherwise the safe 'element84' fallback. Reads fresh (never the
    cache) so an expired TTL or a revoke re-routes to the fallback immediately."""
    snapshot = await current(environment_id)
    if snapshot["effective_enabled"]:
        return {"source": PRIMARY_SOURCE, "gate_state": snapshot["state"], "fallback": False}
    return {
        "source": FALLBACK_SOURCE,
        "gate_state": snapshot["state"],
        "fallback": True,
        "reason": "ttl_expired" if snapshot.get("expired") else snapshot["state"],
    }


def _probe_secret() -> str:
    return os.getenv("ACTIVATION_PROBE_SIGNING_KEY", "").strip()


def probe_signature(environment_id: str, *, secret: str | None = None) -> str:
    key = (secret if secret is not None else _probe_secret()).encode()
    return hmac.new(key, f"{GATE_NAME}:{environment_id}".encode(), hashlib.sha256).hexdigest()


async def probe_state(
    environment_id: str, *, caller_role: str, signature: str, secret: str | None = None
) -> dict[str, Any]:
    if caller_role != PROBE_ROLE:
        raise ActivationProbeDenied("probe requires the activation_probe role")
    expected = probe_signature(environment_id, secret=secret)
    if not hmac.compare_digest(expected, signature or ""):
        raise ActivationProbeDenied("invalid probe signature")
    return await current(environment_id)
