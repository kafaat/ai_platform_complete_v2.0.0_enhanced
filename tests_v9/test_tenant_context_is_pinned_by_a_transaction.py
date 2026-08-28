"""`tenant_context` تُثبِّت مستأجرَها بمعاملة — وإلّا ضاع الضبطُ قبل أوّل استعلام.

**العطلُ المقيس، لا المتوقَّع:** `set_config(..., true)` تعني «محلّيٌّ للمعاملة».
وبلا معاملةٍ محيطة يُلغى الضبطُ فورَ انتهاء العبارة. قِيس على PostgreSQL 16 داخل
كتلة `tenant_context` بعينها:

    الصياغةُ السابقة  ⇒ current_setting('app.current_tenant') = ''
    الصياغةُ الحاليّة ⇒ current_setting('app.current_tenant') = 'tenant-A'

وأثرُه ليس تجميليّاً: `query_with_tenant` و`execute_with_tenant` تُنفّذان استعلامَهما
**بعد** ضياع الضبط، فكانتا تعملان بلا مستأجرٍ أصلاً — على قاعدةٍ تحرسها RLS يعني ذلك
إمّا صفراً كاذباً وإمّا خطأً، وأيّهما وقع فليس عزلاً.

**ولمَ اختبارٌ ساكن لا حيّ:** الحيُّ يحتاج قاعدةً فيحمل `skipif`، والمكنسةُ تعمل بلا
قاعدة فيُتخطّى — فتصير الطفرةُ صمتاً لا تكذيباً (`STABLE_WRONG_TEST`). وهذا الملفّ
يعمل في كلّ بيئة، فيصلح لأن تحرسه طفرة. والبرهانُ الحيُّ مُدوَّنٌ في وصف الدالّة نفسِها.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "shared/helpers.py"


def _function(name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(HELPERS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"لم تعد `{name}` موجودةً في {HELPERS.name}")


def _sets_local_guc(node: ast.AST) -> bool:
    """هل تحوي هذه العقدةُ `set_config(..., true)`؟ — نصّاً على SQL المُمرَّر."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            sql = " ".join(child.value.split()).lower()
            if "set_config(" in sql and sql.rstrip(")\"' ").endswith("true"):
                return True
    return False


def test_tenant_context_sets_the_guc_inside_an_explicit_transaction():
    """الضبطُ المحلّيّ بلا معاملةٍ يُلغى قبل أن يراه أيُّ استعلام.

    يُقاس **الاقتران** لا مجرّد وجود المعاملة: أنّ عبارةَ `set_config(..., true)`
    تقع **داخل** جسم `async with conn.transaction()`. فمعاملةٌ في مكانٍ آخر من
    الدالّة تمرّ أمام فحصٍ ساذجٍ ولا تُثبِّت شيئاً.
    """
    node = _function("tenant_context")
    withs = [n for n in ast.walk(node) if isinstance(n, ast.AsyncWith)]
    assert withs, (
        "`tenant_context` بلا `async with` — فالضبطُ المحلّيّ يُلغى قبل أوّل استعلام، "
        "وتعمل `query_with_tenant` و`execute_with_tenant` بلا مستأجر."
    )
    pinned = [
        w
        for w in withs
        if any("transaction" in ast.dump(item.context_expr) for item in w.items)
        and any(_sets_local_guc(stmt) for stmt in w.body)
    ]
    assert pinned, (
        "`set_config(..., true)` ليست داخل جسم `async with conn.transaction()` — "
        "فهي محلّيّةٌ لمعاملةٍ لا وجودَ لها، وتُلغى فورَ انتهاء العبارة."
    )


def test_the_session_wide_escape_hatch_stays_closed():
    """`is_local=false` يحلّ العطلَ ظاهراً ويفتح أسوأَ منه.

    الضبطُ على مستوى الجلسة يبقى على الاتّصال بعد الكتلة، وفي بِركة اتّصالاتٍ يرثه
    المستعيرُ التالي — تسريبٌ عابرَ مستأجرين أخطرُ من الضياع الأصليّ، ولا يحمرّ منه
    شيء. فيُمنع صراحةً هنا بدل أن يُكتشَف بعد وقوعه.
    """
    node = _function("tenant_context")
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            sql = " ".join(child.value.split()).lower()
            if "set_config(" in sql:
                assert not sql.rstrip(")\"' ").endswith("false"), (
                    "`set_config(..., false)` يضبط على مستوى الجلسة فيتسرّب عبر بِركة "
                    "الاتّصالات إلى المستأجر التالي. المعاملةُ هي الحدُّ الصحيح."
                )


def test_the_dead_enforcer_that_could_never_work_is_gone():
    """`enforce_tenant` كانت تضبط GUC محلّيَّ معاملةٍ **بلا معاملةٍ ولا كتلة**.

    فلا يمكنها أن تُنفّذ شيئاً بحكم البناء: العبارةُ التالية لا ترى الضبطَ أبداً.
    واسمُها يَعِد بإنفاذٍ لا يقع — وهو أسوأُ من غيابها، لأنّ قارئاً يراها فيظنّ
    المسارَ محروساً. صفرُ مُنادين في الشجرة، ويؤكّده جردُ الشيفرة الميّتة
    (`dead_code_candidates.csv:598`). حُذِفت، ويمنع هذا عودتَها.
    """
    tree = ast.parse(HELPERS.read_text(encoding="utf-8"))
    names = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    assert "enforce_tenant" not in names, (
        "عادت `enforce_tenant` — دالّةٌ تَعِد بإنفاذِ مستأجرٍ ولا تستطيعه بحكم البناء. "
        "من أرادها فليجعلها كتلةً بمعاملة، لا سطراً يضبط ويمضي."
    )
