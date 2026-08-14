"""تعليماتُ RLS الحيّة لا تُعلِّم وضع كلمة المرور في سطر الأوامر.

`RLS-DOCS-TEACH-A-COMMAND-LINE-PASSWORD-01`. ثلاثة مواضع حيّة كانت تحمل
`postgresql://sahool_user:PASS@…` في أمرٍ **يُنسَخ ويُشغَّل**: دليل الاختبار، ورأس
سكربت SQL نفسه، وتلميحُ `runtime_truth_report` المطبوع. وسطرُ الأوامر يُقرأ من `ps`
ويُحفظ في تاريخ الصدفة — والقاعدة مكتوبة في `docs/runbooks/` منذ v208: «لا تضع كلمة
المرور في سطر أوامر مشترك ولا في سجلّ». فكانت الوثائق تنهى في موضعٍ وتُعلِّم في آخر.

**والمقياس على الشكل لا على الكلمة:** `PASS` نفسها ليست سرّاً، والعطل أنّ **شكل**
المثال يُعلِّم موضعاً خاطئاً — فمن يستبدلها بسرٍّ حقيقيّ يتبع ما رآه. ولذلك يُرصَد
`scheme://role:anything@` لا السلسلة `PASS`.

**وحدّ الفحص مُعلَن ومقيس:** يحرس **هذه الملفّات الثلاثة** لا الشجرة. المسح الشجريّ
يعطي ١٢٣ موضعاً في ٧١ ملفّاً، وأغلبها مشروع تماماً — قواعد CI المؤقّتة، وتجهيزات
اختبار، و`${VAR}` في compose. فحارسٌ شجريّ كان سيقتضي مُصنِّفاً لا أملك تبريره،
وحارسٌ يتّهم الصحيح يُنزَع في أوّل يوم. والمحروس هنا صنفٌ واحد بيّن: **أمرٌ يكتبه
إنسان في طرفيّته**.

**ولا يُفحَص `docs/history/`:** فيه الشكل نفسه (`POST_EXECUTION_PLAN.md:27`) ولم
يُصحَّح عمداً — سجلٌّ يقول ما قيل حينها، وتصحيحُه يجعل السجلّ يخالف نفسه. ولا أحد
يُشغّل خطّةً من أرشيف.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]

# الملفّات الحيّة التي يقرؤها مُشغِّلٌ بشريّ فينسخ منها أمراً.
_WATCHED = (
    "scripts_v9/README_RLS_TESTING.md",
    "scripts_v9/test_tenant_isolation.sql",
    "scripts_v9/runtime_truth_report.py",
)

# اعتمادٌ مضمَّن: مخطَّط، فدور، فنقطتان، فشيءٌ ليس فارغاً، ثمّ `@`. ويُستثنى
# `${VAR}` لأنّه إحالةٌ إلى بيئة لا سرٌّ مكتوب.
_INLINE_CREDENTIAL = re.compile(r"(?:postgresql|postgres)://[A-Za-z0-9_.-]+:(?!\$\{)[^@\s'\"]+@")


def _offenders(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if _INLINE_CREDENTIAL.search(line)]


@pytest.mark.parametrize("rel", _WATCHED)
def test_no_live_rls_instruction_carries_an_inline_password(rel: str) -> None:
    found = _offenders((_ROOT / rel).read_text(encoding="utf-8"))
    assert found == [], f"{rel}: أمرٌ يُعلِّم كلمة المرور في سطر الأوامر: {found}"


@pytest.mark.parametrize("rel", _WATCHED)
def test_the_instruction_still_names_the_non_superuser_role(rel: str) -> None:
    """نزعُ الاعتماد لا يجوز أن ينزع **الدرس**: الدور غير الـsuperuser هو المقصد.

    لو حُذِف المثال كلّه لَمرّ الفحص الأوّل — وهو أرخص طريقة لإرضاء حارسٍ بلا
    إصلاح. فيُقاس بقاءُ `sahool_user` في نفس الملفّ.
    """
    assert "sahool_user" in (_ROOT / rel).read_text(encoding="utf-8"), rel


@pytest.mark.parametrize("rel", _WATCHED)
def test_each_instruction_says_where_the_password_belongs(rel: str) -> None:
    """«لا تكتبها هنا» بلا «اكتبها هناك» تُنتِج التفافاً لا امتثالاً."""
    text = (_ROOT / rel).read_text(encoding="utf-8")
    assert ".pgpass" in text or "PGPASSWORD" in text, f"{rel}: لا بديل مذكور"


def test_the_detector_actually_fires_on_the_shape_it_claims() -> None:
    """الفحص الذي لا يُجرَّب على الشكل الذي يزعم رصده قد لا يرصد شيئاً.

    والحالة الثالثة هي التي تفصل «رصدُ الشكل» عن «رصدُ الكلمة `PASS`»: سرٌّ
    حقيقيّ لا يحمل الكلمة، وهو بعينه ما سيكتبه من يتبع المثال.
    """
    assert _offenders("psql 'postgresql://sahool_user:PASS@h/db'")
    assert _offenders("export U='postgres://r:s3cr3t@localhost/db'")
    # ولا يتّهم الصحيح: بلا اعتماد، أو إحالةٌ إلى متغيّر بيئة.
    assert _offenders("psql 'postgresql://sahool_user@h:5432/db'") == []
    assert _offenders("postgresql://sahool_user:${DB_PASSWORD}@h/db") == []
