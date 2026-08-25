"""P9 — عمرُ المخبّأ يُعَدّ على الخادم، والمجهولُ يُقال مجهولاً.

المسار القديم لم يكن يحسب عمراً على Redis **إطلاقاً**: ``set`` تكتب
``"age_hint_s": 0`` حرفيّاً، و``get`` تقرؤها وتُعيدها عمراً. فكلّ إصابةٍ طازجة
تُبلِّغ ``cache_age_s: 0`` مهما بلغ عمرُها الحقيقيّ — والرقمُ يُنشَر في أجوبة
الواجهة (``weather_runtime.py:157`` · ``:334`` · ``:918`` · ``:973``).

وفرعُ «البائت» كان يحسب `monotonic() - stored_monotonic` عبر عمليّتين. و``monotonic``
نقطةُ مرجعيّتها **غير معرَّفة** بنصّ PEP 418: الفرقُ بين قراءتَين من عمليّتين هو
فرقٌ بين مبدأَين لا بين لحظتين. ثمّ كان ``max(age, TTL_S)`` يرفع الناتجَ إلى حدٍّ
معقول المظهر — فيُخفي فسادَه بدل أن يكشفه.

العلاج: ``العمر = المدّة الكاملة − TTL(key)``. العدُّ كلُّه داخل Redis، فلا ساعةَ
تُشارَك ولا مبدأَ يُقارَن. والمجهول ``None`` لا ``0``.

**ولماذا التمييز حمولةٌ لا تجميل:** المستهلِك يقرأ ``cache_age_s`` ليقرّر أيثق
بالقراءة أم يُجدّدها. و``0`` تعني «طازجةٌ تماماً» — أقوى ما يمكن قوله. فالعطل لم
يكن رقماً خاطئاً بل **أشدّ الأرقام طمأنةً** يُقال في أسوأ الحالات.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

cache = importlib.import_module("cache")

pytestmark = pytest.mark.unit


class _FakeRedis:
    """Redis صغير يعرف ``TTL`` — العدّادُ هو محلّ القياس كلِّه."""

    def __init__(self, remaining: dict[str, int] | None = None, ttl_raises: bool = False):
        self.store: dict[str, str] = {}
        self.remaining = remaining or {}
        self.ttl_raises = ttl_raises

    def ping(self):
        return True

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.remaining.setdefault(key, ttl)
        return True

    def ttl(self, key: str):
        if self.ttl_raises:
            raise RuntimeError("ttl unavailable")
        return self.remaining.get(key, -2)


@pytest.fixture
def redis_backed(monkeypatch):
    """يُركّب خلفيّة Redis وهميّة ويُعيد دالّةً تُثبّت المتبقّي لكلّ مفتاح."""

    def _install(remaining: dict[str, int] | None = None, ttl_raises: bool = False) -> _FakeRedis:
        client = _FakeRedis(remaining=remaining, ttl_raises=ttl_raises)
        monkeypatch.setattr(cache, "REDIS_URL", "redis://fake:6379/0")
        monkeypatch.setattr(cache, "_REDIS_CLIENT", client)
        monkeypatch.setattr(cache, "_REDIS_ERROR", None)
        cache._CACHE.clear()
        return client

    return _install


def _fresh(key: str) -> str:
    return cache._fresh_key(key)


def _stale(key: str) -> str:
    return cache._stale_key(key)


# ── العمر يُشتقّ من عدّاد الخادم ────────────────────────────────────────
def test_a_fresh_entry_reports_the_age_the_server_counted_not_zero(redis_backed):
    """العطل الأصليّ في جملة واحدة: مدخلةٌ عمرُها ٤٠٠ث كانت تُبلِّغ ``0``."""
    client = redis_backed()
    client.store[_fresh("k")] = '{"value": {"t": 1}}'
    client.remaining[_fresh("k")] = int(cache.TTL_S) - 400

    value, state, age = cache.get("k")

    assert value == {"t": 1}
    assert state == "fresh"
    assert age == 400, "العمرُ عاد صفراً — العدُّ لا يقع على الخادم"


def test_the_age_of_a_just_written_entry_is_zero_because_it_is(redis_backed):
    """الصفرُ ليس ممنوعاً — ممنوعٌ أن يُلفَّق. هنا هو صادق: المدّة كاملة."""
    redis_backed()
    cache.set("k", {"temperature_c": 28.5})

    value, state, age = cache.get("k")

    assert value == {"temperature_c": 28.5}
    assert state == "fresh"
    assert age == 0


def test_a_stale_entry_reports_an_age_beyond_the_fresh_window(redis_backed):
    """البائتُ يُبلِّغ عمرَه الحقيقيّ، بلا ``max(age, TTL_S)`` الذي كان يستره."""
    client = redis_backed()
    client.store[_stale("k")] = '{"value": {"t": 2}}'
    client.remaining[_stale("k")] = int(cache.STALE_TTL_S) - 1800

    value, state, age = cache.get("k")

    assert value == {"t": 2}
    assert state == "stale"
    assert age == 1800
    assert age > cache.TTL_S, "عمرُ البائت يجب أن يتجاوز نافذة الطزاجة"


# ── المجهولُ يُقال مجهولاً ──────────────────────────────────────────────
def test_an_unreadable_counter_yields_no_age_rather_than_a_fabricated_zero(redis_backed):
    """``ttl`` تعطّلت ⇒ ``None``. الرجوعُ إلى ``0`` هو العطل الأصليّ بعينه."""
    client = redis_backed(ttl_raises=True)
    client.store[_fresh("k")] = '{"value": {"t": 3}}'

    value, state, age = cache.get("k")

    assert value == {"t": 3}
    assert state == "fresh", "القيمةُ ما زالت صالحة — الغائبُ هو عمرُها وحده"
    assert age is None


@pytest.mark.parametrize("sentinel", [-1, -2])
def test_a_ttl_sentinel_is_absence_not_a_number(redis_backed, sentinel: int):
    """``-1`` بلا انتهاء و``-2`` غير موجود — كلاهما ليس عمراً بالثواني."""
    client = redis_backed()
    client.store[_fresh("k")] = '{"value": {"t": 4}}'
    client.remaining[_fresh("k")] = sentinel

    _value, _state, age = cache.get("k")

    assert age is None


def test_a_counter_beyond_the_full_window_clamps_to_zero_and_never_goes_negative(redis_backed):
    """``TTL_S`` قد تُخفَّض بعد كتابة مدخلة، فيبدو المتبقّي أكبر من المدّة.

    عمرٌ سالب يعني «كُتبت في المستقبل» — وهو ادّعاءٌ لا يصحّ بحال، فيُقصّ إلى صفر.
    """
    client = redis_backed()
    client.store[_fresh("k")] = '{"value": {"t": 5}}'
    client.remaining[_fresh("k")] = int(cache.TTL_S) + 120

    _value, _state, age = cache.get("k")

    assert age == 0


# ── ما لم يُخزَّن لم يعد يُخزَّن ────────────────────────────────────────
def test_the_stored_payload_no_longer_carries_a_local_clock_or_a_hardcoded_age(redis_backed):
    """``stored_monotonic`` ساعةٌ لا معنى لها عند قارئٍ آخر، و``age_hint_s`` كانت
    ``0`` ثابتة تُقرأ عمراً. تخزينُهما بعد الإصلاح دَينٌ صامت يُغري بالعودة إليهما."""
    import json

    client = redis_backed()
    cache.set("k", {"v": 1})

    stored = json.loads(client.store[_fresh("k")])
    assert stored == {"value": {"v": 1}}
    assert "stored_monotonic" not in stored
    assert "age_hint_s" not in stored


# ── مسارُ الذاكرة لم يُمَسّ: ``monotonic`` صحيحةٌ داخل العمليّة ─────────
def test_the_memory_backend_still_measures_age_with_its_own_clock(monkeypatch):
    """PEP 418 يمنع **المشاركة** لا القياس. ونفس العمليّة نفسُ المبدأ."""
    from time import monotonic

    monkeypatch.setattr(cache, "REDIS_URL", None)
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    cache._CACHE.clear()
    cache._CACHE["k"] = (monotonic() - 120.0, {"v": 2})

    value, state, age = cache.get("k")

    assert value == {"v": 2}
    assert state == "fresh"
    assert 118 <= age <= 122, "مسارُ الذاكرة يقيس عمراً حقيقيّاً لا صفراً"
