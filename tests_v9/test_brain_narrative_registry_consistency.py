"""فجوةٌ يرويها السجلّ ولا يعرفها الجرد = مدخلةٌ ضاعت.

``BRAIN-ENTRIES-REAUTHORED-NOT-CARRIED-ACROSS-REBASES-01``. مقيس على ``d3e09a60``:
**اثنتا عشرة فجوة من أربع عشرة** كُتِبت في جلسة واحدة لم تصل ``main``. الشريحة أُعيد
تأسيسها خمس مرّات، وفي كلّ مرّة حُمِلت المصادر برقعة بينما **كُتِبت مداخل الدماغ من
جديد** بدل حملها من الرأس السابق — فحملت كلّ جولةٍ مداخلَها وحدها.

**ولم يُطلِق ``brain_append_only_guard``، وليس ذلك عيباً فيه.** هو يقيس أن **لا يصغر**
الملفّ، وقاعدته مُصرَّح بها: «القاعدة ليست بادئة‑بايت» لأنّ ``registry.md`` يحمل تعديلات
حالة مشروعة. وفي كلّ جولة كان الملفّ = دماغ ``main`` + المداخل الجديدة، أي **أكبر
دائماً**. المفقود لم يكن حجماً بل **مداخل بعينها** — وذلك خارج ما يقيسه.

**والثابت الذي يمسك الحادثة هو مقارنة الجرد بـ``merge-base origin/main HEAD``** — أي
**نقطة اشتقاق الفرع**، لا رأس ``main``: معرِّفٌ كان في الجرد عند تلك النقطة وغاب عن
الفرع يعني مدخلةً سقطت في إعادة البناء. (المقارنة برأس ``main`` كانت تُحمِّر كلّ فرعٍ
متأخّر — إيجابيّة كاذبة تُبطِل الحارس؛ ولذلك يحتاج هذا الفحص **تاريخ git كاملاً**.) — ويُمسَك حتّى حين **يكبر**
الملفّ، وهو ما يعجز عنه قياسُ الحجم.

**وحدُّ صدقٍ يُقال هنا لا يُكتشَف لاحقاً:** فحصُ الرواية أدناه (معرِّفٌ يرويه السجلّ ولا
يعرفه الجرد) **ما كان ليمسك حادثة 2026-08-11 نفسها**، لأنّ مداخل تلك الجلسة تروي
الفجوات **نثراً بلا معرِّفات**. قِيس ذلك مباشرةً: زُرِع حذفُ
``CRLF-PHANTOM-ARTIFACT-DRIFT-01`` من الجرد فبقي الفحص **أخضر**. فهو يُضيف تغطيةً
لصنفٍ آخر — فقدٌ يُترك أثرُه في السجلّ — ولا يُدَّعى له أكثر.

**والاتّجاه واحد قصداً.** فجوةٌ في الجرد بلا ذكرٍ في السجلّ **ليست** عطلاً: الجرد يحمل
مداخل جلسات سابقة لا يرويها سجلّ اليوم. عكسُ الشرط كان سيُحمِّر مئات المداخل المشروعة —
**وإنذارٌ يُدرَّب قارئُه على تجاوزه ليس حارساً**.

يفشل مغلقاً: ملفّ دماغٍ لا يُقرأ يُبلَّغ فشلاً، لا يُتخطّى.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
BRAIN = ROOT / "sahool-brain"
REGISTRY = BRAIN / "gaps" / "registry.md"
NARRATIVES = (BRAIN / "log.md", BRAIN / "hot.md", BRAIN / "decisions" / "ledger.md")

# معرِّف فجوة: أحرف كبيرة وشرطات، ينتهي برقم تسلسليّ من رقمين — الصيغة السائدة في
# هذا المستودع (`WORKER-TENANT-GUC-SET-OUTSIDE-ANY-TRANSACTION-01`). الشرط على الطول
# يمنع التقاط اختصارات عابرة مثل `CI-01`.
# ``(?<![A-Z0-9-])`` مقصودة: الشرطة حدُّ كلمة في ``re``، فـ``\b`` وحدها تلتقط
# **قُصاصة** من معرِّف أطول — قِيس على الشجرة أنّ
# ``API-VERSIONING-GUARD-IS-A-MIRROR-01`` المُسجَّلة كانت تُبلَّغ ناقصةً بوصفها
# ``VERSIONING-GUARD-IS-A-MIRROR-01`` مفقودة. إيجابيّة كاذبة كهذه تُبطِل الحارس.
# ``(?![A-Z0-9-])`` نظيرتُها على الطرف الآخر، وأُضيفت بالقياس لا بالحدس: الحدُّ
# ``\b`` وحدَه يقطع بعد ``-\d{2}`` ولو تلاه ``-001``، فيلتقط **رأسَ** معرِّفٍ أطول
# كما كان ``\b`` وحدَه يلتقط ذيلَه. مقيسٌ على الشجرة: ``GATE01-ADJ-2026-09-02-001``
# — وهو **معرِّفُ تحكيمٍ لا معرِّفُ فجوة** — كان يُبلَّغ مفقوداً بوصفه
# ``GATE01-ADJ-2026-09-02``. وسابقاه (``2026-08-13`` و``2026-08-28``) نجَوا
# **بالمصادفة** لا بالتصميم: صودف ذكرُهما في ``gaps/registry.md`` فبدا الاقتطاعُ
# سليماً — أي أنّ الحارسَ كان يُصنِّف صنفاً كاملاً خطأً ولا يُحمِّر إلّا حين
# تنقطع المصادفة.
#
# **وهذا تضييقٌ لا توسيع.** التعليقُ أعلاه يرفض «توسيعَ النمط ليتجاهلها» بحقّ —
# التوسيعُ يُخفي فجواتٍ حقيقيّة. وهذه تشترط أن ينتهي المعرِّفُ حيث ينتهي فعلاً،
# فلا تُخفي معرِّفاً قائماً بل تكفّ عن **اختلاق** واحدٍ غيرِ موجود. مقيسٌ على كلّ
# سجلّات الدماغ: ٢٩٧ ⇒ ٢٩٤، والثلاثةُ الساقطة هي معرِّفاتُ التحكيم الثلاثة
# وحدَها — صفرُ معرِّفِ فجوةٍ فُقِد، وصفرُ مدخلٍ أُضيف.
_GAP_ID = re.compile(r"(?<![A-Z0-9-])([A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}-\d{2})(?![A-Z0-9-])")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # فشلٌ مغلق لا تخطٍّ صامت
        pytest.fail(
            f"تعذّرت قراءة {path.relative_to(ROOT)} — {exc}\n"
            "وغيابُ الملفّ نفسه عطلٌ لا عذر: كلّ ملفّ في `NARRATIVES` **يجب** أن يُقرأ "
            "كي يُقاس. تخطّيه عند الغياب كان يجعل **حذف** ملفّ سجلٍّ يُمرّر الفحص أخضر "
            "بلا قياس — أي أنّ أرخص طريقة لإسكات هذا الحارس تصير حذفَ ما يقيسه."
        )


def _ids(text: str) -> set[str]:
    return set(_GAP_ID.findall(text))


# أساسٌ مُعلَن **يتقلّص ولا ينمو**. هذه الستّة تُروى في مداخل يوليو بوصفها وسومَ PR
# وأسماءَ شرائح مُغلَقة، لا مداخل جرد ضائعة — وقِيست على `d3e09a60` واحدةً واحدة.
# إعلانُها دَيناً أصدقُ من توسيع النمط ليتجاهلها: التوسيع يُخفي الصنف كلّه، والإعلان
# يُبقيه مرئيّاً ويمنع نموّه. حذفُ أيّ منها مسموح دائماً؛ إضافةُ جديد محجوبة.
_NARRATED_WITHOUT_ENTRY_BASELINE = frozenset(
    {
        "CANONICAL-WEATHER-ENVELOPE-NOT-EXPOSED-01",
        "CI-RLS-SUPERUSER-ROLE-01",
        "ERP-BRIDGE-FIX-01",
        "GAP-FIELD-FORMS-01",
        "HISTORICAL-SEASON-COMPOSITION-02",
        "PHYSICS-AI-CALIBRATION-01",
    }
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        # `encoding` صريح: `text=True` وحدها تفكّ بترميز الآلة، وخطوة ١٠ تُشغَّل تحت
        # `LC_ALL=C` — فالجرد عربيّ ويُفكّ خطأً. الحارس `test_text_encoding_locale`
        # يمسك هذا، ورسالته تقول: أصلِح القراءة لا تُضِف المدخل إلى الأساس.
        encoding="utf-8",
    )


def _diagnosis(proc: subprocess.CompletedProcess[str]) -> str:
    """مخرجات git حرفيّاً — **السبب المقيس**، تُطبَع بجانب العلاج المُرجَّح.

    رسالةٌ تجزم بسببٍ واحد («استنساخ ضحل») تُضلِّل حين يكون السبب غيره: مرجعٌ
    ``origin/main`` غير موجود، أو صلاحيّات، أو عطل git. والعلاج المُرجَّح يبقى مذكوراً
    لأنّه الأشيع؛ لكنّ **ما قِيس** يسبقه فلا يُقرأ الترجيح تشخيصاً.
    """
    return (
        f"\n\n— ما قالته git (rc={proc.returncode}) —\n"
        f"stdout: {proc.stdout.strip() or '(فارغ)'}\n"
        f"stderr: {proc.stderr.strip() or '(فارغ)'}"
    )


def _registry_ids_at(ref: str) -> tuple[set[str] | None, subprocess.CompletedProcess[str]]:
    """معرِّفات الجرد عند مرجعٍ git، و**العمليّة نفسها** كي لا يُفقَد تشخيص git.

    إعادةُ ``None`` وحدها كانت تبتلع ``stderr``، فيُضطرّ المُستدعي إلى **تخمين** السبب.
    """
    proc = _git("show", f"{ref}:sahool-brain/gaps/registry.md")
    return (_ids(proc.stdout) if proc.returncode == 0 else None), proc


def test_no_registry_entry_that_main_has_disappears_from_this_branch():
    """الثابت الذي يمسك الحادثة: مدخلةٌ في جرد ``main`` لا تختفي من الفرع.

    يُمسَك حتّى حين **يكبر** الملفّ — وهو ما لا يقيسه ``brain_append_only_guard``.
    """
    # القاعدة هي **نقطة الاشتقاق** لا رأس main: فرعٌ متأخّر لا «يفقد» مدخلةً أُضيفت
    # إلى main بعد أن تفرّع — والمقارنة برأس main كانت تُحمِّر كلّ فرعٍ صادق متأخّر،
    # وهي الإيجابيّة الكاذبة التي تُبطِل الحارس. قِيس ذلك: بلغ main `a2cefaac` أثناء
    # العمل فبدا الفرع فاقداً ثلاث مداخل لم تكن في قاعدته أصلاً.
    merge_base = _git("merge-base", "origin/main", "HEAD")
    # **فشلٌ مغلق لا تخطٍّ.** الاستنساخ الضحل (‏`actions/checkout` بلا `fetch-depth: 0`)
    # يجعل `merge-base` غير قابل للحلّ، و`pytest.skip` هنا كان يُنتِج **أخضر بلا قياس** —
    # وهو الصنف نفسه الذي كُتِب هذا الحارس ليمنعه. الرسالة تسمّي العلاج بدل أن تصف عطلاً.
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        pytest.fail(
            "تعذّر حلّ `merge-base origin/main HEAD`. الفحص يحتاج **تاريخ git كاملاً** "
            "ومرجعَ `origin/main`؛ والعلاج الأشيع `fetch-depth: 0` في `actions/checkout` "
            "بالوظيفة المُشغِّلة. **راجع مخرجات git أدناه قبل تطبيقه** — قد يكون السبب "
            "مرجعاً غير موجود أو عطلاً آخر، لا عمقاً. وتخطّي الفحص هنا كان سيُنتِج أخضر "
            "لم يقس شيئاً." + _diagnosis(merge_base)
        )
    base, show = _registry_ids_at(merge_base.stdout.strip())
    if base is None:
        pytest.fail(
            "حُلَّت قاعدة الاشتقاق لكن تعذّرت قراءة `gaps/registry.md` عندها. الأشيع كائنٌ "
            "غير مجلوب (‏`fetch-depth: 0`)، **لكنّ مخرجات git أدناه هي الفيصل** — قد يكون "
            "المسار غير موجود عند تلك القاعدة، أو عطلاً في git." + _diagnosis(show)
        )
    here = _ids(_read(REGISTRY))
    vanished = sorted(base - here)
    assert not vanished, (
        "معرِّفات موجودة في الجرد عند قاعدة الاشتقاق وغائبة عن هذا الفرع — مدخلات سقطت في "
        "إعادة البناء. عند إعادة تأسيس فرع تُحمل `sahool-brain/` **بالرقعة من الرأس "
        "السابق** كما تُحمل المصادر، لا تُكتب من جديد.\n"
        "المفقود:\n  " + "\n  ".join(vanished)
    )


def test_every_gap_id_the_journal_narrates_exists_in_the_registry():
    """رواية بلا مدخلة تعني أنّ المدخلة ضاعت — وهي الحادثة التي أوجبت هذا الحارس."""
    registry_ids = _ids(_read(REGISTRY))
    assert registry_ids, "جرد الفجوات لا يحمل معرِّفاً واحداً — الحارس لا يقيس شيئاً"

    missing: list[str] = []
    for path in NARRATIVES:
        # لا حارس وجود هنا قصداً: `_read` يفشل مغلقاً على الملفّ المفقود.
        orphans = _ids(_read(path)) - registry_ids - _NARRATED_WITHOUT_ENTRY_BASELINE
        for gap_id in sorted(orphans):
            missing.append(f"{path.relative_to(ROOT)}: {gap_id}")

    assert not missing, (
        "معرِّف فجوة يرويه السجلّ ولا يعرفه `gaps/registry.md`. عند إعادة تأسيس فرع، "
        "تُحمل `sahool-brain/` **بالرقعة من الرأس السابق** كما تُحمل المصادر — لا تُكتب "
        "من جديد، وإلّا سقطت مداخل الجولات السابقة بلا إنذار (`brain_append_only_guard` "
        "يقيس الحجم لا المداخل، والملفّ يكبر في كلّ جولة).\n"
        "المفقود:\n  " + "\n  ".join(missing)
    )


def test_the_detector_catches_a_narrated_gap_that_the_registry_lost():
    """تكذيبٌ للكاشف: يُمسِك الرواية اليتيمة، ولا يُمسِك الاتّجاه المعاكس المشروع."""
    narrated = _ids("سقطت `SOME-INVENTED-GAP-IDENTIFIER-01` من الجرد")
    assert "SOME-INVENTED-GAP-IDENTIFIER-01" in narrated, "الكاشف لا يرى معرِّفاً مرويّاً"
    assert not (narrated - {"SOME-INVENTED-GAP-IDENTIFIER-01"}), "الكاشف التقط ضجيجاً"

    # الاتّجاه المعاكس مشروع: مدخلة في الجرد لا يرويها سجلّ اليوم ليست عطلاً.
    registry_only = _ids("## `OLD-SESSION-GAP-FROM-LAST-MONTH-01` — `fixed`")
    assert registry_only - _ids("سجلّ اليوم لا يذكرها"), (
        "الاختبار الأساسيّ يجب أن يفحص اتّجاهاً واحداً فقط — والعكس يُحمِّر المشروع"
    )


def test_the_baseline_only_shrinks_and_names_nothing_the_registry_already_has():
    """أساسٌ يحمل ما صار مُسجَّلاً يُجمِّد ديناً مسدَّداً — فالراتشِت يُنظَّف لا يُترَك."""
    registry_ids = _ids(_read(REGISTRY))
    settled = sorted(_NARRATED_WITHOUT_ENTRY_BASELINE & registry_ids)
    assert not settled, "مدخلات صارت في الجرد وما تزال في الأساس — تُحذف منه: " + ", ".join(settled)

    narrated: set[str] = set()
    for path in NARRATIVES:
        narrated |= _ids(_read(path))  # بلا حارس وجود: الغياب فشلٌ لا تخطٍّ
    stale = sorted(_NARRATED_WITHOUT_ENTRY_BASELINE - narrated)
    assert not stale, (
        "أساسٌ يحمل معرِّفاً لم يعد السجلّ يرويه — إعفاءٌ بائت يُبقي الحارس أضعف ممّا "
        "يُقاس: " + ", ".join(stale)
    )


def test_the_pattern_does_not_match_ordinary_prose_or_short_tokens():
    """إيجابيّة كاذبة تقتل الحارس أسرع من السلبيّة، فالنمط يُقاس لا يُفترَض."""
    benign = (
        "شُغِّل على PG16 وPostGIS 3.4.3 ثمّ دُمِج في d3e09a60.\n"
        "راجع CI-GATES أو المعيار ISO-8601 أو الرمز HTTP-404.\n"
        "`LC_ALL=C` و`PYTHONUTF8=0` ليسا معرِّفَي فجوة.\n"
    )
    assert not _ids(benign), f"النمط التقط نصّاً عاديّاً: {sorted(_ids(benign))}"


def test_a_longer_identifier_is_not_truncated_from_either_end():
    """المعرِّفُ يُقرأ كاملاً أو لا يُقرأ — والاقتطاعُ من الطرفين مُكذَّبٌ هنا.

    الحدُّ ``\\b`` وحدَه يقطع عند الشرطة، فيلتقط **قُصاصةً** من معرِّفٍ أطول:
    ذيلاً من جهةٍ ورأساً من الأخرى. وكلتاهما **إيجابيّةٌ كاذبة تُبطِل الحارس** —
    تُبلَّغ فجوةٌ «مفقودة» لا وجودَ لها أصلاً، فيتعلّم قارئُها تجاوزَه.
    """
    # ذيلٌ مقتطَع — الحالةُ التي أُغلِقت بـ``(?<![A-Z0-9-])``.
    assert _ids("API-VERSIONING-GUARD-IS-A-MIRROR-01") == {"API-VERSIONING-GUARD-IS-A-MIRROR-01"}, (
        "التُقِط ذيلُ معرِّفٍ أطول"
    )

    # رأسٌ مقتطَع — الحالةُ التي أُغلِقت بـ``(?![A-Z0-9-])``. ومعرِّفُ التحكيم
    # ليس معرِّفَ فجوةٍ أصلاً، فالصوابُ ألّا يُلتقَط منه شيء.
    assert not _ids("GATE01-ADJ-2026-09-02-001"), "التُقِط رأسُ معرِّفِ تحكيمٍ بوصفه معرِّفَ فجوة"

    # والشاهدُ السويّ: التضييقُ لم يُعطِّل الالتقاط الصحيح.
    real = "WORKER-TENANT-GUC-SET-OUTSIDE-ANY-TRANSACTION-01"
    assert _ids(f"راجع `{real}` في السجلّ.") == {real}, "ضاع معرِّفٌ صحيحٌ بالتضييق"
