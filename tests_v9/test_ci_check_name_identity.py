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


def _survey(documents: dict[str, dict]) -> dict[str, object]:
    """جردٌ يفصل ثلاثةَ أعداد: ما اشتُقّ · ما تصادم · **وما تعذّر اشتقاقُه**.

    الثالثُ ليس تفصيلاً تجميليّاً. ``_job_display_names`` تُرجِع قائمةً **فارغة** حين
    لا تستطيع حلَّ تعبيرِ الاسم — وتقول ذلك عن نفسها: «an unresolvable name is a
    measurement gap». فوظيفةٌ كهذه تسقط من المقارنة صامتةً، ويصير «صفرُ تصادم» حكماً
    على ما دخل القياسَ لا على الشجرة. إخفاءُ ذلك يُحوِّل فجوةَ قياسٍ إلى خضرةٍ كاذبة.
    """
    claims: dict[str, list[str]] = collections.defaultdict(list)
    unresolved: list[str] = []
    jobs_seen = 0
    for source, document in documents.items():
        for job_key, job in ((document or {}).get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            jobs_seen += 1
            names = _display_names(job_key, job)
            if not names:
                unresolved.append(f"{source}:jobs.{job_key}  name={job.get('name')!r}")
                continue
            for name in names:
                claims[name].append(f"{source}:jobs.{job_key}")
    return {
        "jobs": jobs_seen,
        "derived": sum(len(v) for v in claims.values()),
        "unresolved": sorted(unresolved),
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
    assert survey["derived"] >= survey["jobs"], (
        f"أسماءٌ مُشتقّة ({survey['derived']}) دون عددِ الوظائف ({survey['jobs']}) — "
        "اشتقاقٌ ناقصٌ بلا إبلاغ"
    )


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

_COLLECTOR = ROOT / "scripts/ci/collect_guard_surface_evidence.py"


def _collector():
    spec = importlib.util.spec_from_file_location("collect_guard_surface_for_identity", _COLLECTOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _site(job_names: list[str]) -> dict:
    return {
        "workflow": "auth-main-decomposition.yml",
        "job": "guard",
        "job_names": job_names,
        "step_name": "auth main decomposition guard",
        "continue_on_error": False,
    }


def _run(api_job_name: str) -> dict[str, dict]:
    return {
        "auth-main-decomposition.yml": {
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


def test_the_consumer_follows_the_new_name_when_source_and_run_agree() -> None:
    """الاسمُ الجديدُ المُشتقُّ من المصدر يُطابِق وظيفةً بالاسم الجديد في التشغيل الصحيح."""
    new_name = "auth-main-decomposition / guard"
    verdict = _collector().judge_site(_site([new_name]), _run(new_name))
    assert verdict["status"] == "ran", verdict


def test_the_consumer_reports_a_named_miss_when_source_and_run_disagree() -> None:
    """وحين يختلفان — مصدرٌ بالاسم الجديد وتشغيلٌ بالقديم — يُبلِّغ ولا يصمت.

    هذا هو الشرطُ المُعلَن: التوافقُ ليس تلقائيّاً بل مشروطٌ بتطابق النسختين. ولو
    ابتلع المستهلِكُ هذا الاختلافَ لَقرأنا «لم يعمل» على أنّه «عمل».
    """
    verdict = _collector().judge_site(_site(["auth-main-decomposition / guard"]), _run("guard"))
    assert verdict["status"] == "job_missing"
    assert verdict["detail"] == "auth-main-decomposition / guard"


def test_a_job_whose_name_cannot_be_derived_is_reported_not_assumed_to_have_run() -> None:
    """والمستهلِكُ نفسُه يُسمّي فجوةَ الاشتقاق `job_name_not_derivable` — لا يفترض النجاح."""
    verdict = _collector().judge_site(_site([]), _run("anything"))
    assert verdict["status"] == "job_name_not_derivable"
