"""بوتُ تيليجرام يطلب الصوتَ بتوكن **المُرسِل** المربوط وحده — TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01.

كان ``/voice`` يطلب tts بتوكن الخدمة (``X-Agent-Token``) فتُقرأ الهويّةُ ``__service__`` بلا
مستأجِر. بقرار المالك: طلبُ الخدمة بلا مستأجِرٍ موثَّق يبقى ``local_only``، وطلبُ المستخدم
المربوط يحمل JWT المستخدم. ويُستخرَج التوكن من هويّة المُرسِل (``from_user``) لا من معرّف
المحادثة (مجموعةٌ لها معرّفُ محادثةٍ واحدٌ لأعضاءٍ كُثُر). ولا يُرسَل ``X-Agent-Token`` معه:
توكنُ الخدمة يغلب في مصادقة tts فيُعيد الهويّةَ خدميّة.

يفشل ولا يتخطّى عند تعذّر تحميل البوت: ``aiogram`` في تبعيّات اختبارات CI
(``tests_v9/requirements-test.txt``) فالتخطّي هناك صمتٌ لا دليل.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

_BOT_DIR = Path(__file__).resolve().parents[1] / "bots" / "telegram"


def _load_bot():
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test")
    os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    if str(_BOT_DIR) not in sys.path:
        sys.path.insert(0, str(_BOT_DIR))
    existing = sys.modules.get("sahool_tg_voice_main")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("sahool_tg_voice_main", _BOT_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sahool_tg_voice_main"] = module
    spec.loader.exec_module(module)
    return module


class _Recorder:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    def client_factory(self):
        recorder = self

        class _Resp:
            status_code = 200
            content = b"AUDIO"

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None, headers=None):
                recorder.posts.append({"url": url, "json": json, "headers": dict(headers or {})})
                return _Resp()

        return _Client


def _wire(monkeypatch, bot):
    rec = _Recorder()
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", rec.client_factory())
    sent: list[int] = []

    async def send_voice(chat_id, voice, caption=None):
        sent.append(chat_id)

    monkeypatch.setattr(bot.bot, "send_voice", send_voice)
    return rec, sent


def test_a_linked_sender_is_voiced_with_their_own_jwt_and_no_service_token(monkeypatch):
    bot = _load_bot()
    rec, sent = _wire(monkeypatch, bot)
    monkeypatch.setitem(bot.user_cache, 42, {"token": "USER-JWT-42"})
    ok = asyncio.run(bot.send_voice_alert(-1009, "نصّ", user_id=42))
    assert ok is True and sent == [-1009]
    assert len(rec.posts) == 1
    headers = rec.posts[0]["headers"]
    assert headers == {"Authorization": "Bearer USER-JWT-42"}
    assert "X-Agent-Token" not in headers


def test_an_unlinked_sender_gets_no_voice_and_tts_is_never_called(monkeypatch):
    bot = _load_bot()
    rec, sent = _wire(monkeypatch, bot)
    monkeypatch.setitem(bot.user_cache, 77, {})
    assert asyncio.run(bot.send_voice_alert(-1009, "نصّ", user_id=77)) is False
    assert rec.posts == [] and sent == []


def test_the_voice_command_uses_the_sender_identity_not_the_chat_id(monkeypatch):
    bot = _load_bot()
    seen: dict = {}

    async def fake_send_voice_alert(chat_id, text, voice="yemeni_male", *, user_id):
        seen.update(chat_id=chat_id, user_id=user_id)
        return True

    monkeypatch.setattr(bot, "send_voice_alert", fake_send_voice_alert)
    message = types.SimpleNamespace(
        chat=types.SimpleNamespace(id=-1009),
        from_user=types.SimpleNamespace(id=42),
    )

    async def answer(*a, **k):
        return None

    message.answer = answer
    asyncio.run(bot.cmd_voice(message))
    assert seen == {"chat_id": -1009, "user_id": 42}
