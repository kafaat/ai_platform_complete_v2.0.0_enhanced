"""خلاصةُ تشغيلٍ مكتمل — ATTESTED-IS-NOT-CERTIFIED-01.

الحالةُ المرجعيّة هنا **واقعة مقيسة** لا مثالٌ مصنوع: التشغيل `31728316326` أنتج حزمة
Sigstore صحيحة تشفيريّاً بالكامل — توقيع DSSE، وربطُ `payloadHash` بجسم Rekor، وإثبات
Merkle، وهويّة Fulcio — وخلاصتُه `failure`، وسقطت فيه `Repository Tests (tests/)`
وحدها. فالحزمة **شهادةٌ صحيحة لحالةٍ فاشلة**، وهذا الملفّ يقيس أنّ المُشتقّ يقولها.

والحالة المقابلة تلزم بنفس القدر: تشغيلٌ ناجح **يُعتمَد**. مِصفاةٌ ترفض كلّ شيء تُرضي
كلّ اختبار رفضٍ وتُوقِف الإصدار.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "run_outcome_guard", ROOT / "scripts/ci/run_outcome_guard.py"
)
probe = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(probe)

REPO = "kafaat/ai_platform_complete_v2.0.0_enhanced"
WORKFLOW = ".github/workflows/ci.yml"
HEAD = "278ae8e4c0385f99a1aed10240623d971a31fd89"


def _run(**over) -> dict:
    base = {
        "id": 31728316326,
        "run_attempt": 1,
        "head_sha": HEAD,
        "head_branch": "tests/raster-tiler-contract",
        "event": "pull_request",
        "status": "completed",
        "conclusion": "failure",
        "path": WORKFLOW,
        "repository": {"full_name": REPO},
    }
    base.update(over)
    return base


def _jobs(*pairs) -> dict:
    return {
        "jobs": [
            {"name": name, "status": "completed", "conclusion": conclusion}
            for name, conclusion in pairs
        ]
    }


def _build(run: dict, jobs: dict) -> dict:
    return probe.build(run, jobs, expect_repository=REPO, expect_workflow_path=WORKFLOW)


def test_the_measured_failed_run_is_reported_as_failed() -> None:
    """الواقعة بعينها: حزمةٌ سليمة تشفيريّاً من تشغيلٍ خلاصتُه فشل."""
    outcome = _build(
        _run(), _jobs(("Unit Tests", "success"), ("Repository Tests (tests/)", "failure"))
    )

    assert outcome["run_conclusion"] == "failure"
    assert outcome["job_conclusions"]["Repository Tests (tests/)"] == "failure"
    assert outcome["head_sha"] == HEAD


def test_a_successful_run_is_reported_as_successful() -> None:
    """الاتّجاه المقابل — مِصفاةٌ ترفض كلّ شيء تُوقِف الإصدار وتُرضي كلّ اختبار رفض."""
    outcome = _build(_run(conclusion="success"), _jobs(("Unit Tests", "success")))

    assert outcome["run_conclusion"] == "success"
    assert outcome["job_conclusions"] == {"Unit Tests": "success"}


def test_a_run_still_in_progress_is_refused() -> None:
    """«قيد التنفيذ» ليس «نجح» — وهو بالضبط ما يعجز التشغيلُ عن قوله عن نفسه."""
    with pytest.raises(SystemExit, match="status"):
        _build(_run(status="in_progress", conclusion=None), _jobs(("Unit Tests", "success")))


def test_an_incomplete_job_is_recorded_by_its_status_not_as_blank() -> None:
    """خلاصةٌ فارغة تُقرأ لاحقاً «ليست success» فتحجب — وهو الاتّجاه الصحيح للفشل."""
    outcome = _build(
        _run(conclusion="success"), {"jobs": [{"name": "Slow", "status": "in_progress"}]}
    )

    assert outcome["job_conclusions"] == {"Slow": "<in_progress>"}


def test_a_run_from_another_repository_is_refused() -> None:
    with pytest.raises(SystemExit, match="repository"):
        _build(_run(repository={"full_name": "someone/else"}), _jobs(("Unit Tests", "success")))


def test_a_run_of_another_workflow_is_refused() -> None:
    """workflow آخر في نفس المستودع يُنتِج خلاصةً صادقة عن **شيء غير المقصود**."""
    with pytest.raises(SystemExit, match="path"):
        _build(_run(path=".github/workflows/other.yml"), _jobs(("Unit Tests", "success")))


def test_an_empty_job_inventory_is_refused() -> None:
    """«لم تُقرأ» ليست «كلّها نجحت» — وجردٌ فارغ يجعل كلّ تشغيلٍ نظيفاً."""
    with pytest.raises(SystemExit, match="فارغ"):
        _build(_run(conclusion="success"), {"jobs": []})


def test_a_malformed_jobs_document_is_refused_not_read_as_empty() -> None:
    with pytest.raises(SystemExit, match="مصفوفة"):
        _build(_run(conclusion="success"), {"jobs": "not-a-list"})


def test_the_outcome_feeds_the_certification_gate_end_to_end() -> None:
    """الوصل المقيس: ما يُنتِجه المُشتقّ هو ما يرفضه الحارس — لا شكلان متقاربان."""
    guard_spec = importlib.util.spec_from_file_location(
        "sot_provenance_guard", ROOT / "scripts/ci/sot_provenance_guard.py"
    )
    guard = importlib.util.module_from_spec(guard_spec)
    assert guard_spec.loader is not None
    guard_spec.loader.exec_module(guard)

    failed = _build(
        _run(), _jobs(("Unit Tests", "success"), ("Repository Tests (tests/)", "failure"))
    )
    passed = _build(_run(conclusion="success"), _jobs(("Unit Tests", "success")))

    assert guard.execution_clean(failed, HEAD) == (False, "EXECUTION_RUN_NOT_SUCCESSFUL")
    assert guard.execution_clean(passed, HEAD) == (True, "")


def test_the_certification_workflow_alone_enforces_the_outcome() -> None:
    """الراية في وظيفة الاعتماد وحدها — والاستدعاء داخل CI يبقى بلا فرضٍ لا يستطيعه.

    ولو حملها استدعاءُ `ci.yml` لاحمرّ `main` على غياب شيءٍ لا يملك المُنتِج إنتاجه.
    """
    certify = (ROOT / ".github/workflows/certify-run.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "--require-execution-outcome" in certify
    assert "--require-execution-outcome" not in ci, (
        "الراية في استدعاء `ci.yml` تفرض ما لا يستطيعه المُنتِج: الوظيفة تعمل أثناء "
        "التشغيل ولا تعرف كيف انتهى، فيُحمَّر `main` على غياب أداةٍ لا على عطل. "
        "والمنعُ هنا مقصودٌ ومكتوب السبب — لا تهجئةٌ تُحرَس."
    )
    assert "workflow_run" in certify


def test_the_shipped_probe_is_reachable_from_the_certification_workflow() -> None:
    certify = (ROOT / ".github/workflows/certify-run.yml").read_text(encoding="utf-8")

    assert "scripts/ci/run_outcome_guard.py" in certify
    assert json.loads('{"ok": true}')["ok"] is True


# ── عطلان رفعتهما مراجعةٌ آليّة على #844، وكلاهما أصاب ────────────────────────


def test_the_certification_job_checks_out_the_attested_commit() -> None:
    """الشيفرة التي تحكم هي شيفرة التشغيل المشهود له، لا رأسَ الفرع الافتراضيّ.

    `workflow_run` يستنسخ افتراضيّاً HEAD الفرع الافتراضيّ. فبلا `ref` صريح تُقاس
    مصنوعاتُ تشغيلٍ بحارسٍ من **إصدارٍ آخر** — يُكسَر إعادةُ الإنتاج، ويصير الاعتماد
    حكماً بشيفرةٍ غير التي أنتجت الدليل. وهو الصنف الذي بُنِيت الوظيفة لتغلقه.
    """
    certify = (ROOT / ".github/workflows/certify-run.yml").read_text(encoding="utf-8")

    assert "github.event.workflow_run.head_sha" in certify, (
        "استنساخٌ بلا ref يجعل الاعتماد يقيس شيفرةً غير شيفرة التشغيل المشهود له"
    )


def test_the_changed_file_derivation_fails_closed() -> None:
    """قائمةٌ فارغة عن **فشل** تُقرأ كقائمةٍ فارغة عن **براءة** — ولا شيء يفرّق.

    الصيغة الأولى كانت `git diff … || : > changed.txt`، فأيّ تعذّرٍ في الجلب يُطفئ
    البند الحاجب على مسار التفويضات صامتاً. والبندُ وُضِع ليحجب فعلاً حسّاساً، فيجب
    أن يفشل مغلقاً.
    """
    governance = (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    # **السطور المُنفَّذة وحدها.** أوّل صياغةٍ لهذا التأكيد مسحت الملفّ كلّه فأحمرّها
    # **التعليقُ الذي يشرح الإصلاح** — نصٌّ يصف العطل ليس نصّاً يرتكبه، وهو الصنف
    # المُسجَّل هنا باسم `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`. وقعتُ فيه الآن.
    executable = "\n".join(
        line for line in governance.splitlines() if not line.lstrip().startswith("#")
    )

    assert "|| : > changed.txt" not in executable, (
        "اشتقاقٌ يفشل مفتوحاً يُطفئ الشرط المشروط بدل أن يحجب"
    )
    assert "changed.txt" in executable and "set -euo pipefail" in executable


def test_the_changed_file_derivation_has_history_to_derive_from() -> None:
    """وفشلٌ مغلقٌ فوق اشتقاقٍ لا يستطيع أن ينجح هو حجبٌ دائم، لا إنفاذ.

    أوّل تشغيلٍ صادق (94753838446) ردّ `fatal: origin/main...HEAD: no merge base`:
    استنساخٌ بعمق ١ وجلبٌ بـ`--depth=1` لا يلتقيان في سلف. ومعناه أنّ `changed.txt`
    كانت **فارغة في كلّ تشغيلٍ سابق** — البند المشروط لم يُقيَّم مرّةً منذ كُتِب،
    وأخفى ذلك `|| : > changed.txt`. فالعمق شرطُ صحّةٍ لا تحسين أداء.
    """
    governance = (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in governance.splitlines() if not line.lstrip().startswith("#")
    )
    job = executable.split("branch-protection-contract:", 1)
    assert len(job) == 2, "الوظيفة المعنيّة غير موجودة بهذا الاسم — أُعيدت تسميتُها؟"
    body = job[1]

    assert "fetch-depth: 0" in body.split("- name:", 1)[0], (
        "استنساخٌ ضحل ⇒ لا سلف مشترك ⇒ `no merge base` ⇒ حجبٌ دائم بلا قياس"
    )
    assert 'git fetch origin "${BASE_REF}" --depth=1' not in body, (
        "جلبُ القاعدة بعمق ١ يُعيد رأساً منفصلاً عن التاريخ، فلا merge-base"
    )


# ── اسمُ المصنوعة ادّعاء — كشفه أوّلُ تشغيلٍ حقيقيّ للاعتماد ──────────────────


def _certify_upload_blocks() -> list[dict]:
    """خطواتُ رفع المصنوعات في وظيفة الاعتماد، مقروءةً **كـYAML** لا كنصّ.

    الفحص النصّيّ هنا كان سيقيس تهجئةً لا خاصّيّة، ويحمرّ على التعليق الذي يشرح
    الإصلاح — `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`، وقد وقعتُ فيه مرّتين
    في هذه السلسلة. فالبنية تُقرأ من المُحلِّل.
    """
    import yaml

    doc = yaml.safe_load((ROOT / ".github/workflows/certify-run.yml").read_text(encoding="utf-8"))
    steps = doc["jobs"]["certify"]["steps"]
    return [s for s in steps if "upload-artifact" in str(s.get("uses", ""))]


def test_no_artifact_promises_a_certification_record_it_may_not_contain() -> None:
    """مصنوعةٌ اسمها `certification-record` تحمل خلاصةَ تشغيلٍ فقط تدّعي ما لا تحمل.

    مقيسٌ في تشغيل 31825902904: رُفِعت باسم `certification-record` وفيها **ملفّ
    واحد** هو `execution_outcome.json`، لأنّ التشغيل بلا حزمة أدلّة فلم يُنتَج
    سجلُّ اعتماد. لا يخدع آليّةً، ويخدع قارئاً يُنزّلها — وهو
    `CI-JOB-NAME-CLAIMS-MORE-THAN-IT-MEASURES-01` بعينه.
    """
    for step in _certify_upload_blocks():
        with_ = step["with"]
        paths = [p for p in str(with_["path"]).splitlines() if p.strip()]
        if with_["name"] == "certification-record":
            assert paths == ["certification_record.json"], (
                "مصنوعةُ الاعتماد تحمل سجلَّ الاعتماد وحده — وإلّا وعد اسمُها بما لا تحويه"
            )
            assert "steps.download.outcome == 'success'" in str(step.get("if", "")), (
                "تُرفَع حين وُجِد موضوعُ الاعتماد وحده، فيصير وجودُها نفسه إشارة"
            )


def test_an_empty_artifact_is_not_uploaded_under_a_promising_name() -> None:
    """`if-no-files-found: warn` يجعل الغياب سطراً في السجلّ لا شيئاً يراه المُنزِّل."""
    steps = _certify_upload_blocks()
    assert len(steps) == 2, "المتوقَّع مصنوعتان: خلاصةُ التشغيل وسجلُّ الاعتماد"
    assert {s["with"]["name"] for s in steps} == {"execution-outcome", "certification-record"}
    for step in steps:
        assert step["with"]["if-no-files-found"] == "error", (
            "مصنوعةٌ فارغة باسمٍ يَعِد هي العطل نفسه، فلا تُحتمَل بتحذير"
        )
