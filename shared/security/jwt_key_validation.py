"""Fail-closed validation for JWT PEM keys and placeholder configuration."""

from __future__ import annotations

import re

_PLACEHOLDERS = {
    "aasdasdasdasdasdad",
    "changeme",
    "change-me",
    "placeholder",
    "your-public-key",
    "-----begin public key-----...",
}


def _normalized(value: str | None) -> str:
    return (value or "").strip()


def looks_like_placeholder(value: str | None) -> bool:
    raw = _normalized(value)
    lowered = raw.lower()
    if not raw:
        return False
    if lowered in _PLACEHOLDERS:
        return True
    return any(
        token in lowered for token in ("placeholder", "replace_me", "replace-me", "example-only")
    )


def validate_rsa_public_key_pem(value: str | None) -> str:
    """Return normalized PEM or raise ValueError for invalid/placeholder/non-RSA keys."""
    raw = _normalized(value)
    if not raw:
        return ""
    if looks_like_placeholder(raw):
        raise ValueError("JWT_PUBLIC_KEY contains a placeholder value")
    if not re.search(r"-----BEGIN (RSA )?PUBLIC KEY-----", raw):
        raise ValueError("JWT_PUBLIC_KEY must be a PEM encoded public key")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

        key = serialization.load_pem_public_key(raw.encode("utf-8"))
    except Exception as exc:  # cryptography deliberately supplies the parser details internally
        raise ValueError("JWT_PUBLIC_KEY is not a valid PEM public key") from exc
    if not isinstance(key, RSAPublicKey):
        raise ValueError("JWT_PUBLIC_KEY must contain an RSA public key")
    if key.key_size < 2048:
        raise ValueError("JWT_PUBLIC_KEY RSA key size must be at least 2048 bits")
    return raw


def validate_rsa_private_key_pem(value: str | None) -> str:
    """Return normalized PEM or raise ValueError for invalid/placeholder/non-RSA keys."""
    raw = _normalized(value)
    if not raw:
        return ""
    if looks_like_placeholder(raw):
        raise ValueError("JWT_PRIVATE_KEY contains a placeholder value")
    if "-----BEGIN" not in raw or "PRIVATE KEY-----" not in raw:
        raise ValueError("JWT_PRIVATE_KEY must be a PEM encoded private key")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

        key = serialization.load_pem_private_key(raw.encode("utf-8"), password=None)
    except Exception as exc:
        raise ValueError("JWT_PRIVATE_KEY is not a valid PEM private key") from exc
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("JWT_PRIVATE_KEY must contain an RSA private key")
    if key.key_size < 2048:
        raise ValueError("JWT_PRIVATE_KEY RSA key size must be at least 2048 bits")
    return raw


def validate_rsa_key_pair(private_pem: str | None, public_pem: str | None) -> tuple[str, str]:
    """Validate a complete matching RSA pair; reject partial or mismatched configuration."""
    private_present = bool(_normalized(private_pem))
    public_present = bool(_normalized(public_pem))
    if private_present != public_present:
        raise ValueError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be configured together")
    private_raw = validate_rsa_private_key_pem(private_pem)
    public_raw = validate_rsa_public_key_pem(public_pem)
    if not private_raw:
        return "", ""
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(private_raw.encode("utf-8"), password=None)
    public_key = serialization.load_pem_public_key(public_raw.encode("utf-8"))
    if private_key.public_key().public_numbers() != public_key.public_numbers():
        raise ValueError("JWT private/public keys do not form a matching RSA pair")
    return private_raw, public_raw
