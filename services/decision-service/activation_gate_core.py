"""Phase 3 — the SHARED activation-gate core, extracted after two independent Category-A gates
(irr_f01_reservation + satellite_cdse) proved the machinery in production paths (ACTIVATION-GATE-
PROD-07: extract only what two real gates share, only after both exist and control runtime).

This core owns the machinery that was byte-identical between the two gates:
  * the five-state machine transitions (begin/complete/revoke/reset) with compare-and-swap on a
    monotonic ``activation_generation``,
  * stale-evaluating recovery,
  * TTL/freshness (``current`` reads fresh; enforcement never reads the cache),
  * append-only evidence logging,
  * the SERVER-DERIVED, non-spoofable ``build_sha`` (deploy fingerprint + admitted evidence),
  * the role+HMAC-signature probe envelope,
  * the generation-bound short-TTL read cache (invalidated on every recorded transition).

What stays PER-GATE (deliberately NOT extracted — these are the seams the duplication revealed):
  * the gate name, its ``REQUIRED_CHECKS`` and ``KNOWN_PRODUCERS``, its evidence semantics,
  * the enforcement meaning: a REFUSAL (irr_f01 ``enforce_enabled``) vs a SOURCE SELECTION
    (satellite_cdse ``active_imagery_source``),
  * the table names + the DB-level CAS/append-only triggers (per-migration).

A gate is a thin wrapper that instantiates ``ActivationGateCore(GateConfig(...))`` and adds only its
feature-specific enforcement. Table names come from the gate's own ``GateConfig`` (code constants,
never request input), so the interpolated SQL is safe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from persistence import database_url

STATES = frozenset({"disabled", "evaluating", "enabled", "degraded", "revoked"})
DEFAULT_STALE_EVALUATION_SECONDS = 900
# Generation-bound short-TTL read cache staleness bound for the read-heavy /current + /probe paths.
CACHE_TTL_SECONDS = float(os.getenv("ACTIVATION_CACHE_TTL_SECONDS", "3") or 3)
# Defense-in-depth bound on how long a single receipt can remain replayable. It complements — does
# not replace — the revocation kill switch: even absent an explicit revoke, a receipt's blast radius
# is capped. Enforced at three layers (ingest endpoint, this admissibility check, and a DB CHECK).
MAX_EVIDENCE_VALIDITY_SECONDS = 24 * 60 * 60
# Provenance is a canonical, whitespace-free identifier (not free text). This makes it a stable,
# non-spoofable component of the semantic UNIQUE key: a distinct canonical provenance is, by
# construction, a distinct producer observation — there is no implicit "latest receipt wins" lookup.
PROVENANCE_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,254}$")


class ActivationProbeDenied(Exception):
    """Raised when a probe_only read is attempted without the probe role + valid signature."""


@dataclass(frozen=True)
class GateConfig:
    """The per-gate identity + persistence binding. Table names are code constants (never request
    input); the build_sha namespace pins the migration a verdict was earned under."""

    gate_name: str
    activation_table: str
    events_table: str
    required_checks: frozenset[str]
    known_producers: frozenset[str]
    probe_role: str
    build_sha_namespace: str


def _now() -> datetime:
    return datetime.now(UTC)


def _rowcount(status: str) -> int:
    # asyncpg execute() returns e.g. "UPDATE 1"; take the trailing integer.
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


def deploy_build_sha() -> str:
    """The deployed build fingerprint, supplied server-side by the deploy/CI pipeline
    (``DEPLOY_BUILD_SHA``). Binding activation to it means an enabled verdict is tied to the exact
    build that earned it — a redeploy of a different build changes the fingerprint. Never a request
    input (non-spoofable)."""
    value = os.getenv("DEPLOY_BUILD_SHA", "").strip().lower()
    if not value or len(value) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeError(
            "DEPLOY_BUILD_SHA must be a non-empty 40- or 64-character hexadecimal build identity"
        )
    return value


def _canonical_ts(value: Any) -> str:
    """Timestamps are canonicalised to UTC ISO-8601 before signing, so a receipt verifies
    identically no matter the DB session timezone or the tz-offset the producer happened to send."""
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
        return aware.astimezone(UTC).isoformat()
    return str(value)


def _canonical_payload_field(value: Any) -> dict[str, Any]:
    """The receipt ``payload`` round-trips through jsonb (asyncpg hands it back as text). Normalise
    to a dict so the signed form is identical on the producer, ingest-verify, and resolve-verify
    sides — otherwise a dict signed at ingest would never re-verify against a string read back."""
    if isinstance(value, (str, bytes, bytearray)):
        text = value.decode() if isinstance(value, (bytes, bytearray)) else value
        return json.loads(text) if text else {}
    return value or {}


def canonical_evidence_signature(
    secret: str,
    *,
    gate_name: str,
    producer: str,
    check_name: str,
    environment_id: str,
    observed_at: Any,
    valid_until: Any,
    result: str,
    provenance: str,
    build_sha: str,
    payload: Any,
) -> str:
    """THE single source of truth for a receipt's HMAC. The producer signs with it, the ingest
    endpoint re-derives it to verify the caller, and the gate re-derives it again at resolve. Binding
    ``gate_name`` into the signature means a receipt minted for one gate cannot be replayed under
    another even if an attacker could otherwise satisfy the row lookup."""
    body = {
        "gate_name": gate_name,
        "producer": producer,
        "check_name": check_name,
        "environment_id": environment_id,
        "observed_at": _canonical_ts(observed_at),
        "valid_until": _canonical_ts(valid_until),
        "result": result,
        "provenance": provenance,
        "build_sha": build_sha,
        "payload": _canonical_payload_field(payload),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _probe_secret() -> str:
    return os.getenv("ACTIVATION_PROBE_SIGNING_KEY", "").strip()


class ActivationGateCore:
    """The shared five-state activation gate. One instance per gate; it owns its own read cache."""

    def __init__(self, config: GateConfig) -> None:
        self.cfg = config
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ---- connection ---------------------------------------------------------------------------
    async def _connect(self):
        # Use the service-owned pool when available; fall back to a direct connection only in
        # isolated tests/tools. The returned handle always exposes close(), preserving callers.
        try:
            from persistence import acquire_connection  # type: ignore
        except ImportError:
            acquire_connection = None
        if acquire_connection is not None:
            return await acquire_connection()
        import asyncpg  # type: ignore

        return await asyncpg.connect(database_url(), statement_cache_size=0)

    # ---- evidence + build_sha (server-resolved, producer-signed) ------------------------------
    def _evidence_admissible(
        self, item: dict[str, Any], environment_id: str, now: datetime
    ) -> bool:
        observed_at = _parse_ts(item.get("observed_at"))
        valid_until = _parse_ts(item.get("valid_until"))
        provenance = item.get("provenance")
        return bool(
            item.get("producer") in self.cfg.known_producers
            and item.get("check_name") in self.cfg.required_checks
            and item.get("environment_id") == environment_id
            and item.get("result") == "pass"
            and observed_at is not None
            and observed_at <= now
            and valid_until is not None
            and valid_until > now
            and isinstance(provenance, str)
            and bool(PROVENANCE_RE.fullmatch(provenance))
            and (valid_until - observed_at).total_seconds() <= MAX_EVIDENCE_VALIDITY_SECONDS
        )

    async def _resolve_evidence_refs(
        self, conn: Any, evidence_refs: list[str], environment_id: str
    ) -> list[dict[str, Any]]:
        if not evidence_refs:
            return []
        try:
            ids = [UUID(str(value)) for value in evidence_refs]
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid_evidence_reference") from exc
        # Revocation is enforced INSIDE this single fetch (NOT EXISTS against the append-only
        # revocations table) so admit/reject is decided atomically against one snapshot — no
        # second round-trip, no TOCTOU window between "is it revoked?" and "resolve it".
        rows = await conn.fetch(
            """SELECT r.evidence_id, r.producer, r.check_name, r.environment_id, r.observed_at,
                      r.valid_until, r.result, r.provenance, r.build_sha, r.payload, r.signature
                 FROM activation_evidence_receipts r
                WHERE r.evidence_id = ANY($1::uuid[]) AND r.gate_name=$2
                  AND NOT EXISTS (
                    SELECT 1 FROM activation_evidence_revocations v
                     WHERE v.evidence_id = r.evidence_id)""",
            ids,
            self.cfg.gate_name,
        )
        if len(rows) != len(set(ids)):
            # A referenced receipt is missing, belongs to another gate, or has been revoked.
            raise ValueError("evidence_reference_not_found")
        secret = os.getenv("ACTIVATION_EVIDENCE_SIGNING_KEY", "").strip()
        if not secret:
            raise RuntimeError("ACTIVATION_EVIDENCE_SIGNING_KEY is required")
        evidence: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            fields = {
                "gate_name": self.cfg.gate_name,
                "producer": item["producer"],
                "check_name": item["check_name"],
                "environment_id": item["environment_id"],
                "observed_at": item["observed_at"],
                "valid_until": item["valid_until"],
                "result": item["result"],
                "provenance": item["provenance"],
                "build_sha": item["build_sha"],
                "payload": item["payload"],
            }
            expected = canonical_evidence_signature(secret, **fields)
            if not hmac.compare_digest(expected, item["signature"]):
                raise ValueError("evidence_signature_invalid")
            # The admitted envelope carries canonical ISO timestamps + a dict payload so downstream
            # admissibility (and the digest) see exactly what was signed.
            evidence.append(
                {
                    "producer": item["producer"],
                    "check_name": item["check_name"],
                    "environment_id": item["environment_id"],
                    "observed_at": _canonical_ts(item["observed_at"]),
                    "valid_until": _canonical_ts(item["valid_until"]),
                    "result": item["result"],
                    "provenance": item["provenance"],
                    "build_sha": item["build_sha"],
                    "payload": _canonical_payload_field(item["payload"]),
                }
            )
        return evidence

    def deploy_build_sha(self) -> str:
        return deploy_build_sha()

    def build_sha(self, evidence_items: list[dict[str, Any]]) -> str:
        # The build identity is read from immutable deployment metadata, never supplied by a caller.
        deployed = deploy_build_sha()
        for item in evidence_items:
            if item.get("build_sha") != deployed:
                raise ValueError("evidence_build_sha_mismatch")
        canon = json.dumps(
            sorted(
                f"{e.get('producer')}|{e.get('check_name')}|{e.get('provenance')}|{e.get('valid_until')}"
                for e in evidence_items
            ),
            separators=(",", ":"),
        )
        namespaced = f"{self.cfg.gate_name}:{self.cfg.build_sha_namespace}:{deployed}:{canon}"
        return hashlib.sha256(namespaced.encode()).hexdigest()

    def _evidence_digest(self, evidence_items: list[dict[str, Any]]) -> str:
        return hashlib.sha256(
            json.dumps(evidence_items, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    # ---- cache --------------------------------------------------------------------------------
    def invalidate_cache(self, environment_id: str) -> None:
        self._cache.pop(environment_id, None)

    # ---- row + append-only log ----------------------------------------------------------------
    async def _ensure_row(self, conn: Any, environment_id: str) -> None:
        await conn.execute(
            f"INSERT INTO {self.cfg.activation_table} (environment_id) VALUES ($1) "
            "ON CONFLICT (environment_id) DO NOTHING",
            environment_id,
        )

    async def _log(
        self,
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
            f"""INSERT INTO {self.cfg.events_table}
                 (environment_id, from_state, to_state, activation_generation, build_sha, evidence,
                  actor, reason)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8)
""",
            environment_id,
            from_state,
            to_state,
            generation,
            build_sha_value,
            json.dumps(evidence or []),
            actor,
            reason,
        )
        # Any recorded transition supersedes the read cache for this environment.
        self.invalidate_cache(environment_id)

    # ---- transitions (CAS on activation_generation) -------------------------------------------
    async def begin_evaluation(self, environment_id: str, *, actor: str) -> dict[str, Any]:
        """disabled|degraded|enabled → evaluating (CAS). Refuses when revoked or already evaluating."""
        conn = await self._connect()
        try:
            async with conn.transaction():
                await self._ensure_row(conn, environment_id)
                row = await conn.fetchrow(
                    f"SELECT state, activation_generation FROM {self.cfg.activation_table} "
                    "WHERE environment_id=$1 FOR UPDATE",
                    environment_id,
                )
                if row["state"] == "revoked":
                    return {"status": "conflict", "reason": "revoked"}
                if row["state"] == "evaluating":
                    return {"status": "conflict", "reason": "already_evaluating"}
                expected = row["activation_generation"]
                status = await conn.execute(
                    f"UPDATE {self.cfg.activation_table} "
                    "SET state='evaluating', activation_generation=$2+1, evaluated_at=now(), "
                    "    state_expires_at=NULL, last_reason='evaluation_started', updated_at=now() "
                    "WHERE environment_id=$1 AND activation_generation=$2",
                    environment_id,
                    expected,
                )
                if _rowcount(status) != 1:
                    return {"status": "conflict", "reason": "cas_conflict"}
                await self._log(
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
        self,
        environment_id: str,
        *,
        expected_generation: int,
        evidence_refs: list[str],
        actor: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        """evaluating → enabled|degraded (CAS on the generation begin_evaluation returned). All
        required checks present + admissible ⇒ enabled with a server-derived build_sha; else degraded."""
        now = _now()
        conn = await self._connect()
        try:
            evidence = await self._resolve_evidence_refs(conn, evidence_refs, environment_id)
        except Exception:
            await conn.close()
            raise
        admitted = {
            e.get("check_name")
            for e in evidence
            if self._evidence_admissible(e, environment_id, now)
        }
        enabled = self.cfg.required_checks <= admitted
        to_state = "enabled" if enabled else "degraded"
        sha = self.build_sha(evidence) if enabled else None
        digest = self._evidence_digest(evidence)
        expires = now + timedelta(seconds=max(1, int(ttl_seconds)))
        reason = (
            "evidence_complete"
            if enabled
            else f"missing_checks:{sorted(self.cfg.required_checks - admitted)}"
        )
        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"SELECT state, activation_generation FROM {self.cfg.activation_table} "
                    "WHERE environment_id=$1 FOR UPDATE",
                    environment_id,
                )
                if row is None or row["state"] != "evaluating":
                    return {"status": "conflict", "reason": "not_evaluating"}
                if row["activation_generation"] != expected_generation:
                    return {"status": "conflict", "reason": "cas_conflict"}
                status = await conn.execute(
                    f"UPDATE {self.cfg.activation_table} "
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
                await self._log(
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

    async def revoke(self, environment_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        """Any non-revoked state → revoked (monotonic). Idempotent if already revoked."""
        conn = await self._connect()
        try:
            async with conn.transaction():
                await self._ensure_row(conn, environment_id)
                row = await conn.fetchrow(
                    f"SELECT state, activation_generation FROM {self.cfg.activation_table} "
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
                    f"UPDATE {self.cfg.activation_table} "
                    "SET state='revoked', activation_generation=$2+1, state_expires_at=NULL, "
                    "    build_sha=NULL, last_reason=$3, updated_at=now() "
                    "WHERE environment_id=$1 AND activation_generation=$2",
                    environment_id,
                    expected,
                    reason,
                )
                if _rowcount(status) != 1:
                    return {"status": "conflict", "reason": "cas_conflict"}
                await self._log(
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

    async def reset(self, environment_id: str, *, actor: str) -> dict[str, Any]:
        """revoked → disabled — the only way to re-open an evaluation cycle after a revoke."""
        conn = await self._connect()
        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"SELECT state, activation_generation FROM {self.cfg.activation_table} "
                    "WHERE environment_id=$1 FOR UPDATE",
                    environment_id,
                )
                if row is None or row["state"] != "revoked":
                    return {"status": "conflict", "reason": "not_revoked"}
                expected = row["activation_generation"]
                status = await conn.execute(
                    f"UPDATE {self.cfg.activation_table} "
                    "SET state='disabled', activation_generation=$2+1, last_reason='reset', updated_at=now() "
                    "WHERE environment_id=$1 AND activation_generation=$2",
                    environment_id,
                    expected,
                )
                if _rowcount(status) != 1:
                    return {"status": "conflict", "reason": "cas_conflict"}
                await self._log(
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
        self,
        *,
        stale_seconds: int = DEFAULT_STALE_EVALUATION_SECONDS,
        actor: str = "stale-recovery",
    ) -> list[str]:
        """Reclaim environments stuck in 'evaluating' past the staleness horizon back to 'disabled'
        (a crashed evaluation). Returns the recovered environment ids."""
        conn = await self._connect()
        recovered: list[str] = []
        try:
            async with conn.transaction():
                rows = await conn.fetch(
                    f"UPDATE {self.cfg.activation_table} "
                    "SET state='disabled', activation_generation=activation_generation+1, "
                    "    last_reason='stale_evaluation_recovered', updated_at=now() "
                    "WHERE state='evaluating' AND evaluated_at < now() - ($1 || ' seconds')::interval "
                    "RETURNING environment_id, activation_generation",
                    str(int(stale_seconds)),
                )
                for r in rows:
                    recovered.append(r["environment_id"])
                    await self._log(
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

    # ---- reads (fresh) + generation-bound cache -----------------------------------------------
    def _effective(self, row: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
        if row is None:
            return {
                "state": "disabled",
                "effective_enabled": False,
                "expired": False,
                "generation": 0,
            }
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

    async def current(self, environment_id: str) -> dict[str, Any]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                "SELECT state, activation_generation, build_sha, state_expires_at "
                f"FROM {self.cfg.activation_table} WHERE environment_id=$1",
                environment_id,
            )
            return {
                "environment_id": environment_id,
                **self._effective(dict(row) if row else None, _now()),
            }
        finally:
            await conn.close()

    async def current_cached(self, environment_id: str) -> dict[str, Any]:
        entry = self._cache.get(environment_id)
        if entry is not None and (time.monotonic() - entry[0]) < CACHE_TTL_SECONDS:
            return {**entry[1], "cached": True}
        snapshot = await self.current(environment_id)
        self._cache[environment_id] = (time.monotonic(), snapshot)
        return {**snapshot, "cached": False}

    # ---- probe envelope (role + HMAC signature) -----------------------------------------------
    def probe_signature(self, environment_id: str, *, secret: str | None = None) -> str:
        secret_value = secret if secret is not None else _probe_secret()
        if not secret_value:
            raise ActivationProbeDenied("probe signing key unavailable")
        key = secret_value.encode()
        return hmac.new(
            key, f"{self.cfg.gate_name}:{environment_id}".encode(), hashlib.sha256
        ).hexdigest()

    async def probe_state(
        self, environment_id: str, *, caller_role: str, signature: str, secret: str | None = None
    ) -> dict[str, Any]:
        """Read-only probe, allowed ONLY with the probe role AND a valid HMAC signature — never from
        a normal request path. It performs no transition (probe != enforce)."""
        if caller_role != self.cfg.probe_role:
            raise ActivationProbeDenied(f"probe requires the {self.cfg.probe_role} role")
        expected = self.probe_signature(environment_id, secret=secret)
        if not hmac.compare_digest(expected, signature or ""):
            raise ActivationProbeDenied("invalid probe signature")
        return await self.current(environment_id)
