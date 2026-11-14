"""Short-lived MFA enrollment proofs, never accepted as SAHOOL access tokens."""

from __future__ import annotations

import time
from uuid import uuid4

import jwt

AUDIENCE = "sahool-mfa-enrollment"
PURPOSE = "mfa-enrollment"
TTL_SECONDS = 300


def issue_enrollment_token(
    *, subject: str, stage: str, state: str, key: str, algorithm: str, secret_state: str = ""
) -> str:
    """Only the configured signing algorithm is used, never an untrusted header."""
    if algorithm not in {"HS256", "RS256"} or not key or stage not in {"setup", "activate"}:
        raise ValueError("Invalid enrollment token configuration")
    now = int(time.time())
    return jwt.encode(
        {
            "sub": subject,
            "iss": "sahool-auth",
            "aud": AUDIENCE,
            "purpose": PURPOSE,
            "stage": stage,
            "state": state,
            "secret_state": secret_state,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + TTL_SECONDS,
        },
        key,
        algorithm=algorithm,
        headers={"typ": "mfa-enrollment+jwt"},
    )


def verify_enrollment_token(token: str, *, key: str, algorithm: str, stage: str) -> dict:
    """Separate audience/purpose prevent a proof granting access to other services."""
    if algorithm not in {"HS256", "RS256"} or not key:
        raise jwt.InvalidTokenError("Enrollment verification is not configured")
    claims = jwt.decode(
        token,
        key,
        algorithms=[algorithm],
        audience=AUDIENCE,
        issuer="sahool-auth",
        options={
            "require": [
                "sub",
                "iss",
                "aud",
                "purpose",
                "stage",
                "state",
                "jti",
                "iat",
                "nbf",
                "exp",
            ]
        },
    )
    if (
        jwt.get_unverified_header(token).get("typ") != "mfa-enrollment+jwt"
        or claims["aud"] != AUDIENCE
        or claims["purpose"] != PURPOSE
        or claims["stage"] != stage
        or not isinstance(claims["sub"], str)
        or not claims["sub"].isdigit()
        or not isinstance(claims["state"], str)
        or not claims["state"]
        or not isinstance(claims.get("secret_state"), str)
        or not isinstance(claims["jti"], str)
        or not claims["jti"]
        or type(claims["exp"]) is not int
        or type(claims["iat"]) is not int
        or not 0 < claims["exp"] - claims["iat"] <= TTL_SECONDS
    ):
        raise jwt.InvalidTokenError("Invalid enrollment proof")
    return claims
