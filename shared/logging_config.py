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
import re
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
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = redact_secrets(self.formatStack(record.stack_info))
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


# ── تنقيح الأسرار من السجلّ (S9) ─────────────────────────────────
# httpx يسجّل رابط كلّ طلب بمستوى INFO؛ سرّ في الاستعلام (ZLMediaKit ``secret=``…) كان
# يُكتَب في السجلّ عند كلّ فحص جاهزيّة. حزام ثانٍ بعد نقل السرّ إلى جسم الطلب: أيّ
# ``<param>=<قيمة>`` لمعامِل سرّيّ معروف يُقنَّع قبل الكتابة، أيّاً كان المُسجِّل.
_SECRET_PARAMS = (
    "secret",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "jwt",
    "signature",
    "sig",
)
# القيمة كلّها حتّى ``&`` أو مسافة أو علامة اقتباس أو نهاية النصّ — لا تقف عند ترقيم داخليّ:
# صنفٌ سابق وقف عند ``,`` ``;`` ``)`` ``<`` ``>`` فكان ``password=prefix;CANARY`` يُكتَب
# ``password=***;CANARY`` (مراجعة PR #1324). الإفراط في التقنيع آمن؛ التفريط تسريب.
_SECRET_PARAM_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(" + "|".join(_SECRET_PARAMS) + r")=([^&\s\"']+)"
)
REDACTED = "***"


def redact_secrets(text: str) -> str:
    """يقنّع قيم المعامِلات السرّيّة المعروفة (``secret=…`` → ``secret=***``)."""
    return _SECRET_PARAM_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)


class SecretRedactionFilter(logging.Filter):
    """مرشّح معالِج: يُعيد كتابة الرسالة المنسَّقة مُنقَّحةً (الاستثناء يُنقّحه المنسِّق).

    لا يُسقط سجلّاً أبداً.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — رسالة معطوبة: اتركها لمعالجة logging المعتادة
            return True
        redacted = redact_secrets(msg)
        if redacted != msg:
            record.msg, record.args = redacted, None
        return True


class _LibraryNoiseFilter(logging.Filter):
    """مرشّح معالِج: يُسقط سجلّات httpx/httpcore دون عتبتها **في هذا المعالِج وحده**.

    httpx يسجّل رابط كلّ طلب INFO (وhttpcore DEBUG) وقد يحمل الرابط سرّاً — S9. لا نخفض
    مستوى المُسجِّلَين العامَّين (``setLevel``): ذلك حالةٌ عالميّة تُسكِت معالِجات أخرى في
    العمليّة نفسها ومرشّحاتها (مثل تنقيح رابط بوت Telegram في الوكيل) — فالخفض هنا يخصّ
    ما يكتبه معالِج ``setup_logging`` فقط.
    """

    _PREFIXES = ("httpx", "httpcore")

    def __init__(self, threshold: int) -> None:
        super().__init__()
        self._threshold = threshold

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        noisy = any(name == p or name.startswith(p + ".") for p in self._PREFIXES)
        return not noisy or record.levelno >= self._threshold


def _level_from_env(var: str, default: int) -> int:
    raw = os.getenv(var, "")
    level = logging.getLevelName(raw.upper()) if raw else default
    return level if isinstance(level, int) else default


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
    handler.addFilter(SecretRedactionFilter())
    # httpx/httpcore يسجّلان رابط كلّ طلب INFO/DEBUG (قد يحمل أسراراً في الاستعلام) — S9.
    # مرشّحٌ على هذا المعالِج لا ``setLevel`` عالميّ (انظر ``_LibraryNoiseFilter``).
    handler.addFilter(_LibraryNoiseFilter(_level_from_env("HTTPX_LOG_LEVEL", logging.WARNING)))
    root.addHandler(handler)

    # اخفض ضجيج مكتبات معروفة (uvicorn) إن لزم
    logging.getLogger("uvicorn.access").setLevel(os.getenv("UVICORN_ACCESS_LEVEL", "WARNING"))

    return logging.getLogger(service)
