"""Access-token revocation for JWT consumers outside the platform (``S5``, audit 2026-11-01).

auth revokes a token two ways: ``sahool:jti:revoked:{jti}`` on logout, and the per-user floor
``sahool:user:token_floor:{sub}`` on a role change, password change/reset or deactivation
(``revoke_all_user_sessions``, ``services/auth/main.py``). The platform honours both
(``services/sahool-platform/core/jwt_denylist.py``, ``get_current_user``). guardrails-engine,
supervisor-agent and notification-agent decoded the token and nothing else, so an expert demoted
to farmer kept approving HIL actions with the old ``role`` claim until the token expired.

This module is the same rule for those consumers, with the platform's policy copied as is:

* same keys and same comparison (``int(iat) < int(floor)``) as auth and the platform;
* per check **fail-open** (the store raising does not lock everyone out, it is logged);
* store choice: ``DENYLIST_REDIS_URL``, else ``REDIS_URL`` (``denylist_redis_url``);
* at startup in production (``SAHOOL_ENV`` production/prod) a missing or unreachable store
  refuses to start (governance #408), elsewhere the check is off (``None``).

Read-only: these services never write a revocation (auth and the platform do).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, Protocol

logger = logging.getLogger("sahool.security.token_revocation")

# مفاتيح auth نفسها (services/auth/main.py) والمنصّة (core/jwt_denylist.py) — لا مخطّط موازٍ.
JTI_REVOKED_KEY = "sahool:jti:revoked:{jti}"
TOKEN_FLOOR_KEY = "sahool:user:token_floor:{sub}"


class RevocationStore(Protocol):
    def is_revoked(self, jti: str) -> bool: ...

    def token_floor(self, sub: str) -> int | None: ...


class RedisRevocationStore:
    """Read-only view of auth's revocation keys (EXISTS on the jti key, GET on the floor)."""

    def __init__(self, redis_client: Any):
        self._r = redis_client

    def is_revoked(self, jti: str) -> bool:
        return bool(self._r.exists(JTI_REVOKED_KEY.format(jti=jti)))

    def token_floor(self, sub: str) -> int | None:
        raw = self._r.get(TOKEN_FLOOR_KEY.format(sub=sub))
        return None if raw is None else int(raw)


def revocation_redis_url(env: Mapping[str, str] | None = None) -> str:
    """``DENYLIST_REDIS_URL`` if set and non-empty, else ``REDIS_URL`` (the platform's rule)."""
    env = os.environ if env is None else env
    return (env.get("DENYLIST_REDIS_URL") or "").strip() or env.get("REDIS_URL", "")


def _is_production(env: Mapping[str, str]) -> bool:
    return env.get("SAHOOL_ENV", "development").strip().lower() in {"production", "prod"}


def build_revocation_store(
    env: Mapping[str, str] | None = None,
    *,
    redis_from_url: Callable[..., Any] | None = None,
) -> RevocationStore | None:
    """The store, or ``None`` (check off) outside production when Redis is absent/unreachable.

    حوكمة #408 كالمنصّة: في الإنتاج غيابُ Redis أو تعذّره عند الإقلاع ⇒ رفض الإقلاع، لا قبولٌ
    صامت لتوكنات مُبطَلة.
    """
    env = os.environ if env is None else env
    url = revocation_redis_url(env)
    if url:
        try:
            if redis_from_url is None:
                import redis as _redis

                redis_from_url = _redis.from_url
            client = redis_from_url(url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            logger.info("token revocation: Redis enabled (auth's jti list and token floor)")
            return RedisRevocationStore(client)
        except Exception as e:  # noqa: BLE001 — Redis unavailable
            if _is_production(env):
                raise RuntimeError(
                    "Redis مطلوب في الإنتاج — إبطال التوكنات fail-closed عند الإقلاع"
                ) from e
            logger.warning("token revocation: Redis unavailable (%s) — check disabled", e)
            return None
    if _is_production(env):
        raise RuntimeError("Redis مطلوب في الإنتاج — إبطال التوكنات fail-closed عند الإقلاع")
    return None


def is_token_revoked(store: RevocationStore | None, jti: str | None) -> bool:
    """jti revoked on logout? No jti / no store ⇒ False; store error ⇒ False (fail-open)."""
    if not jti or store is None:
        return False
    try:
        return bool(store.is_revoked(jti))
    except Exception as e:  # noqa: BLE001 — fail-open, as the platform
        logger.warning("token revocation: jti check failed (allowed, fail-open): %s", e)
        return False


def is_token_below_floor(store: RevocationStore | None, payload: Mapping[str, Any]) -> bool:
    """Issued before auth's per-user floor? Same rule as auth: ``int(iat) < int(floor)``."""
    sub = payload.get("sub")
    iat = payload.get("iat")
    floor_of = getattr(store, "token_floor", None)
    if sub is None or iat is None or floor_of is None:
        return False
    try:
        floor = floor_of(str(sub))
        return floor is not None and int(iat) < int(floor)
    except Exception as e:  # noqa: BLE001 — fail-open, as the platform
        logger.warning("token revocation: floor check failed (allowed, fail-open): %s", e)
        return False


def token_is_revoked(store: RevocationStore | None, payload: Mapping[str, Any]) -> bool:
    """Either revocation applies (logout jti, or the revoke-all-sessions floor)."""
    return is_token_revoked(store, payload.get("jti")) or is_token_below_floor(store, payload)
