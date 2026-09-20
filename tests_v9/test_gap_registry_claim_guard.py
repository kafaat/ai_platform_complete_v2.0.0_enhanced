"""تكذيبُ ربط الادّعاءات العدديّة بالقياس — `A-HAND-WRITTEN-COUNT-IN-THE-JOURNAL-DRIFTS-FROM-ITS-OWN-MEASUREMENT-01`.

الخاصّيّةُ المقيسة ليست «يمرّ على شجرةٍ سليمة» — تلك يُحقّقها حارسٌ لا يفعل شيئاً. بل:
**رقمٌ عن الحاضر يخالف المقيسَ يُحمِّر**، و**رقمٌ عن شجرةٍ ماضيةٍ يذكر بصمتَها لا يُحمِّر**.
والثانيةُ ليست تزيّداً: السجلُّ سردٌ تاريخيّ، وحارسٌ يطلب من أعداده الماضية أن تساوي
قياسَ اليوم يُحمِّر على عملٍ سليم فيُطفَأ — وحمايةٌ تُطفَأ حمايةٌ صفر.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "gap_registry_claim_guard.py"
_REGISTRY = _ROOT / "sahool-brain" / "gaps" / "registry.md"

_spec = importlib.util.spec_from_file_location("grcg", _GUARD)
guard = importlib.util.module_from_spec(_spec)
sys.modules["grcg"] = guard
assert _spec.loader is not None
_spec.loader.exec_module(guard)

#: قياسٌ اصطناعيٌّ ثابت — الشواهدُ تقيس **قاعدةَ الربط** لا سجلَّ اليوم.
_MEASURED = {
    "heading_count": 273,
    "section_state_count": 52,
    "gap_row_count": 253,
    "row_count": 267,
    "duplicate_heading_id_count": 14,
    "orphan_gap_heading_count": 211,
    "noncanonical_heading_level_count": 0,
    "contradictory_section_id_count": 0,
    "_unclassified_total": 0,
}


def _evaluate(text: str) -> list[str]:
    return guard.evaluate(guard.claims(text), _MEASURED)


# ── رقمٌ عن الحاضر يجب أن يصدق الآن ────────────────────────────────────────────


def test_a_present_tense_claim_that_disagrees_blocks():
    """**العطلُ المقيس بحرفه.** هذا هو السطرُ الذي دُمِج إلى `main` في #1038."""
    errors = _evaluate("- **المقيسُ بعد الإصلاح:** `heading_count=272` · `section_state_count=51`.")
    assert len(errors) == 2
    assert "heading_count=272" in errors[0] and "**273**" in errors[0]
    assert "section_state_count=51" in errors[1] and "**52**" in errors[1]


def test_a_present_tense_claim_that_agrees_passes():
    """ولا يُحمِّر على الصادق — وإلّا صار الحارسُ ضريبةً لا حماية."""
    assert _evaluate("- المقيس: `heading_count=273` · `section_state_count=52`.") == []


def test_the_message_names_both_remedies():
    """رسالةٌ بلا علاجٍ تُدرِّب قارئَها على تجاوزها، والعلاجان هنا مختلفان.

    إمّا أن يُصحَّح الرقم، وإمّا أن يُعلَن أنّه عن شجرةٍ ماضيةٍ **باسمها** — ولا
    يعرف الحارسُ أيَّهما أراد الكاتب، فيذكرهما معاً.
    """
    message = _evaluate("`heading_count=999`")[0]
    assert "المقيسُ الآن" in message
    assert "بصمتَها" in message


# ── ورقمٌ عن شجرةٍ ماضيةٍ يجب أن يقول أيَّ شجرة ──────────────────────────────────


def test_a_claim_that_names_its_tree_is_not_blocked():
    """**الحدُّ الذي يمنع الحارسَ من أن يُحمِّر على السرد التاريخيّ.**

    هذا سطرٌ حقيقيٌّ في السجلّ: أعدادٌ **صحيحة** عن شجرتين ماضيتين. حارسٌ يطلب
    منها أن تساوي قياسَ اليوم يُحمِّر على توثيقٍ سليم.
    """
    line = "#1033 عند `4b8641af` ⇒ `heading_count=263` · `section_state_count=42`."
    assert _evaluate(line) == []


def test_naming_a_tree_is_what_exempts_not_the_word_historical():
    """المُرساةُ **بصمةُ الشجرة** لا كلمةٌ في النثر — وإلّا صار الإعفاءُ بالادّعاء."""
    assert _evaluate("تاريخيّاً كان `heading_count=263` في الماضي.") != []
    assert _evaluate("عند `4b8641af` كان `heading_count=263`.") == []


# ── الحقلُ ليس أضيقَ من دعواه ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "line,expected",
    [
        ("`orphan=999`", 1),
        ("`orphans=999`", 1),
        ("`duplicates=999`", 1),
        ("`unclassified=999`", 1),
        ("`noncanonical=999`", 1),
        ("`orphan=211`", 0),
        ("`duplicates=14`", 0),
        ("`unclassified=0`", 0),
    ],
)
def test_the_short_forms_people_actually_write_are_read(line: str, expected: int):
    """**المختصراتُ مقيسةٌ من السجلّ لا مُخترَعة.**

    `orphan=` و`duplicates=` و`unclassified=` مكتوبةٌ في الشجرة فعلاً. وحارسٌ يقرأ
    الاسمَ الطويل وحدَه يزعم أنّه يربط الادّعاءات وهو يرى بعضَها — **أضيقُ من دعواه**،
    وهو صنفُ عطلٍ مسجَّلٌ في هذا المستودع باسمه.
    """
    assert len(_evaluate(line)) == expected


def test_unclassified_sums_both_lists_not_one():
    """`unclassified` في نثر هذا السجلّ تعني «لا صفَّ ولا قسمَ بلا تصنيف» — وهما حقلان.

    قراءةُ أحدهما تجعل `unclassified=0` تمرّ بينما قسمٌ غيرُ مصنَّفٍ قائم: سلبيّةٌ
    كاذبةٌ في الحقل الذي وُجِد الحارسُ ليمنعها.
    """
    report = {
        "heading_count": 1,
        "unclassified_rows": [],
        "unclassified_section_states": [{"id": "X"}],
    }
    assert guard.measured_values(report)["_unclassified_total"] == 1


def test_an_invented_field_name_fails_closed():
    """اسمٌ لا يقيسه شيء يُقرأ دليلاً وهو ليس كذلك — فلا يمرّ صامتاً."""
    errors = guard.evaluate(
        [
            {
                "line": 1,
                "key": "heading_count",
                "field": "not_a_field",
                "value": 1,
                "historical": False,
            }
        ],
        _MEASURED,
    )
    assert errors and "لا يقابله حقلٌ" in errors[0]


def test_a_claim_inside_a_fenced_block_is_an_example_not_an_assertion():
    """مثالٌ داخل سياجٍ ليس دعوى — وإلّا صار توثيقُ الحارس يُحمِّر الحارسَ نفسَه."""
    fenced = "```\n`heading_count=999`\n```\n"
    assert _evaluate(fenced) == []
    assert _evaluate("`heading_count=999`\n") != []


# ── على الشجرة الحقيقيّة ────────────────────────────────────────────────────────


def test_the_live_registry_agrees_with_its_own_measurement():
    """**الزرعُ الحيّ.** لا شاهدَ اصطناعيّ: السجلُّ الحقيقيُّ يُقاس ويُقارَن بنفسه."""
    assert guard.main(["--registry", str(_REGISTRY)]) == 0


def test_the_live_registry_still_binds_at_least_one_present_tense_claim():
    """وحدُّ صدقٍ لازم: حارسٌ لا يجد ما يربطه أخضرُ **وفارغ**.

    خضرةٌ بلا ادّعاءٍ واحدٍ عن الحاضر لا تفرّق عن حارسٍ لا يفعل شيئاً — وهذا
    الشاهدُ يجعل تلك الحالةَ مرئيّة بدل أن تُقرأ نجاحاً.
    """
    found = guard.claims(_REGISTRY.read_text(encoding="utf-8"))
    assert any(not claim["historical"] for claim in found), (
        "لا ادّعاءَ عن الحاضر في السجلّ — الحارسُ أخضرُ لأنّه لم يجد ما يقيسه"
    )
