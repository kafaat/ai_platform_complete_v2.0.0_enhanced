"""شريحة CI-PERF-01 — الثلاثة الآمنة بمواصفة المالك، وبوّابةُ قبولها مقافلُ هذا الملفّ.

كلٌّ منها يسدّ عطلاً قِيس هنا: جولاتُ PR بائتة تحجز عدّاءات بعد دفعةٍ فوقها ·
`Unit Tests` بلا سقفٍ فتعليقُها انتظارٌ صامت ٦ ساعات (الذروة المقيسة ٤٠–٤٢ دقيقة) ·
وكلّ وظيفةٍ تُنزّل التبعيّات من الصفر.

وتُقرأ الإعدادات **من المُحلِّل لا كنصّ** — الفحص النصّيّ يحمرّ على التعليقات
الشارحة (`TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`، وقعنا فيه مرّتين).
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _ci() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


def test_stale_pr_runs_are_cancelled_but_every_main_push_keeps_its_record() -> None:
    """الإلغاء على الـPR وحدها — وmain لا تُلغى **ولا تصطفّ**.

    صيغةُ `group` الأولى (`workflow-ref`) لم تكن تُلغي main لكنّها كانت
    **تُصفّفها**: مجموعةٌ واحدة لكلّ الدفعات، والإلغاء معطَّل ⇒ تشغيلٌ ينتظر
    تشغيلاً. وتشغيلات main موضوعُ الاعتماد اللاحق (`certify-run` على
    `workflow_run: completed`)، فلكلّ دفعةٍ سجلُّها الفوريّ: `run_id` في المجموعة
    يجعل كلَّ تشغيل main وحدةً مستقلّة، ورقمُ الـPR يجمع تحديثاتها فيُلغى الأقدم.
    """
    concurrency = _ci().get("concurrency")

    assert concurrency, "لا كتلة concurrency — عادت جولات الـPR البائتة تحجز العدّاءات"
    group = " ".join(str(concurrency["group"]).split())
    assert "format('ci-pr-{0}', github.event.pull_request.number)" in group, (
        "بلا رقم الـPR في المجموعة لا يُلغى تحديثُها الأقدم"
    )
    assert "github.run_id" in group, (
        "بلا run_id تتشارك دفعاتُ main مجموعةً واحدة فتصطفّ — أو تُلغى إن قُلِب الشرط"
    )
    assert " ".join(str(concurrency["cancel-in-progress"]).split()) == (
        "${{ github.event_name == 'pull_request' }}"
    ), "إلغاءٌ غير مشروطٍ بالـPR يبتلع سجلّات main التي يقرؤها الاعتماد"


def test_the_longest_job_has_the_decided_ceiling_not_a_six_hour_default() -> None:
    """السقف ٦٠ قرارُ مالكٍ فوق قياسٍ (الذروة ٤٠.٣) — وتغييرُه تعديلٌ واعٍ لا انجراف.

    يُخفَّض لاحقاً إلى ٥٠/٤٥ بقياس P95 عبر جولات، لا بتخمين.
    """
    timeout = _ci()["jobs"]["unit-tests"].get("timeout-minutes")

    assert timeout == 60, (
        f"السقف {timeout} ≠ 60 المقرَّر — إن كان خفضاً مقيساً بـP95 فحدِّث هذا القفل معه"
    )


def test_pip_caches_are_bound_to_each_jobs_actual_dependency_file() -> None:
    """لا نمطَ شاملاً كونيّاً، ولا كاشَ بلا ملفٍّ يُقاس عليه.

    الربط بملفّ الوظيفة **الفعليّ** (مقيسٌ من خطواتها): مفتاحُ `unit-tests` يتغيّر
    عند تغيّر `tests_v9/requirements-test.txt` — بوّابة قبول الشريحة نصّاً. ووظيفتان
    بلا ملفّ متطلّبات (`lint` · `platform-structure-inspector`) بلا كاش أصلاً:
    مفتاحٌ بلا ملفّ يفشل الالتقاط، وليس «كاش أكثر = أفضل».
    """
    jobs = _ci()["jobs"]
    cached, uncached = {}, []
    for job_name, job in jobs.items():
        for step in job.get("steps", []):
            if "actions/setup-python" not in str(step.get("uses", "")):
                continue
            with_ = step.get("with") or {}
            if with_.get("cache") == "pip":
                cached[job_name] = str(with_.get("cache-dependency-path", ""))
            else:
                uncached.append(job_name)

    assert cached.get("unit-tests", "").strip() == "tests_v9/requirements-test.txt", (
        "مفتاح unit-tests يجب أن يتغيّر عند تغيّر ملفّها الفعليّ وحده"
    )
    for job_name, path in cached.items():
        assert path.strip(), f"{job_name}: cache بلا cache-dependency-path يلتقط غير المقصود"
        # رفعته مراجعةٌ آليّة وقِيس: `services/*/requirements.txt` طابق ٢٩ ملفّاً
        # والبوّابة تستهلك ١٩ — فأيّ نجمةٍ التقاطٌ بالعرَض لا بالقياس، لا `**` وحدها.
        assert "*" not in path, (
            f"{job_name}: نمطٌ نجميّ يُبطل المفتاح على ملفّاتٍ خارج ما تستهلكه الوظيفة"
        )
    assert set(uncached) == {"platform-structure-inspector", "lint"}, (
        f"وظائف بلا كاش خارج المقيس: {sorted(uncached)}"
    )


def test_check_names_survive_the_slice_and_unit_tests_is_a_singleton() -> None:
    """حماية الفرع تشترط `Unit Tests` **بالاسم الحرفيّ** — والمصفوفة تشتقّ أسماءً.

    بوّابة القبول نصّاً: لا `strategy.matrix` ولا تغييرَ أسماء. وقُرِئت أسماءُ
    القائمة المطلوبة من سجلّ `branch_protection_contract_guard` (endpoint الحماية
    نفسه ردّ 403 على قراءةٍ مباشرة) — فالمغامرة بالأسماء بلا أساس قياسٍ ممنوعة.
    """
    jobs = _ci()["jobs"]

    assert jobs["unit-tests"]["name"] == "Unit Tests"
    assert "strategy" not in jobs["unit-tests"], "مصفوفةٌ هنا تُيتّم اسمَ الفحص المطلوب"
    required = {
        "Lint & Format",
        "Repository Structural Lint",
        "Platform Structure Inspector",
        "Validate Docker Compose",
        "Frontend Typecheck",
        "Unit Tests",
        "Platform Unit Tests",
        "Live PG Proofs (fake-connection debt)",
        "Repository Tests (tests/)",
        "Weather Service Unit Tests",
        "Decision Service Tests",
        "Integration Tests",
        "Security Scan",
        "Flutter Analyze & Test",
    }
    present = {j.get("name") for j in jobs.values()}
    missing = required - present
    assert not missing, f"أسماءٌ مطلوبة في حماية الفرع غابت عن ci.yml: {sorted(missing)}"
