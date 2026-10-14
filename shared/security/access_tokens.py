"""Access-token verification for consumers of the existing auth service.

The configured key chooses one algorithm; an untrusted JWT header never chooses
the key or enables a fallback. Production follows auth's explicit migration flag.

**Single decode site** (``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01``). Service call sites
that used to call ``jwt.decode`` themselves go through :func:`decode_access_token`,
which keeps each caller's library (``backend=``), key and single pinned algorithm, so
the decode verdict is unchanged. On top of it the stricter claim policy
(``exp``/``sub``/``aud``/``iss`` present, issuer allow-listed) is evaluated in
**observe mode by default** (owner decision 2026-10-01, #1118): a token the stricter
policy would reject is counted per ``(site, reason)`` and logged without the token or
any claim value, and still accepted. ``SAHOOL_ACCESS_TOKEN_CLAIM_POLICY=enforce``
turns the same verdict into a rejection once the counter reads zero.

Fixed here regardless of mode: an empty verification key is rejected. python-jose
accepts a token HMAC-signed with an empty key when the verification key is empty, so
a service with ``JWT_SECRET`` unset (video-processor) accepted forged identities;
legitimate tokens were already rejected in that state, so no valid caller changes.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import Counter
from typing import Literal

from .jwt_key_validation import looks_like_placeholder, validate_rsa_public_key_pem

logger = logging.getLogger("sahool.security.access_tokens")

#: Audience issued by auth and the platform (``"aud": "sahool"``).
ACCESS_TOKEN_AUDIENCE = "sahool"
#: Internal issuers accepted by every consumer.
ALLOWED_ISSUERS = frozenset({"sahool-auth", "sahool-platform"})
#: Claims the stricter policy requires to be present (a token without ``exp`` never expires).
STRICT_REQUIRED_CLAIMS = ("exp", "sub", "aud", "iss")
#: The only algorithms a caller may pin; one per call, never taken from the token header.
PINNED_ALGORITHMS = frozenset({"RS256", "HS256"})
#: ``observe`` (default) counts would-be rejections; ``enforce`` rejects them.
CLAIM_POLICY_ENV = "SAHOOL_ACCESS_TOKEN_CLAIM_POLICY"

Backend = Literal["pyjwt", "jose"]

_lock = threading.Lock()
_would_reject: Counter[tuple[str, str]] = Counter()
_LOG_EVERY = 1000

try:  # optional: services without prometheus-client still get the in-process counter
    from prometheus_client import Counter as _PromCounter

    try:
        _PROM_WOULD_REJECT = _PromCounter(
            "sahool_access_token_claim_policy_would_reject_total",
            "Access tokens accepted today that the strict claim policy would reject",
            ["site", "reason"],
        )
    except ValueError:  # already registered (module imported under a second name)
        _PROM_WOULD_REJECT = None
except ImportError:  # pragma: no cover - depends on the image
    _PROM_WOULD_REJECT = None


def access_token_verification_key() -> tuple[str, str]:
    public_key = validate_rsa_public_key_pem(os.getenv("JWT_PUBLIC_KEY", ""))
    if public_key:
        return public_key, "RS256"
    production = os.getenv("SAHOOL_ENV", "development").strip().lower() in {"production", "prod"}
    migration = os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if production and not migration:
        raise ValueError("RS256 required in production")
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32 or looks_like_placeholder(secret):
        raise ValueError("Access-token verification is not configured")
    return secret, "HS256"


def claim_policy_mode() -> str:
    """``enforce`` only when explicitly set; anything else observes (no new rejection)."""
    raw = os.getenv(CLAIM_POLICY_ENV, "observe").strip().lower()
    return "enforce" if raw == "enforce" else "observe"


def strict_claim_violations(payload: dict) -> tuple[str, ...]:
    """Pure: reasons the stricter policy would reject an already signature-valid payload."""
    reasons = [f"missing_{claim}" for claim in STRICT_REQUIRED_CLAIMS if not payload.get(claim)]
    iss = payload.get("iss")
    if iss and iss not in ALLOWED_ISSUERS:
        reasons.append("issuer_not_allowed")
    return tuple(reasons)


def would_reject_counts() -> dict[str, dict[str, int]]:
    """Snapshot of the observe-mode counter: ``{site: {reason: count}}``."""
    out: dict[str, dict[str, int]] = {}
    with _lock:
        for (site, reason), n in _would_reject.items():
            out.setdefault(site, {})[reason] = n
    return out


def reset_would_reject_counts() -> None:
    with _lock:
        _would_reject.clear()


def _record(site: str, reasons: tuple[str, ...], mode: str) -> None:
    with _lock:
        counts = []
        for reason in reasons:
            _would_reject[(site, reason)] += 1
            counts.append(_would_reject[(site, reason)])
    if _PROM_WOULD_REJECT is not None:
        for reason in reasons:
            _PROM_WOULD_REJECT.labels(site=site, reason=reason).inc()
    if any(n == 1 or n % _LOG_EVERY == 0 for n in counts):
        # Never the token, never a claim value: site + reason codes only.
        logger.warning(
            "access-token claim policy would reject: site=%s reasons=%s mode=%s",
            site,
            ",".join(reasons),
            mode,
        )


def _backend(backend: str):
    if backend == "pyjwt":
        import jwt

        return jwt.decode, jwt.InvalidTokenError
    if backend == "jose":
        from jose import JWTError
        from jose import jwt as jose_jwt

        return jose_jwt.decode, JWTError
    raise ValueError(f"Unsupported JWT backend: {backend!r}")


def decode_access_token(
    token: str, key: str, *, algorithm: str, backend: Backend, site: str
) -> dict:
    """Verify signature + ``aud=sahool`` with the caller's library and one pinned algorithm.

    Errors are the backend's own invalid-token type (PyJWT ``InvalidTokenError`` /
    python-jose ``JWTError``), so each caller's existing handler keeps mapping them to 401.
    The caller still enforces its own issuer/identity checks; the stricter policy is
    observed here and enforced only under ``SAHOOL_ACCESS_TOKEN_CLAIM_POLICY=enforce``.
    """
    decode, invalid = _backend(backend)
    if algorithm not in PINNED_ALGORITHMS:
        raise invalid(f"Unsupported access-token algorithm: {algorithm!r}")
    if not isinstance(key, str) or not key.strip():
        raise invalid("Access-token verification key is empty")
    payload = decode(token, key, algorithms=[algorithm], audience=ACCESS_TOKEN_AUDIENCE)
    reasons = strict_claim_violations(payload)
    if reasons:
        mode = claim_policy_mode()
        _record(site, reasons, mode)
        if mode == "enforce":
            raise invalid("Access token rejected by claim policy: " + ",".join(reasons))
    return payload


def verify_access_token(token: str) -> dict:
    from jose import JWTError, jwt

    if not isinstance(token, str) or not token:
        raise ValueError("Missing access token")
    key, algorithm = access_token_verification_key()
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience="sahool",
            options={
                "require_exp": True,
                "require_sub": True,
                "require_aud": True,
                "require_iss": True,
            },
        )
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc
    if payload.get("iss") not in {"sahool-auth", "sahool-platform"}:
        raise ValueError("Invalid token issuer")
    if (
        not payload.get("sub")
        or not isinstance(payload.get("tenant_id"), str)
        or not payload["tenant_id"].strip()
    ):
        raise ValueError("Missing token identity")
    return payload
