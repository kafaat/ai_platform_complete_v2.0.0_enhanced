"""‏CANONICAL-FIELD-STATE-ELIGIBILITY-IS-PRESENCE-ONLY-01 — سُلَّم الأهليّة.

‏`operational_eligible` يسأل عن **الوجود** وحده. والعيب المقيس أنّ منتَجاً موجوداً
يُعلن مالكه أنّه `degraded` يجعل الحالة «مؤهّلة» بينما مالكها يقول إنّها ليست صالحة —
فيُبنى على ذلك توصية تنفيذيّة. هذه الاختبارات تُثبّت أنّ الحقل القديم **لم يتغيّر
معناه** (له مستهلكون قائمون) وأنّ السُلَّم الجديد يُجيب السؤال الذي لم يكن يُسأل.
"""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.canonical_field_state import (  # noqa: E402
    ELIGIBILITY_LEVELS,
    HEALTHY_QUALITY_TERMS,
    compose_canonical_field_state,
)

_SCHEMAS = {
    "weather": "canonical_weather_state.v1",
    "water": "canonical_water_state.v1",
    "soil": "canonical_soil_state.v1",
}


def _product(name: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": _SCHEMAS[name],
        "quality_status": "validated",
        "limitations": [],
    }
    base.update(overrides)
    return base


def _state(**overrides: Any):
    products = {name: _product(name) for name in _SCHEMAS}
    products.update(overrides)
    return compose_canonical_field_state(
        field_id="field-1", season_id="season-1", as_of_time="2026-08-01T00:00:00Z", **products
    )


def test_a_degraded_product_still_counts_as_present_but_blocks_proposing():
    """العيب نفسه، مُثبّتاً: «موجود» و«صالح» ليسا سؤالاً واحداً.

    التربة حاضرة بمخطّط صحيح، ومالكها يقول `degraded`. الحقل القديم يبقى `True`
    لأنّه يسأل عن الوجود — وتغييره تحت مستهلكيه أخطر من نقصه — بينما `propose`
    يُحجَب ويُسمّي السبب.
    """
    state = _state(soil=_product("soil", quality_status="degraded"))

    assert state.operational_eligible is True, "الحقل القديم يجب أن يبقى على معناه"
    assert state.eligibility["diagnose"]["allowed"] is True
    assert state.eligibility["propose"]["allowed"] is False
    assert "soil_quality_degraded" in state.eligibility["propose"]["reasons"]


def test_a_missing_required_product_blocks_diagnosing_and_everything_above():
    state = _state(water=None)

    assert state.operational_eligible is False
    assert state.eligibility["discover"]["allowed"] is True, "الاستكشاف يرى سبب الحجب"
    assert state.eligibility["diagnose"]["allowed"] is False
    assert "required_water_unavailable" in state.eligibility["diagnose"]["reasons"]


def test_an_owner_declaring_its_own_product_not_operational_is_believed():
    state = _state(water=_product("water", operational_eligible=False))

    assert state.eligibility["propose"]["allowed"] is False
    assert "water_owner_declares_not_operational" in state.eligibility["propose"]["reasons"]


def test_a_product_that_declares_no_quality_is_not_granted_it():
    """الصمت ليس شهادة سلامة.

    منتَج بلا `quality_status` لا يُمنَح ثقةً ضمنيّة — وإلّا صار أضعف المنتَجات
    (الذي لا يصف نفسه) أسهلها مروراً.
    """
    bare = {"schema_version": _SCHEMAS["weather"]}
    state = _state(weather=bare)

    assert state.operational_eligible is True
    assert state.eligibility["propose"]["allowed"] is False
    assert "weather_quality_undeclared" in state.eligibility["propose"]["reasons"]


def test_an_unknown_quality_vocabulary_is_treated_as_unproven_not_healthy():
    """المفردات **ليست موحَّدة بين المُلّاك** — مقيس: الطقس يُخرِج
    ‏validated/degraded/insufficient/invalid، والماء يُخرِج verified/degraded.

    فمصطلح جديد من مالك جديد يجب أن يُقرأ قراءة صريحة قبل أن يُمنَح ثقة، لا أن يمرّ
    لأنّه ليس مُدرَجاً في قائمة السيّئ. لو كان الفحص «ليس في قائمة سوداء» لمرّ هذا.
    """
    assert "excellent" not in HEALTHY_QUALITY_TERMS
    state = _state(soil=_product("soil", quality_status="excellent"))

    assert state.eligibility["propose"]["allowed"] is False
    assert "soil_quality_excellent" in state.eligibility["propose"]["reasons"]


def test_executing_is_never_allowed_from_field_state_alone():
    """التنفيذ نوع آخر من الإذن لا درجة أعلى من الاقتراح.

    حالةٌ كاملة السلامة تبقى ممنوعة من `execute`، لأنّ هذه البنية لا تحمل إذناً ولا
    توقيعاً ولا هويّة مُوافِق. الجواب الصادق «لا أملك الجواب»، لا `true` مُشتقّ من
    مُدخَلات لا تخصّ الإذن.
    """
    state = _state()

    assert state.eligibility["propose"]["allowed"] is True, "الحالة سليمة تماماً"
    assert state.eligibility["execute"]["allowed"] is False
    assert (
        "execution_authorization_not_carried_by_field_state"
        in state.eligibility["execute"]["reasons"]
    )


def test_the_ladder_is_monotone_so_the_levels_cannot_contradict_each_other():
    """ما يمنع مستوى أدنى يمنع كلّ ما فوقه — وإلّا فهي أربعة أحكام لا سُلَّم."""
    for case in (
        _state(),
        _state(water=None),
        _state(soil=_product("soil", quality_status="degraded")),
        _state(weather=None, soil=_product("soil", quality_status="insufficient")),
    ):
        allowed = [case.eligibility[level]["allowed"] for level in ELIGIBILITY_LEVELS]
        assert allowed == sorted(allowed, reverse=True), (
            f"سُلَّم غير رتيب: {dict(zip(ELIGIBILITY_LEVELS, allowed, strict=True))}"
        )
        for lower, upper in zip(ELIGIBILITY_LEVELS, ELIGIBILITY_LEVELS[1:], strict=False):
            assert set(case.eligibility[lower]["reasons"]) <= set(
                case.eligibility[upper]["reasons"]
            ), f"سبب في {lower} لا يظهر في {upper}"


def test_eligibility_does_not_move_the_state_digest():
    """البصمة تُعرِّف المُدخَلات لا الحكم عليها.

    حالتان بمُدخَلات متطابقة عدا جودةٍ مُعلَنة تُغيّر السُلَّم: البصمة **واحدة**.
    لو دخل الحكم في البصمة لتغيّرت بصمة كلّ حالة قائمة بلا تغيّر مُدخَل، وانكسر كلّ
    ما رُبِط ببصمة مُخزَّنة.
    """
    healthy = _state()
    degraded = _state(soil=_product("soil", quality_status="degraded"))

    assert healthy.eligibility["propose"]["allowed"] is True
    assert degraded.eligibility["propose"]["allowed"] is False
    assert healthy.state_digest != degraded.state_digest, (
        "‏quality_status جزء من المنتَج المُبصَم، فاختلافه يجب أن يُغيّر البصمة"
    )

    repeat = _state()
    assert repeat.state_digest == healthy.state_digest
    assert repeat.eligibility == healthy.eligibility


def test_every_declared_level_is_present_and_shaped():
    state = _state()
    assert set(state.eligibility) == set(ELIGIBILITY_LEVELS)
    for level, verdict in state.eligibility.items():
        assert isinstance(verdict["allowed"], bool), level
        assert isinstance(verdict["reasons"], list), level
        assert all(isinstance(r, str) for r in verdict["reasons"]), level
    assert "eligibility" in state.to_dict()
