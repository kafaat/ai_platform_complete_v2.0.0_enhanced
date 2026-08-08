"""أوامر بناء MANIFEST تُقرأ بـ`grep` محمول — `MANIFEST-GREP-USES-GNU-ONLY-SHORTHAND-01`.

`\\s` **امتداد GNU لا POSIX**. على `grep` غير GNU (BusyBox في صور alpine · macOS/BSD)
لا يُطابِق `\\s` مسافةً بل **الحرف `s` حرفيّاً** — فسطرُ تعليقٍ لا يُستبعَد، ويُقرأ
اسمَ هجرة.

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

#: كلّ استدعاء `grep` يقرأ `MANIFEST.txt` — يُلتقَط نمطُه المقتبَس بنيويّاً.
_MANIFEST_GREP = re.compile(r"grep\s+-[a-zA-Z]*E\s+'([^']+)'\s+migrations/MANIFEST\.txt")

#: مختصرات فئات المحارف في GNU ERE. غيابها من POSIX هو العطل.
_GNU_ONLY = ("\\s", "\\S", "\\d", "\\D", "\\w", "\\W")


def _patterns() -> list[str]:
    return _MANIFEST_GREP.findall(WORKFLOW.read_text(encoding="utf-8"))


def test_every_manifest_reader_was_found():
    """حارسٌ لا يجد موضوعه يُبلِغ خضرةً عن سؤالٍ لم يطرحه.

    فإن تغيّرت صياغة الاستدعاء يوماً (‏`"…"` بدل `'…'`، أو مسارٌ آخر) يسقط الالتقاط
    إلى صفر — ويصير هذا الملفّ كلّه أخضر بلا أن يفحص شيئاً. يُمسَك هنا صراحةً.
    """
    found = _patterns()
    assert len(found) >= 3, f"لم تُلتقَط أوامر MANIFEST — صحّح النمط لا الاختبار: {found}"


@pytest.mark.parametrize("index", range(3))
def test_no_manifest_pattern_uses_gnu_only_shorthand(index):
    """مَنعٌ يُسمّي سببه — عقد `prohibition_reason_guard`.

    ولا يمكن قياس هذا سلوكيّاً هنا: `grep` في هذه البيئة **هو** GNU، فالنمطان
    متكافئان تحته. الفارق يظهر على BusyBox/BSD وحدهما، ولا مُفسِّر لهما في الشجرة.
    فالتأكيد نصّيّ **بالضرورة**، وسببه مكتوب في رسالته لا في مراجعة.
    """
    patterns = _patterns()
    if index >= len(patterns):
        pytest.skip("عدد الأنماط أقلّ — يُمسَك في test_every_manifest_reader_was_found")
    pattern = patterns[index]
    for shorthand in _GNU_ONLY:
        assert shorthand not in pattern, (
            f"‏`{shorthand}` امتداد GNU لا POSIX: على BusyBox/BSD يُطابِق الحرف نفسه "
            f"لا الفئة، فسطر تعليقٍ يُقرأ اسمَ هجرة ويُفسِد عدّ «طُبِّق N من M». "
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
