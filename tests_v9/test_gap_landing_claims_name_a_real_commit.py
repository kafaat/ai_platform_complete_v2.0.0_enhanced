"""عنوان فجوة يقول «هبطت في `<sha>`» يجب أن يسمّي التزاماً موجوداً وسلفاً لـHEAD.

**الحادثة التي أوجبته، لا فرضيّة.** ثلاثة عناوين في `gaps/registry.md` بقيت تقول
«مُصلَحة في **مرشّح الدمج**» بعد أن دُمِجت مرشّحاتها الثلاثة (#770 · #771 · #772).
الحالة كانت **صحيحة يوم كُتِبت** وبائتة يوم تُقرأ — وهذا أخبث من الخطأ الصريح:
قارئٌ يرى «مرشّح» يفترض عملاً معلّقاً ويبحث عن PR مفتوح لا وجود له.

وهو الصنف الذي يسمّيه السجلّ عن نفسه: «بندٌ يقول «مفتوح» بعد إغلاقه يجعل السجلّ
يكذب بصمت».

**والحارس هنا يقيس الشطر القابل للقياس فقط.** لا يمكنه أن يعرف متى *يجب* أن تتغيّر
حالة، لكنّه يعرف أنّ حالةً تدّعي هبوطاً في التزام **يجب أن تسمّي التزاماً حقيقيّاً**
سلفاً لِما نحن عليه. فالادّعاء يصير قابلاً للتكذيب بدل أن يكون نصّاً.

هذا يمسك: SHA مختلقاً · SHA بمطبعة · وادّعاء هبوط كُتِب **قبل** الهبوط فعلاً (وهو
بالضبط ما كان سيمنع كتابة «مرشّح الدمج» بوصفها حالة نهائيّة).

**ولا يمسك** بقاء «مرشّح الدمج» نفسها — تلك تحتاج معرفة حالة PR خارجيّة، وهي خارج
ما يُقاس بلا شبكة. الحدّ مُصرَّح به هنا بدل أن يُترك ليُقرأ الأخضر أوسع ممّا يقيس.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = _ROOT / "sahool-brain" / "gaps" / "registry.md"

# عنوان فجوة يعلن هبوطاً: `## <GAP-ID> — هبطت في `<sha>``.
# المرساة `^##` مقصودة: ذكرُ SHA داخل متن ليس إعلان حالة، ومطابقته تُنتج نفس صنف
# الإيجابيّ الكاذب الذي أسقط `CONFLICT_RE` غير المُرسى، وأسقط `CLOSED_RE` على
# `production_certified=0/81` المذكور نفياً لا ادّعاءً.
_LANDED_RE = re.compile(
    r"^##\s+(?P<gap_id>[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)+)\s+—\s+هبطت في\s+`(?P<sha>[0-9a-f]{7,40})`",
    re.M,
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def _landing_claims() -> list[tuple[str, str]]:
    text = _REGISTRY.read_text(encoding="utf-8")
    return [(m.group("gap_id"), m.group("sha")) for m in _LANDED_RE.finditer(text)]


def test_the_registry_actually_carries_landing_claims():
    """حارسٌ على قائمة فارغة يبقى أخضر إلى الأبد — والفراغ نفسه يجب أن يُدان.

    بلا هذا الفحص كان تغييرُ صياغة العنوان (أو حذف الادّعاءات) يُطفئ الحارس كلّه
    بصمت ويُبقيه أخضر. وهو عطل الحارس الأكثر تكراراً في هذا المستودع: أخضر لأنّه
    **لم ينظر** لا لأنّه **لم يجد**.
    """
    claims = _landing_claims()
    assert claims, "لا ادّعاء هبوط في السجلّ — إمّا تغيّرت الصياغة فعمي الحارس، أو حُذِفت الادّعاءات"


def test_every_landing_claim_names_a_commit_that_exists_and_precedes_head():
    """الادّعاء يصير قابلاً للتكذيب: التزام موجود، وسلفٌ لـHEAD."""
    # **الضحالة تُقاس من المستودع، لا تُستنتَج من فشل البحث.** أوّل صياغة تخطّت عند
    # أيّ `cat-file` فاشل «لأنّها قد تكون نسخة ضحلة» — وقياسها بطفرة مزروعة أظهر أنّ
    # SHA **مختلقاً** (`deadbeef`) يُنتج نفس الإشارة بالضبط، فيُتخطّى بدل أن يُدان.
    # أي أنّ الاختبار كان أعمى عن **الحالة الأساسيّة التي بُني لها**، وأخضرَ عنها.
    shallow = _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true"

    for gap_id, sha in _landing_claims():
        exists = _git("cat-file", "-e", f"{sha}^{{commit}}")
        if exists.returncode != 0:
            if shallow:
                pytest.skip(f"استنساخ ضحل — تاريخ {sha} غير محمَّل")
            raise AssertionError(
                f"{gap_id} يدّعي الهبوط في {sha}، ولا التزام بهذا المعرّف في مستودع كامل "
                "— معرّف مختلق أو مطبعة"
            )

        ancestor = _git("merge-base", "--is-ancestor", sha, "HEAD")
        assert ancestor.returncode == 0, (
            f"{gap_id} يدّعي الهبوط في {sha}، وهو ليس سلفاً لـHEAD — "
            "أي أنّ الحالة كُتِبت قبل الهبوط أو على فرع آخر"
        )


def test_the_transient_candidate_status_is_not_left_on_a_landed_gap():
    """**الحدّ المقابل، والحادثة نفسها.**

    «مرشّح الدمج» حالة مشروعة **ما دام المرشّح مفتوحاً**. ما لا يُقاس هنا هو حالة الـPR،
    فلا يُمنَع اللفظ. المقيس أنّ فجوة **تحمل الحالتين معاً** — تدّعي هبوطاً وتقول
    مرشّحاً — متناقضة على وجهها، وهي شكل ما بقي في السجلّ فعلاً قبل هذا الإصلاح.
    """
    text = _REGISTRY.read_text(encoding="utf-8")
    contradictory = [
        line
        for line in text.splitlines()
        if line.startswith("## ") and "هبطت في" in line and "مرشّح الدمج" in line
    ]
    assert not contradictory, "عنوان يدّعي الهبوط والترشيح معاً: " + " · ".join(contradictory)
