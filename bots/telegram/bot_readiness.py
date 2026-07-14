"""Capability-aware readiness heartbeat for the Telegram bot (container-audit V21 §2.3).

الخلفيّة (تدقيق الحاويات V21 §2.3): كان healthcheck بوت تيليجرام يفحص فقط أنّ
``/proc/1/cmdline`` يحوي ``main.py`` — يُثبِت وجود العمليّة لا جاهزيّتها الوظيفيّة.
عمليّة موجودة قد تكون: توكن تيليجرام مرفوض/منتهٍ، حلقة الاستطلاع (polling) متوقّفة،
أو حلقة الحدث (event loop) عالقة — وكلّها تنجح في فحص ``/proc/1/cmdline``.

الحلّ (مرآةً لـ``services/sahool-platform/api/worker_heartbeat.py``): البوت يتحقّق من
التوكن فعليّاً عبر ``getMe`` مرّة عند الإقلاع (نتيجة مُخزَّنة، لا نستطلع Telegram في كلّ
فحص)، ثمّ يكتب نبضةً (heartbeat) دوريّاً من داخل حلقة الحدث نفسها. يقرأ الـhealthcheck
حداثة النبضة + راية الجاهزيّة (``telegram_ready``) بدل مجرّد وجود العمليّة.

ما يُثبِته هذا الفحص بصدق:
  * التوكن قُبِل من Telegram (getMe نجح) — راية ``telegram_ready``.
  * حلقة الحدث حيّة والنبضة تتحرّك (النبضة تُكتب من مهمّة async في نفس الحلقة التي
    يعمل فيها ``start_polling``؛ إن ماتت الحلقة أو خرج الاستطلاع، تتقادم النبضة).
  * صلاحيّة التوكن يُعاد التحقّق منها دوريّاً بتردّد منخفض (لا إغراق لـTelegram API).

ما لا يُثبِته (صدقٌ في الحدود): لا يُثبِت تسليم رسالة فعليّة لمستخدم نهائيّ، ولا صحّة
webhook خارجيّ، ولا وصول NATS (لا عميل NATS في هذه العمليّة — لا نزيّف إشارته). وصول
Redis يُسجَّل كإشارة إعلاميّة فقط (``redis_ok``) ولا يُبوِّب الجاهزيّة، لأنّ للبوت بديلاً
``MemoryStorage`` عند تعذّر Redis فيظلّ يخدم.

فحص ملفّات نقيّ بمكتبة قياسيّة فقط (stdlib) — يعمل داخل الحاوية بلا تبعيّات إضافيّة،
ويتوافق مع تقوية الحاويات لاحقاً (read_only + tmpfs على /tmp).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_DIR = "/tmp/sahool_bot_readiness"
DEFAULT_BOT_NAME = "sahool-telegram-bot"


def readiness_dir() -> Path:
    return Path(os.getenv("TELEGRAM_HEARTBEAT_DIR", DEFAULT_DIR))


def readiness_path(bot_name: str = DEFAULT_BOT_NAME) -> Path:
    safe = bot_name.replace("/", "_").replace(os.sep, "_")
    return readiness_dir() / f"{safe}.json"


def evaluate_readiness(
    data: dict[str, Any] | None, now_epoch: float, max_age_seconds: float
) -> tuple[bool, str]:
    """منطق صرف: هل البوت جاهز؟ يعيد (ok, reason).

    غير جاهز إذا: غابت النبضة/فسدت · حالتها ``failed`` · التوكن غير مقبول
    (``telegram_ready`` كاذبة) · تقادمت النبضة (now - last_beat_at > max_age).
    """
    if not data:
        return False, "missing_or_unreadable_readiness_heartbeat"
    state = str(data.get("current_state", "")).strip().lower()
    if state == "failed":
        return False, f"bot_state_failed:{str(data.get('last_error', ''))[:120]}"
    if not data.get("telegram_ready"):
        return False, "telegram_token_not_accepted (getMe not yet succeeded)"
    last_beat = data.get("last_beat_at")
    if not isinstance(last_beat, (int, float)):
        return False, "readiness_missing_last_beat_at"
    age = now_epoch - float(last_beat)
    if age > max_age_seconds:
        return False, f"readiness_stale:age={int(age)}s>max={int(max_age_seconds)}s"
    redis_ok = data.get("redis_ok")
    redis_note = "" if redis_ok is None else f" redis_ok={bool(redis_ok)}"
    username = data.get("bot_username") or "?"
    return True, f"ready:age={int(max(age, 0))}s @{username}{redis_note}"


def read_readiness(bot_name: str = DEFAULT_BOT_NAME) -> dict[str, Any] | None:
    try:
        raw = readiness_path(bot_name).read_text(encoding="utf-8")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


class ReadinessState:
    """يجمع حالة جاهزيّة البوت ويكتب النبضة ذرّيّاً (بلا تبعيّة قاعدة بيانات)."""

    def __init__(self, bot_name: str = DEFAULT_BOT_NAME) -> None:
        self.bot_name = bot_name
        self.instance_id = os.getenv("HOSTNAME") or str(os.getpid())
        self.started_at = time.time()
        self.telegram_ready = False
        self.bot_username: str | None = None
        self.last_getme_ok_at: float | None = None
        self.last_beat_at: float | None = None
        self.last_error_at: float | None = None
        self.redis_ok: bool | None = None
        self.current_state = "starting"
        self.last_error = ""

    def mark_ready(self, username: str | None) -> None:
        """getMe نجح — التوكن مقبول من Telegram."""
        now = time.time()
        self.telegram_ready = True
        self.bot_username = username
        self.last_getme_ok_at = now
        self.last_beat_at = now
        if self.current_state != "failed":
            self.current_state = "ready"

    def mark_beat(self) -> None:
        """نبضة حياة من حلقة الحدث — تُثبِت أنّ الحلقة تتحرّك."""
        self.last_beat_at = time.time()
        if self.telegram_ready and self.current_state != "failed":
            self.current_state = "ready"

    def set_redis(self, ok: bool) -> None:
        self.redis_ok = bool(ok)

    def mark_error(self, message: str) -> None:
        now = time.time()
        self.last_beat_at = now
        self.last_error_at = now
        self.current_state = "failed"
        self.last_error = str(message)[:240]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "instance_id": self.instance_id,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "telegram_ready": self.telegram_ready,
            "bot_username": self.bot_username,
            "last_getme_ok_at": self.last_getme_ok_at,
            "last_beat_at": self.last_beat_at,
            "last_error_at": self.last_error_at,
            "redis_ok": self.redis_ok,
            "current_state": self.current_state,
            "last_error": self.last_error,
        }

    def write(self) -> None:
        try:
            d = readiness_dir()
            d.mkdir(parents=True, exist_ok=True)
            path = readiness_path(self.bot_name)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)  # كتابة ذرّيّة
        except OSError:
            # لا نُسقِط البوت بسبب فشل كتابة النبضة (الفحص سيتقادم عندها بصدق).
            pass


def _cli_check(bot_name: str, max_age_seconds: float) -> int:
    data = read_readiness(bot_name)
    ok, reason = evaluate_readiness(data, time.time(), max_age_seconds)
    print(reason)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="telegram bot readiness check")
    sub = parser.add_subparsers(dest="cmd", required=True)
    chk = sub.add_parser("check", help="exit 0 if the bot readiness heartbeat is fresh + ready")
    chk.add_argument("--bot", default=DEFAULT_BOT_NAME)
    chk.add_argument("--max-age", type=float, required=True, help="max heartbeat age in seconds")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.cmd == "check":
        return _cli_check(args.bot, args.max_age)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
