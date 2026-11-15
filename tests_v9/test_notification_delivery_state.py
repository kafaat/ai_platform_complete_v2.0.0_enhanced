"""The one notification-delivery state machine (shared/notification_delivery_state.py).

Both writers of ``notification_delivery`` build their SQL guard from this module: the platform
receipt route and the notification agent. The live module
``test_notification_delivery_transitions_live_pg.py`` proves the SQL on PostgreSQL; this file
pins the rule itself and that both writers really use it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shared.notification_delivery_state import (
    ALLOWED,
    STATUSES,
    is_written,
    transition_guard_sql,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_the_rule_is_the_documented_table():
    assert STATUSES == ("queued", "sent", "failed", "delivered")
    assert {s: set(t) for s, t in ALLOWED.items()} == {
        "queued": {"sent", "failed", "delivered"},
        "sent": {"failed", "delivered"},
        "failed": {"sent", "delivered"},
        "delivered": set(),
    }


@pytest.mark.parametrize("current", STATUSES)
@pytest.mark.parametrize("wanted", STATUSES)
def test_nothing_returns_to_queued_and_nothing_leaves_delivered(current, wanted):
    written = is_written(current, wanted, "a", "b")
    if wanted == "queued" or current == "delivered":
        assert not written
    if current == wanted and current != "failed":
        assert not written, "a same-status write is a replay"


def test_failed_is_rewritten_only_for_a_new_reason():
    assert is_written("failed", "failed", "timeout", "offline")
    assert not is_written("failed", "failed", "timeout", "timeout")
    assert is_written("failed", "failed", None, "timeout")


def test_the_sql_guard_has_one_clause_per_live_status_and_none_for_delivered():
    sql = transition_guard_sql("cur.status", "new.status", "cur.error", "new.error")
    assert "cur.status = 'delivered'" not in sql
    for status, targets in ALLOWED.items():
        if targets:
            listed = ",".join(f"'{t}'" for t in STATUSES if t in targets)
            assert f"(cur.status = '{status}' AND new.status IN ({listed}))" in sql
    assert "cur.error IS DISTINCT FROM new.error" in sql


@pytest.mark.parametrize(
    "path",
    [
        "services/sahool-platform/api/routers/notifications.py",
        "agents/notification/agent.py",
    ],
)
def test_every_writer_of_the_table_builds_its_guard_from_the_shared_rule(path):
    """A writer that inlines its own WHERE would drift from the other one again."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "transition_guard_sql"
    ]
    assert calls, f"{path} writes notification_delivery without the shared transition guard"
    source = (ROOT / path).read_text(encoding="utf-8")
    assert "notification_delivery.status = 'queued'" not in source, (
        f"{path} spells out its own transition clause: a second copy of the rule can drift "
        "from shared/notification_delivery_state.py, the drift the #1468 lab follow-up closed"
    )
    if path.startswith("agents/"):
        # One outcome write in the agent, and it is the guarded constant.
        assert source.count("UPDATE notification_delivery") == 1
        assert "_DELIVERY_UPDATE_SQL = (" in source
