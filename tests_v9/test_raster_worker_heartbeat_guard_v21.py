"""حارس نبضة عاملَي الراستر (تدقيق الحاويات V21 §2.2 / CT-06).

يُثبِت أنّ healthcheck عاملَي raster-service (إبطال الكاش · فحص backfill) صار واعياً
بالقدرة: نبضة تُكتَب كلّ دورة (last_poll_at + عدّادات + حالة)، والفحص يقيس الحداثة والحالة —
لا مجرّد وجود ``DATABASE_URL``. الوحدة نقيّة (stdlib فقط) فتُختبَر مباشرةً، مع فحص ساكن
لتوصيل الحلقتين و compose، وتأكيد أنّ نقل مرساة ``&id002`` أبقى YAML سليماً وكلّ ``*id002``
قابلاً للحلّ. ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
_MOD = RASTER / "worker_heartbeat.py"
_CACHE_WORKER = RASTER / "cache_invalidation_worker.py"
_BACKFILL_WORKER = RASTER / "backfill_scan_worker.py"
_COMPOSE = ROOT / "docker-compose.v9.yml"


def _load():
    spec = importlib.util.spec_from_file_location("raster_worker_heartbeat_under_test", _MOD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hb = _load()


# ── منطق التقييم الصرف (evaluate matrix) ─────────────────────────────────────
def test_evaluate_fresh_running_is_healthy():
    data = {"current_state": "running", "last_poll_at": 1000.0}
    ok, reason = hb.evaluate_heartbeat(data, now_epoch=1005.0, max_age_seconds=120)
    assert ok and "ok" in reason


def test_evaluate_missing_is_unhealthy():
    ok, reason = hb.evaluate_heartbeat(None, now_epoch=1000.0, max_age_seconds=120)
    assert not ok and "missing" in reason


def test_evaluate_stale_is_unhealthy():
    data = {"current_state": "running", "last_poll_at": 1000.0}
    ok, reason = hb.evaluate_heartbeat(data, now_epoch=5000.0, max_age_seconds=2100)
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
    state = hb.HeartbeatState("raster-backfill-scan")
    state.mark_poll(2)
    state.write()
    data = json.loads((tmp_path / "raster-backfill-scan.json").read_text(encoding="utf-8"))
    assert data["processed_total"] == 2 and data["current_state"] == "running"
    assert isinstance(data["last_poll_at"], (int, float))
    assert hb.main(["check", "--worker", "raster-backfill-scan", "--max-age", "2100"]) == 0
    assert hb.main(["check", "--worker", "does-not-exist", "--max-age", "10"]) == 1
    state.mark_error("kaboom")
    state.write()
    assert hb.main(["check", "--worker", "raster-backfill-scan", "--max-age", "2100"]) == 1


# ── توصيل الحلقتين (كلاهما يكتب نبضة كلّ دورة + عند الخطأ ثمّ يُعيد الرفع) ──────
def test_cache_invalidation_loop_writes_heartbeat_each_iteration():
    src = _CACHE_WORKER.read_text(encoding="utf-8")
    assert "from worker_heartbeat import HeartbeatState" in src
    assert 'HeartbeatState(worker_name="raster-cache-invalidation")' in src
    assert "hb.mark_poll(processed)" in src
    assert "hb.mark_error(str(e))" in src
    assert src.count("hb.write()") >= 3  # بدء + خمول + نجاح كلّ دورة + مسار الخطأ


def test_backfill_scan_loop_writes_heartbeat_each_iteration():
    src = _BACKFILL_WORKER.read_text(encoding="utf-8")
    assert "from worker_heartbeat import HeartbeatState" in src
    assert 'HeartbeatState(worker_name="raster-backfill-scan")' in src
    assert "hb.mark_poll(processed)" in src
    # كلا فرعَي الاستثناء (انجراف المخطّط + العابر) يسجّلان النبضة قبل إعادة الرفع.
    assert src.count("hb.mark_error(str(e))") >= 2
    assert src.count("hb.write()") >= 4  # بدء + خمول/نجاح + فرعا الخطأ


# ── compose: كلا العاملَين يستعملان فحص النبضة، ونقل المرساة أبقى id002 صالحاً ──
def test_compose_raster_workers_use_heartbeat_healthcheck():
    doc = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    svcs = doc["services"]
    cache_hc = svcs["sahool-raster-cache-invalidation-worker"]["healthcheck"]["test"]
    backfill_hc = svcs["sahool-raster-backfill-scan-worker"]["healthcheck"]["test"]
    assert any("worker_heartbeat check --worker raster-cache-invalidation" in p for p in cache_hc)
    assert any("worker_heartbeat check --worker raster-backfill-scan" in p for p in backfill_hc)


def test_id002_env_healthcheck_anchor_fully_retired():
    # حالة متقاربة بعد §2.1+§2.2: كلّ العمّال (phase-runtime الخمسة + الراستريّان) على نبضة
    # قدرة-واعية، فلم يبقَ مُشير إلى ``*id002`` وأُزيلت المرساة اليتيمة (لا كتلة ميّتة).
    text = _COMPOSE.read_text(encoding="utf-8")
    # لا تعريف مرساة ولا أيّ إشارة alias فعليّة (نتجاهل ذِكرها داخل التعليق التوثيقيّ).
    code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("&id002" in ln for ln in code_lines)
    assert not any("*id002" in ln for ln in code_lines)
    doc = yaml.safe_load(text)
    assert "x-worker-env-healthcheck" not in doc  # المفتاح اليتيم أُزيل
    # كلّ عمّال phase-runtime + الراستر يعملون بفحص نبضة (لا فحص وجود متغيّر بيئة).
    svcs = doc["services"]
    for name in (
        "sahool-plugin-runtime-worker",
        "sahool-model-registry-worker",
        "sahool-raster-cache-invalidation-worker",
        "sahool-raster-backfill-scan-worker",
    ):
        test = svcs[name]["healthcheck"]["test"]
        assert any("worker_heartbeat check --worker" in p for p in test), name


def test_module_is_stdlib_only():
    src = _MOD.read_text(encoding="utf-8")
    for forbidden in ("import fastapi", "import asyncpg", "from fastapi", "import httpx"):
        assert forbidden not in src
