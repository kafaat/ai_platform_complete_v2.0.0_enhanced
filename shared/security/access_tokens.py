"""Access-token verification for consumers of the existing auth service.

The configured key chooses one algorithm; an untrusted JWT header never chooses
the key or enables a fallback. Production follows auth's explicit migration flag.
"""

from __future__ import annotations

import os

from jose import JWTError, jwt

from .jwt_key_validation import looks_like_placeholder, validate_rsa_public_key_pem


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


def verify_access_token(token: str) -> dict:
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
