"""Who may decide or resume an advisor tool approval.

Before this module the three human-governance endpoints (approve / deny / resume) only
required *some* authenticated user of the tenant, so a viewer or a farmer could approve a
mutating tool call, the person who asked for the action could approve it themselves, and an
approved record could be resumed any number of times (one human approval, many handoffs).

- Role: ``X-User-Role`` is injected by the gateway from the verified JWT ``role`` claim
  (``frontend/nginx.conf`` and ``nginx/nginx.v9.conf`` both set it after ``auth_request``,
  overwriting any client value). The approver roles are the identity-service names that the
  platform maps to a role holding ``Permission.DECISION_APPROVE``
  (``services/sahool-platform/api/main.py`` role map + ``core/authorization.py``).
- Self-approval: the chat request that produced the approval is stamped server-side with the
  gateway user id (``requested_by``); that user cannot approve it. Service-token callers have
  no human requester, so their records carry ``requested_by=None``.
- Single use: ``resume`` moves the record approved -> resumed atomically in the store, so a
  second resume of the same approval loses the transition and gets 409.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Header, HTTPException

# Identity-service role names whose platform role holds DECISION_APPROVE:
# admin/owner -> OWNER, manager -> MANAGER, agronomist/expert -> AGRONOMIST.
# farmer/worker/viewer/platform_admin and anything unknown are refused (fail-closed).
APPROVER_ROLES = frozenset({"owner", "admin", "manager", "agronomist", "expert"})

STATUS_RESUMED = "resumed"


def require_approver_role(
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> str:
    role = (x_user_role or "").strip().lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="approver_role_required")
    return role


def refuse_self_approval(record: dict[str, Any], user_id: str) -> None:
    requester = str(record.get("requested_by") or "")
    if requester and requester == str(user_id):
        raise HTTPException(status_code=403, detail="self_approval_forbidden")


def stamp_requester(
    saver: Callable[[dict[str, Any]], None], user_id: str | None
) -> Callable[[dict[str, Any]], None]:
    """Wrap the approval saver so every record created in this request names its requester."""
    requester = (user_id or "").strip() or None

    def _save(request: dict[str, Any]) -> None:
        saver({**request, "requested_by": requester})

    return _save
