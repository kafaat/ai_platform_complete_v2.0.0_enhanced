"""أعمدةُ ``jsonb`` تصل **نصّاً** — والمنسّقُ كان يُعاملها كأنّها مفكوكة.

**العطلُ المقيس لا المتوقَّع:** ``asyncpg`` يُسلّم ``jsonb`` سلسلةً ما لم يُسجَّل
مُرمِّز، ومسبحُ ``api/main.py`` لا يُسجّله — يقيس ذلك بقاعدةٍ حيّة
``tests_v9/test_live_pg_fake_connection_debt.py::test_asyncpg_really_returns_jsonb_as_str_without_a_codec``.
فكان ``dict(row["payload"])`` يرفع ``ValueError`` عند أوّل صفٍّ حقيقيّ، وكانت
``list(row["blocking_reasons"])`` تُحوّل ``"[]"`` إلى ``['[', ']']`` **بلا خطأ**.

**ولماذا نجا العطلُ من الجناح:** بديلُ ``fetchrow`` في
``services/sahool-platform/tests/test_irrigation_runtime_orchestrator.py`` يبني
الصفَّ بكائناتٍ **مفكوكةٍ أصلاً** — فيفترض الجوابَ الذي يدّعي قياسه. وهذا الملفّ
يقيس الشكلَ الذي تُسلّمه القاعدةُ فعلاً.

**والعطلُ نفسُه أُصلح مرّةً من قبل** في العامل، ووُثّق في docstring الدالّة
``decode_jsonb`` حرفيّاً — وبقي هذا الموضعُ عليه. فالشاهدُ هنا يمنع عودتَه ثالثةً.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api import irrigation_runtime_orchestrator as orchestrator

pytestmark = pytest.mark.unit

# استيرادٌ مباشر بلا `importorskip`: `conftest.py` في الجذر يضع
# `services/sahool-platform` على `sys.path` أصلاً. وتخطٍّ هنا كان سيُحوّل كلَّ
# طفرةٍ تُسمّي هذه الاختبارات إلى **صمتٍ** لا تكذيب (STABLE_WRONG_TEST).
_PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"


# ── الشكلُ الذي تُسلّمه القاعدة فعلاً: نصّ ───────────────────────────────────


def test_a_jsonb_object_arriving_as_text_is_decoded_not_crashed():
    """هذا هو العطلُ بعينِه: ``dict('{"a": 1}')`` يرفع ``ValueError``."""
    assert orchestrator._jsonb_object('{"a": 1, "b": [2]}', column="t.c") == {"a": 1, "b": [2]}


def test_a_jsonb_array_arriving_as_text_is_a_list_not_its_characters():
    """``list('["X"]')`` يُعيد حروفاً **بلا خطأ** — والصمتُ أخطرُ من الرفع.

    لو بقي العطلُ لصار سببا حجبٍ مختلقان من قوسين، ولا يحمرّ شيء.
    """
    assert orchestrator._jsonb_reasons('["A", "B"]', column="t.c") == ["A", "B"]
    assert orchestrator._jsonb_reasons("[]", column="t.c") == []


# ── والاتّجاه المقابل: ما كان يعمل لا ينكسر ─────────────────────────────────


def test_an_already_decoded_value_still_passes_through():
    """بعضُ المستهلكين يمرّون بقيمةٍ مفكوكة (مُرمِّزٌ مُسجَّل، أو بديلُ اختبار).

    بلا هذا الاتّجاه يمرّ إصلاحٌ يفكّ النصَّ ويكسر المفكوك.
    """
    assert orchestrator._jsonb_object({"a": 1}, column="t.c") == {"a": 1}
    assert orchestrator._jsonb_reasons(["A"], column="t.c") == ["A"]


def test_a_null_column_falls_back_to_its_empty_shape():
    assert orchestrator._jsonb_object(None, column="t.c") == {}
    assert orchestrator._jsonb_reasons(None, column="t.c") == []


# ── والبنيةُ الفاسدة حجبٌ مسمّى لا خمسُمئة عارية ────────────────────────────


@pytest.mark.parametrize(
    ("value", "decoder"),
    [
        ("[1, 2]", "_jsonb_object"),
        ('"نصّ"', "_jsonb_object"),
        ('{"a": 1}', "_jsonb_reasons"),
        ("3", "_jsonb_reasons"),
    ],
)
def test_a_wrong_shape_names_its_column_instead_of_escaping_as_500(value, decoder):
    with pytest.raises(orchestrator._MalformedCanonicalRow) as caught:
        getattr(orchestrator, decoder)(value, column="canonical_x.payload")
    assert caught.value.column == "canonical_x.payload"


@pytest.mark.parametrize("decoder", ["_jsonb_object", "_jsonb_reasons"])
def test_truncated_json_blocks_by_name_instead_of_escaping_as_500(decoder):
    """عمودٌ محفوظٌ مبتوراً يرفع ``JSONDecodeError`` من ``json.loads``.

    وهي ``ValueError`` **لا** يلتقطها اشتراطُ البنية وحدَه، فتهرب خمسمئةً عارية —
    وهو ثغرةُ الصياغة الأولى لهذا الإصلاح، سدّها ``_decode_or_block``.
    """
    with pytest.raises(orchestrator._MalformedCanonicalRow) as caught:
        getattr(orchestrator, decoder)("{", column="canonical_x.payload")
    assert caught.value.column == "canonical_x.payload"


def test_a_reason_list_of_non_strings_is_malformed_not_a_numeric_block_reason():
    """``[1]`` قائمةٌ صحيحة البنية، لكنّها تُنتِج سببَ حجبٍ رقميّاً يقرؤه إنسان.

    اشتراطُ نوع العنصر لا يزيد على اشتراط القائمة — وهو ما أضافته المراجعة المتوازية.
    """
    with pytest.raises(orchestrator._MalformedCanonicalRow):
        orchestrator._jsonb_reasons("[1]", column="t.blocking_reasons")
    with pytest.raises(orchestrator._MalformedCanonicalRow):
        orchestrator._jsonb_reasons('["ok", 2]', column="t.blocking_reasons")


def test_every_jsonb_column_the_orchestrator_reads_goes_through_a_decoder():
    """حارسُ الانحدار: عمودٌ جديد يُقرأ بـ``dict(...)``/``list(...)`` يُعيد العطل.

    يُشتقّ من المصدر لا من قائمةٍ مكتوبة، فلا يبيت حين يُضاف عمود.
    """
    source = (_PLATFORM / "api" / "irrigation_runtime_orchestrator.py").read_text(encoding="utf-8")
    for raw in ('dict(row["', 'list(row["'):
        assert raw not in source, (
            f"قراءةٌ مباشرة {raw}…) عادت إلى المنسّق — وهي العطلُ نفسُه: "
            "asyncpg يُسلّم jsonb نصّاً. مرّرها عبر _jsonb_object/_jsonb_reasons."
        )
