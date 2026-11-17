"""W3-01: FEATURE_NATS_PUBLISHERS staging enablement — preflight, backlog signal, readiness.

Pure-logic layer (no database, no broker): the declarative stream, the preflight verdicts,
the relay gate, the backlog warning, and the /readyz and /metrics surfaces. The real
PostgreSQL + JetStream proof is ``tests_v9/test_nats_outbox_staging_enablement_live.py``;
the real broker identities are proven in ``tests_v9/test_nats_least_privilege.py``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


# ── doubles for the broker (not the database) ──────────────────────────────────────


class _NotFound(Exception):
    pass


class _JS:
    def __init__(self, *, stream=None, consumers=()):
        self.stream = stream
        self.consumers = set(consumers)

    async def stream_info(self, name):
        if self.stream is None:
            raise _NotFound(name)
        return SimpleNamespace(config=self.stream)

    async def consumer_info(self, stream, name):
        if name not in self.consumers:
            raise _NotFound(name)
        return SimpleNamespace(name=name)


class _NC:
    def __init__(self, js, connected=True):
        self._js, self.is_connected = js, connected

    def jetstream(self):
        return self._js


def _spec_config(**override):
    from shared.nats_stream_contract import STREAM_SPEC

    values = {**STREAM_SPEC, **override}
    return SimpleNamespace(**values)


def _all_consumers(pick_queue=False):
    from shared.nats_stream_contract import REQUIRED_CONSUMERS

    return {g[-1] if pick_queue else g[0] for g in REQUIRED_CONSUMERS}


# ── the declarative stream ─────────────────────────────────────────────────────────


def test_stream_config_is_the_declared_spec_and_matches_the_server_echo():
    from shared.nats_stream_contract import STREAM_SPEC, stream_config, stream_drift

    cfg = stream_config()
    assert cfg.name == "sahool" and cfg.subjects == ["sahool.>"], cfg
    # The server echoes enums and numbers; the drift check must read them as the spec.
    assert stream_drift(cfg) == [], f"the spec does not match its own config: {stream_drift(cfg)}"
    assert STREAM_SPEC["retention"] == "limits" and STREAM_SPEC["max_age"] == 0, (
        "retention changed: shared.notification_consumers.validate_stream requires "
        "limits + unlimited retention"
    )


def test_drift_is_reported_field_by_field_never_silently_accepted():
    from shared.nats_stream_contract import stream_drift

    drift = stream_drift(_spec_config(max_age=3600, subjects=["sahool.events.>"]))
    assert any(d.startswith("max_age") for d in drift), drift
    assert any(d.startswith("subjects") for d in drift), drift


def test_notification_agent_creates_the_stream_from_the_declaration():
    text = (ROOT / "agents" / "notification" / "agent.py").read_text(encoding="utf-8")
    assert "add_stream(stream_config())" in text, "the agent must create the declared stream"
    assert 'StreamConfig(name="sahool"' not in text, "an inline stream definition came back"


# ── credentials: presence as booleans, never values ────────────────────────────────


def test_credential_facts_are_booleans_and_never_carry_the_secret():
    from shared.nats_stream_contract import credential_facts

    facts = credential_facts("tls://sahool-platform:s3cr3t-value@sahool-nats:4222")
    assert facts == {
        "url_present": True,
        "user_present": True,
        "password_present": True,
        "tls": True,
    }, facts
    assert "s3cr3t" not in json.dumps(facts), "a credential value leaked into the facts"
    assert credential_facts("nats://sahool-nats:4222")["password_present"] is False, "no password"
    assert credential_facts(None)["url_present"] is False, "no URL must read as absent"


# ── preflight verdicts (fail closed) ───────────────────────────────────────────────


async def test_preflight_fails_closed_when_not_connected():
    from shared.nats_stream_contract import run_preflight

    out = await run_preflight(_NC(_JS(), connected=False), flag=True, url=None)
    assert out["status"] == "failed" and "not_connected" in out["errors"], out
    out = await run_preflight(None, flag=True, url=None)
    assert out["status"] == "failed", f"no connection must not pass: {out}"


async def test_preflight_fails_on_missing_stream_then_on_missing_consumers():
    from shared.nats_stream_contract import run_preflight

    out = await run_preflight(_NC(_JS()), flag=True, url=None)
    assert out["status"] == "failed" and out["stream"]["exists"] is False, out
    assert out["errors"] == ["stream_info:_NotFound"], out

    out = await run_preflight(_NC(_JS(stream=_spec_config())), flag=True, url=None)
    assert out["stream"]["exists"] and out["stream"]["covers_platform_events"], out
    missing = [e for e in out["errors"] if e.startswith("consumer_missing:")]
    assert out["status"] == "failed" and len(missing) == 4, out


async def test_preflight_passes_with_either_notification_mode_and_rejects_drift():
    from shared.nats_stream_contract import run_preflight

    for queue_mode in (False, True):
        js = _JS(stream=_spec_config(), consumers=_all_consumers(pick_queue=queue_mode))
        out = await run_preflight(_NC(js), flag=True, url=None)
        assert out["status"] == "passed", f"queue_mode={queue_mode}: {out}"

    js = _JS(stream=_spec_config(subjects=["other.>"]), consumers=_all_consumers())
    out = await run_preflight(_NC(js), flag=True, url=None)
    assert out["status"] == "failed", out
    assert {"stream_drift", "stream_does_not_cover_platform_events"} <= set(out["errors"]), out


# ── the relay gate ─────────────────────────────────────────────────────────────────


async def test_gate_holds_the_relay_until_the_preflight_passes():
    from shared.nats_stream_contract import PreflightState

    js = _JS()
    state, started = PreflightState(), []

    async def start():
        started.append(True)

    assert await state.gate(_NC(js), start, url=None, retry_s=0.01) is False
    assert started == [], "the relay started while the stream was missing"
    assert state.gate_task is not None and not state.gate_task.done(), "no background retry"

    js.stream, js.consumers = _spec_config(), _all_consumers()
    await asyncio.wait_for(state.gate_task, timeout=2)
    assert started == [True], "provisioning the topology did not start the relay"
    assert state.snapshot(flag=True)["status"] == "passed", state.snapshot(flag=True)
    await state.reset()
    assert state.result is None and state.gate_task is None, "reset left state behind"


async def test_reset_cancels_a_pending_gate():
    from shared.nats_stream_contract import PreflightState

    state = PreflightState()

    async def start():
        raise AssertionError("must not start")

    await state.gate(_NC(_JS()), start, url=None, retry_s=3600)
    task = state.gate_task
    await state.reset()
    assert task.cancelled(), "a stopped platform left the gate retrying"


def test_snapshot_reports_disabled_when_the_flag_is_off_and_pending_before_a_run():
    from shared.nats_stream_contract import PreflightState

    state = PreflightState()
    assert state.snapshot(flag=False) == {"status": "disabled", "flag": False}, "flag off"
    assert state.snapshot(flag=True)["status"] == "pending", "never-run preflight must not pass"


# ── the outbox backlog signal ──────────────────────────────────────────────────────


def test_backlog_with_flag_off_warns_that_enabling_replays_the_held_events():
    from api.event_bus import NATS_PUBLISHERS_FLAG, outbox_backlog_summary

    out = outbox_backlog_summary(
        {
            "held": 7,
            "dead_letter": 0,
            "oldest_held_age_seconds": 86400.04,
            "sees_all_tenants": True,
        },
        flag_enabled=False,
    )
    assert out["held"] == 7 and out["replay_on_enable"] == 7, out
    assert out["oldest_held_age_seconds"] == 86400.0 and out["scope"] == "all_tenants", out
    assert len(out["warnings"]) == 1, out
    assert NATS_PUBLISHERS_FLAG in out["warnings"][0] and "will replay 7" in out["warnings"][0], out


def test_backlog_with_flag_on_reports_draining_and_dead_letter_and_scope():
    from api.event_bus import outbox_backlog_summary

    out = outbox_backlog_summary(
        {"held": 2, "dead_letter": 3, "oldest_held_age_seconds": 5.0, "sees_all_tenants": False},
        flag_enabled=True,
    )
    assert out["replay_on_enable"] == 0, out
    text = " | ".join(out["warnings"])
    assert "draining 2" in text and "3 event(s) exhausted" in text, text
    assert out["scope"] == "tenant_scoped_undercount" and "RLS" in text, out


def test_empty_backlog_has_no_warnings():
    from api.event_bus import outbox_backlog_summary

    out = outbox_backlog_summary(
        {"held": 0, "dead_letter": 0, "oldest_held_age_seconds": None, "sees_all_tenants": True},
        flag_enabled=False,
    )
    assert out["warnings"] == [] and out["oldest_held_age_seconds"] is None, out


def test_backlog_sql_counts_dead_letters_at_the_workers_own_retry_limit():
    from api.event_bus import OUTBOX_BACKLOG_SQL, OUTBOX_MAX_RETRIES, OutboxWorker

    worker = OutboxWorker(pool=None, nats_publish_fn=None)
    assert worker.max_retries == OUTBOX_MAX_RETRIES, "backlog and worker disagree on DLQ limit"
    assert "retry_count < $1" in OUTBOX_BACKLOG_SQL, "held rows must stop at the retry limit"
    assert "retry_count >= $1" in OUTBOX_BACKLOG_SQL, "dead letters start at the retry limit"
    upper = OUTBOX_BACKLOG_SQL.upper()
    assert "INSERT" not in upper and "UPDATE" not in upper, "the backlog probe must only read"


# ── /readyz and /metrics ───────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    from api import main
    from api.routers import platform_health
    from fastapi.testclient import TestClient

    from shared.nats_stream_contract import NATS_PREFLIGHT

    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.setattr(main, "_DB_POOL", None)
    monkeypatch.setattr(main.NATS_RELAY, "conn", None)
    backlog = {
        "status": "ok",
        "held": 4,
        "dead_letter": 1,
        "oldest_held_age_seconds": 12.5,
        "scope": "all_tenants",
        "replay_on_enable": 4,
        "warnings": ["FEATURE_NATS_PUBLISHERS is off: enabling it will replay 4 held event(s)"],
    }

    async def _backlog():  # stubbed at the store-function level: no fake pool
        return dict(backlog)

    monkeypatch.setattr(platform_health, "_outbox_backlog", _backlog)
    NATS_PREFLIGHT.result, NATS_PREFLIGHT.checked_at = None, None
    yield TestClient(main.app)
    NATS_PREFLIGHT.result, NATS_PREFLIGHT.checked_at = None, None


def test_readyz_flag_off_reports_disabled_and_the_replay_warning(client, monkeypatch):
    monkeypatch.delenv("FEATURE_NATS_PUBLISHERS", raising=False)
    resp = client.get("/readyz")
    body = resp.json()
    assert resp.status_code == 200, body
    assert body["nats_preflight"] == {"status": "disabled", "flag": False}, body
    assert body["outbox"]["replay_on_enable"] == 4 and body["outbox"]["warnings"], body


def test_readyz_flag_on_without_a_broker_fails_closed(client, monkeypatch):
    monkeypatch.setenv("FEATURE_NATS_PUBLISHERS", "true")
    resp = client.get("/readyz")
    body = resp.json()
    assert resp.status_code == 503, body
    assert body["status"] == "not ready", body
    assert body["nats_preflight"]["status"] == "failed", body
    assert "not_connected" in body["nats_preflight"]["errors"], body
    assert body["outbox"]["held"] == 4, "the backlog signal must survive a failed readiness"


def test_readyz_flag_on_with_a_passing_preflight_is_ready(client, monkeypatch):
    from api import main

    monkeypatch.setenv("FEATURE_NATS_PUBLISHERS", "true")
    js = _JS(stream=_spec_config(), consumers=_all_consumers())
    monkeypatch.setattr(main.NATS_RELAY, "conn", _NC(js))
    resp = client.get("/readyz")
    body = resp.json()
    assert resp.status_code == 200, body
    assert body["nats_preflight"]["status"] == "passed", body
    assert body["nats_preflight"]["credentials"]["url_present"] in (True, False), body


def test_metrics_expose_backlog_dead_letter_and_flag_gauges(client, monkeypatch):
    monkeypatch.delenv("FEATURE_NATS_PUBLISHERS", raising=False)
    text = client.get("/metrics").text
    for line in (
        "sahool_platform_outbox_held 4",
        "sahool_platform_outbox_dead_letter 1",
        "sahool_platform_outbox_oldest_held_age_seconds 12.5",
        "sahool_platform_outbox_backlog_all_tenants 1",
        "sahool_platform_nats_publishers_enabled 0",
        "sahool_platform_nats_preflight_passed 0",
        "sahool_platform_outbox_backlog_probe_ok 1",
        "sahool_platform_up 1",
    ):
        assert line in text.splitlines(), f"missing gauge line {line!r}"


async def test_backlog_probe_without_a_pool_is_disabled_not_zero(monkeypatch):
    from api import main
    from api.routers import platform_health

    monkeypatch.setattr(main, "_DB_POOL", None)
    monkeypatch.setattr(main, "_JOBS_POOL", None)
    out = await platform_health._outbox_backlog()
    assert out == {"status": "disabled"}, f"no pool must not read as an empty backlog: {out}"


# ── the learning worker follows the same flag ──────────────────────────────────────


def _learning_worker():
    import importlib.util

    path = ROOT / "services/sahool-platform/workers/canonical_execution_learning_worker.py"
    spec = importlib.util.spec_from_file_location("_w301_learning_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_learning_worker_is_not_ready_while_publishers_are_off(monkeypatch):
    worker = _learning_worker()
    monkeypatch.delenv("FEATURE_NATS_PUBLISHERS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert worker.event_source_readiness()["status"] == "publishers_disabled", (
        "flag off ⇒ not ready"
    )
    with pytest.raises(RuntimeError, match="FEATURE_NATS_PUBLISHERS is off"):
        await worker.preflight()  # raises before touching PostgreSQL or NATS

    monkeypatch.setenv("FEATURE_NATS_PUBLISHERS", "true")
    assert worker.event_source_readiness() == {
        "flag": "FEATURE_NATS_PUBLISHERS",
        "enabled": True,
        "status": "passed",
    }, "flag on ⇒ the event source is ready"


def test_compose_keeps_the_flag_off_for_both_platform_and_worker():
    import yaml

    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    for name in ("sahool-platform", "sahool-canonical-execution-learning-worker"):
        value = services[name]["environment"]["FEATURE_NATS_PUBLISHERS"]
        assert value == "${FEATURE_NATS_PUBLISHERS:-false}", f"{name} enables the flag: {value}"
