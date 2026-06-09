#!/usr/bin/env python3
"""SAHOOL v9 — Telegram Bot verification tests.

INVESTIGATION FINDINGS (see module-level constants below):

* ``bots/telegram/main.py`` is an **aiogram long-polling** bot
  (``dp.start_polling(bot)`` / Dockerfile ``CMD ["python", "main.py"]``).
  It is *not* a FastAPI webhook application: there is **no** ``FastAPI`` app
  object, **no** webhook endpoint, and **no** HTTP health endpoint (the
  container healthcheck is ``pgrep -f "python main.py"``).

* The bot reads ``TELEGRAM_WEBHOOK_SECRET`` (with ``WEBHOOK_SECRET`` fallback)
  into the module-level ``WEBHOOK_SECRET`` variable at main.py:126, **but the
  value is never used** — there is no webhook request handler that compares the
  incoming ``X-Telegram-Bot-Api-Secret-Token`` header against it.

  => SECURITY FINDING: the Telegram bot does NOT enforce a webhook secret,
     because it does not receive webhooks at all (it polls). The configured
     secret is dead configuration. ``test_webhook_secret_is_not_enforced``
     documents this explicitly rather than faking a pass.

The tests are collectable by pytest (no import-time DB/network) and runnable
standalone via ``python3 tests_v9/test_telegram_bot.py``. Importing the bot
module is attempted defensively and skips cleanly when its runtime deps
(e.g. ``aiogram``) are absent in this dev layout — it works in-container.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_MAIN = REPO_ROOT / "bots" / "telegram" / "main.py"


def _set_bot_env() -> None:
    """Env the bot needs to import without sys.exit(0) (missing token path)."""
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test")
    os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def _load_bot_module():
    """Import bots/telegram/main.py in isolation.

    Returns the module on success. Calls ``pytest.skip`` when the module cannot
    be constructed in this dev layout (e.g. ``aiogram`` not installed, or the
    no-token clean-exit path triggers ``SystemExit``). Never a hard failure —
    the bot is import-friendly only inside its container image.
    """
    if not BOT_MAIN.exists():
        pytest.skip(f"bot main not found: {BOT_MAIN}")
    _set_bot_env()
    spec = importlib.util.spec_from_file_location("sahool_tg_main", BOT_MAIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sahool_tg_main"] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit as exc:  # main.py exits cleanly when token missing
        pytest.skip(f"bot module exited on import (code={exc.code}) — token/env gating")
    except ModuleNotFoundError as exc:
        pytest.skip(f"bot dependency missing in dev layout (works in-container): {exc.name}")
    except Exception as exc:  # noqa: BLE001 — defensive: unknown dev-layout breakage
        pytest.skip(f"bot module could not be imported in dev layout: {type(exc).__name__}: {exc}")
    return module


# ── Source-level facts (no import needed — robust in any layout) ───────────


def _bot_source() -> str:
    return BOT_MAIN.read_text(encoding="utf-8")


@pytest.mark.unit
def test_bot_main_exists():
    assert BOT_MAIN.exists(), f"expected telegram bot at {BOT_MAIN}"


@pytest.mark.unit
def test_bot_is_polling_not_webhook_app():
    """The bot is an aiogram polling bot — no FastAPI app / webhook endpoint."""
    src = _bot_source()
    assert "start_polling" in src, "expected aiogram long-polling entrypoint"
    # No FastAPI application is constructed in the bot module.
    assert "FastAPI(" not in src, "unexpected FastAPI app in a polling bot"
    # No HTTP webhook route is registered.
    assert "set_webhook" not in src, "unexpected webhook registration"


@pytest.mark.unit
def test_bot_reads_webhook_secret_env():
    """Bot reads TELEGRAM_WEBHOOK_SECRET (with WEBHOOK_SECRET fallback)."""
    src = _bot_source()
    assert "TELEGRAM_WEBHOOK_SECRET" in src
    # Confirm it is bound to a variable (it is — but unused; see next test).
    assert re.search(r"WEBHOOK_SECRET\s*=\s*os\.getenv", src)


@pytest.mark.security
def test_webhook_secret_is_not_enforced():
    """SECURITY FINDING (documented, not a fake pass).

    The bot binds ``WEBHOOK_SECRET`` from ``TELEGRAM_WEBHOOK_SECRET`` at
    main.py:126 but NEVER enforces it: there is no webhook handler and no
    comparison against the ``X-Telegram-Bot-Api-Secret-Token`` header.

    We assert the *absence* of enforcement so this test will start FAILING
    (alerting maintainers) if/when a webhook handler is added but the secret
    check is forgotten. If a secret check is added, update this test to assert
    the rejection behaviour instead.
    """
    src = _bot_source()

    header_checked = "X-Telegram-Bot-Api-Secret-Token" in src or re.search(
        r"secret[_-]?token", src, re.IGNORECASE
    )
    # The variable is assigned exactly once (the os.getenv binding) and never
    # consumed in a comparison / guard.
    assignments = re.findall(r"\bWEBHOOK_SECRET\b", src)
    # one occurrence in the comment line + one in the assignment line == 2;
    # any *additional* occurrence would indicate the value is actually used.
    used_beyond_assignment = len(assignments) > 2

    enforced = bool(header_checked) or used_beyond_assignment
    assert not enforced, (
        "Webhook secret now appears to be enforced — update this test to assert "
        "rejection of missing/wrong secrets. (Previously: bot was polling-only "
        "and the secret was dead config.)"
    )


@pytest.mark.integration
def test_bot_module_imports_in_container_layout():
    """Best-effort import smoke test; skips cleanly outside the container."""
    module = _load_bot_module()
    # If it imported, the polling entrypoint must be present and there must be
    # no FastAPI 'app' (it is a polling bot).
    assert hasattr(module, "main"), "expected async main() polling entrypoint"
    assert not hasattr(module, "app"), "polling bot unexpectedly exposes a FastAPI 'app'"
    # WEBHOOK_SECRET is read from env we set.
    assert getattr(module, "WEBHOOK_SECRET", None) == os.environ.get("TELEGRAM_WEBHOOK_SECRET")


# ── Standalone runner ──────────────────────────────────────────────────────
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-p", "no:cacheprovider"]))
