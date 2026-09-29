"""اسمُ الفحص المعروض يجب أن يُميِّز وظيفةً واحدة — ``CI-CHECK-DISPLAY-NAME-COLLISION-01``.

**ما قِيس (2026-09-22، على ``58fdcf4``):** تسعُ workflows مستقلّة كانت تُعرِّف
``jobs.guard`` بلا اسمِ عرضٍ مميّز، واثنتان تُعرِّفان ``jobs.contract`` كذلك. فأربعةُ
فحوصٍ ناجحةٍ على PR #1073 وصلت واجهةَ Actions باسمٍ واحدٍ هو ``guard``، من التطبيق
نفسِه، من أربعة تشغيلاتٍ مختلفة. ومستهلِكٌ يُطابِق الفحوصَ بـ(الاسم + التطبيق) لا
يستطيع فصلَها — وهذا ما رصدَته أداةُ المالك فأصدرت ``AMBIGUOUS_CHECKS_IDENTITY:guard``.

**وحدُّ الادّعاء مُعلَنٌ هنا صراحةً:** التكرارُ **مقيس**؛ أمّا أن يُجيز نجاحُ وظيفةٍ
واحدةٍ غيابَ بقيّة الوظائف في إنفاذ حماية الفرع فـ**لم يُثبَت**، ولا يُسجَّل تجاوزَ
حمايةٍ مؤكَّداً. توثيقُ GitHub يحذّر من الالتباس ويربطه بتعطّل الدمج، لكنّ إثباتَ
سلوكِ الإنفاذ يحتاج تجربةً خارج المستودع التشغيليّ. ولم يكن أيٌّ من الاسمين ضمن
السياقات العشرين المطلوبة في القاعدة ``20645828`` وقتَ القياس.

**ما يمنعه هذا الاختبار وما يُجيزه — والفرقُ مقصود:**

* يُجيز تكرارَ **مفتاح** الوظيفة (``jobs.guard``) بين ملفّات مختلفة: المفتاحُ محلّيٌّ
  لملفّه، ولا تراه واجهةُ Actions. ولا يُمنَع استعمالُ كلمة ``guard`` في YAML.
* يمنع تصادمَ **الاسم المعروض** — وهو وحدَه هويّةُ الفحص عند المستهلِك.

الأسماءُ تُشتقّ بـ``guard_catalogue._job_display_names`` لا بإعادة اشتقاقٍ هنا،
لأنّها تُوسِّع أرجلَ المصفوفة (``matrix``): وظيفةُ YAML واحدةٌ تصل الواجهةَ بعدّة
أسماء، ومَن أعاد الاشتقاقَ مبسَّطاً أثبت غيرَ ما يقيس.
"""

from __future__ import annotations

import collections
import importlib.util
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
CATALOGUE = ROOT / "scripts/ci/guard_catalogue.py"


def _display_names(job_key: str, job: dict) -> list[str]:
    """أسماءُ العرض كما يشتقّها الكتالوجُ نفسُه — مصدرٌ واحدٌ للحقيقة لا نسخةٌ ثانية."""
    spec = importlib.util.spec_from_file_location("guard_catalogue_for_identity", CATALOGUE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._job_display_names(job_key, job)


def _expected_leg_count(job: dict) -> int:
    """كم اسماً **يجب** أن تُنتِج هذه الوظيفة — من بيانات المصفوفة، لا من الناتج.

    وظيفةٌ بلا تعبيرٍ في اسمها تُنتِج اسماً واحداً. وذاتُ التعبير تُنتِج اسماً لكلّ
    ساقٍ في ``strategy.matrix.include``. ويُقرَأ العددُ من **المُدخَل** عمداً، لأنّ
    قراءتَه من المخرَج تجعل السؤالَ يُجيب نفسَه.
    """
    declared = job.get("name")
    if not isinstance(declared, str) or "${{" not in declared:
        return 1
    include = ((job.get("strategy") or {}).get("matrix") or {}).get("include")
    return sum(1 for leg in include if isinstance(leg, dict)) if isinstance(include, list) else 0


def _survey(documents: dict[str, dict]) -> dict[str, object]:
    """جردٌ يفصل: ما اشتُقّ · ما تصادم · ما تعذّر كلّيّاً · **وما تعذّر جزئيّاً**.

    الأخيران ليسا تفصيلاً تجميليّاً، والرابعُ هو الأخبث.

    ``_job_display_names`` تُرجِع **فارغاً** حين يتعذّر حلُّ الاسم كلّيّاً — وتقول ذلك
    عن نفسها: «an unresolvable name is a measurement gap».

    **لكنّها لا تُرجِع فارغاً عند تعذّرٍ جزئيّ.** فهي تُبقي كلَّ ساقٍ رُسِمت وتُسقِط ما
    بقي فيه تعبير. فمصفوفةٌ بساقَين، إحداهما ينقصها المفتاحُ المُشار إليه، تُعيد اسماً
    واحداً — **قائمةٌ غيرُ فارغة**. ولو اكتفى الجردُ بسؤال «هل عادت فارغة؟» لعدَّها
    محلولةً وأخفى وظيفةَ واجهةٍ كاملةً، ولبقي ``derived >= jobs`` صادقاً رغم الضياع.
    (رصدَها مراجعُ #1092، وقِيست: ساقان مُعلَنتان ⇐ ``['probe a']``.)

    فيُقارَن عددُ الأسماء العائدة بعددِ السيقان المُعلَنة في المُدخَل.
    """
    claims: dict[str, list[str]] = collections.defaultdict(list)
    unresolved: list[str] = []
    partial: list[str] = []
    jobs_seen = 0
    for source, document in documents.items():
        for job_key, job in ((document or {}).get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            jobs_seen += 1
            names = _display_names(job_key, job)
            expected = _expected_leg_count(job)
            if not names:
                unresolved.append(f"{source}:jobs.{job_key}  name={job.get('name')!r}")
                continue
            if len(names) < expected:
                partial.append(
                    f"{source}:jobs.{job_key}  name={job.get('name')!r}  "
                    f"legs={expected} derived={len(names)} got={names}"
                )
            for name in names:
                claims[name].append(f"{source}:jobs.{job_key}")
    return {
        "jobs": jobs_seen,
        "derived": sum(len(v) for v in claims.values()),
        "unresolved": sorted(unresolved),
        "partially_resolved": sorted(partial),
        "collisions": {n: sorted(w) for n, w in claims.items() if len(w) > 1},
    }


def _collisions(documents: dict[str, dict]) -> dict[str, list[str]]:
    """اختصارٌ للتصادمات وحدَها — للحالات المُصطنَعة التي لا تحمل فجوةَ اشتقاق."""
    return _survey(documents)["collisions"]  # type: ignore[return-value]


def _tree() -> dict[str, dict]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted(WORKFLOWS.glob("*.y*ml"))
    }


def test_no_two_ci_jobs_report_under_the_same_display_name() -> None:
    """الشجرةُ اليوم: لا اسمَ عرضٍ تدّعيه وظيفتان — لا بين الملفّات ولا داخل الملفّ."""
    found = _collisions(_tree())
    assert found == {}, (
        f"اسمُ فحصٍ تدّعيه أكثرُ من وظيفة، فهويّةُ الفحص ملتبسةٌ عند أيّ مستهلِكٍ يُطابِق بالاسم: {found}"
    )


def test_every_job_in_the_tree_actually_entered_the_measurement() -> None:
    """صفرُ تصادمٍ لا يساوي اكتمالَ الاشتقاق — فيُقاس الفرقُ بدل أن يُفترَض.

    لو تعذّر اشتقاقُ اسمِ وظيفةٍ لَسقطت من المقارنة، وبقي الاختبارُ أعلاه أخضرَ وهو
    لم يرَها. المقيسُ حاليّاً صفرٌ غيرُ قابلٍ للاشتقاق؛ وإن صار غيرَ صفر، هذا الاختبارُ
    يُسمّي الوظائفَ بدل أن يبتلعها — فيُختار عندئذٍ إمّا إصلاحُ التعبير في المصدر أو
    توسيعُ المحلّل، لا إخفاءُ العدّ.
    """
    survey = _survey(_tree())
    assert survey["unresolved"] == [], (
        "وظائفُ لم يُشتقّ اسمُها فلم تدخل قياسَ التصادم — «لم أنظر» ليس «لا يوجد»: "
        f"{survey['unresolved']}"
    )
    assert survey["partially_resolved"] == [], (
        "وظائفُ رُسِم بعضُ سيقانها وضاع بعضُها، فوظيفةُ واجهةٍ كاملةٌ خارج القياس "
        f"بلا أن تعود القائمةُ فارغة: {survey['partially_resolved']}"
    )
    assert survey["derived"] >= survey["jobs"], (
        f"أسماءٌ مُشتقّة ({survey['derived']}) دون عددِ الوظائف ({survey['jobs']}) — "
        "اشتقاقٌ ناقصٌ بلا إبلاغ"
    )


@pytest.mark.parametrize(
    ("job", "expect_key", "why"),
    [
        pytest.param(
            {
                "name": "probe ${{ matrix.leg }}",
                "strategy": {"matrix": {"include": [{"leg": "a"}, {"other": "b"}]}},
            },
            "partially_resolved",
            "ساقان مُعلَنتان واسمٌ واحدٌ عائد — القائمةُ غيرُ فارغة فلا يكفي سؤالُ الفراغ",
            id="تعذّرٌ جزئيّ: ساقٌ تُحَلّ وأخرى ينقصها المفتاح",
        ),
        pytest.param(
            {"name": "probe ${{ matrix.leg }}"},
            "unresolved",
            "تعبيرٌ بلا include إطلاقاً ⇒ فارغة",
            id="تعذّرٌ كلّيّ: تعبيرٌ بلا مصفوفة",
        ),
    ],
)
def test_the_survey_separates_total_from_partial_derivation_failure(
    job: dict, expect_key: str, why: str
) -> None:
    """تكذيبُ الصنفين معاً — والجزئيُّ هو ما كان يفلت.

    قبل هذا كان الجردُ يسأل «هل عادت القائمةُ فارغة؟» وحدَه، فيمرّ التعذّرُ الجزئيُّ
    صامتاً. الشاهدُ الأوّل يُحمِّر تلك الحالةَ بعينها.
    """
    survey = _survey({"probe.yml": {"jobs": {"probe": job}}})
    assert survey[expect_key], why
    other = "unresolved" if expect_key == "partially_resolved" else "partially_resolved"
    assert not survey[other], f"صُنِّفت في الخانة الخطأ: {survey}"


def test_repeating_a_job_key_across_files_is_allowed_when_the_names_differ() -> None:
    """المفتاحُ المكرَّرُ ليس هو العطل — وهذا يمنع الاختبارَ من الحجب على الصواب."""
    assert (
        _collisions(
            {
                "a.yml": {"jobs": {"guard": {"name": "a / guard", "runs-on": "ubuntu-latest"}}},
                "b.yml": {"jobs": {"guard": {"name": "b / guard", "runs-on": "ubuntu-latest"}}},
            }
        )
        == {}
    )


@pytest.mark.parametrize(
    ("documents", "expected_name"),
    [
        pytest.param(
            {
                "a.yml": {"jobs": {"guard": {"runs-on": "ubuntu-latest"}}},
                "b.yml": {"jobs": {"guard": {"runs-on": "ubuntu-latest"}}},
            },
            "guard",
            id="مفتاحان بلا اسمٍ في ملفّين — الشكلُ الذي قِيس فعلاً",
        ),
        pytest.param(
            {
                "a.yml": {"jobs": {"one": {"name": "shared", "runs-on": "ubuntu-latest"}}},
                "b.yml": {"jobs": {"two": {"name": "shared", "runs-on": "ubuntu-latest"}}},
            },
            "shared",
            id="اسمان صريحان متطابقان — التصادمُ بالاسم لا بالمفتاح",
        ),
        pytest.param(
            {
                "a.yml": {
                    "jobs": {
                        "x": {"name": "same", "runs-on": "ubuntu-latest"},
                        "y": {"name": "same", "runs-on": "ubuntu-latest"},
                    }
                }
            },
            "same",
            id="تصادمٌ داخل ملفٍّ واحد — الواجهةُ لا تفرّق بينهما أيضاً",
        ),
    ],
)
def test_the_detector_reddens_when_a_collision_is_reintroduced(
    documents: dict[str, dict], expected_name: str
) -> None:
    """تكذيبٌ مباشر: لو عاد التصادمُ لَما بقي هذا الاختبارُ أخضر.

    بلا هذه الحالات يكون الأخضرُ أعلاه شهادةً على نظافة الشجرة لا على أنّ الكاشفَ
    يقيس — وهما ليسا الشيءَ نفسَه.
    """
    assert expected_name in _collisions(documents)


# ── توافقُ المستهلِك — سلوكيّاً لا بقراءة `_match_job` ────────────────────────────
#
# `collect_guard_surface_evidence.judge_site` يختار التشغيلَ بـ`site["workflow"]` ثمّ
# يُطابِق `site["job_names"]` بأسماء وظائف الواجهة. والأسماءُ تُشتقّ من **المصدر** عبر
# `guard_catalogue`، فهي تتبع الاسمَ الجديد بلا تعديلِ المستهلِك — **بشرط** أن يكون
# تعريفُ الوظائف والتشغيلُ المرصود من النسخة المتوافقة نفسِها. وذاك الشرطُ هو ما
# يُثبِته هذان الشاهدان: قراءةُ `_match_job` وحدَها ليست اختبارَ توافق.
#
# **وتصحيحٌ بعد مراجعة #1092:** كانت الصيغةُ الأولى تحقن الاسمَ المتوقَّع في طرفَي
# التجربة معاً — في تجهيز المصدر وفي تشغيل الواجهة — فتبقى خضراءُ حتّى لو كفّ
# الـworkflow الحقيقيُّ أو `_job_display_names` عن إنتاج ذلك الاسم. أي أنّها تُعيد
# اختبارَ `judge_site` بمُدخَلٍ يدويّ لا تعبر حدَّ «المصدر ⇒ المستهلِك» الذي يدّعيه
# الـPR. فصار الاسمُ يُشتقّ من **الملفّ المُلتزَم** بالمحلّل المشترك.

_COLLECTOR = ROOT / "scripts/ci/collect_guard_surface_evidence.py"
_WITNESS_WORKFLOW = "auth-main-decomposition.yml"
_WITNESS_JOB_KEY = "guard"
_LEGACY_BARE_NAME = "guard"


def _collector():
    spec = importlib.util.spec_from_file_location("collect_guard_surface_for_identity", _COLLECTOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _name_from_the_checked_in_workflow() -> str:
    """الاسمُ كما يشتقّه المحلّلُ المشترك من الملفّ على القرص — لا نصٌّ يدويّ."""
    job = _tree()[_WITNESS_WORKFLOW]["jobs"][_WITNESS_JOB_KEY]
    names = _display_names(_WITNESS_JOB_KEY, job)
    assert len(names) == 1, f"وظيفةُ الشاهد يجب أن تُنتِج اسماً واحداً، فأنتجت {names}"
    return names[0]


def _site(job_names: list[str]) -> dict:
    return {
        "workflow": _WITNESS_WORKFLOW,
        "job": _WITNESS_JOB_KEY,
        "job_names": job_names,
        "step_name": "auth main decomposition guard",
        "continue_on_error": False,
    }


def _run(api_job_name: str) -> dict[str, dict]:
    return {
        _WITNESS_WORKFLOW: {
            "run_id": 1,
            "jobs": [
                {
                    "name": api_job_name,
                    "conclusion": "success",
                    "steps": [{"name": "auth main decomposition guard", "conclusion": "success"}],
                }
            ],
        }
    }


def test_the_consumer_follows_the_name_the_checked_in_workflow_actually_declares() -> None:
    """الاسمُ يُشتقّ من الملفّ المُلتزَم، ثمّ يُطابَق في تشغيلٍ يحمله."""
    derived = _name_from_the_checked_in_workflow()
    verdict = _collector().judge_site(_site([derived]), _run(derived))
    assert verdict["status"] == "ran", verdict


def test_the_consumer_misses_a_run_that_still_reports_under_the_bare_legacy_name() -> None:
    """وهذا هو الشاهدُ الذي يعبر حدَّ «المصدر ⇒ المستهلِك» فعلاً.

    الطرفُ المصدريُّ **مُشتقٌّ** من الـworkflow المُلتزَم، والطرفُ الآخر مثبَّتٌ على
    الاسم القديم المجرَّد ``guard``. فلو ارتدّ الـworkflow إلى الاسم المجرَّد — أو كفّ
    ``_job_display_names`` عن إنتاج الاسم المميّز — لتساوى الطرفان ولعاد الحكمُ
    ``ran`` بدل ``job_missing``، فيحمرّ هذا الاختبار.

    هذا ما كانت الصيغةُ الأولى تفتقده: كانت تحقن الاسمَ نفسَه في الطرفين، فتنجو من
    أيّ ارتدادٍ في المصدر.
    """
    derived = _name_from_the_checked_in_workflow()
    assert derived != _LEGACY_BARE_NAME, (
        "الشاهدُ يفترض أنّ المصدرَ يُعلِن اسماً مميّزاً؛ لو صار مجرَّداً فهذا هو الارتداد نفسُه"
    )
    verdict = _collector().judge_site(_site([derived]), _run(_LEGACY_BARE_NAME))
    assert verdict["status"] == "job_missing"
    assert verdict["detail"] == derived


def test_a_job_whose_name_cannot_be_derived_is_reported_not_assumed_to_have_run() -> None:
    """والمستهلِكُ نفسُه يُسمّي فجوةَ الاشتقاق `job_name_not_derivable` — لا يفترض النجاح."""
    verdict = _collector().judge_site(_site([]), _run("anything"))
    assert verdict["status"] == "job_name_not_derivable"
