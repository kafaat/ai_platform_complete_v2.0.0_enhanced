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


def _collisions(documents: dict[str, dict]) -> dict[str, list[str]]:
    """اسمُ عرضٍ ⇒ المواضعُ التي تدّعيه، لكلّ اسمٍ تدّعيه أكثرُ من وظيفة."""
    claims: dict[str, list[str]] = collections.defaultdict(list)
    for source, document in documents.items():
        for job_key, job in ((document or {}).get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for name in _display_names(job_key, job):
                claims[name].append(f"{source}:jobs.{job_key}")
    return {name: sorted(where) for name, where in claims.items() if len(where) > 1}


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
