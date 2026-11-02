"""R3 (audit 2026-11-01): a crashed worker's claim must not wedge the lifecycle runtime.

Before: ``worker.execute_activation/rollback`` minted ``secrets.token_urlsafe`` per attempt. The
decision-service claim row is append-only and keyed by (tenant, command) with the token HASH, so a
successor worker (same REGISTRY_ADAPTER_ID, after a crash between claim and receipt) presented a
different token and got 409 "claimed_by_another_adapter" forever; and because that exception
escaped ``service.run_once``, the one stuck item blocked every later item and every other tenant
(rollbacks included) on every iteration.

After:
  * the delivery token is a deterministic HMAC of (kind, tenant, command, adapter) under a secret,
    so the successor replays the SAME claim (decision-service returns replay=ok);
  * a CAS refused because the alias already holds the target digest (our pre-crash swap) is an
    idempotent success, not a false "failed" receipt;
  * each work item fails alone; after RUNTIME_ITEM_MAX_ATTEMPTS it is parked (dead-letter, visible
    in STATE) and no longer retried every loop; one tenant's feed failure doesn't starve others.

Pure logic: no network, no DB.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ADAPTER_DIR = pathlib.Path(__file__).resolve().parents[1]
_NAMES = ("adapter", "runtime", "worker", "worker_assertion", "service")
TENANT_A = "00000000-0000-0000-0000-00000000000a"
TENANT_B = "00000000-0000-0000-0000-00000000000b"

ACTIVATION = {
    "activation_command_id": "ac-1",
    "model_id": "m1",
    "target_environment": "staging",
    "registry_alias": "champion",
    "previous_artifact_digest": "e" * 64,
    "candidate_artifact_uri": "s3://c",
    "candidate_artifact_digest": "d" * 64,
}
ROLLBACK = {
    "rollback_command_id": "rc-1",
    "model_id": "m1",
    "target_environment": "staging",
    "registry_alias": "champion",
    "replace_artifact_digest": "d" * 64,
    "restore_artifact_uri": "s3://r",
    "restore_artifact_digest": "e" * 64,
}


@pytest.fixture
def mods(monkeypatch):
    """Import the adapter modules fresh under their bare names, then restore sys.modules."""
    env = {
        "SAHOOL_ENV": "staging",
        "MODEL_REGISTRY_URL": "http://registry.local",
        "MODEL_REGISTRY_TOKEN": "tok",
        "MODEL_REGISTRY_BACKEND": "http",
        "REGISTRY_ADAPTER_ID": "adapter-1",
        "DECISION_SERVICE_URL": "http://decision.local",
        "DECISION_SERVICE_TOKEN": "decision-token-for-tests",
        "RUNTIME_ITEM_MAX_ATTEMPTS": "3",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("REGISTRY_DELIVERY_TOKEN_SECRET", raising=False)
    saved = {n: sys.modules.get(n) for n in _NAMES}
    for n in _NAMES:
        sys.modules.pop(n, None)
    sys.path.insert(0, str(ADAPTER_DIR))
    try:
        loaded = SimpleNamespace(**{n: importlib.import_module(n) for n in _NAMES})
        yield loaded
    finally:
        sys.path.remove(str(ADAPTER_DIR))
        for n, mod in saved.items():
            if mod is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = mod


def _capture_posts(monkeypatch, wk):
    posts: list[dict] = []

    def _post(path, payload, tenant_id, extra=None):
        posts.append({"path": path, "payload": payload, "tenant": tenant_id})
        return {"accepted": True}

    monkeypatch.setattr(wk, "_post", _post)
    return posts


class _Registry:
    def __init__(self, ad, *, current_digest: str, cas_ok: bool):
        self.ad = ad
        self.current = current_digest
        self.cas_ok = cas_ok

    def compare_and_swap(self, **k):
        if not self.cas_ok or k["expected_digest"] != self.current:
            raise self.ad.RegistryError("registry http 409: expected digest mismatch")
        self.current = k["artifact_digest"]
        return self.ad.RegistryState(k["alias"], k["artifact_uri"], k["artifact_digest"], "2")

    def get(self, model_id, environment, alias):
        return self.ad.RegistryState(alias, "s3://live", self.current, "2")


def _claim_tokens(posts):
    return [p["payload"]["delivery_token"] for p in posts if p["path"].endswith("/claim")]


def test_retry_after_crash_presents_the_same_claim_proof(mods, monkeypatch):
    wk = mods.worker
    posts = _capture_posts(monkeypatch, wk)
    monkeypatch.setattr(
        wk, "HttpRegistry", lambda: _Registry(mods.adapter, current_digest="e" * 64, cas_ok=True)
    )
    wk.execute_activation(dict(ACTIVATION), TENANT_A)  # first worker
    wk.execute_activation(dict(ACTIVATION), TENANT_A)  # its successor after a crash
    first, second = _claim_tokens(posts)
    assert first == second, "successor must replay the same claim, not mint a new token"
    receipts = [p for p in posts if p["path"].endswith("/receipt")]
    assert all(r["payload"]["delivery_token"] == first for r in receipts)


def test_token_is_scoped_and_secret_keyed(mods, monkeypatch):
    wk = mods.worker
    t = wk.delivery_token("activation", "ac-1", TENANT_A)
    assert len(t) >= 24
    assert t != wk.delivery_token("activation", "ac-1", TENANT_B)
    assert t != wk.delivery_token("rollback", "ac-1", TENANT_A)
    assert t != wk.delivery_token("activation", "ac-2", TENANT_A)
    monkeypatch.setenv("REGISTRY_DELIVERY_TOKEN_SECRET", "another-secret")
    assert t != wk.delivery_token("activation", "ac-1", TENANT_A)
    monkeypatch.delenv("REGISTRY_DELIVERY_TOKEN_SECRET")
    monkeypatch.delenv("DECISION_SERVICE_TOKEN")
    monkeypatch.setenv("SAHOOL_ENV", "production")
    with pytest.raises(mods.adapter.RegistryError):
        wk.delivery_token("activation", "ac-1", TENANT_A)


@pytest.mark.parametrize("kind", ["activation", "rollback"])
def test_swap_already_applied_before_crash_is_idempotent_success(mods, monkeypatch, kind):
    """The pre-crash CAS succeeded; the retry's CAS is refused (expected digest moved). That is
    NOT a failure: the alias already serves the target artifact."""
    wk = mods.worker
    posts = _capture_posts(monkeypatch, wk)
    target = "d" * 64 if kind == "activation" else "e" * 64
    monkeypatch.setattr(
        wk, "HttpRegistry", lambda: _Registry(mods.adapter, current_digest=target, cas_ok=True)
    )
    if kind == "activation":
        wk.execute_activation(dict(ACTIVATION), TENANT_A)
        expected_state = "activated"
    else:
        wk.execute_rollback(dict(ROLLBACK), TENANT_A)
        expected_state = "rolled_back"
    (receipt,) = [p for p in posts if p["path"].endswith("/receipt")]
    assert receipt["payload"]["receipt_state"] == expected_state
    assert receipt["payload"]["active_artifact_digest"] == target


def test_genuine_cas_conflict_still_records_failure(mods, monkeypatch):
    wk = mods.worker
    posts = _capture_posts(monkeypatch, wk)
    monkeypatch.setattr(
        wk, "HttpRegistry", lambda: _Registry(mods.adapter, current_digest="f" * 64, cas_ok=True)
    )
    with pytest.raises(mods.adapter.RegistryError):
        wk.execute_activation(dict(ACTIVATION), TENANT_A)
    (receipt,) = [p for p in posts if p["path"].endswith("/receipt")]
    assert receipt["payload"]["receipt_state"] == "failed"


class _Runtime:
    adapter_id = "adapter-1"

    def __init__(self, feeds):
        self.feeds = feeds
        self.done: list[tuple[str, str]] = []
        outer = self

        class _Decision:
            def get(self, path, tenant, params=None, *, as_worker=None):
                feed = outer.feeds[tenant]
                if isinstance(feed, Exception):
                    raise feed
                return {"items": feed}

        self.decision = _Decision()

    def verify_activation(self, tenant, payload):
        self.done.append((tenant, payload["activation_receipt_id"]))


def test_stuck_item_does_not_block_other_items_or_tenants(mods, monkeypatch):
    svc = mods.service
    monkeypatch.setenv("RUNTIME_TENANT_IDS", f"{TENANT_A},{TENANT_B}")

    def stuck_claim(payload, tenant):
        raise RuntimeError("HTTP 409: activation_command_claimed_by_another_adapter")

    monkeypatch.setattr(svc, "execute_activation", stuck_claim)
    rt = _Runtime(
        {
            TENANT_A: [
                {"work_type": "activation_command", "payload": dict(ACTIVATION)},
                {
                    "work_type": "post_activation_verification",
                    "payload": {"activation_receipt_id": "rcpt-a"},
                },
            ],
            TENANT_B: [
                {
                    "work_type": "post_activation_verification",
                    "payload": {"activation_receipt_id": "rcpt-b"},
                }
            ],
        }
    )
    assert svc.run_once(rt) == 2
    assert rt.done == [(TENANT_A, "rcpt-a"), (TENANT_B, "rcpt-b")]


def test_poison_item_is_parked_after_bounded_attempts(mods, monkeypatch):
    svc = mods.service
    monkeypatch.setenv("RUNTIME_TENANT_IDS", TENANT_A)
    attempts: list[int] = []

    def stuck_claim(payload, tenant):
        attempts.append(1)
        raise RuntimeError("HTTP 409: claim conflict")

    monkeypatch.setattr(svc, "execute_activation", stuck_claim)
    rt = _Runtime({TENANT_A: [{"work_type": "activation_command", "payload": dict(ACTIVATION)}]})
    for _ in range(6):
        svc.run_once(rt)
    assert len(attempts) == svc.ITEM_MAX_ATTEMPTS == 3  # parked: not retried every loop
    (parked,) = svc.STATE["parked_items"]
    assert parked["tenant_id"] == TENANT_A
    assert parked["work_type"] == "activation_command"
    assert parked["key"] == "activation_command_id=ac-1"
    assert "claim conflict" in parked["last_error"]


def test_one_tenant_feed_failure_does_not_starve_the_others(mods, monkeypatch):
    svc = mods.service
    monkeypatch.setenv("RUNTIME_TENANT_IDS", f"{TENANT_A},{TENANT_B}")
    rt = _Runtime(
        {
            TENANT_A: RuntimeError("HTTP 403 for tenant A"),
            TENANT_B: [
                {
                    "work_type": "post_activation_verification",
                    "payload": {"activation_receipt_id": "rcpt-b"},
                }
            ],
        }
    )
    assert svc.run_once(rt) == 1
    assert rt.done == [(TENANT_B, "rcpt-b")]
    # every assigned tenant unreadable ⇒ the iteration still fails (readiness flips to 503).
    rt_all_down = _Runtime({TENANT_A: RuntimeError("down"), TENANT_B: RuntimeError("down")})
    with pytest.raises(mods.runtime.RuntimeContractError):
        svc.run_once(rt_all_down)
