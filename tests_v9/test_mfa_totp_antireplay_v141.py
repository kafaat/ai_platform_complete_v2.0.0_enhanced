"""V29.7 / v141 — منع إعادة تشغيل TOTP (anti-replay).

المشكلة: كان التحقّق ``pyotp.TOTP(secret).verify(code, valid_window=1)`` بلا تسجيل
آخر خطوة زمنيّة مقبولة ⇒ رمز صالح يُعاد استخدامه ضمن نافذته (~90 ثانية). الإصلاح:
عمود ``users.mfa_last_totp_step`` + دالّة نقيّة ``mfa_crypto.matched_totp_step`` +
استهلاك ذرّيّ بشرط التقدّم في كلّ مسارات التحقّق الأربعة.

طبقتان:
- وحدة (pure، ``unit``): صحّة مطابقة الخطوة + حُرّاس مصدر (كلّ verify يستهلك الخطوة،
  لا فحص pyotp خام متبقٍّ) + ربط الهجرة. pyotp متاح في طبقة الاختبار الدنيا.
- تكامل (``integration``): على Postgres حقيقيّ — العمود موجود + نمط التحديث الشرطيّ
  يرفض إعادة الخطوة نفسها ويقبل الأحدث (يتخطّى إن لا DB).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_AUTH = ROOT / "services" / "auth"
if str(_AUTH) not in sys.path:
    sys.path.insert(0, str(_AUTH))

import mfa_crypto  # noqa: E402  (من services/auth — نقيّ، يستورد pyotp المتاح في التير)
import pyotp  # noqa: E402


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══ 1. صحّة matched_totp_step (نقيّ) ══
_T = 1_700_000_040  # زمن ثابت (قابل للقسمة على 30 → بداية خطوة)


def test_matches_current_step():
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).at(_T)
    assert mfa_crypto.matched_totp_step(secret, code, for_time=_T) == _T // 30


def test_wrong_code_returns_none():
    secret = pyotp.random_base32()
    good = pyotp.TOTP(secret).at(_T)
    bad = f"{(int(good) + 1) % 1_000_000:06d}"  # رمز مختلف حتميّاً
    assert mfa_crypto.matched_totp_step(secret, bad, for_time=_T) is None


def test_prev_step_matches_within_window_only():
    secret = pyotp.random_base32()
    prev = pyotp.TOTP(secret).at(_T - 30)
    # نافذة 1 ⇒ الخطوة السابقة تُطابق وتُعاد رقمها الحقيقيّ.
    assert (
        mfa_crypto.matched_totp_step(secret, prev, for_time=_T, valid_window=1) == (_T - 30) // 30
    )
    # نافذة 0 ⇒ لا تطابق (خارج النافذة).
    assert mfa_crypto.matched_totp_step(secret, prev, for_time=_T, valid_window=0) is None


def test_later_code_has_strictly_greater_step():
    """أساس منع إعادة التشغيل: رمز لاحق شرعيّ ⇒ خطوة أكبر تماماً ⇒ يُقبَل بعد المخزَّن."""
    secret = pyotp.random_base32()
    s_now = mfa_crypto.matched_totp_step(secret, pyotp.TOTP(secret).at(_T), for_time=_T)
    s_later = mfa_crypto.matched_totp_step(secret, pyotp.TOTP(secret).at(_T + 60), for_time=_T + 60)
    assert s_later > s_now


def test_blank_inputs_fail_closed():
    assert mfa_crypto.matched_totp_step(None, "123456", for_time=_T) is None
    assert mfa_crypto.matched_totp_step("SECRET", None, for_time=_T) is None
    assert mfa_crypto.matched_totp_step("SECRET", "  ", for_time=_T) is None


# ══ 2. حُرّاس مصدر — لا فحص pyotp خام متبقٍّ؛ كلّ مسار يستهلك الخطوة ══
def test_no_raw_totp_verify_remains_in_verify_paths():
    # P1 decomposition: منطق MFA انتقل إلى mfa_runtime.py — نمسحه أيضاً (توسيع نطاق).
    combined = (
        _read("services/auth/main.py")
        + _read("services/auth/mfa_runtime.py")
        + _read("services/auth/routers/mfa.py")
    )
    assert "pyotp.TOTP(secret).verify(" not in combined, (
        "فحص TOTP خام متبقٍّ (بلا anti-replay) في مسار تحقّق"
    )


def test_all_four_verify_sites_consume_step():
    # P1 decomposition: _consume_totp_step ومواضع الاستدعاء انتقلت إلى mfa_runtime.py —
    # نمسح main.py + الشقيقة معاً بنفس التأكيدات.
    main_src = _read("services/auth/main.py") + _read("services/auth/mfa_runtime.py")
    mfa_src = _read("services/auth/routers/mfa.py")
    assert "async def _consume_totp_step" in main_src, "دالّة الاستهلاك الذرّيّ مفقودة"
    # التحديث الذرّيّ بشرط التقدّم (آمن ضدّ التسابق).
    assert "mfa_last_totp_step < $1" in main_src or "mfa_last_totp_step < $" in main_src
    # ٤ مواضع تحقّق تستدعي الاستهلاك: 2 في main + 2 في routers/mfa.
    assert main_src.count("_consume_totp_step(") >= 3  # التعريف + استدعاءان
    assert mfa_src.count("_consume_totp_step(") == 2


def test_v141_migration_present_and_wired():
    body = _read("migrations/v141_mfa_totp_antireplay.sql")
    assert "mfa_last_totp_step" in body
    assert "ADD COLUMN IF NOT EXISTS" in body
    assert "v141_mfa_totp_antireplay.sql" in _read("migrations/MANIFEST.txt")
    assert "v141_mfa_totp_antireplay.sql" in _read("scripts_v9/run_migrations.sql")


# ══ 3. تكامل asyncpg — النمط الذرّيّ يرفض إعادة الخطوة (يتخطّى إن لا DB) ══
_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


def _db_available() -> bool:
    try:
        import asyncpg

        async def _ping():
            c = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


@pytest.mark.integration
def test_column_exists_and_conditional_update_is_antireplay():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg

    async def _run():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            # العمود الحقيقيّ موجود (v141 مُطبَّق على DB الاختبار).
            col = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='mfa_last_totp_step'"
            )
            assert col == 1, "عمود mfa_last_totp_step مفقود — v141 لم يُطبَّق"

            # نمط الاستهلاك الذرّيّ على جدول مؤقّت بنفس الشكل (لا نلوّث users).
            await conn.execute(
                "CREATE TEMP TABLE _ar(id INT PRIMARY KEY, mfa_last_totp_step BIGINT)"
            )
            await conn.execute("INSERT INTO _ar VALUES (1, NULL)")
            upd = (
                "UPDATE _ar SET mfa_last_totp_step=$1 "
                "WHERE id=1 AND (mfa_last_totp_step IS NULL OR mfa_last_totp_step < $1)"
            )
            first = await conn.execute(upd, 100)  # NULL→100 ⇒ UPDATE 1
            replay = await conn.execute(upd, 100)  # نفس الخطوة ⇒ UPDATE 0 (رُفِض)
            older = await conn.execute(upd, 99)  # أقدم ⇒ UPDATE 0 (رُفِض)
            newer = await conn.execute(upd, 101)  # أحدث ⇒ UPDATE 1 (قُبِل)
            assert first.rsplit(" ", 1)[-1] == "1", "أوّل استهلاك يجب أن ينجح"
            assert replay.rsplit(" ", 1)[-1] == "0", "إعادة الخطوة نفسها يجب أن تُرفَض"
            assert older.rsplit(" ", 1)[-1] == "0", "خطوة أقدم يجب أن تُرفَض"
            assert newer.rsplit(" ", 1)[-1] == "1", "خطوة أحدث يجب أن تُقبَل"
        finally:
            await conn.close()

    asyncio.run(_run())
