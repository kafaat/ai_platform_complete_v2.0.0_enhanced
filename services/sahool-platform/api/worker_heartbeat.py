"""Worker heartbeat — capability-aware liveness for Phase-runtime workers (V21 §2.1 / CT-06).

خلفيّة (تدقيق الحاويات V21): healthcheck العمّال كان ينجح بمجرّد وجود ``DATABASE_URL`` —
لا يُثبِت أنّ العمليّة حيّة ولا أنّ حلقة المعالجة تتحرّك. هنا يكتب العامل نبضةً (heartbeat)
كلّ دورة إلى ملفّ محلّيّ (last_poll_at + عدّادات + الحالة)، ويقرأ الـhealthcheck حداثتها
وحالتها بدل مجرّد وجود متغيّر بيئة. ملفّ لا جدول: الفحص خفيف ولا يتطلّب وصول قاعدة بيانات،
ويتوافق مع تقوية الحاويات لاحقاً (read_only + tmpfs على /tmp).

آليّة صادقة: عامل مُتعطّل/متوقّف ⇒ النبضة تتقادم ⇒ الفحص يفشل (لا يُخفى التوقّف). خطأ في
المُشغّل يُسجَّل في النبضة (last_error_at + failed_total + state) ثمّ يُعاد رفعه فتنهار الحلقة
وتتقادم النبضة — الحاوية تُعاد وفق سياسة restart.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_DIR = "/tmp/sahool_worker_heartbeats"


def heartbeat_dir() -> Path:
    return Path(os.getenv("WORKER_HEARTBEAT_DIR", DEFAULT_DIR))


def heartbeat_path(worker_name: str) -> Path:
    # اسم ملفّ آمن (لا شرطات مائلة) لكلّ عامل.
    safe = worker_name.replace("/", "_").replace(os.sep, "_")
    return heartbeat_dir() / f"{safe}.json"


def evaluate_heartbeat(
    data: dict[str, Any] | None, now_epoch: float, max_age_seconds: float
) -> tuple[bool, str]:
    """منطق صرف: هل النبضة صحّيّة؟ يعيد (ok, reason).

    غير صحّيّة إذا: غابت/فسدت · حالتها ``failed`` · تقادمت (now - last_poll_at > max_age).
    """
    if not data:
        return False, "missing_or_unreadable_heartbeat"
    state = str(data.get("current_state", "")).strip().lower()
    if state == "failed":
        return False, f"worker_state_failed:{data.get('last_error', '')[:120]}"
    last_poll = data.get("last_poll_at")
    if not isinstance(last_poll, (int, float)):
        return False, "heartbeat_missing_last_poll_at"
    age = now_epoch - float(last_poll)
    if age > max_age_seconds:
        return False, f"heartbeat_stale:age={int(age)}s>max={int(max_age_seconds)}s"
    return True, f"ok:age={int(max(age, 0))}s state={state or 'unknown'}"


def read_heartbeat(worker_name: str) -> dict[str, Any] | None:
    try:
        raw = heartbeat_path(worker_name).read_text(encoding="utf-8")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


class HeartbeatState:
    """يجمع عدّادات العامل ويكتب النبضة ذرّيّاً كلّ دورة (لا تبعيّة قاعدة بيانات)."""

    def __init__(self, worker_name: str) -> None:
        self.worker_name = worker_name
        self.instance_id = os.getenv("HOSTNAME") or str(os.getpid())
        self.started_at = time.time()
        self.last_poll_at: float | None = None
        self.last_success_at: float | None = None
        self.last_error_at: float | None = None
        self.processed_total = 0
        self.failed_total = 0
        self.current_state = "starting"
        self.last_error = ""

    def mark_poll(self, processed: int) -> None:
        now = time.time()
        self.last_poll_at = now
        self.last_success_at = now
        self.processed_total += int(processed or 0)
        self.current_state = "running"

    def mark_error(self, message: str) -> None:
        now = time.time()
        self.last_poll_at = now
        self.last_error_at = now
        self.failed_total += 1
        self.current_state = "failed"
        self.last_error = str(message)[:240]

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_name": self.worker_name,
            "instance_id": self.instance_id,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "last_poll_at": self.last_poll_at,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "processed_total": self.processed_total,
            "failed_total": self.failed_total,
            "current_state": self.current_state,
            "last_error": self.last_error,
        }

    def write(self) -> None:
        try:
            d = heartbeat_dir()
            d.mkdir(parents=True, exist_ok=True)
            path = heartbeat_path(self.worker_name)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)  # كتابة ذرّيّة
        except OSError:
            # لا نُسقِط حلقة العامل بسبب فشل كتابة النبضة (الفحص سيتقادم عندها بصدق).
            pass


def _cli_check(worker_name: str, max_age_seconds: float) -> int:
    data = read_heartbeat(worker_name)
    ok, reason = evaluate_heartbeat(data, time.time(), max_age_seconds)
    print(reason)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="worker heartbeat liveness check")
    sub = parser.add_subparsers(dest="cmd", required=True)
    chk = sub.add_parser("check", help="exit 0 if the worker heartbeat is fresh + not failed")
    chk.add_argument("--worker", required=True)
    chk.add_argument("--max-age", type=float, required=True, help="max heartbeat age in seconds")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.cmd == "check":
        return _cli_check(args.worker, args.max_age)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
