"""دوالّ OTP النقيّة (تأكيد البريد/الهاتف) — معزولة عن FastAPI/Redis/الشبكة.

استُخرِجت من main.py كي تُختبَر وحدةً (pytest -m unit) دون تثبيت fastapi: كان
استيراد main.py في الاختبار يكسر مهمّة الـUnit في CI (لا fastapi هناك). main.py
يستورد هذه الدوالّ، والاختبار يستوردها مباشرةً من هنا.
"""

from __future__ import annotations

import os
import secrets

# ── ضبط OTP ──────────────────────────────────────────────────────
OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "600"))  # 10 دقائق
OTP_LENGTH = 6  # رمز من ٦ أرقام
OTP_MAX_REQUESTS = int(os.getenv("OTP_MAX_REQUESTS", "5"))  # طلبات/ساعة لكلّ مستخدم+قناة


def generate_otp(length: int = OTP_LENGTH) -> str:
    """يولّد رمز OTP رقميّاً آمناً تشفيريّاً بطول ثابت (أصفار بادئة محفوظة).

    secrets.randbelow ⇒ توزيع منتظم بلا انحياز، ونملأ بأصفار يساريّة حتى
    لا يتسرّب طول الرمز (مثلاً '007421'). دالّة نقيّة — لا أثر جانبيّ.
    """
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def normalize_otp(raw: str) -> str:
    """يُشذّب إدخال المستخدم: يزيل الفراغات والمسافات، يُبقي الأرقام فقط."""
    return "".join(ch for ch in raw.strip() if ch.isdigit())


def is_valid_otp_shape(code: str, length: int = OTP_LENGTH) -> bool:
    """يتحقّق أنّ الرمز (بعد التشذيب) رقميّ بالطول المتوقّع تماماً."""
    return len(code) == length and code.isdigit()


def otp_redis_key(user_id: int, channel: str) -> str:
    """مفتاح Redis لرمز التحقّق — مُنطّق بالمستخدم والقناة (بريد/هاتف منفصلان)."""
    return f"sahool:otp:{channel}:{user_id}"


def otp_codes_match(submitted: str, stored: str) -> bool:
    """مقارنة ثابتة الزمن لرمزَي OTP (بعد التشذيب) — تمنع تسريب التوقيت."""
    return secrets.compare_digest(normalize_otp(submitted), stored)
