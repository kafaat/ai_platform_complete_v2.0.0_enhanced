"""Voice notifications require provider acceptance, never synthesis alone.

Execute the production function without booting the agent's NATS/DB/tracing
services. HTTPX MockTransport handles every request; no provider is contacted.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import re
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
BOT_TOKEN = "test-voice-bot-token"
CALLER_TOKEN = "test-caller-token"
CHAT_ID = 123
AUDIO = b"ID3test-audio"


def receipt(chat_id=CHAT_ID, message_id=42):
    return {
        "ok": True,
        "result": {
            "chat": {"id": chat_id},
            "message_id": message_id,
            "voice": {"file_id": "voice-file"},
        },
    }


@pytest.fixture
def delivery(monkeypatch):
    monkeypatch.setenv("TTS_URL", "http://tts-test:8000")
    tree = ast.parse((ROOT / "agents/notification/agent.py").read_text(encoding="utf-8"))
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name
        in {
            "_TelegramHTTPLogFilter",
            "_install_telegram_http_log_redaction",
            "send_tts_voice",
            "send_telegram",
        }
    ]
    namespace = {
        "os": os,
        "re": re,
        "logging": logging,
        "httpx": httpx,
        "TG_TOKEN": BOT_TOKEN,
        "logger": logging.getLogger("test-voice-receipt"),
    }
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "agent.py", "exec"), namespace)
    http_logger = logging.getLogger("httpx")
    previous_filters = list(http_logger.filters)
    namespace["_install_telegram_http_log_redaction"]()
    try:
        yield namespace
    finally:
        http_logger.filters[:] = previous_filters


def invoke(
    delivery,
    monkeypatch,
    *,
    tts_response=None,
    send_response=None,
    text="جرعة معتمدة",
    chat_id=CHAT_ID,
    caller_token=CALLER_TOKEN,
):
    requests = []

    def handler(request):
        requests.append(request)
        response = tts_response if len(requests) == 1 else send_response
        if isinstance(response, Exception):
            raise response
        if response is not None:
            return response
        if len(requests) == 1:
            return httpx.Response(200, content=AUDIO, headers={"content-type": "audio/mpeg"})
        return httpx.Response(200, json=receipt(chat_id))

    actual_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    accepted = asyncio.run(delivery["send_tts_voice"](text, chat_id, caller_token=caller_token))
    return accepted, requests


def test_true_requires_uploaded_audio_and_matching_provider_receipt(delivery, monkeypatch):
    text = "كمية 0.75 مل لكل لتر؛ مدة 7 أيام"
    accepted, requests = invoke(delivery, monkeypatch, text=text)
    assert accepted is True
    assert len(requests) == 2
    assert requests[0].url.host == "tts-test"
    assert json.loads(requests[0].content)["text"] == text
    assert requests[0].headers["Authorization"] == f"Bearer {CALLER_TOKEN}"
    assert "X-Agent-Token" not in requests[0].headers
    upload = requests[1]
    assert upload.url == f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice"
    assert "Authorization" not in upload.headers
    assert "X-Agent-Token" not in upload.headers
    assert AUDIO in upload.content
    assert b'name="voice"; filename="recommendation.mp3"' in upload.content
    assert b'name="chat_id"\r\n\r\n123' in upload.content
    assert text.encode() in upload.content  # Text is sent unchanged as caption.


@pytest.mark.parametrize(
    "text,chat_id,caller_token",
    [
        ("", CHAT_ID, CALLER_TOKEN),
        ("  ", CHAT_ID, CALLER_TOKEN),
        ("1" * 1001, CHAT_ID, CALLER_TOKEN),
        (None, CHAT_ID, CALLER_TOKEN),
        ("text", 0, CALLER_TOKEN),
        ("text", True, CALLER_TOKEN),
        ("text", "123", CALLER_TOKEN),
        ("text", CHAT_ID, ""),
        ("text", CHAT_ID, " "),
        ("text", CHAT_ID, None),
    ],
)
def test_invalid_input_is_rejected_before_synthesis(
    delivery, monkeypatch, text, chat_id, caller_token
):
    accepted, requests = invoke(
        delivery, monkeypatch, text=text, chat_id=chat_id, caller_token=caller_token
    )
    assert accepted is False
    assert requests == []


def test_missing_bot_token_rejects_before_synthesis(delivery, monkeypatch):
    delivery["TG_TOKEN"] = ""
    accepted, requests = invoke(delivery, monkeypatch)
    assert accepted is False
    assert requests == []


def test_original_positional_api_without_caller_identity_fails_closed(delivery):
    assert asyncio.run(delivery["send_tts_voice"]("text", CHAT_ID, "yemeni_male")) is False


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, content=AUDIO),
        httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"}),
        httpx.Response(200, content=b"error", headers={"content-type": "application/json"}),
        httpx.Response(200, content=b"RIFFwave", headers={"content-type": "audio/wav"}),
        httpx.Response(
            200, content=b"x" * (10 * 1024 * 1024 + 1), headers={"content-type": "audio/mpeg"}
        ),
        httpx.ConnectError("synthesis failed"),
    ],
)
def test_invalid_synthesis_never_attempts_delivery(delivery, monkeypatch, response):
    accepted, requests = invoke(delivery, monkeypatch, tts_response=response)
    assert accepted is False
    assert len(requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"ok": False},
        {"ok": 1, "result": receipt()["result"]},
        {"ok": True},
        {"ok": True, "result": []},
        receipt(chat_id=999),
        receipt(message_id=0),
        receipt(message_id=True),
        receipt(message_id="42"),
        {"ok": True, "result": {"chat": {"id": CHAT_ID}, "message_id": 42}},
        {
            "ok": True,
            "result": {"chat": {"id": CHAT_ID}, "message_id": 42, "voice": {"file_id": ""}},
        },
        {
            "ok": True,
            "result": {
                "chat": {"id": str(CHAT_ID)},
                "message_id": 42,
                "voice": {"file_id": "voice"},
            },
        },
    ],
)
def test_http_success_without_valid_matching_receipt_is_false(delivery, monkeypatch, payload):
    accepted, requests = invoke(
        delivery, monkeypatch, send_response=httpx.Response(200, json=payload)
    )
    assert accepted is False
    assert len(requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"ok": False}),
        httpx.Response(200, content=b"not json"),
        httpx.ReadTimeout(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice private-dose"),
    ],
)
def test_delivery_error_is_false_without_automatic_retry_or_secret_logging(
    delivery, monkeypatch, caplog, response
):
    with caplog.at_level(logging.INFO):
        accepted, requests = invoke(delivery, monkeypatch, send_response=response)
    assert accepted is False
    assert len(requests) == 2
    assert BOT_TOKEN not in caplog.text
    assert CALLER_TOKEN not in caplog.text
    assert "private-dose" not in caplog.text


def test_maximum_text_length_and_negative_chat_id_are_not_clipped(delivery, monkeypatch):
    text = "x" * 1000
    accepted, requests = invoke(delivery, monkeypatch, text=text, chat_id=-123)
    assert accepted is True
    assert json.loads(requests[0].content)["text"] == text


def test_httpx_info_request_logging_redacts_bot_url_only(delivery, monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        accepted, requests = invoke(delivery, monkeypatch)
    assert accepted is True
    assert len(requests) == 2
    assert BOT_TOKEN not in caplog.text
    assert "https://api.telegram.org/bot[REDACTED]/sendVoice" in caplog.text
    assert "http://tts-test:8000/v1/tts/synthesize" in caplog.text


def test_httpx_exception_url_is_redacted_without_mutating_exception(delivery, caplog):
    original = RuntimeError(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice")
    with caplog.at_level(logging.INFO):
        try:
            raise original
        except RuntimeError:
            logging.getLogger("httpx").info("Transport request failed", exc_info=True)
    assert BOT_TOKEN not in caplog.text
    assert "Transport request failed" in caplog.text
    assert "/bot[REDACTED]/sendVoice" in caplog.text
    assert BOT_TOKEN in str(original)  # The filter does not mutate caller objects.


def test_http_redaction_preserves_unrelated_records_and_is_idempotent(delivery):
    logger = logging.getLogger("httpx")
    before_level = logger.level
    before_filters = len(logger.filters)
    delivery["_install_telegram_http_log_redaction"]()
    assert len(logger.filters) == before_filters
    assert logger.level == before_level
    filter_instance = next(
        item for item in logger.filters if getattr(item, "_sahool_telegram_redaction", False)
    )
    args = ("https://example.org/botpublic/sendVoice",)
    record = logging.LogRecord("httpx", logging.INFO, "test", 1, "GET %s", args, None)
    assert filter_instance.filter(record) is True
    assert record.msg == "GET %s"
    assert record.args is args


def test_text_telegram_exception_does_not_expose_credential_url(delivery, monkeypatch, caplog):
    def fail(request):
        raise httpx.ReadTimeout(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage private-text")

    actual_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(fail)),
    )
    with caplog.at_level(logging.INFO):
        accepted = asyncio.run(delivery["send_telegram"]("123", "private-text"))
    assert accepted is False
    assert BOT_TOKEN not in caplog.text
    assert "private-text" not in caplog.text
    assert "ReadTimeout" in caplog.text
