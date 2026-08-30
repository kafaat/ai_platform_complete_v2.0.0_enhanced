"""`TEMPLATE-INJECTION-IN-A-JOB-THAT-CAN-SIGN-01` — لا قالبَ في متن وظيفةٍ تكتب.

`${{ … }}` داخل `run:` **ليس تمريرَ قيمة**: مُحرِّك القوالب يُصيّرها نصَّ السكربت
قبل أن يبدأ bash. فمُدخَلٌ حرُّ النصّ يصير **شيفرة**، وأيُّ فحصٍ لشكله مكتوبٍ في
السكربت نفسِه يُنفَّذ في سكربتٍ حُقِن أصلاً — **الحارسُ داخل ما يحرسه**.

**والحدُّ ليس «كلّ workflow» بل «كلُّ وظيفةٍ تملك صلاحيةَ كتابة»** — ونطاقٌ مُشتقٌّ
لا قائمةٌ مكتوبة. حُقِنَ في وظيفةٍ بلا امتياز يُتلِف جولةً؛ حُقِنَ في وظيفةٍ تحمل
`attestations: write` **يُصدِر شهادةَ منشأٍ موقّعة** — أي يُنتِج بالضبط الدليلَ الذي
تقوم عليه سلسلةُ التوريد، فيصير الحقنُ **نقضاً لفصل السلطة** لا مجرّد تنفيذِ أمر.

**والمواضعُ التي وُجِدت مقيسةٌ لا مفترَضة، وأخطرُها في مسار الترقية نفسِه:**
`runtime-verification-promotion.yml` كان يُقحِم `inputs.target_sha` في أربعة مواضع،
أحدُها في `approval-receipt` — الوظيفةِ المحميّة بـ`environment` والحاملةِ
`attestations: write`. **والبيئةُ المحميّة تحرس مَن يوافق لا ما يُنفَّذ بعد الموافقة:**
الحمولةُ تعمل بعد إجازة المُراجِع وبصلاحياتها، والمُراجِعُ رأى المُدخَل وسيطاً لا شيفرة.
واثنان في `runtime-image-provenance.yml` (`inputs.source_sha`) حيث كان فحصُ الشكل
يقع **بعد** أن صار المُدخَل سطراً في السكربت — ستّةٌ مقروءةٌ بالجارِد لا بالذاكرة.

**وحدُّ صدقٍ يُقال صراحةً:** هذا يقيس **الشكل** — قالبٌ في متنِ وظيفةٍ ذاتِ صلاحية.
لا يقيس أنّ القيمة المُمرَّرة عبر `env` مُتحقَّقٌ منها، ولا يبلغ `uses:` ولا
`workflow_call`. والقيمةُ المُمرَّرة بيانات لا شيفرة، وذلك وحدَه ما يُدَّعى هنا.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def _write_scopes(permissions: object) -> set[str]:
    if not isinstance(permissions, dict):
        return set()
    return {key for key, value in permissions.items() if value == "write"}


def _privileged_run_steps() -> list[tuple[str, str, tuple[str, ...], str]]:
    """كلُّ خطوةِ ``run`` في وظيفةٍ تملك صلاحيةَ كتابة — مع نصّها."""
    found: list[tuple[str, str, tuple[str, ...], str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        file_scopes = _write_scopes(document.get("permissions"))
        for job_name, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            # الوظيفةُ بلا `permissions:` ترث صلاحياتِ الملفّ — والوراثةُ هي
            # الطريقُ الذي حمل `attestations: write` إلى وظيفةٍ لا تُصدِر شهادة.
            declared = job.get("permissions")
            scopes = _write_scopes(declared) if declared is not None else file_scopes
            if not scopes:
                continue
            for step in job.get("steps") or []:
                if isinstance(step, dict) and isinstance(step.get("run"), str):
                    found.append((path.name, job_name, tuple(sorted(scopes)), step["run"]))
    return found


def test_no_template_expression_runs_inside_a_job_that_holds_a_write_scope():
    """المرساةُ المسمّاة — والمواضعُ الستّة التي أطلقتها كانت في مسارَي الترقية والصور."""
    offenders = [
        f"{workflow} · {job} · صلاحيات {list(scopes)}"
        for workflow, job, scopes, script in _privileged_run_steps()
        if "${{" in script
    ]
    assert not offenders, (
        "قالبٌ يُصيَّر داخل متن `run` في وظيفةٍ تملك صلاحيةَ كتابة:\n  "
        + "\n  ".join(sorted(set(offenders)))
        + '\nمرِّر القيمة عبر `env:` واستعملها متغيّرَ صَدَفة (`"$NAME"`). '
        "وفحصُ الشكل يسبق الاستعمال، ولا يُكتَب في السكربت الذي يحرسه."
    )


def test_the_scan_actually_reaches_privileged_jobs():
    """**الشاهدُ الموجب — وبدونه يبقى الملفُّ أخضرَ وهو لا يقرأ شيئاً.**

    البيانةُ أعلاه تأكيدٌ على **الغياب**: تبقى صادقةً لو عاد الجارِدُ فارغاً — يتبدّل
    مخطَّطُ الصلاحيات، أو يُخفِق التحليل، فيصير «لا مخالف» يعني «لم يُنظَر».
    وهو نمطُ `assertion_presence_guard` بعينه.

    فيُقاس أنّ الجردَ **بلغ وظائفَ ذاتَ امتياز فعلاً**، وأنّ فيها خطواتِ ``run``.
    """
    steps = _privileged_run_steps()
    assert steps, "الجردُ لم يبلغ خطوةَ `run` واحدة في وظيفةٍ ذاتِ صلاحية — المقياسُ بلا موضوع"

    workflows = {workflow for workflow, _job, _scopes, _script in steps}
    assert len(workflows) >= 2, f"الجردُ بلغ {len(workflows)} ملفّاً فقط — نطاقٌ أضيق من الشجرة"

    scopes_seen = {scope for _w, _j, scopes, _s in steps for scope in scopes}
    assert "contents" in scopes_seen, "لم يُرَ `contents: write` — الوراثةُ من الملفّ لا تُقرَأ"


def test_the_two_repaired_workflows_pass_their_dispatch_input_through_env():
    """**الحدّ: أنّ الشجرة نظيفةٌ اليوم لا يقول إنّ الإصلاح هو الذي نظّفها.**

    حذفُ الخطوة يُرضي البيانةَ الأولى حرفيّاً — «لا قالب» يصدق على «لا خطوة». فيُقاس
    أنّ الربطَ **ما يزال قائماً**: كلا الملفّين يُمرِّر مُدخَلَ الإطلاق عبر `env`،
    ويفحص شكلَه بأربعين خانةً ستّ عشريّة، ويقارن `git rev-parse HEAD` به.
    """
    for name, variable in (
        ("runtime-verification-promotion.yml", "TARGET_SHA"),
        ("runtime-image-provenance.yml", "SOURCE_SHA"),
    ):
        source = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert f'[[ "${variable}" =~ ^[0-9a-f]{{40}}$ ]]' in source, (
            f"{name}: فحصُ شكل الـSHA غاب — الربطُ بلا تحقّق"
        )
        assert f'test "$(git rev-parse HEAD)" = "${variable}"' in source, (
            f"{name}: الربطُ بين اللقطة المستنسَخة والمُدخَل غاب — الخطوةُ حُذِفت لا أُصلِحت"
        )


def test_the_image_provenance_privilege_is_declared_where_it_is_used():
    """صلاحيةُ التوقيع تُعلَن في الوظيفة التي توقّع، لا في الملفّ فتُورَث إلى غيرها.

    `publish-manifest` يجمّع شظايا JSON ولا يدفع صورةً ولا يُصدِر شهادة — وكان يرث
    `packages`/`id-token`/`attestations` بالكتابة لأنّها أُعلِنت على مستوى الملفّ.
    """
    document = yaml.safe_load(
        (WORKFLOWS / "runtime-image-provenance.yml").read_text(encoding="utf-8")
    )
    assert _write_scopes(document.get("permissions")) == set(), (
        "صلاحيةُ كتابةٍ على مستوى الملفّ — تُورَث إلى كلّ وظيفة، ومَن لا يحتاجها يحملها"
    )

    jobs = document["jobs"]
    signer = _write_scopes(jobs["build-and-attest"].get("permissions"))
    assert {"packages", "id-token", "attestations"} <= signer, (
        "الوظيفةُ الموقِّعة فقدت صلاحيّتَها — الدفعُ والشهادةُ يفشلان"
    )
    assert _write_scopes(jobs["publish-manifest"].get("permissions")) == set(), (
        "`publish-manifest` يحمل صلاحيةَ كتابةٍ لا يستعملها"
    )
