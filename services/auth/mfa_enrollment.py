"""Password-proven MFA enrollment capabilities, restricted to setup/activate only.

Why a sibling module and not ``routers/``: ``routers/`` holds ``APIRouter`` slices only
(``services/auth/tests/test_router_decomposition_guard.py::test_no_orphan_router_module``).
Like ``mfa_runtime``, ``main`` is resolved lazily on each call, so a test that reloads the
auth service never leaves this cached module pointing at a stale ``main``.

Contract (wire-stable): login returns 403 + ``enrollment_token`` (stage ``setup``);
``/v1/auth/mfa/setup`` accepts it as ``Authorization: Bearer`` and returns an
``enrollment_token`` of stage ``activate``; ``/v1/auth/mfa/activate`` accepts that one.

Binding — security columns only, never ``updated_at``:
the BEFORE UPDATE trigger ``trg_users_updated_at`` (migrations/v9_foundation.sql:53) bumps
``updated_at`` on *every* users UPDATE, including the anti-replay TOTP step and the MFA
failure counter that run inside the activation itself. Binding to it made every real-Postgres
activation return 409, and any wrong code invalidate the proof.

Single use: the proof digest lives in Redis; it is read non-destructively while the request is
validated and consumed with GETDEL only after the TOTP is verified, so a wrong code does not
burn it — but at most ``MAX_ACTIVATION_ATTEMPTS`` wrong codes are accepted per proof.
Redis failure is fail-closed (503).

Scope (``MFA_SELF_ENROLLMENT_SCOPE``): ``bootstrap`` (default) offers password-only enrollment
only to an account that never enrolled, in a tenant without an enrolled MFA-required account;
``all`` offers it to every unenrolled MFA-required account; ``off`` never. Unknown ⇒ bootstrap.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from session_tokens import consume_once

from shared.security.mfa_enrollment_tokens import (
    TTL_SECONDS,
    issue_enrollment_token,
    verify_enrollment_token,
)

logger = logging.getLogger("auth")

MAX_ACTIVATION_ATTEMPTS = 5
SCOPES = ("bootstrap", "all", "off")
_OFF_SPELLINGS = frozenset({"false", "0", "no", "none", "disabled", "disable"})
SCOPE_ENV = "MFA_SELF_ENROLLMENT_SCOPE"
# Columns whose change must invalidate a proof. ``mfa_enabled`` is refused outright and the
# encrypted secret is bound separately (``secret_state``) because setup itself writes it.
_STATE_COLUMNS = ("id", "password_hash", "role", "tenant_id", "active")

# One statement, current DB state: the account never enrolled (``mfa_enabled_at`` is stamped
# on activation and never cleared) and no *other* active account of the same tenant with an
# MFA-required role has MFA enabled. auth runs as app.current_role='admin', so RLS shows all.
_BOOTSTRAP_SQL = (
    "SELECT u.mfa_enabled_at IS NULL AS never_enrolled, EXISTS ("
    "SELECT 1 FROM users o WHERE o.id <> u.id AND o.active = TRUE AND o.mfa_enabled = TRUE "
    "AND o.tenant_id IS NOT DISTINCT FROM u.tenant_id "
    "AND lower(btrim(o.role)) = ANY($2::text[])) AS tenant_has_enrolled_admin "
    "FROM users u WHERE u.id = $1"
)

_warned_scopes: set[str] = set()


def _main():
    import main  # loaded service entrypoint; delayed to avoid bootstrap cycles

    return main


def _key(jti: str) -> str:
    return f"sahool:mfa:enrollment:{jti}"


def _state(row) -> str:
    material = {k: str(row[k]) for k in _STATE_COLUMNS}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def secret_state(encrypted: str | None) -> str:
    return hashlib.sha256((encrypted or "").encode()).hexdigest()


def self_enrollment_scope() -> str:
    """Read at call time; anything unknown fails closed to the narrow ``bootstrap`` scope."""
    value = (os.getenv("MFA_SELF_ENROLLMENT_SCOPE") or "bootstrap").strip().lower()
    if value in SCOPES:
        return value
    # An operator who writes a "disable" spelling means off; widening it to bootstrap would
    # keep password-only enrollment on against their intent. Never widen to "all" implicitly.
    if value in _OFF_SPELLINGS:
        return "off"
    if value not in _warned_scopes:
        _warned_scopes.add(value)
        logger.warning(
            "%s=%r is not one of %s; using 'bootstrap'", SCOPE_ENV, value, "|".join(SCOPES)
        )
    return "bootstrap"


async def offer_allowed(user_id: int) -> bool:
    """May this account enroll MFA with a password-proven capability (no access token)?"""
    scope = self_enrollment_scope()
    if scope == "off":
        return False
    if scope == "all":
        return True
    m = _main()
    async with m._acquire() as conn:
        state = await conn.fetchrow(_BOOTSTRAP_SQL, user_id, sorted(m.REQUIRE_MFA_ROLES))
    return bool(state) and bool(state["never_enrolled"]) and not state["tenant_has_enrolled_admin"]


async def _account(user_id: int):
    async with _main()._acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, password_hash, role, tenant_id, active, mfa_enabled, "
            "encrypted_mfa_secret FROM users WHERE id=$1",
            user_id,
        )


def _redis():
    client = _main()._redis
    if client is None:
        raise HTTPException(503, "MFA enrollment requires Redis")
    return client


async def issue(row, *, stage: str, encrypted: str | None = None) -> str:
    m = _main()
    client = _redis()
    token = issue_enrollment_token(
        subject=str(row["id"]),
        stage=stage,
        state=_state(row),
        key=m.JWT_SIGNING_KEY,
        algorithm=m.JWT_ALGORITHM,
        secret_state=secret_state(encrypted) if stage == "activate" else "",
    )
    claims = verify_enrollment_token(
        token, key=m.JWT_VERIFY_KEY, algorithm=m.JWT_ALGORITHM, stage=stage
    )
    try:
        await client.setex(
            _key(claims["jti"]), TTL_SECONDS, hashlib.sha256(token.encode()).hexdigest()
        )
    except Exception as exc:
        raise HTTPException(503, "MFA enrollment state unavailable") from exc
    return token


async def user_for(credentials: HTTPAuthorizationCredentials | None, stage: str) -> dict:
    """Ordinary access session, or a valid unconsumed enrollment proof of ``stage``."""
    if credentials is None:
        raise HTTPException(401, "No token")
    m = _main()
    # Ordinary sessions retain the existing optional-MFA flow. Enrollment proofs
    # fail the access-token audience check and cannot enter any other endpoint.
    try:
        return await m.get_current_user(credentials)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    try:
        claims = verify_enrollment_token(
            credentials.credentials,
            key=m.JWT_VERIFY_KEY,
            algorithm=m.JWT_ALGORITHM,
            stage=stage,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid MFA enrollment proof") from exc
    row = await _account(int(claims["sub"]))
    if (
        not row
        or not row["active"]
        or row["mfa_enabled"]
        or not hmac.compare_digest(claims["state"], _state(row))
    ):
        raise HTTPException(401, "MFA enrollment state changed; sign in again")
    if stage == "activate" and not hmac.compare_digest(
        claims.get("secret_state", ""), secret_state(row["encrypted_mfa_secret"])
    ):
        raise HTTPException(401, "MFA enrollment secret changed; sign in again")
    # The scope is re-read at every stage: another administrator finishing enrollment, or an
    # operator switching the scope off, closes proofs already in flight.
    if not await offer_allowed(row["id"]):
        raise HTTPException(
            401, "MFA self-enrollment is no longer available; ask an enrolled administrator"
        )
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    try:
        stored = await _redis().get(_key(claims["jti"]))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "MFA enrollment state unavailable") from exc
    if stored != digest:
        raise HTTPException(401, "MFA enrollment proof expired or consumed")
    return {
        "sub": claims["sub"],
        "_enrollment": claims,
        "_enrollment_digest": digest,
        "_enrollment_account": row,
    }


async def consume(user: dict) -> None:
    """GETDEL compare: of two parallel successful requests exactly one wins."""
    claims = user.get("_enrollment")
    if claims is None:
        return
    try:
        stored = await consume_once(_redis(), _key(claims["jti"]))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "MFA enrollment state unavailable") from exc
    if stored != user["_enrollment_digest"]:
        raise HTTPException(401, "MFA enrollment proof already consumed")


async def reserve_attempt(user: dict) -> int:
    """Reserve one activation attempt BEFORE the TOTP check (atomic INCR).

    Counting only after a failed check let parallel requests all reach the TOTP check before
    any of them was counted; reserving first bounds the number of checks per proof to
    ``MAX_ACTIVATION_ATTEMPTS`` whatever the concurrency. Over the cap the proof is deleted.
    Returns the attempt number (0 for an ordinary access session, which has no proof).
    """
    claims = user.get("_enrollment")
    if claims is None:
        return 0
    key = _key(claims["jti"])
    counter = key + ":attempts"
    try:
        client = _redis()
        attempts = int(await client.incr(counter))
        if attempts == 1:
            await client.expire(counter, TTL_SECONDS)
        if attempts > MAX_ACTIVATION_ATTEMPTS:
            await client.delete(key, counter)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "MFA enrollment state unavailable") from exc
    if attempts > MAX_ACTIVATION_ATTEMPTS:
        raise HTTPException(401, "MFA enrollment proof invalidated after too many attempts")
    return attempts


async def register_failed_attempt(user: dict, attempts: int) -> None:
    """A reserved attempt failed: invalidate the proof once the cap is reached."""
    claims = user.get("_enrollment")
    if claims is None or attempts < MAX_ACTIVATION_ATTEMPTS:
        return
    key = _key(claims["jti"])
    try:
        await _redis().delete(key, key + ":attempts")
    except Exception as exc:
        raise HTTPException(503, "MFA enrollment state unavailable") from exc


def guard_values(user: dict) -> tuple:
    """Parameters for the static guard ``(NOT $n::boolean OR (password_hash, role, tenant_id
    IS NOT DISTINCT FROM ...))`` — binds the final write to the proof's account snapshot.

    An ordinary access session carries no snapshot, so the guard is disabled (``False``).
    """
    row = user.get("_enrollment_account")
    if row is None:
        return (False, None, None, None)
    return (True, row["password_hash"], row["role"], row["tenant_id"])
