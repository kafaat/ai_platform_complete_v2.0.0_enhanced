"""حارس V21 §2.3: فحص جاهزيّة قادر على الإدراك لبوت تيليجرام (لا مجرّد /proc/1/cmdline).

الخلفيّة (تدقيق الحاويات V21 §2.3): كان healthcheck بوت تيليجرام في
``docker-compose.v9.yml`` يفحص فقط أنّ ``/proc/1/cmdline`` يحوي ``main.py`` — يُثبِت
وجود العمليّة لا جاهزيّتها الوظيفيّة (توكن مقبول، حلقة استطلاع حيّة، تبعيّات). هذا الحارس
يقفل الثابتة (invariant) المضادّة للانحدار:

  1. فحص خدمة تيليجرام في compose لم يعُد يعتمد على ``/proc/1/cmdline`` وحده، ويستدعي
     مُدقّق الجاهزيّة ``bot_readiness``.
  2. كود البوت يكتب/يستخدم إشارة الجاهزيّة (وحدة ``bot_readiness`` + تسجيل startup +
     كتابة النبضة في ``main.py``).
  3. اختبار منطق صرف لمُقيّم الحداثة ``evaluate_readiness`` (بلا خدمات).

فحص ملفّات/منطق نقيّ — يعمل تحت ``pytest -m unit`` (بلا خدمات). لا يُشغّل البوت ولا
يلمس Telegram API.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.v9.yml"
_BOT_DIR = _REPO_ROOT / "bots" / "telegram"
_BOT_MAIN = _BOT_DIR / "main.py"
_BOT_READINESS = _BOT_DIR / "bot_readiness.py"
_TELEGRAM_SERVICE = "sahool-telegram-bot"


def _load_bot_readiness():
    """حمِّل ``bot_readiness`` مباشرةً من مساره (بلا تشغيل ``main.py`` وتبعيّاته)."""
    spec = importlib.util.spec_from_file_location("bot_readiness", _BOT_READINESS)
    assert spec and spec.loader, "تعذّر تحميل bot_readiness"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bot_readiness"] = mod
    spec.loader.exec_module(mod)
    return mod


def _telegram_healthcheck_test() -> str:
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "docker-compose.v9.yml لم يُحلَّل إلى خريطة"
    svc = (data.get("services") or {}).get(_TELEGRAM_SERVICE)
    assert isinstance(svc, dict), f"خدمة {_TELEGRAM_SERVICE} مفقودة في compose"
    hc = svc.get("healthcheck")
    assert isinstance(hc, dict), f"لا healthcheck لخدمة {_TELEGRAM_SERVICE}"
    test = hc.get("test")
    assert test, "healthcheck بلا test"
    return " ".join(test) if isinstance(test, list) else str(test)


@pytest.mark.unit
def test_compose_parses():
    """docker-compose.v9.yml يجب أن يُحلَّل بـyaml.safe_load (لا انحدار في البنية)."""
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data.get("services"), "لا خدمات في compose"


@pytest.mark.unit
def test_telegram_healthcheck_not_solely_proc_cmdline():
    """فحص تيليجرام لم يعُد يعتمد على /proc/1/cmdline وحده — يستدعي مُدقّق الجاهزيّة."""
    cmd = _telegram_healthcheck_test()
    assert "/proc/1/cmdline" not in cmd, (
        "healthcheck بوت تيليجرام ما زال يعتمد على /proc/1/cmdline (وجود العمليّة لا "
        "جاهزيّتها) — استبدله بفحص جاهزيّة قادر على الإدراك (V21 §2.3)."
    )
    assert "bot_readiness" in cmd, (
        "healthcheck بوت تيليجرام يجب أن يستدعي مُدقّق الجاهزيّة bot_readiness."
    )


@pytest.mark.unit
def test_bot_writes_and_uses_readiness_signal():
    """كود البوت يكتب/يستخدم إشارة الجاهزيّة: وحدة موجودة + startup + كتابة نبضة."""
    assert _BOT_READINESS.exists(), "bots/telegram/bot_readiness.py مفقود"
    main_src = _BOT_MAIN.read_text(encoding="utf-8")
    assert "bot_readiness" in main_src, "main.py لا يستورد bot_readiness"
    assert "ReadinessState" in main_src, "main.py لا يُنشئ ReadinessState"
    # يتحقّق فعليّاً من التوكن عبر getMe (قبول التوكن، لا مجرّد وجود عمليّة).
    assert "get_me" in main_src, "main.py لا يتحقّق من التوكن عبر getMe"
    # يسجّل خطّاف الإقلاع ويكتب النبضة دوريّاً.
    assert "dp.startup.register" in main_src, "main.py لا يسجّل خطّاف startup للجاهزيّة"
    assert "_heartbeat_loop" in main_src, "main.py لا يبدأ حلقة كتابة النبضة"
    assert ".write()" in main_src, "main.py لا يكتب نبضة الجاهزيّة"


@pytest.mark.unit
def test_readiness_module_exposes_capability_signals():
    """وحدة bot_readiness تكشف إشارات القدرة: قبول التوكن + حداثة النبضة."""
    mod = _load_bot_readiness()
    state = mod.ReadinessState()
    d = state.to_dict()
    for key in ("telegram_ready", "last_beat_at", "current_state", "redis_ok"):
        assert key in d, f"نبضة الجاهزيّة تفتقد الحقل {key}"


@pytest.mark.unit
def test_evaluate_readiness_pure_logic():
    """منطق صرف لمُقيّم الجاهزيّة: قبول التوكن + حداثة + كشف الفشل/التقادم."""
    mod = _load_bot_readiness()
    ev = mod.evaluate_readiness
    now = 1_000_000.0

    # نبضة غائبة → غير جاهز.
    ok, reason = ev(None, now, 90)
    assert not ok and "missing" in reason

    # التوكن غير مقبول (getMe لم ينجح) → غير جاهز حتى لو النبضة طازجة.
    ok, reason = ev({"telegram_ready": False, "last_beat_at": now}, now, 90)
    assert not ok and "token_not_accepted" in reason

    # جاهز: توكن مقبول + نبضة طازجة.
    ok, reason = ev(
        {"telegram_ready": True, "last_beat_at": now - 10, "bot_username": "sahool_bot"},
        now,
        90,
    )
    assert ok and reason.startswith("ready")

    # تقادم النبضة → غير جاهز (لا يُخفي توقّف حلقة الحدث/الاستطلاع).
    ok, reason = ev({"telegram_ready": True, "last_beat_at": now - 200}, now, 90)
    assert not ok and "stale" in reason

    # حالة failed → غير جاهز صراحةً.
    ok, reason = ev(
        {
            "telegram_ready": True,
            "last_beat_at": now,
            "current_state": "failed",
            "last_error": "getMe failed",
        },
        now,
        90,
    )
    assert not ok and "failed" in reason


@pytest.mark.unit
def test_readiness_state_roundtrip_marks_ready(tmp_path, monkeypatch):
    """mark_ready يضبط telegram_ready + حالة ready + نبضة طازجة، ويُكتب ذرّيّاً."""
    monkeypatch.setenv("TELEGRAM_HEARTBEAT_DIR", str(tmp_path))
    mod = _load_bot_readiness()
    state = mod.ReadinessState()
    assert state.to_dict()["telegram_ready"] is False  # يبدأ غير جاهز
    state.mark_ready("sahool_bot")
    state.write()
    data = mod.read_readiness(state.bot_name)
    assert data is not None and data["telegram_ready"] is True
    ok, reason = mod.evaluate_readiness(data, time.time(), 90)
    assert ok, reason
