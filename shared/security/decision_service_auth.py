"""Outbound credential contract for the decision-service HTTP boundary.

Compose maps the operator's DECISION_SERVICE_AUTH_TOKEN to DECISION_SERVICE_TOKEN
in callers. User JWTs and the general agent token are different credentials and
must never be substituted. Tenant and actor context is supplied only after the
calling API has applied its own authentication and authorization policy.
"""

from __future__ import annotations

import os


class DecisionServiceAuthUnavailable(RuntimeError):
    """A missing or malformed local service credential, never its secret value."""

    def __init__(self) -> None:
        super().__init__("decision_service_auth_unavailable")


def decision_service_auth_headers(*, required: bool = False) -> dict[str, str]:
    """Resolve fresh credentials; unauthenticated development mirrors remain supported."""
    token = os.getenv("DECISION_SERVICE_TOKEN", "").strip()
    required = (
        required
        or os.getenv("SAHOOL_ENV", "development").strip().lower() in {"production", "prod"}
        or os.getenv("DECISION_REQUIRE_AUTH_TOKEN", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if (required and not token) or any(c in token for c in "\r\n"):
        raise DecisionServiceAuthUnavailable()
    return {"Authorization": f"Bearer {token}"} if token else {}
