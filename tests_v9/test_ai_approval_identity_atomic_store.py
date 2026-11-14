"""Agent approvals: server identity, create-once, one atomic decision, and a compose ACL that
grants what the store really calls.

**Defects measured on main@2a7fcb3a4:**

1. The approval ``id`` was the model's tool call id (``call.id`` or ``req-{idx}``) and the store
   keyed and overwrote by it alone (``SET`` without ``NX``). Two chats that both produced
   ``req-0`` (any tenants) overwrote each other's pending approval, and a later save could put a
   decided record back to ``pending``.
2. Approve and deny each read, checked and saved. Concurrent approve and deny could both return
   200 (last write won). The in-memory store had the same race.
3. ``RedisAuditStore.append`` calls ``LTRIM``; the compose ACL user had no ``+ltrim``, so every
   audit append raised NOPERM and ``/v1/approvals/approve`` returned 500 after recording.
4. The agent store pointed at ``sahool-redis`` (``allkeys-lru``): an approval could be evicted.

The Redis tests use ``tests_v9/redis_txn_double.py`` (``fakeredis`` is not installed); it
implements WATCH/MULTI/EXEC, ``SET NX/XX/EX/KEEPTTL`` with Redis semantics. It is a double, not
a live server.
"""

from __future__ import annotations

import ast
import inspect
import re
import shlex
import threading
from pathlib import Path

import pytest
import yaml

from services.ai_agronomist import agent_stores as S
from services.ai_agronomist import approval as AP
from services.ai_agronomist import tool_loop as TL
from tests_v9.redis_txn_double import RedisTxnDouble

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
STORES_SRC = ROOT / "services" / "ai_agronomist" / "agent_stores.py"
COMPOSE = ROOT / "docker-compose.v9.yml"
_TS = "2026-11-13T00:00:00Z"
_MUTATING_CALL = {
    "id": "req-0",
    "tool": "request_imagery_backfill",
    "params": {"field_id": "field-1", "months": 12},
}
_CAPS = ["can_trigger_backfill"]


def _memory_store():
    return S.InMemoryApprovalStore()


def _redis_store():
    return S.RedisApprovalStore(RedisTxnDouble())


STORES = [pytest.param(_memory_store, id="memory"), pytest.param(_redis_store, id="redis")]


def _creator(store):
    """``store.create``. On a tree without it (main@2a7fcb3a4) the old ``save`` is used, so the
    identity and overwrite tests fail on the defect itself rather than on a missing method."""
    return getattr(store, "create", None) or store.save


def _run(store, tenant: str, call: dict | None = None, **kw):
    return TL.run_tool_calls(
        [dict(call or _MUTATING_CALL)],
        allowed_capabilities=_CAPS,
        fetcher=None,
        tenant_id=tenant,
        actor="ai_agronomist",
        timestamp=_TS,
        approval_saver=_creator(store),
        **kw,
    )


def _pending(tenant: str = "tenant-A", tool_call_id: str = "req-0") -> dict:
    # main@2a7fcb3a4 named the model's id ``request_id`` (and used it as the approval id);
    # accepting both keeps the fail-before run on the missing behaviour, not on a TypeError.
    params = inspect.signature(AP.build_approval_request).parameters
    id_kw = "tool_call_id" if "tool_call_id" in params else "request_id"
    return AP.build_approval_request(
        **{id_kw: tool_call_id},
        tool_name="request_imagery_backfill",
        params={"field_id": "field-1"},
        tenant_id=tenant,
        actor="ai_agronomist",
        risk="medium",
        capability="can_trigger_backfill",
        requested_at=_TS,
    )


# ── identity ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("make_store", STORES)
def test_two_tenants_with_the_same_tool_call_id_get_distinct_records(make_store):
    store = make_store()
    out_a = _run(store, "tenant-A")
    out_b = _run(store, "tenant-B")
    rec_a, rec_b = out_a["pending_approvals"][0], out_b["pending_approvals"][0]
    assert rec_a["id"] != rec_b["id"], "both chats got the model's id: one overwrites the other"
    assert store.get(rec_a["id"])["tenant_id"] == "tenant-A"
    assert store.get(rec_b["id"])["tenant_id"] == "tenant-B"
    assert {r["id"] for r in store.list_pending()} == {rec_a["id"], rec_b["id"]}


@pytest.mark.parametrize("make_store", STORES)
def test_tool_call_id_is_kept_separately_and_the_id_is_server_generated(make_store):
    store = make_store()
    out = _run(store, "tenant-A", {**_MUTATING_CALL, "id": "call_model_42"})
    rec = out["pending_approvals"][0]
    result = out["tool_calls"][0]
    assert rec["tool_call_id"] == "call_model_42"
    assert rec["id"] != "call_model_42" and rec["id"].startswith("apr_")
    # the tool result keeps the model's id (provider tool_use mapping) and names the approval
    assert result["tool_call_id"] == "call_model_42"
    assert result["approval_id"] == rec["id"]
    assert store.get(rec["id"])["tool_call_id"] == "call_model_42"


# ── create-once ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("make_store", STORES)
def test_a_second_create_with_an_existing_id_is_refused(make_store):
    store = make_store()
    first = dict(_MUTATING_CALL, id="apr_fixed", tenant_id="tenant-A", status="pending")
    _creator(store)(first)
    intruder = dict(first, tenant_id="tenant-B", params={"field_id": "other"})
    with pytest.raises(getattr(S, "ApprovalExistsError", Exception)):
        _creator(store)(intruder)
    assert store.get(first["id"]) == first


@pytest.mark.parametrize("make_store", STORES)
def test_a_decided_record_cannot_be_reopened_by_create_or_transition(make_store):
    store = make_store()
    rec = _pending()
    store.create(rec)
    approved = AP.approve(rec, approver="user-1", decided_at=_TS)
    assert store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, approved) is True
    with pytest.raises(S.ApprovalExistsError):
        store.create(rec)  # same id, status pending
    assert store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, rec) is False
    denied = AP.deny(rec, approver="user-2", decided_at=_TS)
    assert store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, denied) is False
    assert store.get(rec["id"])["status"] == AP.STATUS_APPROVED
    assert store.list_pending() == []


@pytest.mark.parametrize("make_store", STORES)
def test_transition_refuses_another_tenant_or_a_changed_input_hash(make_store):
    store = make_store()
    rec = _pending()
    store.create(rec)
    approved = AP.approve(rec, approver="user-1", decided_at=_TS)
    assert store.transition(rec["id"], "tenant-B", AP.STATUS_PENDING, approved) is False
    assert (
        store.transition(
            rec["id"], "tenant-A", AP.STATUS_PENDING, dict(approved, tenant_id="tenant-B")
        )
        is False
    )
    assert (
        store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, dict(approved, input_hash="x"))
        is False
    )
    assert store.transition("apr_missing", "tenant-A", AP.STATUS_PENDING, approved) is False
    assert store.get(rec["id"])["status"] == AP.STATUS_PENDING


# ── one decision wins ───────────────────────────────────────────────────────
def test_memory_concurrent_approve_and_deny_exactly_one_wins():
    for _ in range(50):
        store = S.InMemoryApprovalStore()
        rec = _pending()
        store.create(rec)
        barrier = threading.Barrier(2)
        won: dict[str, bool] = {}

        def decide(name, new, store=store, rec=rec, barrier=barrier, won=won):
            barrier.wait()
            won[name] = store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, new)

        threads = [
            threading.Thread(
                target=decide, args=("approved", AP.approve(rec, approver="u", decided_at=_TS))
            ),
            threading.Thread(
                target=decide, args=("denied", AP.deny(rec, approver="u", decided_at=_TS))
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(won.values()) == [False, True], won
        winner = next(k for k, v in won.items() if v)
        assert store.get(rec["id"])["status"] == winner


def test_redis_a_decision_landing_between_watch_and_exec_aborts_the_other():
    """Deny commits while approve sits between its WATCHed read and EXEC: approve loses."""
    server = RedisTxnDouble()
    store = S.RedisApprovalStore(server)
    rec = _pending()
    store.create(rec)
    denied = AP.deny(rec, approver="u2", decided_at=_TS)
    deny_won: list[bool] = []
    server.on_watched_get = lambda: deny_won.append(
        S.RedisApprovalStore(server).transition(rec["id"], "tenant-A", AP.STATUS_PENDING, denied)
    )
    approved = AP.approve(rec, approver="u1", decided_at=_TS)
    assert store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, approved) is False
    assert deny_won == [True]
    assert store.get(rec["id"])["status"] == AP.STATUS_DENIED
    assert store.list_pending() == []
    assert {"watch", "multi", "exec"} <= set(server.commands)


def test_redis_decision_keeps_the_remaining_ttl():
    server = RedisTxnDouble()
    store = S.RedisApprovalStore(server, ttl_s=1000)
    rec = _pending()
    store.create(rec)
    key = "sahool:agent:approval:" + rec["id"]
    server.tick(250)
    assert server.ttl(key) == 750
    approved = AP.approve(rec, approver="u", decided_at=_TS)
    assert store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, approved) is True
    assert server.ttl(key) == 750, "the decision reset or dropped the record's expiry"


def test_redis_decision_does_not_recreate_an_expired_record():
    server = RedisTxnDouble()
    store = S.RedisApprovalStore(server, ttl_s=10)
    rec = _pending()
    store.create(rec)
    approved = AP.approve(rec, approver="u", decided_at=_TS)
    server.on_watched_get = lambda: server.tick(10)  # expires between read and EXEC
    assert store.transition(rec["id"], "tenant-A", AP.STATUS_PENDING, approved) is False
    assert store.get(rec["id"]) is None


# ── tool loop: an approval that was not stored is not advertised ─────────────
def test_unpersisted_approval_is_a_failed_result_not_a_pending_one():
    audits: list[dict] = []

    def refusing_saver(_req):
        raise S.ApprovalExistsError("apr_x")

    out = TL.run_tool_calls(
        [dict(_MUTATING_CALL), {"id": "req-1", "tool": "get_field_index", "params": {}}],
        allowed_capabilities=_CAPS,
        fetcher=None,
        tenant_id="tenant-A",
        actor="ai_agronomist",
        timestamp=_TS,
        approval_saver=refusing_saver,
        audit_saver=audits.append,
        stop_on_pending=True,
    )
    assert out["pending_approvals"] == []
    first = out["tool_calls"][0]
    assert first["outcome"] == "failed"
    assert first["reason"] == "approval_not_persisted"
    assert first["data"] is None
    assert first["tool_call_id"] == "req-0"
    assert first["input_hash"] == AP.input_hash(_MUTATING_CALL["params"])
    assert "approval_id" not in first
    assert audits and audits[0]["outcome"] == "failed"
    assert out["tool_calls"][1]["outcome"] == TL.OUTCOME_SKIPPED_PENDING_GATE


# ── API: approve/deny use the atomic transition ─────────────────────────────
_AUTH = {"X-Tenant-Id": "tenant-A", "X-User-Id": "user-1"}


@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.ai_agronomist import main as M

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-agent-token-atomic")
    monkeypatch.setattr(M, "_APPROVAL_STORE", S.InMemoryApprovalStore())
    monkeypatch.setattr(M, "_AUDIT_STORE", S.InMemoryAuditStore())
    return M, TestClient(M.app, raise_server_exceptions=False)


def test_api_round_trip_from_tool_loop_to_resume_uses_the_server_id(api):
    M, client = api
    out = TL.run_tool_calls(
        [dict(_MUTATING_CALL)],
        allowed_capabilities=_CAPS,
        fetcher=None,
        tenant_id="tenant-A",
        actor="ai_agronomist",
        timestamp=_TS,
        approval_saver=M._save_pending_approval,
    )
    rec = out["pending_approvals"][0]
    listed = client.get("/v1/approvals/pending", headers=_AUTH).json()["pending"]
    assert [p["id"] for p in listed] == [rec["id"]]
    # The console posts the whole listed record back; a forged tool_call_id does not stick.
    body = {"approval": {**listed[0], "tool_call_id": "forged"}}
    resp = client.post("/v1/approvals/approve", json=body, headers=_AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["approval"]["id"] == rec["id"]
    assert resp.json()["approval"]["tool_call_id"] == "req-0"
    assert resp.json()["resume"]["approval_id"] == rec["id"]
    resumed = client.post("/v1/approvals/resume", json={"approval_id": rec["id"]}, headers=_AUTH)
    assert resumed.status_code == 200
    again = client.post("/v1/approvals/deny", json={"approval": {"id": rec["id"]}}, headers=_AUTH)
    assert again.status_code == 409


def test_api_lost_race_is_409_and_writes_no_success_audit(api):
    M, client = api
    rec = _pending()
    M._APPROVAL_STORE.create(rec)
    real_transition = M._APPROVAL_STORE.transition

    def racing_transition(approval_id, tenant_id, expected, new_record):
        # a concurrent deny commits after the endpoint read the record, before it decides
        real_transition(
            approval_id, tenant_id, expected, AP.deny(rec, approver="other", decided_at=_TS)
        )
        return real_transition(approval_id, tenant_id, expected, new_record)

    M._APPROVAL_STORE.transition = racing_transition
    resp = client.post("/v1/approvals/approve", json={"approval": {"id": rec["id"]}}, headers=_AUTH)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "approval_state_changed"
    assert M._APPROVAL_STORE.get(rec["id"])["status"] == AP.STATUS_DENIED
    assert M._AUDIT_STORE.recent(10) == []


@pytest.mark.parametrize("path", ["/v1/approvals/approve", "/v1/approvals/deny"])
def test_api_store_failure_is_503_before_any_success_audit(api, path):
    M, client = api
    rec = _pending()
    M._APPROVAL_STORE.create(rec)

    def broken(*_a, **_k):
        raise ConnectionError("redis down")

    M._APPROVAL_STORE.transition = broken
    resp = client.post(path, json={"approval": {"id": rec["id"]}}, headers=_AUTH)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "approval_store_unavailable"
    assert M._AUDIT_STORE.recent(10) == []


# ── compose: the ACL grants exactly what agent_stores.py calls ───────────────
#: redis-py client/pipeline method -> the Redis commands it sends.
_METHOD_COMMANDS = {
    "ping": {"ping"},
    "get": {"get"},
    "set": {"set"},
    "sadd": {"sadd"},
    "srem": {"srem"},
    "smembers": {"smembers"},
    "rpush": {"rpush"},
    "ltrim": {"ltrim"},
    "lrange": {"lrange"},
    "watch": {"watch"},
    "unwatch": {"unwatch"},
    "multi": {"multi"},
    "execute": {"exec"},
    # pipeline() is client-side; leaving the block while watching sends UNWATCH (Pipeline.reset)
    "pipeline": {"unwatch"},
}


def _redis_receivers(tree: ast.AST) -> set[str]:
    """Names bound to a Redis client or pipeline: ``self._c``, ``with ... .pipeline() as X``,
    and ``X = redis.from_url(...)``."""
    names = {"self._c"}
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "pipeline"
                    and isinstance(item.optional_vars, ast.Name)
                ):
                    names.add(item.optional_vars.id)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "from_url":
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _commands_called_by_agent_stores() -> set[str]:
    tree = ast.parse(STORES_SRC.read_text(encoding="utf-8"))
    receivers = _redis_receivers(tree)
    used: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if ast.unparse(node.func.value) not in receivers:
            continue
        method = node.func.attr
        assert method in _METHOD_COMMANDS, (
            f"agent_stores.py calls Redis method {method!r}: map it to its commands here and "
            "grant them in docker-compose.v9.yml + docs/architecture/redis_acl_matrix.json"
        )
        used |= _METHOD_COMMANDS[method]
    return used


def _agent_acl_rules() -> list[str]:
    """The ``sahool-ai-agronomist`` ACL rules, on whichever Redis server defines the user."""
    for server in ("sahool-redis-state", "sahool-redis"):
        rules = _compose_user_rules(server, "sahool-ai-agronomist")
        if rules is not None:
            return rules
    raise AssertionError("no sahool-ai-agronomist ACL user in docker-compose.v9.yml")


def _compose_user_rules(server: str, user: str) -> list[str] | None:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    argv = shlex.split(str(data["services"][server]["command"]))
    for i, arg in enumerate(argv):
        if arg == "--user" and argv[i + 1] == user:
            rules = []
            for rule in argv[i + 2 :]:
                if rule.startswith("--"):
                    break
                rules.append(rule)
            return rules
    return None


def test_every_redis_command_agent_stores_calls_is_granted_to_the_compose_user():
    used = _commands_called_by_agent_stores()
    assert {"ltrim", "watch", "multi", "exec", "set", "get"} <= used, used
    granted = {r[1:] for r in _agent_acl_rules() if r.startswith("+")}
    assert used - granted == set(), f"called but not granted (NOPERM in compose): {used - granted}"
    assert granted - used == set(), f"granted but never called: {granted - used}"
    assert not {"eval", "evalsha"} & granted


def test_commands_seen_by_the_double_are_granted_too():
    server = RedisTxnDouble()
    audit = S.RedisAuditStore(server, max_records=2)
    for i in range(3):
        audit.append({"seq": i})
    assert [r["seq"] for r in audit.recent(5)] == [1, 2]
    rules = _agent_acl_rules()
    granted = {r[1:] for r in rules if r.startswith("+")}
    assert set(server.commands) - granted == set(), set(server.commands) - granted
    store = S.RedisApprovalStore(server)
    rec = _pending()
    store.create(rec)
    store.list_pending()
    store.transition(rec["id"], "tenant-B", AP.STATUS_PENDING, rec)  # refused: UNWATCH path
    store.transition(
        rec["id"], "tenant-A", AP.STATUS_PENDING, AP.approve(rec, approver="u", decided_at=_TS)
    )
    assert set(server.commands) - granted == set(), set(server.commands) - granted


def test_agent_store_lives_on_the_noeviction_state_server():
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert _compose_user_rules("sahool-redis", "sahool-ai-agronomist") is None
    state_cmd = str(data["services"]["sahool-redis-state"]["command"])
    assert "--maxmemory-policy noeviction" in state_cmd
    svc = data["services"]["sahool-ai-agronomist"]
    url = svc["environment"]["SAHOOL_AGENT_REDIS_URL"]
    assert re.search(r"@sahool-redis-state:6379/0\}$", url), url
    assert "sahool-redis-state" in svc["depends_on"]
    assert "sahool-redis" not in svc["depends_on"]
