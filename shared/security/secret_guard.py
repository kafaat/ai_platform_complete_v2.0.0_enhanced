"""Central weak/default-secret guard — one production check for every shared secret.

Deep-audit finding: ``video-processor`` already refuses to start in production with a
missing/known-development ZLMediaKit secret (a good pattern), but that logic lived only in
that one service, while other paths shipped a bare ``"dev-secret"`` default. This module
generalizes the ZLMediaKit pattern so any secret read can apply the same check.

Pure logic, no framework import — unit-testable and importable anywhere.
"""

from __future__ import annotations

import os

# Known development/placeholder secret values that must never be honored in production.
KNOWN_WEAK_SECRETS = frozenset(
    {
        "dev-secret",
        "changeme",
        "change-me",
        "secret",
        "password",
        "dev-secret-change-in-production",
        "sahool-zlm-dev-secret",
    }
)

_TRUE = frozenset({"1", "true", "yes", "on"})


def is_production(env: dict[str, str] | None = None) -> bool:
    e = os.environ if env is None else env
    for var in ("SAHOOL_ENV", "APP_ENV", "ENV", "ENVIRONMENT"):
        if e.get(var, "").strip().lower() == "production":
            return True
    return False


def weak_secret_error(
    name: str,
    value: str | None,
    *,
    known_weak: frozenset[str] | set[str] = KNOWN_WEAK_SECRETS,
    min_len: int = 16,
    production: bool = True,
) -> str | None:
    """Return a startup-error string if ``value`` is unsafe in production, else ``None``.

    Unsafe means: empty, a known development/placeholder value, or shorter than ``min_len``.
    Outside production the check is skipped (returns ``None``) so dev stays ergonomic.
    """
    if not production:
        return None
    v = (value or "").strip()
    if not v:
        return f"{name} is empty in production — refusing to start with an unauthenticated/weak secret."
    if v.lower() in {s.lower() for s in known_weak}:
        return f"{name} is a known development/default value in production — configure a strong secret."
    if len(v) < min_len:
        return f"{name} is too short (<{min_len} chars) in production — configure a strong secret."
    return None


def is_weak_secret(
    value: str | None, *, known_weak: frozenset[str] | set[str] = KNOWN_WEAK_SECRETS
) -> bool:
    """True iff ``value`` is empty or a known development/placeholder secret (env-agnostic)."""
    v = (value or "").strip()
    return not v or v.lower() in {s.lower() for s in known_weak}
