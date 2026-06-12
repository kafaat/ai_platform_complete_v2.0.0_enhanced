"""اختبارات وحدة للدوالّ النقيّة لـOTP في auth-service (تأكيد البريد/الهاتف).

تُغطّي المنطق القابل للاختبار دون Redis/قاعدة بيانات/شبكة:
توليد الرمز، تشذيب الإدخال، التحقّق من الصيغة، مفتاح Redis، والمقارنة الثابتة.

يعمل بطريقتين:
  • pytest -m unit tests_v9/test_otp.py
  • python3 tests_v9/test_otp.py   (تشغيل مستقل، بلا pytest)
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_auth_otp():
    """يُحمّل services/auth/otp.py (دوالّ OTP النقيّة) — بلا fastapi كي تُجمَع
    وتُشغَّل في مهمّة الـUnit بـCI دون تثبيت fastapi (كان استيراد main.py يكسرها)."""
    sys.path.insert(0, os.path.join(ROOT, "services/auth"))
    spec = importlib.util.spec_from_file_location(
        "auth_otp", os.path.join(ROOT, "services/auth/otp.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_otp"] = m
    spec.loader.exec_module(m)
    return m


m = _load_auth_otp()


class TestGenerateOtp:
    @pytest.mark.unit
    def test_length_is_six(self):
        assert len(m.generate_otp()) == m.OTP_LENGTH

    @pytest.mark.unit
    def test_all_digits(self):
        assert m.generate_otp().isdigit()

    @pytest.mark.unit
    def test_leading_zeros_preserved(self):
        # تشغيل متكرّر ⇒ بعض الرموز ستبدأ بصفر، ويجب بقاء الطول ٦ دائماً.
        for _ in range(2000):
            code = m.generate_otp()
            assert len(code) == m.OTP_LENGTH

    @pytest.mark.unit
    def test_custom_length(self):
        code = m.generate_otp(length=8)
        assert len(code) == 8 and code.isdigit()


class TestNormalizeOtp:
    @pytest.mark.unit
    def test_strips_spaces_and_nondigits(self):
        assert m.normalize_otp("  12 34-56 ") == "123456"

    @pytest.mark.unit
    def test_keeps_only_digits(self):
        assert m.normalize_otp("abc123def456") == "123456"


class TestIsValidOtpShape:
    @pytest.mark.unit
    def test_valid_six_digits(self):
        assert m.is_valid_otp_shape("000421") is True

    @pytest.mark.unit
    def test_too_short(self):
        assert m.is_valid_otp_shape("12345") is False

    @pytest.mark.unit
    def test_too_long(self):
        assert m.is_valid_otp_shape("1234567") is False

    @pytest.mark.unit
    def test_non_digit_rejected(self):
        assert m.is_valid_otp_shape("12a456") is False


class TestOtpRedisKey:
    @pytest.mark.unit
    def test_key_is_channel_and_user_scoped(self):
        assert m.otp_redis_key(7, "email") == "sahool:otp:email:7"
        assert m.otp_redis_key(7, "phone") == "sahool:otp:phone:7"

    @pytest.mark.unit
    def test_channels_do_not_collide(self):
        assert m.otp_redis_key(7, "email") != m.otp_redis_key(7, "phone")


class TestOtpCodesMatch:
    @pytest.mark.unit
    def test_exact_match(self):
        assert m.otp_codes_match("123456", "123456") is True

    @pytest.mark.unit
    def test_match_after_normalizing_input(self):
        # الإدخال قد يحوي فراغات/شرطات؛ المخزّن نظيف. يجب أن يتطابقا.
        assert m.otp_codes_match(" 123-456 ", "123456") is True

    @pytest.mark.unit
    def test_mismatch(self):
        assert m.otp_codes_match("123456", "654321") is False

    @pytest.mark.unit
    def test_empty_stored_does_not_match(self):
        assert m.otp_codes_match("123456", "") is False


def _run_standalone() -> int:
    """تشغيل مستقلّ بسيط بلا pytest — يُرجِع ٠ عند النجاح."""
    failures = []

    def ck(name: str, cond: bool):
        mark = "✓" if cond else "✗"
        print(f"  {mark} {name}")
        if not cond:
            failures.append(name)

    print("\n══ OTP pure-helper unit checks ══")
    ck("generate_otp طوله ٦", len(m.generate_otp()) == 6)
    ck("generate_otp أرقام فقط", m.generate_otp().isdigit())
    ck("normalize_otp يشذّب", m.normalize_otp(" 12 34-56 ") == "123456")
    ck("is_valid_otp_shape يقبل ٦", m.is_valid_otp_shape("000421"))
    ck("is_valid_otp_shape يرفض ٥", not m.is_valid_otp_shape("12345"))
    ck("otp_redis_key مُنطّق", m.otp_redis_key(7, "email") == "sahool:otp:email:7")
    ck("otp_codes_match يطابق", m.otp_codes_match(" 123-456 ", "123456"))
    ck("otp_codes_match يرفض", not m.otp_codes_match("123456", "654321"))

    print(f"\n{'─' * 40}")
    if failures:
        print(f"✗ {len(failures)} فشل: {failures}")
        return 1
    print("✓ كلّ اختبارات OTP النقيّة نجحت")
    return 0


if __name__ == "__main__":
    sys.exit(_run_standalone())
