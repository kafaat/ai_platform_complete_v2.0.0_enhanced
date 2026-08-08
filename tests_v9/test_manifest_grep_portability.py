"""أوامر بناء MANIFEST تُقرأ بـ`grep` محمول — `MANIFEST-GREP-USES-GNU-ONLY-SHORTHAND-01`.

`\\s` **ليس جزءاً من POSIX ERE**، وتفسيرُ الشرطة المائلة قبل حرفٍ عاديّ مثل `s`
**غير محدَّد** في المواصفة خارج امتدادات التطبيق. فالسلوك **قد يختلف** بين GNU
وBusyBox وBSD، **ولا يجوز الاعتماد عليه**. والبديل المحمول `[[:space:]]`.

**وما لا يُقال هنا:** لم يُدَّعَ أنّ تطبيقاً بعينه يُطابِق `s` حرفيّاً — ذلك يقتضي
تشغيله فعلاً، وهو غير متاح في هذه الشجرة. المُثبَت هو **عدم التحديد**، وهو وحده كافٍ:
بوّابةٌ تعتمد سلوكاً غير محدَّد بوّابةٌ لا تعرف ماذا تقيس.

**والموضعان اللذان يقرآن `MANIFEST.txt` ليسا زخرفاً:** أحدهما يغذّي الحلقة التي
**تُطبّق** الهجرات، والآخر يغذّي `expected` في بوّابة «طُبِّق N من M» — وهي البوّابة
التي تكشف إسقاط ملفٍّ صامتاً. فنمطٌ يُخطئ الاستبعاد يُفسِد **العدّ الذي تُبنى عليه**،
لا الشكل وحده.

**ولماذا لم يُمسَك حتّى الآن:** CI يعمل على `ubuntu-latest` بـ`grep` GNU، فالنمطان
متكافئان هناك تماماً — مقيس: كلاهما يُعطي العدد نفسه على `MANIFEST.txt` الحقيقيّ.
العطل **كامنٌ في المحمولية لا واقعٌ في CI**، وهو بالضبط ما يجعله يمرّ سنةً كاملة.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
MANIFEST = ROOT / "migrations" / "MANIFEST.txt"

#: استدعاء `grep` يقرأ `MANIFEST.txt` **بنمطٍ مقتبَس** — يُلتقَط النمط للفحص.
_MANIFEST_GREP = re.compile(r"grep\s+-[a-zA-Z]*E\s+'([^']+)'\s+migrations/MANIFEST\.txt")

#: **كلّ** استدعاء `grep` يذكر `MANIFEST.txt` — أوسع عمداً من الذي يلتقط النمط.
#: الفارق بين العدّتين هو **قياس اكتمال الاستخراج**: استدعاءٌ يُرى ولا يُلتقَط نمطُه
#: يعني أنّ هذا الملفّ يفحص بعضاً ويُبلِّغ عن كلّ.
_ANY_MANIFEST_GREP = re.compile(r"grep\b[^\n]*migrations/MANIFEST\.txt")

#: مختصرات فئات محارف **ليست من POSIX ERE**. الاسم يقول ما يُثبَت: خارجَ POSIX،
#: لا «GNU وحدها» — فبعض التطبيقات تدعمها وبعضها لا، وذلك بالضبط ما لا يُعتمَد عليه.
_NON_POSIX_SHORTHAND = ("\\s", "\\S", "\\d", "\\D", "\\w", "\\W")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _patterns() -> list[str]:
    return _MANIFEST_GREP.findall(_workflow_text())


def _all_grep_invocations() -> list[str]:
    return _ANY_MANIFEST_GREP.findall(_workflow_text())


def test_the_extraction_covers_every_manifest_grep():
    """**اكتمال الاستخراج مقيس، لا `len(...) >= 3`.**

    عتبةٌ مثل «ثلاثة على الأقلّ» تمرّ خضراء وفيها استدعاءٌ رابع لا يُفحَص — فتصير
    خضرةُ هذا الملفّ ادّعاءَ تغطيةٍ لا يملكها. فيُقارَن **مجموع** استدعاءات `grep`
    التي تذكر `MANIFEST.txt` بعدد الأنماط المُلتقَطة: كلّ استدعاءٍ يُرى يجب أن
    يُلتقَط نمطُه.

    والفارق يقع حقيقةً حين تتغيّر الصياغة: اقتباسٌ مزدوج بدل مفرد، أو نمطٌ في متغيّر
    شِلّيّ. عندها يبقى الاستدعاء مرئيّاً ويسقط التقاطُه — وهذا الاختبار يحمرّ بدل أن
    يصمت.
    """
    invocations = _all_grep_invocations()
    patterns = _patterns()
    assert invocations, "لم يُعثَر على أيّ `grep` يقرأ MANIFEST.txt — صحّح المرساة لا الاختبار"
    assert len(patterns) == len(invocations), (
        f"استُخرِج {len(patterns)} نمطاً من {len(invocations)} استدعاءً — "
        f"الفارق لا يُفحَص وهذا الملفّ يُبلِّغ عن كلّه:\n" + "\n".join(f"  · {inv}" for inv in invocations)
    )


@pytest.mark.parametrize("pattern", _patterns())
def test_no_manifest_pattern_uses_non_posix_shorthand(pattern):
    """مَنعٌ يُسمّي سببه — عقد `prohibition_reason_guard`.

    ولا يمكن قياس هذا سلوكيّاً هنا: `grep` في هذه البيئة **هو** GNU، فالنمطان
    متكافئان تحته. وخارجه السلوك **غير محدَّد بالمواصفة** لا معروفاً ومختلفاً —
    ولا مُفسِّر آخر في الشجرة يُقاس عليه. فالتأكيد نصّيّ **بالضرورة**، وسببه مكتوب
    في رسالته لا في مراجعة.
    """
    for shorthand in _NON_POSIX_SHORTHAND:
        assert shorthand not in pattern, (
            f"‏`{shorthand}` ليس من POSIX ERE، وتفسيرُه خارج امتدادات التطبيق "
            f"**غير محدَّد** — فقد يختلف بين GNU وBusyBox وBSD ولا يُعتمَد عليه. "
            f"وعليه يقوم عدّ «طُبِّق N من M». "
            f"استعمل `[[:space:]]` — النمط المُخالِف: {pattern}"
        )


def test_all_manifest_patterns_count_the_same_lines():
    """**الشقّ السلوكيّ — وهو الأهمّ:** يقيس ما تبني عليه البوّابة لا كيف كُتِب.

    تُشغَّل كلّ الأنماط المُستخرَجة على `MANIFEST.txt` **الحقيقيّ**، ويُؤكَّد أنّها
    تُعطي العدد نفسه. فلو أُصلِح نمطٌ بصياغةٍ تُغيّر ما يُستبعَد — لا محموليّته وحدها —
    لتحرّك العدد الذي تقارن به بوّابة «طُبِّق N من M»، وهو **أخطر من عدم المحمولية**:
    يفشل في CI نفسه بلا سببٍ ظاهر.
    """
    patterns = _patterns()
    counts = {}
    for pattern in patterns:
        proc = subprocess.run(
            ["grep", "-vcE", pattern, str(MANIFEST)],
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        counts[pattern] = int(proc.stdout.strip())

    assert len(set(counts.values())) == 1, f"أنماط MANIFEST تعدّ أعداداً مختلفة: {counts}"

    declared = [
        line
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert next(iter(counts.values())) == len(declared), (
        f"عدّ `grep` ({next(iter(counts.values()))}) لا يساوي الهجرات المُعلَنة "
        f"({len(declared)}) — البوّابة تقارن برقمٍ لا يعني ما تظنّه"
    )
