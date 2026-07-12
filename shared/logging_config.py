"""
shared/logging_config.py — تسجيل منظّم موحّد (JSON) لكلّ خدمات SAHOOL.

يحلّ مشكلتين:
  ١. عدم الاتّساق: بعض الخدمات basicConfig نصّي، أخرى بلا تهيئة.
  ٢. الهشاشة: تنسيق format-string القديم يُنتج JSON مكسوراً حين تحوي الرسالة
     اقتباسات/أسطراً جديدة (مثل '{"msg":"حقل "A" فشل"}' = JSON غير صالح).

الحلّ: JSONFormatter يستخدم json.dumps (يهرّب كلّ شيء صحيحاً) + حقول موحّدة:
  ts, level, service, logger, message, + أيّ حقول إضافيّة (extra) + الاستثناء.

الاستخدام في أيّ خدمة:
    from shared.logging_config import setup_logging
    logger = setup_logging("auth")            # في أعلى main.py
    logger.info("بدء الخدمة", extra={"port": 8089})

متوافق رجوعيّاً: يبقى logging.getLogger القياسي يعمل؛ نضبط المعالِج فقط.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

# الحقول القياسيّة في LogRecord (نستثنيها عند جمع الحقول الإضافيّة)
_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


class JSONFormatter(logging.Formatter):
    """ينسّق سجلّ اللوق ككائن JSON صالح دائماً (يهرّب الاقتباسات/الأسطر)."""

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # الاستثناء (لو وُجد) — traceback كامل بدل ابتلاعه
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        # الحقول الإضافيّة المُمرَّرة عبر extra={...}
        for key, val in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                try:
                    json.dumps(val)  # تأكّد أنّها قابلة للتسلسل
                    payload[key] = val
                except (TypeError, ValueError):
                    payload[key] = repr(val)
        # ensure_ascii=False ليبقى العربي مقروءاً لا \uXXXX
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str, level: str | None = None) -> logging.Logger:
    """يضبط تسجيل JSON موحّداً للخدمة، ويعيد logger الجذر للخدمة.

    level: يؤخذ من المعامل أو متغيّر البيئة LOG_LEVEL أو INFO افتراضيّاً.
    آمن للاستدعاء المتكرّر (لا يُكرّر المعالِجات).
    """
    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    root = logging.getLogger()
    root.setLevel(log_level)

    # أزِل المعالِجات السابقة (مثل basicConfig) لتجنّب لوق مزدوج
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service))
    root.addHandler(handler)

    # اخفض ضجيج مكتبات معروفة (uvicorn/httpx) إن لزم
    logging.getLogger("uvicorn.access").setLevel(os.getenv("UVICORN_ACCESS_LEVEL", "WARNING"))

    return logging.getLogger(service)
