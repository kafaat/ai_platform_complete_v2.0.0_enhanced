"""The notification delivery state machine, in one place for every writer of the table.

``notification_delivery`` (v83) has two writers:

- the platform receipt route ``POST /api/v1/notifications/delivery``
  (``services/sahool-platform/api/routers/notifications.py``), an ``INSERT … ON CONFLICT …
  DO UPDATE … WHERE``;
- the notification agent's channel delivery (``agents/notification/agent.py``,
  ``_deliver_channel``), an ``UPDATE`` after the provider call.

Both build their guard from :func:`transition_guard_sql`, so PostgreSQL applies the same rule
to both under the row lock. A refused transition writes nothing, whatever the caller checked
in Python first (lab follow-up on #1468: the rule lived in one statement while a second writer
updated the table directly).

The rule:

=========  ===========================================  =============================
current    written                                      replay (no write)
=========  ===========================================  =============================
queued     sent, failed, delivered                      queued
sent       failed, delivered                            sent
failed     sent, delivered, failed with a new reason    failed with the same reason
delivered  (terminal)                                   delivered
=========  ===========================================  =============================

Anything else is refused: the route answers 409, the agent raises.
"""

from __future__ import annotations

STATUSES: tuple[str, ...] = ("queued", "sent", "failed", "delivered")

#: Status changes that are written. A same-status write is a replay, except ``failed`` with
#: a different reason, which is written so the latest failure reason is kept.
ALLOWED: dict[str, frozenset[str]] = {
    "queued": frozenset({"sent", "failed", "delivered"}),
    "sent": frozenset({"failed", "delivered"}),
    "failed": frozenset({"sent", "delivered"}),
    "delivered": frozenset(),
}


def is_written(
    current: str, wanted: str, current_error: str | None, wanted_error: str | None
) -> bool:
    """True when the guard lets ``current`` → ``wanted`` write (the Python mirror of the SQL)."""
    if wanted in ALLOWED[current]:
        return True
    return current == wanted == "failed" and current_error != wanted_error


def transition_guard_sql(current: str, wanted: str, current_error: str, wanted_error: str) -> str:
    """The SQL predicate that is true exactly when :func:`is_written` is.

    The arguments are SQL expressions: the stored status and error, and the requested ones
    (``EXCLUDED.status`` in an upsert, a bind parameter in an ``UPDATE``). Statuses with no
    outgoing transition (``delivered``) get no clause, so a terminal row matches nothing.
    """
    clauses = []
    for status in STATUSES:
        targets = ALLOWED[status]
        if not targets:
            continue
        listed = ",".join(f"'{t}'" for t in STATUSES if t in targets)
        clauses.append(f"({current} = '{status}' AND {wanted} IN ({listed}))")
    clauses.append(
        f"({current} = 'failed' AND {wanted} = 'failed' "
        f"AND {current_error} IS DISTINCT FROM {wanted_error})"
    )
    return "(" + "\n        OR ".join(clauses) + ")"
