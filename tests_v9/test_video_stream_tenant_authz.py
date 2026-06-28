"""تفويض عزل المستأجرين في video-processor — حارس متعدّد المستأجرين.

السبب (تدقيق أمنيّ): كان `_assert_stream_tenant` يحوي اختصار `role == "admin"`
شاملاً يسمح لأيّ admin (حتى من مستأجِر آخر) بالوصول لأيّ بثّ — يُبطل العزل. كما كان
`create_stream` يخزّن `req.tenant_id` من جسم الطلب دون ربطه بمستأجِر الرمز.

الإصلاح (مرآةً لـraster/soil):
  • `_assert_stream_tenant`: tenant_id المخزَّن للبثّ يجب أن يساوي مستأجِر الرمز،
    وإلّا 404 (fail-closed). لا تجاوز admin شامل — admin المستأجِر محصور بمستأجِره؛
    العبور المشروع عبر break-glass فقط (v90)، لا اختصار دور هنا.
  • `create_stream`: tenant_id يُشتقّ من مطالبة الرمز — لا من الجسم. جسم متعارض ⇒ رفض.

تعاقُد الاختبار: نفس المستأجِر يمرّ؛ admin مستأجِر آخر يُرفَض (لا تجاوز شامل)؛
الإنشاء يربط مستأجِر الرمز ويتجاهل/يرفض tenant_id المتعارض في الجسم.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]  # CI يشغّل -m unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
VIDEO = os.path.join(ROOT, "services/video-processor")

# يتطلّب تبعيّات الخدمة (fastapi/aiomqtt/numpy/httpx/jose). في بيئة CI الخفيفة قد
# تغيب؛ نتخطّى بصدق إن غابت (وظيفة الوحدات الكاملة تُثبّت requirements ⇒ تُشغّلها).
_DEPS = ("fastapi", "aiomqtt", "numpy", "httpx", "jose", "pydantic")
_have_deps = all(importlib.util.find_spec(m) is not None for m in _DEPS)


@pytest.fixture
def vp():
    """يستورد video-processor.main معزولاً وينظّف STREAMS قبل/بعد كلّ اختبار.

    اسم الوحدة 'main' عامّ عبر الخدمات، فنُسقط المُخبّأ ونُعيد الاستيراد من مسار
    video-processor، ونتحقّق أنّه فعلاً video-processor (لا تصادم أسماء)."""
    if not _have_deps:
        pytest.skip("تبعيّات video-processor غائبة — يُنفَّذ في وظيفة الوحدات الكاملة")
    if VIDEO not in sys.path:
        sys.path.insert(0, VIDEO)
    # توحيد main↔cert: بعد تفكيك المسارات إلى routers/، نُسقط main + وحدات routers معاً
    # كي تُعيد routers الاستيراد ضدّ main الطازج (وإلّا يحتفظ routers.streams بمرجع main
    # متعفّن عبر الاختبارات ⇒ STREAMS مختلف عمّا يراه الاختبار). نمط soil #570.
    for _m in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
        sys.modules.pop(_m, None)
    vmain = importlib.import_module("main")
    assert hasattr(vmain, "STREAMS") and hasattr(vmain, "_assert_stream_tenant"), (
        "استُورد main خاطئ (تصادم أسماء عبر الخدمات) — ليس video-processor"
    )
    vmain.STREAMS.clear()
    try:
        yield vmain
    finally:
        vmain.STREAMS.clear()
        sys.modules.pop("main", None)


def _seed_stream(vp, stream_id: str, owner_tenant: str):
    """يُسجّل StreamState لبثّ مملوك لمستأجِر (كما يفعل create_stream)."""
    cfg = vp.StreamConfig(stream_id=stream_id, tenant_id=owner_tenant)
    state = vp.StreamState(cfg)
    vp.STREAMS[stream_id] = state
    return state


# ─── _assert_stream_tenant: عزل الوصول ────────────────────────────
def test_same_tenant_allowed(vp):
    """مستأجِر يملك البثّ ⇒ يمرّ (لا يرفع)."""
    state = _seed_stream(vp, "s1", "tenant_a")
    vp._assert_stream_tenant(state, {"tenant_id": "tenant_a", "role": "user"})


def test_different_tenant_admin_denied(vp):
    """admin من مستأجِر آخر ⇒ 404 (لا تجاوز admin شامل — هذا جوهر الإصلاح)."""
    from fastapi import HTTPException

    state = _seed_stream(vp, "s1", "tenant_a")
    with pytest.raises(HTTPException) as ei:
        vp._assert_stream_tenant(state, {"tenant_id": "tenant_b", "role": "admin"})
    assert ei.value.status_code == 404


def test_same_tenant_admin_allowed(vp):
    """admin من نفس المستأجِر ⇒ يمرّ (admin محصور بمستأجِره، لكن يصل لبثّه)."""
    state = _seed_stream(vp, "s1", "tenant_a")
    vp._assert_stream_tenant(state, {"tenant_id": "tenant_a", "role": "admin"})


def test_missing_token_tenant_denied(vp):
    """fail-closed: رمز بلا tenant_id ⇒ 404 (لا يطابق أيّ بثّ مملوك)."""
    from fastapi import HTTPException

    state = _seed_stream(vp, "s1", "tenant_a")
    with pytest.raises(HTTPException) as ei:
        vp._assert_stream_tenant(state, {"role": "admin"})
    assert ei.value.status_code == 404


def test_no_blanket_admin_bypass_in_source():
    """حارس مصدر (بلا تبعيّات): لا اختصار `role == "admin"` يُعيد بلا فحص المستأجِر
    في _assert_stream_tenant. يعمل في أيّ بيئة (تحليل نصّ صرف، لا استيراد)."""
    src = open(os.path.join(VIDEO, "main.py"), encoding="utf-8").read()
    # نقطة بدء الدالّة حتى نهايتها (قبل الدالّة/الزخرفة التالية).
    start = src.index("def _assert_stream_tenant(")
    body = src[start : start + 900]
    assert 'role") == "admin"' not in body and "role')=='admin'" not in body, (
        "اختصار admin شامل ما زال في _assert_stream_tenant — يُبطل العزل"
    )


# ─── create_stream: ربط tenant_id بالرمز ──────────────────────────
async def _call_create(vp, req_kwargs, user):
    req = vp.CreateStreamRequest(**req_kwargs)
    return await vp.create_stream(req, user=user)


async def test_create_binds_token_tenant(vp):
    """الإنشاء يربط tenant_id من الرمز (لا من الجسم) — حتى لو الجسم 'default'."""
    res = await _call_create(
        vp,
        {"stream_id": "s1", "usb_index": 0},
        {"tenant_id": "tenant_a", "role": "user"},
    )
    assert res["stream_id"] == "s1"
    assert vp.STREAMS["s1"].config.tenant_id == "tenant_a"
    vp.STREAMS["s1"].status = "inactive"  # أوقِف حلقة الخلفيّة


async def test_create_rejects_body_tenant_mismatch(vp):
    """جسم بـtenant_id متعارض مع الرمز ⇒ 403 (لا تجاوز صامت)، ولا يُنشأ بثّ."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await _call_create(
            vp,
            {"stream_id": "s1", "usb_index": 0, "tenant_id": "tenant_evil"},
            {"tenant_id": "tenant_a", "role": "admin"},
        )
    assert ei.value.status_code == 403
    assert "s1" not in vp.STREAMS  # fail-closed: لا إنشاء عند التعارض


async def test_create_body_matching_tenant_ok(vp):
    """جسم بـtenant_id يطابق الرمز ⇒ يمرّ ويُربَط بمستأجِر الرمز."""
    res = await _call_create(
        vp,
        {"stream_id": "s1", "usb_index": 0, "tenant_id": "tenant_a"},
        {"tenant_id": "tenant_a", "role": "user"},
    )
    assert res["stream_id"] == "s1"
    assert vp.STREAMS["s1"].config.tenant_id == "tenant_a"
    vp.STREAMS["s1"].status = "inactive"


async def test_create_requires_token_tenant(vp):
    """fail-closed: رمز بلا tenant_id لا يستطيع امتلاك بثّ ⇒ 403، ولا إنشاء."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await _call_create(
            vp,
            {"stream_id": "s1", "usb_index": 0},
            {"role": "admin"},
        )
    assert ei.value.status_code == 403
    assert "s1" not in vp.STREAMS


# ─── list_streams: لا تجاوز admin شامل ────────────────────────────
async def test_list_streams_scoped_to_tenant(vp):
    """admin مستأجِر آخر لا يرى بثوث غير مستأجِره في القائمة."""
    _seed_stream(vp, "s_a", "tenant_a")
    _seed_stream(vp, "s_b", "tenant_b")
    res = await vp.list_streams(user={"tenant_id": "tenant_b", "role": "admin"})
    ids = {s["stream_id"] for s in res["streams"]}
    assert ids == {"s_b"}  # لا s_a رغم دور admin


# ─── stop_stream: لا حذف عابر للمستأجرين ───────────────────────────
async def test_stop_stream_cross_tenant_denied_and_preserves_stream(vp):
    """مستأجِر آخر لا يستطيع حذف/إيقاف بثّ لا يملكه بمعرفة stream_id فقط."""
    from fastapi import HTTPException

    state = _seed_stream(vp, "s_a", "tenant_a")
    state.status = "active"
    with pytest.raises(HTTPException) as ei:
        await vp.stop_stream("s_a", user={"tenant_id": "tenant_b", "role": "admin"})
    assert ei.value.status_code == 404
    assert "s_a" in vp.STREAMS
    assert vp.STREAMS["s_a"].status == "active"


async def test_stop_stream_same_tenant_stops_and_removes(vp):
    """مالك البثّ يستطيع إيقافه؛ وبعد التفويض فقط يُزال من السجلّ."""
    state = _seed_stream(vp, "s_a", "tenant_a")
    state.status = "active"
    res = await vp.stop_stream("s_a", user={"tenant_id": "tenant_a", "role": "user"})
    assert res == {"stream_id": "s_a", "status": "stopped"}
    assert state.status == "inactive"
    assert "s_a" not in vp.STREAMS
