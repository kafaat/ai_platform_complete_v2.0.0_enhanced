"""مُرسِلات الإشعارات (بريد SMTP / SMS عبر HTTP) لخدمة auth — معزولة عن FastAPI.

استُخرِجت من main.py لتقليص ضخامته وفصل منطق التسليم (I/O) عن مسارات HTTP وحالة
الخدمة المتغيّرة (Redis/المسبح). لا تعتمد هذه الدوالّ على `_redis`/`_pool`/`app`
ولا على JWT — تقرأ ضبط SMTP/SMS من البيئة فقط (نفس مفاتيح main.py حرفيّاً) — لذا
آمن استخراجها مع حفظ السلوك. main.py يعيد تصديرها فتبقى متاحة كـ`main.<name>`.

السلوك محفوظ: نفس التوقيعات، نفس مفاتيح البيئة، نفس الرسائل، نفس قيم الإرجاع.
"""

from __future__ import annotations

import asyncio
import logging
import os

# OTP_TTL_SECONDS مصدره الوحيد otp.py (لا تكرار للثابت) — يُستعمل في نصّ الرسائل.
from otp import OTP_TTL_SECONDS

# تسجيل منظّم موحّد (JSON) — نفس fallback main.py الآمن لو غابت الحزمة المشتركة.
try:
    from shared.logging_config import setup_logging

    logger = setup_logging("auth")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"auth","level":"%(levelname)s","msg":"%(message)s"}',
    )
    logger = logging.getLogger("auth")

# ── ضبط SMTP/SMS (نفس مفاتيح البيئة المستعملة في main.py حرفيّاً) ──────
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@sahool.ye")
# مزوّد SMS عامّ عبر HTTP (Twilio/مزوّد محلّيّ) — يُفعَّل عند ضبط العنوان والمفتاح.
SMS_PROVIDER_URL = os.getenv("SMS_PROVIDER_URL", "")
SMS_API_KEY = os.getenv("SMS_API_KEY", "")
SMS_FROM = os.getenv("SMS_FROM", "SAHOOL")


# ── Password Reset Helpers ─────────────────────────────────────
async def send_reset_email(email: str, token: str) -> bool:
    """Send password reset email via SMTP."""
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("SMTP not configured — cannot send reset email")
        return False
    try:
        from email.mime.text import MIMEText

        import aiosmtplib

        reset_url = (
            f"{os.getenv('FRONTEND_URL', 'https://app.sahool.ye')}/reset-password?token={token}"
        )
        body = f"""
مرحباً،

طلبت إعادة تعيين كلمة المرور لحساب SAHOOL المرتبط بـ {email}.

رابط إعادة التعيين (صالح 30 دقيقة):
{reset_url}

إذا لم تطلب ذلك، تجاهل هذا البريد.

فريق SAHOOL — منصة الزراعة الذكية اليمنية
"""
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "SAHOOL — إعادة تعيين كلمة المرور"
        msg["From"] = SMTP_FROM
        msg["To"] = email

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info(f"Reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


# ── OTP Verification Helpers (تأكيد البريد/الهاتف) ─────────────
# دوالّ تسليم الرمز عبر القنوات (بريد SMTP / SMS عبر HTTP).


async def _send_otp_email(destination: str, code: str) -> bool:
    """يُرسِل OTP بريداً عبر SMTP (نفس نمط send_reset_email)."""
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("OTP بريد: SMTP غير مضبوط — لم يُرسَل (destination=%s)", destination)
        return False
    try:
        from email.mime.text import MIMEText

        import aiosmtplib

        body = (
            f"رمز تحقّق SAHOOL هو: {code}\n\n"
            f"صالح لمدّة {OTP_TTL_SECONDS // 60} دقيقة. لا تشاركه مع أحد.\n\n"
            "فريق SAHOOL — منصّة الزراعة الذكيّة اليمنيّة"
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "SAHOOL — رمز التحقّق"
        msg["From"] = SMTP_FROM
        msg["To"] = destination
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info("OTP بريد أُرسِل إلى %s", destination)
        return True
    except Exception as e:
        logger.error("فشل إرسال OTP بريداً: %s", e)
        return False


def _post_sms_blocking(phone: str, message: str) -> bool:
    """POST متزامن لمزوّد SMS عامّ (urllib — بلا تبعيّة جديدة)."""
    import json
    import urllib.error
    import urllib.request

    # المفتاح في ترويسة Authorization فقط — لا نُكرّره في الجسم (يقلّل سطح التعرّض).
    payload = json.dumps({"to": phone, "from": SMS_FROM, "message": message}).encode()
    req = urllib.request.Request(
        SMS_PROVIDER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SMS_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.URLError as e:
        logger.error("فشل إرسال OTP عبر SMS: %s", e)
        return False


def _is_valid_phone(destination: str) -> bool:
    """رقم هاتف صالح للإرسال؟ (أرقام دوليّة E.164 مبسّطة) — يستبعد النوائب مثل
    'user:{id}' المستعمَلة قبل حفظ أرقام الهواتف فعليّاً."""
    d = destination.strip().lstrip("+")
    return d.isdigit() and 7 <= len(d) <= 15


async def _send_otp_sms(destination: str, code: str) -> bool:
    """يُرسِل OTP عبر مزوّد SMS HTTP — تشغيل الطلب الحاجب في خيط."""
    if not SMS_PROVIDER_URL or not SMS_API_KEY:
        logger.warning("OTP هاتف: مزوّد SMS غير مضبوط — لم يُرسَل (destination=%s)", destination)
        return False
    if not _is_valid_phone(destination):
        # وجهة نائبة (لم يُحفَظ رقم هاتف بعد) — لا نُرسِل لرقم غير حقيقيّ (إهدار/أخطاء).
        logger.warning("OTP هاتف: وجهة غير صالحة (نائبة؟) — لم يُرسَل")
        return False
    message = f"رمز تحقّق SAHOOL: {code} (صالح {OTP_TTL_SECONDS // 60} دقيقة)"
    return await asyncio.to_thread(_post_sms_blocking, destination, message)


async def send_otp(channel: str, destination: str, code: str) -> bool:
    """يُرسِل رمز التحقّق عبر القناة المطلوبة (بريد SMTP أو SMS عبر HTTP).

    حقيقيّ عند ضبط الاعتماد: البريد عبر SMTP_*، والهاتف عبر SMS_PROVIDER_URL/SMS_API_KEY.
    تدهور رشيق: إن لم يُضبط مزوّد القناة نُسجّل تحذيراً (دون الرمز) ونُعيد False —
    يبقى الرمز في Redis (فيعمل التطوير) لكن دون إعلان نجاح زائف في الإنتاج.
    التوقيع ثابت فلا يتغيّر المنادون. أمان: لا نُسجّل الرمز نفسه أبداً.
    """
    if channel == "email":
        return await _send_otp_email(destination, code)
    if channel == "phone":
        return await _send_otp_sms(destination, code)
    logger.warning("OTP: قناة غير مدعومة channel=%s", channel)
    return False
