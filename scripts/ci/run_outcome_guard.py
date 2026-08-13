#!/usr/bin/env python3
"""خلاصةُ تشغيلٍ مكتمل، مُشتقّةً من استجابتَي GitHub لا مكتوبةً بيد.

``ATTESTED-IS-NOT-CERTIFIED-01``. سُلَّم الضمان يحتاج جواباً عن سؤالٍ لا يستطيع
التشغيلُ أن يُجيبه عن نفسه: **كيف انتهيتَ؟** وظيفةٌ تعمل الآن لا تعرف خلاصة تشغيلها،
فالجواب يُقرأ من الواجهة **بعد** الاكتمال — وهذا ما يجعل الاعتماد خطوةً لاحقة بالضرورة،
لا تفضيلاً في التصميم.

**والقسمة بين هذا الملفّ والـworkflow مقصودة:** ``scripts/ci/**`` لا يستدعي GitHub في
هذا المستودع (مقيس، ويحرسه عقد ``test_local_preflight_contract``). فالوظيفة تجلب
وتُجسّد الاستجابتين ملفَّين، وهذا يحكم عليهما — تماماً كما يفعل
``branch_protection_contract_guard``. والسبب مكتوب هناك: منطقٌ مدفون في ``run: |`` لا
يُقاس إلّا بتشغيل الوظيفة كاملةً.

**وما يرفضه هذا صراحةً:**

* تشغيلٌ لم يكتمل (``status != completed``) — «قيد التنفيذ» ليس «نجح».
* خلاصةٌ غير ``success`` — والفشلُ لا يُبطِل التوقيع، لكنّه يمنع **الاعتماد**.
* وظيفةٌ ساقطة داخل تشغيلٍ يُعلَن ناجحاً — الخلاصة المجمَّعة ليست دليلاً
  (``JOB-STATUS-HID-A-FAILED-STEP-01``، ووقعت حرفيّاً في التشغيل ``31728316326``).
* تشغيلٌ لمستودعٍ أو workflow غير المقصود.
* جردُ وظائف فارغ — «لم تُقرأ» ليست «كلّها نجحت».

**وحدّ صدق:** يقرأ ما أعلنته الواجهة عن تشغيلٍ جرى؛ ولا يشهد بأنّ الواجهة صدقت.
والشاهد على ذلك حدودُ الثقة في GitHub نفسها لا هذا الملفّ.

    python scripts/ci/run_outcome_guard.py --run-file run.json --jobs-file jobs.json \\
        --expect-repository owner/repo --expect-workflow-path .github/workflows/ci.yml \\
        --output execution_outcome.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجٌ عربيّ يُرمَّز بلغة الآلة.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SCHEMA = "sahool.execution-outcome/v1"

#: وظائفٌ لا تُدان بعدم النجاح — ولا واحدة اليوم. الحقل قائمٌ ليُقرأ فارغاً بوضوح
#: بدل أن يُضاف استثناءٌ صامت أوّلَ مرّة تُزعِج فيها البوّابة.
TOLERATED_JOBS: frozenset[str] = frozenset()


def _load(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"✗ لا ملفّ {label} في {path} — لم تُجلَب الاستجابة أصلاً.") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"✗ تعذّرت قراءة {path}: {exc} — «لم يُقرأ» ليس «نجح».") from None


def job_conclusions(jobs_document: object) -> dict[str, str]:
    """{اسم الوظيفة: خلاصتها} — وشكلٌ لا يُفهَم يُرفَض لا يُقرأ فارغاً."""
    if not isinstance(jobs_document, dict):
        raise SystemExit("✗ استجابةُ الوظائف ليست كائناً — جسمُ خطأٍ في موضع جرد.")
    jobs = jobs_document.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit("✗ `jobs` ليست مصفوفة — «لم تُقرأ» ليست «كلّها نجحت».")
    out: dict[str, str] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = job.get("name")
        if not isinstance(name, str) or name in TOLERATED_JOBS:
            continue
        # وظيفةٌ لم تكتمل تُسجَّل بحالتها لا بخلاصةٍ فارغة: `None` تُقرأ لاحقاً
        # «ليست success» فتحجب — وهو الاتّجاه الصحيح للفشل المغلق.
        out[name] = job.get("conclusion") or f"<{job.get('status', 'unknown')}>"
    return out


def build(
    run: object,
    jobs_document: object,
    *,
    expect_repository: str,
    expect_workflow_path: str,
) -> dict:
    if not isinstance(run, dict):
        raise SystemExit("✗ استجابةُ التشغيل ليست كائناً.")
    problems: list[str] = []

    repository = (run.get("repository") or {}).get("full_name")
    if repository != expect_repository:
        problems.append(f"`repository` = {repository!r} والمقصود {expect_repository!r}")
    if run.get("path") != expect_workflow_path:
        problems.append(f"`path` = {run.get('path')!r} والمقصود {expect_workflow_path!r}")
    if run.get("status") != "completed":
        problems.append(f"`status` = {run.get('status')!r} — «قيد التنفيذ» ليس «نجح»")
    if problems:
        raise SystemExit("✗ استجابةُ تشغيلٍ لا تخصّ المقصود:\n  - " + "\n  - ".join(problems))

    conclusions = job_conclusions(jobs_document)
    if not conclusions:
        raise SystemExit("✗ جردُ وظائف فارغ — «لم تُقرأ» ليست «كلّها نجحت».")

    return {
        "schema": SCHEMA,
        "run_id": str(run.get("id")),
        "run_attempt": run.get("run_attempt"),
        "head_sha": run.get("head_sha"),
        "head_branch": run.get("head_branch"),
        "event": run.get("event"),
        "workflow_path": run.get("path"),
        "run_conclusion": run.get("conclusion"),
        "job_conclusions": conclusions,
        "$honesty_limit_ar": (
            "يقرأ ما أعلنته واجهة GitHub عن تشغيلٍ جرى، ولا يشهد بأنّ الواجهة صدقت. "
            "والخلاصة تُقرأ **بعد** الاكتمال لأنّ التشغيل لا يعرف كيف انتهى."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="خلاصةُ تشغيلٍ مكتمل من استجابتَي GitHub")
    ap.add_argument("--run-file", type=Path, required=True)
    ap.add_argument("--jobs-file", type=Path, required=True)
    ap.add_argument("--expect-repository", required=True)
    ap.add_argument("--expect-workflow-path", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)

    outcome = build(
        _load(args.run_file, "التشغيل"),
        _load(args.jobs_file, "الوظائف"),
        expect_repository=args.expect_repository,
        expect_workflow_path=args.expect_workflow_path,
    )
    args.output.write_text(
        json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    failed = sorted(k for k, v in outcome["job_conclusions"].items() if v != "success")
    print(
        f"run_outcome_guard: {outcome['run_id']}/{outcome['run_attempt']} "
        f"⇒ {outcome['run_conclusion']} · {len(outcome['job_conclusions'])} وظيفة"
        + (f" · غير ناجحة: {failed}" if failed else "")
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
