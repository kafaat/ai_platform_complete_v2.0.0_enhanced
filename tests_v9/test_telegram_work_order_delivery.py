"""Import the real aiogram bot and verify honest work-order receipts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.unit
BOT = Path(__file__).resolve().parents[1] / "bots/telegram"


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.syspath_prepend(str(BOT))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:synthetic-unit-test-token")
    for key in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        monkeypatch.delenv(key, raising=False)
    spec = importlib.util.spec_from_file_location("telegram_delivery_test", BOT / "main.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    mod.user_cache[7] = {"token": "synthetic-user-token"}
    return mod


def context():
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        message=SimpleNamespace(message_id=11, chat=SimpleNamespace(id=22), edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "pest_task": {
                    "message_id": 11,
                    "field_id": "f-1",
                    "recommendation": {"id": "rec-1", "wo_type": "scouting"},
                }
            }
        )
    )
    return callback, state


@pytest.mark.asyncio
async def test_unlinked_user_cannot_create(bot, respx_mock):
    bot.user_cache.clear()
    callback, state = context()
    await bot.cb_create_pest_task(callback, state)
    callback.message.edit_text.assert_not_awaited()
    assert len(respx_mock.calls) == 0
    assert "/link" in callback.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_old_button_cannot_create_new_recommendation(bot, respx_mock):
    callback, state = context()
    callback.message.message_id = 999
    await bot.cb_create_pest_task(callback, state)
    callback.message.edit_text.assert_not_awaited()
    assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"persisted": False}),
        httpx.Response(200, json={"persisted": True}),
    ],
)
async def test_no_success_text_without_persisted_identifier(bot, response, respx_mock):
    respx_mock.post(f"{bot.PLATFORM_URL}/api/v1/work-orders/from-recommendation").mock(
        return_value=response
    )
    callback, state = context()
    await bot.cb_create_pest_task(callback, state)
    callback.message.edit_text.assert_not_awaited()
    assert "تعذر تأكيد" in callback.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_real_receipt_and_stable_retry_identity(bot, respx_mock):
    route = respx_mock.post(f"{bot.PLATFORM_URL}/api/v1/work-orders/from-recommendation").mock(
        return_value=httpx.Response(200, json={"persisted": True, "work_order_id": "wo-123"})
    )
    callback, state = context()
    await bot.cb_create_pest_task(callback, state)
    await bot.cb_create_pest_task(callback, state)
    assert "wo-123" in callback.message.edit_text.call_args.args[0]
    requests = [call.request for call in route.calls]
    assert requests[0].headers["idempotency-key"] == requests[1].headers["idempotency-key"]
    assert requests[0].headers["authorization"] == "Bearer synthetic-user-token"
    assert json.loads(requests[0].content)["field_id"] == "f-1"


def test_voice_handler_precedes_generic_text_handler(bot):
    callbacks = [handler.callback.__name__ for handler in bot.router.message.handlers]
    assert callbacks.index("cmd_voice") < callbacks.index("handle_natural_language")
