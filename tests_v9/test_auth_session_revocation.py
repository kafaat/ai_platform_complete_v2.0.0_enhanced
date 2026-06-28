"""إبطال جلسات المستخدم عند تغيير الحساب (مراجعة أمنيّة #4) — حُرّاس + سلوكيّ.

الفجوة: change_password / confirm_password_reset / deactivate_user / change_role لم تُبطل
التوكنات القائمة ⇒ جلسات تبقى صالحة بعد اختراق/إعادة تعيين/تعطيل/خفض دور. الإصلاح: أرضيّة
توكن لكلّ مستخدم (تُبطل كلّ access tokens الأقدم) + حذف كلّ refresh tokens، مع فحص الأرضيّة
في get_current_user.

(A) حُرّاس مصدر — تُنفَّذ في CI دائماً (لا تستورد الخدمة).
(B) سلوكيّ — يتخطّى إن تعذّر استيراد خدمة auth (بيئة CI خفيفة).
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
AUTH = os.path.join(ROOT, "services/auth/main.py")

# بعد تفكيك مسارات auth إلى routers/: مُعالِجات confirm_password_reset / change_password /
# change_role / deactivate_user انتقلت إلى routers/*.py (المساعِدات وget_current_user تبقى في
# main.py). نمسح المصدر المُسلسَل (main.py + routers/*.py) كي يبقى الحارس صحيحاً بلا إضعاف أيّ
# تأكيد أمنيّ (يكفي أن يكون السطر موجوداً في أيّ من الملفّين).
from auth_route_source import auth_combined_source  # noqa: E402


def _src() -> str:
    return auth_combined_source(ROOT)


def _func(src: str, name: str) -> str:
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    return src[start : (start + 1 + nxt.start()) if nxt else len(src)]


# ── (A) حُرّاس المصدر ──
def test_helpers_exist():
    src = _src()
    for fn in ("set_user_token_floor", "is_token_below_floor", "revoke_all_user_sessions"):
        assert f"async def {fn}(" in src, f"الدالّة {fn} مفقودة"


def test_get_current_user_checks_floor():
    body = _func(_src(), "get_current_user")
    assert "is_token_below_floor(payload)" in body, "get_current_user لا يفحص أرضيّة التوكن"


@pytest.mark.parametrize(
    "endpoint",
    ["confirm_password_reset", "change_password", "change_role", "deactivate_user"],
)
def test_mutating_endpoints_revoke_sessions(endpoint):
    body = _func(_src(), endpoint)
    assert "revoke_all_user_sessions(user_id)" in body, (
        f"{endpoint} لا يُبطل جلسات المستخدم بعد التغيير"
    )


def test_refresh_token_registered_in_user_set():
    body = _func(_src(), "create_refresh_token")
    assert "refreshset" in body and "sadd" in body, "refresh tokens غير مُسجَّلة في مجموعة المستخدم"


# ── (B) سلوكيّ — يتخطّى بلا تبعيّات auth ──
class _FakeRedis:
    """مخزن Redis لا-متزامن في الذاكرة (يكفي لاختبار منطق الإبطال)."""

    def __init__(self):
        self.kv: dict = {}
        self.sets: dict = {}

    async def setex(self, k, ttl, v):
        self.kv[k] = str(v)

    async def get(self, k):
        return self.kv.get(k)

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.sets.pop(k, None)

    async def sadd(self, k, *vals):
        self.sets.setdefault(k, set()).update(str(v) for v in vals)

    async def expire(self, k, ttl):
        pass

    async def smembers(self, k):
        return set(self.sets.get(k, set()))


@pytest.fixture(scope="module")
def auth_mod():
    # وحدة الخدمة تُستورَد مرّة واحدة (إعادة الاستيراد تكسر تسجيل Prometheus).
    pytest.importorskip("jose")
    pytest.importorskip("redis")
    import importlib.util
    import sys

    auth_dir = os.path.join(ROOT, "services/auth")
    if auth_dir not in sys.path:
        sys.path.insert(0, auth_dir)  # كي تُحلّ وحدات الخدمة الشقيقة (otp …)
    spec = importlib.util.spec_from_file_location("auth_main_sessions_test", AUTH)
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception:  # noqa: BLE001 — تبعيّات ناقصة في بيئة خفيفة
        pytest.skip("تعذّر استيراد خدمة auth (تبعيّات ناقصة)")
    return m


@pytest.fixture
def auth(auth_mod):
    # كلّ اختبار يبدأ بمخزن Redis نظيف في الذاكرة.
    auth_mod._redis = _FakeRedis()
    return auth_mod


async def test_floor_revokes_old_tokens(auth):
    await auth.set_user_token_floor(42)
    # توكن أُصدِر «قبل» الأرضيّة (iat قديم) ⇒ مُبطَل
    assert await auth.is_token_below_floor({"sub": "42", "iat": 1}) is True
    # توكن أُصدِر «بعد» الأرضيّة (iat كبير) ⇒ صالح
    assert await auth.is_token_below_floor({"sub": "42", "iat": 9999999999}) is False
    # مستخدم آخر بلا أرضيّة ⇒ صالح
    assert await auth.is_token_below_floor({"sub": "99", "iat": 1}) is False


async def test_revoke_all_deletes_refresh_tokens(auth):
    # سجّل refresh token للمستخدم ثمّ أبطِل جلساته
    await auth.create_refresh_token(7, "tenant-x")
    setkey = "sahool:user:refreshset:7"
    assert auth._redis.sets.get(setkey), "لم يُسجَّل refresh token في مجموعة المستخدم"
    await auth.revoke_all_user_sessions(7)
    # المجموعة + مفاتيح refresh حُذِفت، والأرضيّة ضُبِطت
    assert not auth._redis.sets.get(setkey)
    assert auth._redis.kv.get("sahool:user:token_floor:7") is not None


async def test_no_redis_fails_open(auth):
    auth._redis = None
    # بلا Redis: لا انهيار، ولا إبطال (fail-open متّسق مع is_jti_revoked)
    assert await auth.is_token_below_floor({"sub": "1", "iat": 1}) is False
    await auth.revoke_all_user_sessions(1)  # لا يرفع
