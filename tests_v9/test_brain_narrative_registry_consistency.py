"""فجوةٌ يرويها السجلّ ولا يعرفها الجرد = مدخلةٌ ضاعت.

``BRAIN-ENTRIES-REAUTHORED-NOT-CARRIED-ACROSS-REBASES-01``. مقيس على ``d3e09a60``:
**اثنتا عشرة فجوة من أربع عشرة** كُتِبت في جلسة واحدة لم تصل ``main``. الشريحة أُعيد
تأسيسها خمس مرّات، وفي كلّ مرّة حُمِلت المصادر برقعة بينما **كُتِبت مداخل الدماغ من
جديد** بدل حملها من الرأس السابق — فحملت كلّ جولةٍ مداخلَها وحدها.

**ولم يُطلِق ``brain_append_only_guard``، وليس ذلك عيباً فيه.** هو يقيس أن **لا يصغر**
الملفّ، وقاعدته مُصرَّح بها: «القاعدة ليست بادئة‑بايت» لأنّ ``registry.md`` يحمل تعديلات
حالة مشروعة. وفي كلّ جولة كان الملفّ = دماغ ``main`` + المداخل الجديدة، أي **أكبر
دائماً**. المفقود لم يكن حجماً بل **مداخل بعينها** — وذلك خارج ما يقيسه.

**والثابت الذي يمسك الحادثة هو مقارنة الجرد بـ``origin/main``:** معرِّفٌ موجود في جرد
``main`` وغائب عن الفرع يعني مدخلةً سقطت في إعادة البناء — ويُمسَك حتّى حين **يكبر**
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
_GAP_ID = re.compile(r"(?<![A-Z0-9-])([A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}-\d{2})\b")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # فشلٌ مغلق لا تخطٍّ صامت
        pytest.fail(f"تعذّرت قراءة {path.relative_to(ROOT)} — {exc}")


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


def _registry_ids_at(ref: str) -> set[str] | None:
    """معرِّفات الجرد عند مرجعٍ git، أو ``None`` إن تعذّر حلّه (استنساخ ضحل)."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{ref}:sahool-brain/gaps/registry.md"],
        capture_output=True,
        text=True,
        # `encoding` صريح: `text=True` وحدها تفكّ بترميز الآلة، وخطوة ١٠ تُشغَّل تحت
        # `LC_ALL=C` — فالجرد عربيّ ويُفكّ خطأً. الحارس `test_text_encoding_locale`
        # يمسك هذا، ورسالته تقول: أصلِح القراءة لا تُضِف المدخل إلى الأساس.
        encoding="utf-8",
    )
    return _ids(proc.stdout) if proc.returncode == 0 else None


def test_no_registry_entry_that_main_has_disappears_from_this_branch():
    """الثابت الذي يمسك الحادثة: مدخلةٌ في جرد ``main`` لا تختفي من الفرع.

    يُمسَك حتّى حين **يكبر** الملفّ — وهو ما لا يقيسه ``brain_append_only_guard``.
    """
    # القاعدة هي **نقطة الاشتقاق** لا رأس main: فرعٌ متأخّر لا «يفقد» مدخلةً أُضيفت
    # إلى main بعد أن تفرّع — والمقارنة برأس main كانت تُحمِّر كلّ فرعٍ صادق متأخّر،
    # وهي الإيجابيّة الكاذبة التي تُبطِل الحارس. قِيس ذلك: بلغ main `a2cefaac` أثناء
    # العمل فبدا الفرع فاقداً ثلاث مداخل لم تكن في قاعدته أصلاً.
    merge_base = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "origin/main", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if merge_base.returncode != 0:
        pytest.skip("تعذّر حلّ قاعدة الاشتقاق (استنساخ ضحل) — الفحص يحتاجها")
    base = _registry_ids_at(merge_base.stdout.strip())
    if base is None:
        pytest.skip("تعذّر قراءة الجرد عند قاعدة الاشتقاق")
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
        if not path.is_file():
            continue
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
        if path.is_file():
            narrated |= _ids(_read(path))
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
