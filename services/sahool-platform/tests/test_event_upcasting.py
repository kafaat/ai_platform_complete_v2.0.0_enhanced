"""اختبارات ترقية مخطّط الأحداث (api.event_upcasting) — منطق نقيّ offline.

يتحقّق من مفتاح الترتيب العدديّ (`_vkey`)، وتسجيل المرقّيات (`register_upcaster`)،
وسلسلة الترقية (`upcast`): اللا-تغيير حين النسخة حاليّة أو النوع مجهول، الترقية
متعدّدة الخطوات، التوقّف الصادق عند انقطاع السلسلة، الحتميّة (نسخة دفاعيّة).

ملاحظة: `register_upcaster` يحقن في سجلّ عامّ `_UPCASTERS`. لتفادي تلويث الحالة
عبر الاختبارات نستعمل أنواع أحداث فريدة لكلّ اختبار وننظّف بعدها (fixture).
"""

import pytest
from api import event_upcasting
from api.event_upcasting import _vkey, register_upcaster, upcast

pytestmark = pytest.mark.unit


@pytest.fixture
def registry_cleanup():
    """ينظّف ما أُضيف لسجلّ المرقّيات والنسخ الحاليّة بعد كلّ اختبار."""
    before_up = dict(event_upcasting._UPCASTERS)
    before_cur = dict(event_upcasting.CURRENT_VERSIONS)
    yield
    event_upcasting._UPCASTERS.clear()
    event_upcasting._UPCASTERS.update(before_up)
    event_upcasting.CURRENT_VERSIONS.clear()
    event_upcasting.CURRENT_VERSIONS.update(before_cur)


# ─── _vkey ───────────────────────────────────────────────────────────────


def test_vkey_parses_numeric_tuple():
    assert _vkey("1.0") == (1, 0)
    assert _vkey("1.2.3") == (1, 2, 3)
    assert _vkey("2") == (2,)


def test_vkey_numeric_ordering_beats_lexicographic():
    # جوهر إصلاح L2: عدديّاً 1.2 < 1.10 (نصّيّاً العكس خاطئ).
    assert _vkey("1.2") < _vkey("1.10")


def test_vkey_invalid_returns_zero_tuple():
    assert _vkey("abc") == (0,)
    assert _vkey("1.x") == (0,)
    assert _vkey(None) == (0,)


# ─── upcast: حالات اللا-تغيير ────────────────────────────────────────────


def test_upcast_unknown_event_type_is_noop():
    payload = {"a": 1}
    out, ver = upcast("نوع.غير.مسجّل", payload, "1.0")
    assert out is payload  # لا نسخ، لا تغيير
    assert ver == "1.0"


def test_upcast_current_version_is_noop():
    # lifecycle.transitioned نسخته الحاليّة 1.0 — لا ترقية.
    payload = {"x": 9}
    out, ver = upcast("lifecycle.transitioned", payload, "1.0")
    assert out is payload
    assert ver == "1.0"


# ─── upcast: سلسلة خطوة واحدة ─────────────────────────────────────────────


def test_single_step_upcast_applies_transform(registry_cleanup):
    et = "test.single.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.1"

    @register_upcaster(et, "1.0")
    def _to_1_1(p):
        p["added"] = True
        return p

    out, ver = upcast(et, {"orig": 1}, "1.0")
    assert ver == "1.1"
    assert out == {"orig": 1, "added": True}


def test_register_upcaster_returns_function_unchanged(registry_cleanup):
    et = "test.return.event"

    @register_upcaster(et, "1.0")
    def _fn(p):
        return p

    # الديكوريتر يُرجِع الدالّة نفسها (يصلح للاستدعاء المباشر).
    assert _fn is event_upcasting._UPCASTERS[(et, "1.0")]


# ─── upcast: سلسلة متعدّدة الخطوات ────────────────────────────────────────


def test_multi_step_chain_applies_in_order(registry_cleanup):
    et = "test.multi.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.2"
    order = []

    @register_upcaster(et, "1.0")
    def _s0(p):
        order.append("1.0")
        p["v"] = p.get("v", 0) + 1
        return p

    @register_upcaster(et, "1.1")
    def _s1(p):
        order.append("1.1")
        p["v"] = p.get("v", 0) + 10
        return p

    out, ver = upcast(et, {"v": 0}, "1.0")
    assert ver == "1.2"
    assert order == ["1.0", "1.1"]  # بالتسلسل الصاعد
    assert out["v"] == 11


def test_chain_starting_midway_skips_earlier(registry_cleanup):
    # بدء من 1.1 يتخطّى مرقّي 1.0.
    et = "test.midway.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.2"

    @register_upcaster(et, "1.0")
    def _s0(p):
        p["s0"] = True
        return p

    @register_upcaster(et, "1.1")
    def _s1(p):
        p["s1"] = True
        return p

    out, ver = upcast(et, {}, "1.1")
    assert ver == "1.2"
    assert "s0" not in out
    assert out["s1"] is True


def test_two_digit_subversion_ordering(registry_cleanup):
    # سلسلة 1.0→1.2→1.10: الترتيب العدديّ يضمن 1.2 قبل 1.10.
    et = "test.twodigit.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.10"
    seen = []

    @register_upcaster(et, "1.0")
    def _a(p):
        seen.append("1.0")
        return p

    @register_upcaster(et, "1.2")
    def _b(p):
        seen.append("1.2")
        return p

    out, ver = upcast(et, {}, "1.0")
    assert ver == "1.10"
    assert seen == ["1.0", "1.2"]  # 1.2 قبل 1.10 (عدديّاً)


# ─── upcast: التوقّف الصادق عند انقطاع السلسلة ───────────────────────────


def test_broken_chain_stops_honestly(registry_cleanup):
    # لا مرقّي للنسخة الابتدائيّة → يتوقّف ويُرجِع كما هو دون تغيير النسخة.
    et = "test.broken.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.5"
    out, ver = upcast(et, {"k": 1}, "1.0")
    assert ver == "1.0"  # لم يصل للحاليّة (لا مرقّي)
    assert out == {"k": 1}


def test_chain_breaks_mid_way(registry_cleanup):
    # مرقّي 1.0 موجود لكن 1.1 مفقود → يتوقّف عند 1.1.
    et = "test.midbreak.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.3"

    @register_upcaster(et, "1.0")
    def _s0(p):
        p["s0"] = True
        return p

    out, ver = upcast(et, {}, "1.0")
    # طُبِّق 1.0، ثمّ لا مرقّي تالٍ في السلسلة المتاحة → النسخة الحاليّة (fallback).
    assert out["s0"] is True
    # available لا يحوي إلّا 1.0، فبعد تطبيقه nxt=None → v=current.
    assert ver == "1.3"


# ─── upcast: الحتميّة وعدم التحوير ────────────────────────────────────────


def test_upcast_does_not_mutate_input_payload(registry_cleanup):
    et = "test.nomutate.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.1"

    @register_upcaster(et, "1.0")
    def _s0(p):
        p["new"] = 1
        return p

    original = {"x": 5}
    out, _ = upcast(et, original, "1.0")
    assert original == {"x": 5}  # نسخة دفاعيّة dict(payload) تحمي الأصل
    assert out == {"x": 5, "new": 1}


def test_upcast_is_idempotent_on_current(registry_cleanup):
    et = "test.idem.event"
    event_upcasting.CURRENT_VERSIONS[et] = "1.1"

    @register_upcaster(et, "1.0")
    def _s0(p):
        p["c"] = p.get("c", 0) + 1
        return p

    once, v1 = upcast(et, {"c": 0}, "1.0")
    # إعادة الترقية على ناتج بالنسخة الحاليّة → لا تغيير.
    twice, v2 = upcast(et, once, v1)
    assert twice is once  # نسخة حاليّة → لا تغيير، يُعيد المُدخل نفسه
    assert v2 == "1.1"
