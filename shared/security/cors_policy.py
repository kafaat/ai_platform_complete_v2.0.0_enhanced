"""Central CORS origin sanitizer — one contract for every SAHOOL service.

Historical drift (deep-audit finding): services read ``CORS_ORIGINS`` with a raw
``os.getenv(...).split(",")`` that keeps surrounding whitespace and empty tokens, and
none of them reject the ``*`` wildcard while ``allow_credentials=True``. A wildcard
combined with credentials is a configuration footgun — the browser spec forbids it, and
a middleware that ever honored it would reflect arbitrary origins back with cookies.

This module is the single sanitizer so every service parses origins identically:

  * strips whitespace and drops empty tokens (``"a, ,b"`` -> ``["a", "b"]``);
  * with credentials on, drops any ``*`` / ``null`` wildcard token — never wildcard+credentials;
  * production with no configured origin -> ``[]`` (fail-closed, no silent dev fallback);
  * development with no configured origin -> conservative localhost defaults.

Pure logic, no FastAPI import — callable from any service or a unit test.
"""

from __future__ import annotations

import logging
import os

_LOG = logging.getLogger("sahool.cors")

# Tokens that must never survive alongside credentialed CORS.
_WILDCARD_TOKENS = frozenset({"*", "null"})

# Conservative dev-only defaults when no origin is configured and we are not in production.
_DEV_DEFAULTS: tuple[str, ...] = ("http://localhost:3000", "http://10.0.2.2:8000")


def _is_production(production: bool | None) -> bool:
    if production is not None:
        return production
    # Accept the several env spellings already used across services.
    for var in ("SAHOOL_ENV", "APP_ENV", "ENV", "ENVIRONMENT"):
        if os.getenv(var, "").strip().lower() == "production":
            return True
    return False


def parse_cors_origins(
    raw: str | None,
    *,
    allow_credentials: bool = True,
    production: bool | None = None,
    dev_defaults: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """Return the sanitized allow_origins list for a CORS middleware.

    ``raw`` is the unparsed env value (e.g. ``os.getenv("CORS_ORIGINS")``). ``production``
    forces the fail-closed branch when no origin is configured; when ``None`` it is derived
    from the environment. When ``allow_credentials`` is True, wildcard tokens are dropped and
    never returned (wildcard+credentials is rejected, not echoed).
    """
    tokens = [tok.strip() for tok in (raw or "").split(",")]
    origins = [tok for tok in tokens if tok]

    if allow_credentials:
        safe = [o for o in origins if o.lower() not in _WILDCARD_TOKENS]
        if len(safe) != len(origins):
            _LOG.warning(
                "CORS: dropped wildcard origin because allow_credentials=True "
                "(wildcard+credentials is rejected). Configure explicit origins."
            )
        origins = safe

    if origins:
        return origins

    # Nothing configured (or only a rejected wildcard): fail closed in production.
    if _is_production(production):
        return []
    return list(dev_defaults if dev_defaults is not None else _DEV_DEFAULTS)


def wildcard_with_credentials(raw: str | None, *, allow_credentials: bool) -> bool:
    """True iff the raw value would pair a ``*``/``null`` wildcard with credentials.

    Guard/test helper: lets CI assert no service ships that combination.
    """
    if not allow_credentials:
        return False
    tokens = {tok.strip().lower() for tok in (raw or "").split(",")}
    return bool(tokens & _WILDCARD_TOKENS)
