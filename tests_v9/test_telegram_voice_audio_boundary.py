"""Exercise the real bot voice function without starting Telegram/Redis/DB."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
CHAT_ID = 123
USER_ID = 456
TOKEN = "authenticated-tenant-jwt"
AUDIO = b"ID3testaudio"


def acknowledgement(chat_id=CHAT_ID, message_id=42, file_id="voice-file"):
    return types.SimpleNamespace(
        message_id=message_id,
        chat=types.SimpleNamespace(id=chat_id),
        voice=types.SimpleNamespace(file_id=file_id),
    )


@pytest.fixture
def voice_sender(monkeypatch):
    tree = ast.parse((ROOT / "bots/telegram/main.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_voice_alert"
    )

    class BufferedInputFile:
        def __init__(self, data, filename):
            self.data = data
            self.filename = filename

    fake_types = types.ModuleType("aiogram.types")
    fake_types.BufferedInputFile = BufferedInputFile
    monkeypatch.setitem(sys.modules, "aiogram.types", fake_types)
    namespace = {
        "logger": logging.getLogger("test-telegram-voice"),
        "TTS_URL": "http://tts-test:8000",
        "get_user_token": AsyncMock(return_value=TOKEN),
        "bot": types.SimpleNamespace(send_voice=AsyncMock(return_value=acknowledgement())),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"), namespace)
    return namespace


def invoke(
    voice_sender,
    monkeypatch,
    *,
    response=None,
    text="مقدار 0.75 مل لكل لتر",
    chat_id=CHAT_ID,
    user_id=USER_ID,
):
    requests = []

    def handler(request):
        requests.append(request)
        if isinstance(response, Exception):
            raise response
        return (
            response
            if response is not None
            else httpx.Response(200, content=AUDIO, headers={"content-type": "audio/mpeg"})
        )

    actual_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    result = asyncio.run(voice_sender["send_voice_alert"](chat_id, text, user_id=user_id))
    return result, requests


def test_valid_audio_and_receipt_preserve_caller_and_caption(voice_sender, monkeypatch):
    text = "مقدار 0.75 مل لكل لتر؛ فترة 7 أيام"
    result, requests = invoke(voice_sender, monkeypatch, text=text)
    assert result is True
    voice_sender["get_user_token"].assert_awaited_once_with(USER_ID)
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "X-Agent-Token" not in requests[0].headers
    assert json.loads(requests[0].content)["text"] == text
    sent = voice_sender["bot"].send_voice.call_args.kwargs
    assert sent["chat_id"] == CHAT_ID
    assert sent["caption"] == text
    assert sent["voice"].data == AUDIO
    assert sent["voice"].filename == "sahool_voice.mp3"


@pytest.mark.parametrize(
    "text,chat_id,user_id",
    [
        ("", CHAT_ID, USER_ID),
        (" ", CHAT_ID, USER_ID),
        (None, CHAT_ID, USER_ID),
        ("x" * 1001, CHAT_ID, USER_ID),
        ("text", True, USER_ID),
        ("text", 0, USER_ID),
        ("text", CHAT_ID, 0),
        ("text", CHAT_ID, True),
    ],
)
def test_invalid_input_does_not_lookup_identity_or_send(
    voice_sender, monkeypatch, text, chat_id, user_id
):
    result, requests = invoke(
        voice_sender, monkeypatch, text=text, chat_id=chat_id, user_id=user_id
    )
    assert result is False
    assert not requests
    voice_sender["get_user_token"].assert_not_awaited()
    voice_sender["bot"].send_voice.assert_not_awaited()


def test_missing_caller_token_never_synthesizes(voice_sender, monkeypatch):
    voice_sender["get_user_token"].return_value = ""
    result, requests = invoke(voice_sender, monkeypatch)
    assert result is False
    assert not requests
    voice_sender["bot"].send_voice.assert_not_awaited()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"RIFFwave", headers={"content-type": "audio/wav"}),
        httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"}),
        httpx.Response(200, content=b"error", headers={"content-type": "application/json"}),
        httpx.Response(
            200, content=b"x" * (10 * 1024 * 1024 + 1), headers={"content-type": "audio/mpeg"}
        ),
        httpx.Response(403, content=b"denied"),
        httpx.ReadTimeout("timeout"),
    ],
)
def test_synthesis_invalid_audio_never_reaches_telegram(voice_sender, monkeypatch, response):
    result, requests = invoke(voice_sender, monkeypatch, response=response)
    assert result is False
    assert len(requests) == 1
    voice_sender["bot"].send_voice.assert_not_awaited()


@pytest.mark.parametrize(
    "receipt",
    [
        None,
        acknowledgement(chat_id=999),
        acknowledgement(message_id=0),
        acknowledgement(message_id=True),
        acknowledgement(message_id="42"),
        acknowledgement(chat_id="123"),
        acknowledgement(file_id=""),
        types.SimpleNamespace(message_id=42, chat=types.SimpleNamespace(id=CHAT_ID)),
    ],
)
def test_success_requires_matching_sdk_acknowledgement(voice_sender, monkeypatch, receipt):
    voice_sender["bot"].send_voice.return_value = receipt
    result, requests = invoke(voice_sender, monkeypatch)
    assert result is False
    assert len(requests) == 1
    voice_sender["bot"].send_voice.assert_awaited_once()


def test_sdk_exception_is_sanitized_and_not_retried(voice_sender, monkeypatch, caplog):
    secret = "bot-secret-token private-dose"
    voice_sender["bot"].send_voice.side_effect = RuntimeError(secret)
    with caplog.at_level(logging.INFO):
        result, _ = invoke(voice_sender, monkeypatch)
    assert result is False
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    voice_sender["bot"].send_voice.assert_awaited_once()


def test_identity_lookup_failure_is_false_and_sanitized(voice_sender, monkeypatch, caplog):
    voice_sender["get_user_token"].side_effect = RuntimeError(TOKEN)
    result, requests = invoke(voice_sender, monkeypatch)
    assert result is False
    assert not requests
    assert TOKEN not in caplog.text
    voice_sender["bot"].send_voice.assert_not_awaited()


def test_maximum_length_text_is_not_clipped(voice_sender, monkeypatch):
    text = "x" * 1000
    result, _ = invoke(voice_sender, monkeypatch, text=text)
    assert result is True
    assert voice_sender["bot"].send_voice.call_args.kwargs["caption"] == text


def test_chunked_audio_over_limit_aborts_without_upload(voice_sender, monkeypatch):
    class Chunks(httpx.AsyncByteStream):
        def __init__(self):
            self.reads = 0

        async def __aiter__(self):
            for chunk in (b"x" * (6 * 1024 * 1024), b"y" * (5 * 1024 * 1024), b"z"):
                self.reads += 1
                yield chunk

        async def aclose(self):
            pass

    chunks = Chunks()
    response = httpx.Response(200, stream=chunks, headers={"content-type": "audio/mpeg"})
    result, requests = invoke(voice_sender, monkeypatch, response=response)
    assert result is False
    assert len(requests) == 1
    assert chunks.reads == 2
    voice_sender["bot"].send_voice.assert_not_awaited()
