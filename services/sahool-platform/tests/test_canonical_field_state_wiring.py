"""canonical_field_state موصولة بمستهلك إنتاجيّ — وتقول الحقيقة عن نواقصها.

النواة تشترط ``weather`` و``water`` و``soil``. المنصّة تُنتِج **الماء** و**التربة** (عبر
``api/canonical_soil_state.py`` — عميل HTTP لِـ``soil-service``) من الثلاثة؛ **الطقس** يبقى
غائباً (قرار معماريّ مؤجَّل). فالربط اليوم لا يُنتِج حالة صالحة تشغيليّاً — وهذا **هو
المطلوب**: أن يُسمّى المنتَج الغائب باسمه بدل اختلاقه لإرضاء العقد.

الفشل الذي تمنعه هذه الاختبارات: منتَج بمخطّط صحيح ومحتوى مُلفَّق يجعل
``operational_eligible=true`` فتبدو الحالة صالحة وهي ليست كذلك.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from core.canonical_field_state import SCHEMA_VERSION, compose_canonical_field_state

pytestmark = pytest.mark.unit

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "internal_service.py"

_WATER = {"schema_version": "canonical_water_state.v1", "depletion_mm": 60, "taw_mm": 100}


def _compose(**kw):
    return compose_canonical_field_state(
        field_id="f1", season_id=None, as_of_time="2026-07-28T00:00:00Z", **kw
    )


# ── الحقيقة الحاليّة: الماء وحده متاح ───────────────────────────────────────
def test_water_only_names_every_missing_required_product():
    state = _compose(water=_WATER)
    assert state.schema_version == SCHEMA_VERSION
    assert state.availability == {
        "weather": False,
        "water": True,
        "soil": False,
        "spectral": False,
    }
    assert "required_weather_unavailable" in state.limitations
    assert "required_soil_unavailable" in state.limitations
    assert "required_water_unavailable" not in state.limitations
    assert state.operational_eligible is False


def test_absent_product_is_named_missing_not_silently_dropped():
    state = _compose(water=_WATER)
    assert "weather_missing" in state.limitations
    assert "soil_missing" in state.limitations


def test_a_wrong_schema_is_rejected_rather_than_accepted_as_canonical():
    """منتَج بمخطّط غير كنسيّ لا يُقبَل لمجرّد أنّه dict."""
    state = _compose(water={"schema_version": "something_else.v1", "depletion_mm": 60})
    assert "water_noncanonical_schema" in state.limitations
    assert state.availability["water"] is False


def test_eligibility_requires_all_three_and_never_a_subset():
    """الضمانة الجوهريّة: لا يُرفَع operational_eligible بمنتَجين من ثلاثة."""
    partial = _compose(water=_WATER, soil={"schema_version": "canonical_soil_state.v1"})
    assert partial.operational_eligible is False
    complete = _compose(
        water=_WATER,
        soil={"schema_version": "canonical_soil_state.v1"},
        weather={"schema_version": "canonical_weather_state.v1"},
    )
    assert complete.operational_eligible is True


def test_digest_is_deterministic_so_the_state_is_comparable():
    assert _compose(water=_WATER).state_digest == _compose(water=_WATER).state_digest


# ── المستهلك الإنتاجيّ ──────────────────────────────────────────────────────
def test_router_consumes_the_core():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "core.canonical_field_state"
        for alias in node.names
    }
    assert "compose_canonical_field_state" in imported


def test_no_new_route_was_spent():
    """السقف لم يُمسّ: الربط معامل على مسار قائم (سابقة INT-004A)."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    paths = [
        d.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in node.decorator_list
        if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
    ]
    assert sorted(paths) == ["/internal/events/ai-advice", "/internal/fields/{field_id}/state"]


def test_consumer_sources_weather_from_owner_resolver_not_a_literal():
    """weather must come from weather-service lineage, never a local literal/calculation."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_compose_canonical"
    )
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "get_canonical_field_weather")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "get_canonical_field_weather")
        )
    ]
    assert len(calls) == 1, "weather must be resolved exactly once through its owner boundary"
    compose = next(
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "compose_canonical_field_state"
    )
    passed = {kw.arg: kw.value for kw in compose.keywords}
    assert isinstance(passed.get("weather"), ast.Name)
    assert passed["weather"].id == "weather_payload"


def test_consumer_sources_soil_from_a_resolver_call_not_a_literal():
    """soil يُمرَّر عبر متغيّر مصدره استدعاء resolve_canonical_soil_state — لا Constant/Dict مُلفَّق."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_compose_canonical"
    )
    imported = {
        alias.name
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom) and node.module == "api.canonical_soil_state"
        for alias in node.names
    }
    assert "resolve_canonical_soil_state" in imported, (
        "soil يجب أن يُحلَّ عبر api.canonical_soil_state.resolve_canonical_soil_state"
    )
    call = next(
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "compose_canonical_field_state"
    )
    passed = {kw.arg: kw.value for kw in call.keywords}
    assert "soil" in passed, "soil يجب أن يُمرَّر صراحةً لا أن يُحذَف"
    assert not isinstance(passed["soil"], (ast.Constant, ast.Dict)), (
        "soil يجب أن يأتي من نتيجة الحلّ (resolver) — لا Constant/Dict مُلفَّق هنا"
    )
    resolver_calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "resolve_canonical_soil_state"
    ]
    assert resolver_calls, "لا بدّ من استدعاء resolve_canonical_soil_state فعليّاً داخل الدالّة"


def test_consumer_sources_spectral_from_a_resolver_call_not_a_literal():
    """P0-2 (نصف الطيف): ``spectral`` كان ``None`` حرفيّاً بينما المُحلِّل موجود.

    المُنتِج (``core.crop_intelligence.build_canonical_spectral_state``) والمُحلِّل الخادميّ
    كانا في الشجرة، لكنّ الثاني يعيش داخل ``routers/crop_twin.py`` فلا يبلغه هذا المُركِّب.
    فكانت الحالة الكنسيّة تُعلن ``spectral_missing`` لحقولٍ تُقرأ مؤشّراتها فعلاً — غيابٌ
    مُصطنَع لا مقيس. هذا الحارس نظير حارس التربة أعلاه: القيمة تأتي من نتيجة حلّ، لا من
    ثابت ولا من قاموس مُلفَّق.
    """
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_compose_canonical"
    )
    imported = {
        alias.name
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom) and node.module == "api.canonical_spectral_state"
        for alias in node.names
    }
    assert "resolve_canonical_spectral_state" in imported, (
        "spectral يجب أن يُحلَّ عبر api.canonical_spectral_state.resolve_canonical_spectral_state"
    )
    call = next(
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "compose_canonical_field_state"
    )
    passed = {kw.arg: kw.value for kw in call.keywords}
    assert "spectral" in passed, "spectral يجب أن يُمرَّر صراحةً لا أن يُحذَف"
    assert not isinstance(passed["spectral"], (ast.Constant, ast.Dict)), (
        "spectral يجب أن يأتي من نتيجة الحلّ (resolver) — لا None حرفيّة ولا Dict مُلفَّق"
    )
    resolver_calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "resolve_canonical_spectral_state"
    ]
    assert resolver_calls, "لا بدّ من استدعاء resolve_canonical_spectral_state فعليّاً داخل الدالّة"


def test_wiring_spectral_cannot_raise_eligibility_on_its_own():
    """قفل صدق: الطيف **ليس** من الثلاثة المشترطة، فوصله لا يجوز أن يرفع الأهليّة.

    لولا هذا القفل لأمكن أن يُقرأ وصلُ الطيف تقدّماً نحو ``operational_eligible=true``
    وهو لا يمسّها إطلاقاً — والفارق بين «أضفنا معرفة» و«صارت الحالة صالحة تشغيليّاً»
    هو بالضبط ما يحرسه هذا الملفّ.
    """
    spectral = {"schema": "canonical_spectral_state.v1", "indices": {"ndvi": 0.7}}
    with_spectral = _compose(water=_WATER, spectral=spectral)
    assert with_spectral.availability["spectral"] is True
    assert with_spectral.operational_eligible is False
    assert "required_weather_unavailable" in with_spectral.limitations
    assert "required_soil_unavailable" in with_spectral.limitations
