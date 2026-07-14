"""حارس نبضة العمّال (تدقيق الحاويات V21 §2.1 / CT-06).

يُثبِت أنّ healthcheck العمّال صار واعياً بالقدرة: نبضة تُكتَب كلّ دورة (last_poll_at +
عدّادات + حالة)، والفحص يقيس الحداثة والحالة — لا مجرّد وجود متغيّر بيئة. الوحدة نقيّة
(stdlib فقط) فتُختبَر مباشرةً، مع فحص ساكن لتوصيل الحلقة و compose. ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_MOD = ROOT / "services" / "sahool-platform" / "api" / "worker_heartbeat.py"


def _load():
    spec = importlib.util.spec_from_file_location("worker_heartbeat_under_test", _MOD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hb = _load()


def test_evaluate_fresh_running_is_healthy():
    data = {"current_state": "running", "last_poll_at": 1000.0}
    ok, reason = hb.evaluate_heartbeat(data, now_epoch=1005.0, max_age_seconds=120)
    assert ok and "ok" in reason


def test_evaluate_missing_is_unhealthy():
    ok, reason = hb.evaluate_heartbeat(None, now_epoch=1000.0, max_age_seconds=120)
    assert not ok and "missing" in reason


def test_evaluate_stale_is_unhealthy():
    data = {"current_state": "running", "last_poll_at": 1000.0}
    ok, reason = hb.evaluate_heartbeat(data, now_epoch=2000.0, max_age_seconds=120)
    assert not ok and "stale" in reason


def test_evaluate_failed_state_is_unhealthy():
    data = {"current_state": "failed", "last_poll_at": 1000.0, "last_error": "boom"}
    ok, reason = hb.evaluate_heartbeat(data, now_epoch=1001.0, max_age_seconds=120)
    assert not ok and "failed" in reason


def test_evaluate_missing_last_poll_is_unhealthy():
    data = {"current_state": "starting", "last_poll_at": None}
    ok, reason = hb.evaluate_heartbeat(data, now_epoch=1001.0, max_age_seconds=120)
    assert not ok and "last_poll" in reason


def test_state_roundtrip_and_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_DIR", str(tmp_path))
    state = hb.HeartbeatState("phase-runtime-outbox")
    state.mark_poll(3)
    state.write()
    # الملفّ مكتوب ذرّيّاً بالحقول المتوقّعة.
    data = json.loads((tmp_path / "phase-runtime-outbox.json").read_text())
    assert data["processed_total"] == 3 and data["current_state"] == "running"
    assert isinstance(data["last_poll_at"], (int, float))
    # CLI check يعود 0 لنبضة طازجة، و1 لعامل مجهول (لا نبضة).
    assert hb.main(["check", "--worker", "phase-runtime-outbox", "--max-age", "3600"]) == 0
    assert hb.main(["check", "--worker", "does-not-exist", "--max-age", "10"]) == 1
    # خطأ يُسجَّل حالة failed ⇒ غير صحّيّ حتى لو طازجاً.
    state.mark_error("kaboom")
    state.write()
    assert hb.main(["check", "--worker", "phase-runtime-outbox", "--max-age", "3600"]) == 1


def test_loop_worker_writes_heartbeat_each_iteration():
    src = (ROOT / "services" / "sahool-platform" / "api" / "phase_runtime_workers.py").read_text()
    # يُنشئ HeartbeatState ويكتب النبضة (كلّ دورة + عند الخطأ قبل إعادة الرفع).
    assert "from api.worker_heartbeat import HeartbeatState" in src
    assert "hb.mark_poll(processed)" in src
    assert "hb.mark_error(str(exc))" in src
    assert src.count("hb.write()") >= 3  # بدء + نجاح كلّ دورة + مسار الخطأ


def test_compose_target_workers_use_heartbeat_healthcheck():
    compose = (ROOT / "docker-compose.v9.yml").read_text()
    for worker in (
        "phase-runtime-outbox",
        "phase-runtime-actuator",
        "phase-runtime-water_ledger",
    ):
        assert f"worker_heartbeat check --worker {worker}" in compose, worker


# نتأكّد أنّ الوحدة بلا تبعيّات ثقيلة (تعمل في بيئة الوحدة الدنيا في CI).
def test_module_is_stdlib_only():
    src = _MOD.read_text()
    for forbidden in ("import fastapi", "import asyncpg", "from fastapi", "import httpx"):
        assert forbidden not in src
