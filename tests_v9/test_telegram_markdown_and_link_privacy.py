"""S13 — Telegram bot: MarkdownV2 escaping of dynamic text + /link only in private chats.

Imports the real aiogram bot module (no network, no fake DB) and drives the handlers
with ``SimpleNamespace`` messages whose send methods are ``AsyncMock``s.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit
BOT = Path(__file__).resolve().parents[1] / "bots/telegram"
RESERVED = "_*[]()~`>#+-=|{}.!"


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.syspath_prepend(str(BOT))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:synthetic-unit-test-token")
    for key in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        monkeypatch.delenv(key, raising=False)
    spec = importlib.util.spec_from_file_location("telegram_md2_test", BOT / "main.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    mod.user_cache.clear()
    return mod


def unescaped_reserved(text: str) -> list[str]:
    """Reserved MarkdownV2 chars that are NOT preceded by an escaping backslash."""
    bad, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch in RESERVED:
            bad.append(ch)
        i += 1
    return bad


def message(chat_type: str = "private", text: str = "x"):
    wait = SimpleNamespace(edit_text=AsyncMock())
    return SimpleNamespace(
        text=text,
        chat=SimpleNamespace(id=22, type=chat_type),
        from_user=SimpleNamespace(id=7, username="u"),
        answer=AsyncMock(return_value=wait),
        delete=AsyncMock(),
        wait=wait,
    )


def fsm(data: dict | None = None):
    return SimpleNamespace(
        clear=AsyncMock(),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
        get_data=AsyncMock(return_value=data or {}),
    )


# ── escaper table ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain", "plain"),
        ("a.b", "a\\.b"),
        ("1-2", "1\\-2"),
        ("(x)!", "\\(x\\)\\!"),
        ("_*[]()~`>#+-=|{}.!", "".join("\\" + c for c in RESERVED)),
        ("back\\slash", "back\\\\slash"),
        ("\\.", "\\\\\\."),
        ("مرحباً بك في سهول.", "مرحباً بك في سهول\\."),
        ("الحالة: جيّدة (٧٠٪) - تابع!", "الحالة: جيّدة \\(٧٠٪\\) \\- تابع\\!"),
        ("🌾 *قمح*", "🌾 \\*قمح\\*"),
        (None, ""),
    ],
)
def test_md2_escaper_table(bot, raw, escaped):
    assert bot._md2(raw) == escaped
    if raw is not None:
        assert unescaped_reserved(bot._md2(raw)) == []
        assert bot._md2_to_plain(bot._md2(raw)) == raw


def test_link_injection_is_rendered_literal(bot):
    out = bot._md2("[اضغط هنا](https://evil.example/login?x=1)")
    assert out == "\\[اضغط هنا\\]\\(https://evil\\.example/login?x\\=1\\)"
    assert unescaped_reserved(out) == []


# ── model replies are escaped end to end ──────────────────────

INJECTION = "النتيجة جيّدة. [سجّل الدخول](https://evil.example) *عاجل* - 50% (تقريباً)!"


async def test_model_reply_is_escaped_in_natural_language_handler(bot, monkeypatch):
    monkeypatch.setattr(bot, "call_supervisor", AsyncMock(return_value={"response_ar": INJECTION}))
    msg = message(text="كيف حال حقلي؟")
    await bot.handle_natural_language(msg)
    sent = msg.wait.edit_text.call_args.args[0]
    assert unescaped_reserved(sent) == []
    assert "\\[سجّل الدخول\\]\\(https://evil\\.example\\)" in sent
    assert bot._md2_to_plain(sent) == INJECTION


@pytest.mark.parametrize("handler", ["cmd_weather", "cmd_market"])
async def test_model_reply_is_escaped_in_menu_handlers(bot, monkeypatch, handler):
    monkeypatch.setattr(bot, "call_supervisor", AsyncMock(return_value={"response_ar": INJECTION}))
    msg = message()
    await getattr(bot, handler)(msg)
    sent = msg.wait.edit_text.call_args.args[0]
    assert unescaped_reserved(sent) == []


async def test_error_text_in_code_span_is_escaped(bot, monkeypatch):
    monkeypatch.setattr(bot, "call_supervisor", AsyncMock(side_effect=RuntimeError("bad `x` \\ y")))
    msg = message()
    await bot.handle_natural_language(msg)
    sent = msg.wait.edit_text.call_args.args[0]
    assert "bad \\`x\\` \\\\ y" in sent


# ── plain-text fallback on "can't parse entities" ─────────────


async def test_parse_error_falls_back_to_plain_text_once(bot):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SendMessage

    calls = []

    async def make_request(_bot, method):
        calls.append(method)
        if len(calls) == 1:
            raise TelegramBadRequest(method, "Bad Request: can't parse entities: x")
        return "ok"

    method = SendMessage(chat_id=1, text="تم الحفظ\\. *مرحبا*")
    out = await bot.MarkdownV2PlainFallback()(make_request, bot.bot, method)
    assert out == "ok"
    assert len(calls) == 2
    assert calls[1].parse_mode is None
    assert calls[1].text == "تم الحفظ. *مرحبا*"


async def test_other_bad_requests_are_not_retried(bot):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SendMessage

    make_request = AsyncMock(side_effect=TelegramBadRequest(None, "Bad Request: chat not found"))
    with pytest.raises(TelegramBadRequest):
        await bot.MarkdownV2PlainFallback()(make_request, bot.bot, SendMessage(chat_id=1, text="t"))
    assert make_request.await_count == 1

    make_request = AsyncMock(side_effect=TelegramBadRequest(None, "can't parse entities"))
    plain = SendMessage(chat_id=1, text="t", parse_mode=None)
    with pytest.raises(TelegramBadRequest):
        await bot.MarkdownV2PlainFallback()(make_request, bot.bot, plain)
    assert make_request.await_count == 1


def test_fallback_is_registered_on_the_bot_session(bot):
    assert any(isinstance(m, bot.MarkdownV2PlainFallback) for m in bot.bot.session.middleware)


# ── /link refuses outside private chats ───────────────────────


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
async def test_link_refused_in_group_chat(bot, chat_type):
    msg, state = message(chat_type, "/link"), fsm()
    await bot.cmd_link(msg, state)
    state.set_state.assert_not_awaited()
    reply = msg.answer.call_args.args[0]
    assert "خاصّة" in reply and "كلمة المرور" not in reply
    assert unescaped_reserved(reply) == []
    msg.delete.assert_awaited()


async def test_link_refusal_survives_missing_delete_rights(bot):
    from aiogram.exceptions import TelegramBadRequest

    msg, state = message("group", "/link"), fsm()
    msg.delete.side_effect = TelegramBadRequest(None, "message can't be deleted")
    await bot.cmd_link(msg, state)
    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


async def test_link_prompts_for_email_in_private_chat(bot):
    msg, state = message("private", "/link"), fsm()
    await bot.cmd_link(msg, state)
    state.set_state.assert_awaited_once_with(bot.LinkStates.waiting_email)


async def test_password_in_group_is_deleted_never_used_never_echoed(bot, monkeypatch):
    link = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "link_account", link)
    secret = "S3cret-pass!"
    msg, state = message("group", secret), fsm({"email": "a@b.c"})
    await bot.link_password(msg, state)
    link.assert_not_awaited()
    msg.delete.assert_awaited()
    state.clear.assert_awaited()
    assert all(secret not in str(c) for c in msg.answer.call_args_list)


async def test_private_password_is_deleted_and_not_echoed(bot, monkeypatch):
    monkeypatch.setattr(bot, "link_account", AsyncMock(return_value=True))
    secret = "S3cret-pass!"
    msg, state = message("private", secret), fsm({"email": "a@b.c"})
    await bot.link_password(msg, state)
    msg.delete.assert_awaited()
    reply = msg.answer.call_args.args[0]
    assert secret not in reply
    assert unescaped_reserved(reply) == []
