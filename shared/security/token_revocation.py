"""Fail-closed access-token revocation check for physical-effect consumers.

S5 / ACTUATOR-SERVICE-IGNORES-JWT-REVOCATION-01: auth revokes a token on logout by writing
``sahool:jti:revoked:{jti}``, and revokes every session of a user (password, role or account
change) by writing ``sahool:user:token_floor:{sub}``. The platform reads both
(``services/sahool-platform/core/jwt_denylist.py``) but fails *open*: an unreachable store lets
the request through, because locking every user out is worse for a read path.

A consumer that moves valves cannot take that trade. This module answers one question,
"may this token still act?", and raises :class:`RevocationUnavailable` whenever the answer is
not known, so the caller refuses the physical action instead of performing it. It does not
gate service startup: S5 was held back because consumers refusing to *start* without the
revocation store would take a whole service down. Here only the physical action is refused.

The key schema is auth's; ``tests_v9/test_actuator_token_revocation.py`` pins it equal to the
platform module so the two readers cannot drift apart.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

JTI_REVOKED_KEY = "sahool:jti:revoked:{jti}"
TOKEN_FLOOR_KEY = "sahool:user:token_floor:{sub}"


class RevocationUnavailable(RuntimeError):
    """The revocation state of a token could not be established."""


def revocation_redis_url(env: Mapping[str, str] | None = None) -> str:
    """``DENYLIST_REDIS_URL`` (auth's state server) if set, otherwise ``REDIS_URL``."""
    env = os.environ if env is None else env
    return (env.get("DENYLIST_REDIS_URL") or "").strip() or (env.get("REDIS_URL") or "").strip()


def build_revocation_client(env: Mapping[str, str] | None = None) -> Any:
    """A Redis client for auth's revocation keys, or ``None`` when no URL is configured.

    Compose points ``DENYLIST_REDIS_URL`` at auth's state server with a read-only ACL user
    (``docs/architecture/redis_acl_matrix.json``). Building the client opens no connection;
    the first ``EXISTS`` does, under the 2 s timeouts.
    """
    url = revocation_redis_url(env)
    if not url:
        return None
    import redis

    return redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def revocation_reason(client: Any, payload: Mapping[str, Any]) -> str | None:
    """``"revoked"`` / ``"below_token_floor"`` when the token may no longer act, else ``None``.

    Raises :class:`RevocationUnavailable` when there is no client, when the token carries no
    ``jti`` (it cannot be looked up, so it cannot be cleared), or when the store fails.
    """
    if client is None:
        raise RevocationUnavailable("no revocation store configured")
    jti = payload.get("jti")
    if not jti:
        raise RevocationUnavailable("token has no jti, so its revocation cannot be checked")
    try:
        if client.exists(JTI_REVOKED_KEY.format(jti=jti)):
            return "revoked"
        sub, iat = payload.get("sub"), payload.get("iat")
        if sub is not None and iat is not None:
            raw = client.get(TOKEN_FLOOR_KEY.format(sub=sub))
            if raw is not None and int(iat) < int(raw):
                return "below_token_floor"
    except Exception as exc:  # noqa: BLE001 - any store failure leaves the state unknown
        raise RevocationUnavailable(f"revocation store error: {type(exc).__name__}") from exc
    return None
