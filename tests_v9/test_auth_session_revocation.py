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

    # D02 — أنبوبٌ مُعامَلاتيّ: بديلُ `GETDEL` لنسخ Redis القديمة. يُعيد
    # `[value, deleted_count]`، و**العدَدُ** هو ما يفصل الفائزَ عن الخاسر.
    # ولا يحمل هذا المُزيَّفُ `getdel` قصداً كي يُقاس المسارُ البديل لا يُفترَض.
    def pipeline(self, transaction: bool = True):
        outer = self

        class _Pipe:
            def __init__(self):
                self._ops: list = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def get(self, k):
                self._ops.append(("get", k))
                return self

            def delete(self, k):
                self._ops.append(("delete", k))
                return self

            async def execute(self):
                out = []
                for op, k in self._ops:
                    if op == "get":
                        out.append(outer.kv.get(k))
                    else:
                        out.append(1 if outer.kv.pop(k, None) is not None else 0)
                return out

        return _Pipe()


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


# ─── D02/D03 من التدقيق الموحَّد (2026-09-22) ──────────────────────────────────
#
# `consume_refresh_token` تعيش في `services/auth/session_tokens.py` لا في `main.py`:
# حارسُ التفكيك يحدّ أسطرَ `main.py` بـ1050، ومحاولتي الأولى تجاوزَته بالتوثيق —
# **فأمسكها الحارسُ وهو مُحِقّ**. والوحدةُ الشقيقةُ تأخذ `redis` وسيطاً صريحاً، فتُختبَر
# بمُضاعَفٍ بلا استيراد الخدمة كلّها.


def _consume(redis, token):
    import importlib.util

    path = os.path.join(ROOT, "services/auth/session_tokens.py")
    spec = importlib.util.spec_from_file_location("auth_session_tokens_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.consume_refresh_token(redis, token)


async def test_the_refresh_token_is_consumed_atomically_so_only_one_caller_wins(auth):
    """D02 — طلبان متزامنان على التوكن نفسِه: واحدٌ يفوز لا اثنان.

    **العطل:** كان التدويرُ ``GET`` ثمّ ``DELETE`` منفصلَين. في الجدول المضبوط قرأ
    الطلبان القيمةَ القديمةَ نفسَها، ثمّ رجع الحذفُ ``1`` للأوّل و``0`` للثاني —
    **ولم يقرأ أحدٌ ذلك الرقم**، فمضى المساران إلى استجابتين ناجحتين بتوكنين
    جديدين مختلفين للجلسة نفسِها.

    **حدُّ صدق:** هذا يقيس الخوارزميّة تحت تداخلٍ يسمح به منطقُها، **لا احتمالَ
    السباق ولا توقيتَه على Redis حقيقيّ**، ولا يُثبِت ذرّيّةَ السلسلة كلّها
    (إنشاءٌ + فهرسةٌ + إبطالُ عائلة) — تلك بقيّةُ شرط الإغلاق ولم تُنفَّذ هنا.
    """
    token = await auth.create_refresh_token(11, "tenant-x")

    first = await _consume(auth._redis, token)
    second = await _consume(auth._redis, token)

    assert first, "الفائزُ الأوّل لم يحصل على القيمة"
    assert second is None, "التوكنُ نفسُه استُهلِك مرّتين — السباقُ ما زال مفتوحاً"


async def test_consuming_an_unknown_refresh_token_yields_nothing(auth):
    """والاتّجاه الآخر: توكنٌ لا وجودَ له لا يُنتِج قيمةً ولا يرفع."""
    assert await _consume(auth._redis, "no-such-token") is None


async def test_consume_falls_back_when_the_client_has_no_getdel(auth):
    """بديلُ النسخ القديمة: المعاملةُ + **عدَدُ المحذوف** يفصل الفائز.

    ``_FakeRedis`` هنا بلا ``getdel`` قصداً، فيسلك الشاهدُ مسارَ الأنبوب — وهو
    المسارُ الذي كان سيمرّ بلا قياسٍ لو اكتُفي بـ``GETDEL``.
    """
    assert not hasattr(auth._redis, "getdel"), "المُزيَّفُ اكتسب getdel فسقط قياسُ البديل"
    token = await auth.create_refresh_token(12, "tenant-y")
    assert await _consume(auth._redis, token)
    assert await _consume(auth._redis, token) is None


async def test_the_loser_of_an_interleaved_race_is_rejected_even_though_it_read_a_value(auth):
    """الحالةُ الفارقةُ التي لا يبلغها التسلسل: **قرأ القيمةَ وحذف صفراً**.

    الشاهدُ السابق لا يكفي — فيه تقع القراءةُ الثانية بعد الحذف الأوّل فتعود فارغةً
    مهما كان المنطق. والسباقُ الحقيقيُّ أن يقرأ الطرفان القيمةَ **قبل** أيّ حذف؛
    عندها يحذف الأوّلُ ``1`` والثاني ``0``، **وحدَه عدَدُ المحذوف يفصلهما**.

    فيُحاكى العميلُ هنا ليُرجِع ``[القيمة، 0]`` — أي خاسرٌ رأى قيمةً. وإن عاد بها
    فقد مضى مساران بجلسةٍ واحدة، وهو عينُ D02. وبهذا يصير حذفُ ``if deleted``
    من المصدر **مرئيّاً** بدل أن يمرّ صامتاً.
    """

    class _LoserRedis(_FakeRedis):
        def pipeline(self, transaction: bool = True):
            class _P:
                async def __aenter__(self_inner):
                    return self_inner

                async def __aexit__(self_inner, *exc):
                    return False

                def get(self_inner, k):
                    return self_inner

                def delete(self_inner, k):
                    return self_inner

                async def execute(self_inner):
                    # قرأ القيمة، لكنّ غيرَه حذفها أوّلاً ⇒ الحذفُ صفر.
                    return ["9:tenant-x", 0]

            return _P()

    auth._redis = _LoserRedis()
    assert await _consume(auth._redis, "contended") is None, (
        "الخاسرُ حصل على القيمة رغم أنّ الحذفَ صفر — السباقُ يُنتِج جلستين"
    )


async def test_a_token_issued_in_the_same_second_as_the_revocation_is_revoked(auth):
    """D03 — التعادلُ عند حدّ الثانية كان يمرّ.

    كانت المقارنةُ ``iat < floor`` بثوانٍ صحيحة، فتوكنٌ ``iat = floor`` يبقى صالحاً
    رغم صدوره في ثانية الإبطال نفسِها. والثانيةُ تسع إصداراً وإبطالاً معاً.

    **والإصلاحُ في جانب الأرضيّة:** تُرفَع ثانيةً واحدة، فيسقط كلُّ ما صدر في ثانية
    الإبطال أو قبلها. وتحويلُ ``<`` إلى ``<=`` كان سيُبطِل توكناً جديداً مشروعاً.
    """
    import datetime as _dt

    now = int(_dt.datetime.now(_dt.UTC).timestamp())
    await auth.set_user_token_floor(77)

    assert await auth.is_token_below_floor({"sub": "77", "iat": now}) is True, (
        "توكنٌ صدر في ثانية الإبطال نفسِها لم يُبطَل"
    )
    assert await auth.is_token_below_floor({"sub": "77", "iat": now - 1}) is True
    # وأوّلُ ثانيةٍ بعد الإبطال تمرّ — وإلّا كان العلاجُ إبطالَ الجديد أيضاً.
    assert await auth.is_token_below_floor({"sub": "77", "iat": now + 2}) is False
