"""شريحة CI-PERF-01 — الثلاثة الآمنة بمواصفة المالك، وبوّابةُ قبولها مقافلُ هذا الملفّ.

كلٌّ منها يسدّ عطلاً قِيس هنا: جولاتُ PR بائتة تحجز عدّاءات بعد دفعةٍ فوقها ·
`Unit Tests` بلا سقفٍ فتعليقُها انتظارٌ صامت ٦ ساعات (الذروة المقيسة ٤٠–٤٢ دقيقة) ·
وكلّ وظيفةٍ تُنزّل التبعيّات من الصفر.

وتُقرأ الإعدادات **من المُحلِّل لا كنصّ** — الفحص النصّيّ يحمرّ على التعليقات
الشارحة (`TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`، وقعنا فيه مرّتين).
"""

from __future__ import annotations

import json
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
    """السقف ٩٠ قرارُ مالكٍ فوق قياسٍ (الذروة ٥٩.٠) — وتغييرُه تعديلٌ واعٍ لا انجراف.

    **رُفِع من ٦٠ إلى ٩٠ بقياسٍ لا بتخمين — ``MUT-SWEEP-TIMEOUT-01``:** على #882
    أنهت الوظيفةُ عند ٥٩:٠٢ مقابل سقف ٦٠، أي بفارق **٥٨ ثانية**؛ والأساسُ على
    ``1cb3f278`` كان ٤٦:٠٦. والسببُ مقيس: السجلّ انتقل من ٣٨٤ إلى ٤٠١ طفرةً مُعلَنة،
    و``MUT-PRE0`` فوقها فعّلت ٨ مواصفاتٍ كانت محسوبةً في ٣٨٤ **ولا تُشغَّل قطّ**.

    وكانت الذروةُ المكتوبة هنا ٤٠.٣ — رقمٌ بائتٌ يصف كوناً أصغر ممّا يُشغَّل، فيُقرأ
    الهامشُ أوسعَ ممّا هو. فتُكتَب الأرقام بما قِيس وبتاريخه.

    والحدُّ البنيويّ ليس الرفع: نقلُ المكنسة إلى وظيفةٍ مستقلّة — ومعه شرطُه المكتوب
    في ``tests_v9/test_mutation_sweep_headroom.py``. ويبقى الخفضُ لاحقاً بقياس P95
    عبر جولات، لا بتخمين.
    """
    timeout = _ci()["jobs"]["unit-tests"].get("timeout-minutes")

    assert timeout == 90, f"السقف {timeout} ≠ 90 المقرَّر — إن كان تغييراً مقيساً فحدِّث هذا القفل معه"


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
    # **مصدرٌ واحد** — `REQUIRED-CHECKS-DRIFT-IS-INVISIBLE-IN-BOTH-DIRECTIONS-01`:
    # كانت القائمة مكتوبةً هنا بأربعة عشر اسماً، تُقارَن بأسماء وظائف `ci.yml` **ولا
    # تُقارَن بالمُنفَذ فعلاً**. والمقيس على تشغيل 97630483312: الـRuleset يفرض **١٥**
    # سياقاً — ينقصها هنا `Frontend E2E (Playwright · MapLibre/WebGL QA)`. فصار العقد
    # ملفَّ بياناتٍ واحداً يقرؤه هذا الاختبار (مقابلَ الشجرة) و
    # `branch_protection_contract_guard` (مقابلَ الإنفاذ الحيّ) معاً.
    contract = json.loads(
        (ROOT / "docs/architecture/required_status_checks_contract.json").read_text(
            encoding="utf-8"
        )
    )
    required = set(contract["required_contexts"])
    present = {j.get("name") for j in jobs.values()}
    # أسماءُ حزم المصفوفة تُعلَن **حرفيّاً** في `include` (MUT-SHARD-JOB-01) — فهي سياقاتٌ
    # يُبلِّغها GitHub بالاسم كما كُتِبت، وتُحسَب حاضرةً من هناك لا من `name` المشتقّ.
    for job in jobs.values():
        for entry in ((job.get("strategy") or {}).get("matrix") or {}).get("include") or []:
            if isinstance(entry, dict) and isinstance(entry.get("check_name"), str):
                present.add(entry["check_name"])
    missing = required - present
    assert not missing, f"أسماءٌ مطلوبة في حماية الفرع غابت عن ci.yml: {sorted(missing)}"


def test_the_required_lane_runs_on_every_pr_and_cannot_be_skipped_green() -> None:
    """الخطّ الإلزاميّ ثابت: كلّ فحصٍ مطلوب يعمل على كلّ PR، ولا شيء يُحوّله «تخطّياً» أخضر.

    في GitHub طريقان يُفرغان الفحص المطلوب من معناه دون أن يحمرّ شيء:
    * **مرشّح مسارات على الـworkflow**: يتخطّاه GitHub فلا يُبلَّغ السياق أبداً، فيبقى
      الـPR معلّقاً بلا فشلٍ حقيقيّ؛
    * **`if:` على الوظيفة، أو `needs:` على وظيفةٍ غير مطلوبة تفشل**: تُبلَّغ الوظيفة
      `skipped`، وGitHub يعدّ المطلوب المتخطّى ناجحاً. فتمرّ البوّابة صامتةً.
    وكذلك `continue-on-error` على وظيفةٍ مطلوبة يجعل فشلها أخضر.

    واسمٌ مطلوب يحمله workflow آخر يُرضي السياقَ نفسه بالاسم. فإن كان ذاك الآخر مُرشَّحاً
    بالمسارات أو أضيق، صار المطلوب يُقضى بغير ci.yml. فالاسم يجب أن يكون **لـci.yml وحده**.

    مقيسٌ عند كتابة هذا الاختبار على 8216ef4: لا شيء من ذلك قائم (١٦ وظيفة تُبلِّغ
    ٢٠ سياقاً، بلا `if` ولا `needs` ولا مرشّح). فهذا قفلٌ على حالٍ صحيحة، لا إصلاح.
    والخطوط الاختياريّة (بقيّة الـworkflows، ومنها المُرشَّحة بالمسارات) حرّةٌ في ذلك
    ما دامت لا تحمل اسماً مطلوباً.
    """
    ci = _ci()
    on = ci.get(True, ci.get("on"))
    assert isinstance(on, dict) and "pull_request" in on, "ci.yml يجب أن يعمل على pull_request"
    pr = on["pull_request"] or {}
    assert "paths" not in pr and "paths-ignore" not in pr, (
        "مرشّح مسارات على ci.yml يُعلّق الفحوص المطلوبة على كلّ PR لا يمسّها"
    )
    if "branches" in pr:
        assert "main" in pr["branches"], "ci.yml لا يعمل على PRs إلى main"
    assert "branches-ignore" not in pr

    required = set(
        json.loads(
            (ROOT / "docs/architecture/required_status_checks_contract.json").read_text(
                encoding="utf-8"
            )
        )["required_contexts"]
    )
    jobs = ci["jobs"]

    def reported(key: str, job: dict) -> set[str]:
        names = {job.get("name", key)}
        for entry in ((job.get("strategy") or {}).get("matrix") or {}).get("include") or []:
            if isinstance(entry, dict) and isinstance(entry.get("check_name"), str):
                names.add(entry["check_name"])
        return names

    required_jobs = {key for key, job in jobs.items() if reported(key, job) & required}
    assert required_jobs, "لم تُوجَد أيّ وظيفةٍ مطلوبة — القراءة نفسها معطوبة"

    def needs(key: str) -> set[str]:
        direct = jobs[key].get("needs") or []
        direct = [direct] if isinstance(direct, str) else list(direct)
        found = set(direct)
        for item in direct:
            found |= needs(item)
        return found

    problems = []
    for key in sorted(required_jobs):
        job = jobs[key]
        if "if" in job:
            problems.append(f"{key}: `if:` على وظيفةٍ مطلوبة — تخطّيها يُحسَب نجاحاً")
        if job.get("continue-on-error"):
            problems.append(f"{key}: `continue-on-error` على وظيفةٍ مطلوبة — فشلها يصير أخضر")
        optional = sorted(needs(key) - required_jobs)
        if optional:
            problems.append(f"{key}: `needs` على وظائف غير مطلوبة {optional} — فشلها يتخطّاها أخضر")
    assert not problems, "\n".join(problems)

    elsewhere = []
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        if path.name == "ci.yml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, job in (document.get("jobs") or {}).items():
            if isinstance(job, dict):
                clash = reported(key, job) & required
                if clash:
                    elsewhere.append(f"{path.name}:{key} → {sorted(clash)}")
    assert not elsewhere, f"أسماءٌ مطلوبة تحملها workflows غير ci.yml: {elsewhere}"


def test_the_sharded_sweep_job_declares_literal_check_names() -> None:
    """أسماءُ الفحوص المطلوبة تُطابَق حرفيّاً — واسمٌ يشتقّه التعبير يُيتَّم.

    نفس درس `test_check_names_survive_the_slice…` فوقه: المصفوفة تشتقّ أسماءً،
    فالاسمُ يُعلَن صريحاً في `include` ويُقرأ منه — لا `${{ matrix.shard }}`
    مُركَّباً في نصّ الاسم.
    """
    job = _ci()["jobs"]["mutation-sweep"]
    entries = job["strategy"]["matrix"]["include"]
    names = [entry["check_name"] for entry in entries]

    assert names == [f"Mutation Sweep {i}/5" for i in range(1, 6)], names
    assert len({entry["shard"] for entry in entries}) == len(entries), "حزمةٌ مكرَّرة"
    assert [entry["shard"] for entry in entries] == [f"{i}/5" for i in range(5)]
    # `fail-fast` مُطفَأة: حزمةٌ تسقط لا تُلغي أخواتها فتُخفي أعطالها.
    assert job["strategy"]["fail-fast"] is False


def test_the_union_guard_runs_in_every_shard_before_planting() -> None:
    """الفحصُ الذي يقع في أختها لا يشهد لها — فيُشغَّل في كلّ حزمة، وقبل الزرع."""
    steps = _ci()["jobs"]["mutation-sweep"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    union = next(i for i, r in enumerate(runs) if "--shard-inventory" in r)
    plant = next(i for i, r in enumerate(runs) if "--run --shard" in r)
    assert union < plant, "حارسُ الاتّحاد بعد الزرع يشهد على ما جرى لا على ما سيجري"


def test_the_sweep_stays_in_unit_tests_until_the_ruleset_is_set() -> None:
    """**بوّابةُ التسلسل نفسها.**

    نقلُ المكنسة قبل إضافة أسماء الحزم إلى الفحوص المطلوبة يجعلها إرشاديّةً
    **صامتاً** — تحمرّ ولا تحجب. فالحذف يقع في التزامٍ واحد مع إضافة الأسماء إلى
    `required_status_checks_contract.json`، وهذا الاختبار يفرض اقترانهما:
    إمّا الاثنان معاً وإمّا لا شيء.
    """
    contract = json.loads(
        (ROOT / "docs/architecture/required_status_checks_contract.json").read_text(
            encoding="utf-8"
        )
    )
    shard_names = {f"Mutation Sweep {i}/5" for i in range(1, 6)}
    required = set(contract["required_contexts"])
    sweep_in_unit_tests = any(
        "guard_mutation_guard.py --run" in str(step.get("run", ""))
        for step in _ci()["jobs"]["unit-tests"]["steps"]
    )

    if shard_names & required:
        assert shard_names <= required, "بعضُ الحزم مطلوبةٌ وبعضُها لا — تغطيةٌ نصفيّة"
        assert not sweep_in_unit_tests, (
            "الحزم صارت مطلوبةً والمكنسة ما تزال في Unit Tests — ازدواجٌ يُبطئ بلا فائدة"
        )
    else:
        assert sweep_in_unit_tests, (
            "المكنسة خرجت من Unit Tests وأسماءُ الحزم ليست في العقد — نافذةُ صمت: تحمرّ ولا تحجب"
        )


def test_every_shard_plants_its_defects() -> None:
    """الحزمةُ التي لا تزرع لا تحرس — واسمٌ مطلوبٌ في الـRuleset بلا زرعٍ خضرةٌ فارغة.

    بعد نزع المكنسة من *Unit Tests* صارت `mutation-sweep` المكنسةَ الحاجبة الوحيدة،
    فخطوةُ الزرع فيها هي كلُّ ما يحجب الطفرات. وتُطابَق بهويّة الخطوة لا بنصّ الأمر
    وحده (`MUTATION-ANCHOR-MATCHES-A-COMMAND-NOT-A-STEP-01`).
    """
    steps = _ci()["jobs"]["mutation-sweep"]["steps"]
    plant = [
        s
        for s in steps
        if s.get("name") == "Plant this shard's defects"
        and "guard_mutation_guard.py --run --shard ${{ matrix.shard }}" in str(s.get("run", ""))
    ]
    assert len(plant) == 1, "خطوةُ الزرع في حزم المكنسة غائبةٌ أو مكرّرة — خضرةٌ بلا زرع"
