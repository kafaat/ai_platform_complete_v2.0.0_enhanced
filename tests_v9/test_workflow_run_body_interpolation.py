"""مُدخَلٌ يملكه غيرُنا لا يُستبدَل نصّاً داخل `run:` — `WORKFLOW-RUN-BODY-INTERPOLATION-01`.

**العطل المقيس، لا المُتخيَّل.** حتّى `5112a613` كانت **٢٣** تعبيراً من عائلاتٍ
يملكها طرفٌ خارجَ الشيفرة تُستبدَل نصّاً داخل أجسام `run:` — منها ثلاثةٌ في
`runtime-image-provenance.yml`، وهي الوظيفةُ التي تحمل `id-token: write` و
`attestations: write` و`packages: write`. أي: **حقنُ صدَفةٍ في الوظيفة الموقِّعة**
⇒ برهانٌ مزوَّر، وهدمُ الفصل الذي وُجِدت GATE-01 لحمايته من داخله.

أغلقها #964 بنقل الاستبدال إلى `env:` — والقياسُ يصدّق ذلك: `764713df` صفرٌ.

**ولماذا اختبارٌ بعده؟** لأنّ ما بقي يحرس ذلك الإغلاقَ **ليس محلّيّاً**:
`scripts/ci/github_actions_security_guard.py` حارسٌ فوقيّ لا يحلّل الحقن أصلاً —
يتحقّق أنّ مسار الفحص قائمٌ ومثبَّتُ البصمات وأنّ أوامرَه مذكورةٌ في `ci.yml`.
والكشفُ الفعليّ مُفوَّضٌ كلُّه إلى `zizmor --min-severity high --min-confidence high`
— ثنائيّةٌ تُنزَّل زمنَ التشغيل، وعتبتُها لم يكذّبها أحدٌ في هذا المستودع. فإن فشل
التنزيل، أو صنّف zizmor مُدخَلَ `workflow_dispatch` دون high/high، عاد الانحدارُ
**صامتاً**. هذه الحالةُ تقيس الشرطَ نفسَه بلا أداةٍ ولا شبكة.

**العلاجُ حين تحمرّ** — وهو موجودٌ في الشجرة أصلاً: انقل القيمة إلى `env:` على
الخطوة، ثمّ استعملها في الصدَفة بـ`"$NAME"` مُقتبَسةً. المثالُ القانونيّ
`.github/workflows/runtime-image-provenance.yml` (`SOURCE_SHA`).

**حدودُ الصدق.** تُقاس ثلاثُ عائلاتٍ فقط: `inputs.` و`github.event.` و
`github.head_ref`. ولا تُقاس `steps.*.outputs.*` — قد تحمل قيمةً ملوّثةً من خطوةٍ
سابقة، لكنّ تتبُّعَها يحتاج تحليلَ تدفّقٍ لا مطابقةَ نصّ، وقاعدةٌ تُعمَّم بلا ذلك
تُنتِج ضجيجاً يُسقِط نفسَه. ولا تُقاس دلالاتُ المنصّة (البيئات المحميّة، الأذونات)
— تلك تبقى لـzizmor وactionlint، وهذه مكمِّلةٌ لهما لا بديل.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"

#: تعبيرُ Actions. `DOTALL` لأنّ الأجسامَ متعدّدةُ الأسطر والتعبيرُ قد يُلَفّ.
_EXPRESSION = re.compile(r"\$\{\{\s*(?P<body>.+?)\s*\}\}", re.DOTALL)

#: العائلاتُ التي يملك قيمتَها طرفٌ خارجَ الشيفرة المُراجَعة. `github.event.`
#: يغطّي `github.event.inputs.*` أيضاً — وهي الصيغةُ التي ظهرت في
#: `docker-build-matrix-verifier.yml` قبل الإغلاق.
_ATTACKER_OWNED = ("inputs.", "github.event.", "github.head_ref")


def _workflow_files() -> list[Path]:
    return sorted(_WORKFLOWS.glob("*.yml")) + sorted(_WORKFLOWS.glob("*.yaml"))


def _run_steps(document: object):
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        return
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                yield job_name, index, step


def _offences(text: str) -> list[tuple[str, str, str]]:
    """يعيد (الوظيفة · اسمُ الخطوة · التعبير) لكلّ استبدالٍ مملوكٍ لغيرنا داخل `run:`."""
    document = yaml.safe_load(text)
    found: list[tuple[str, str, str]] = []
    for job_name, index, step in _run_steps(document):
        label = str(step.get("name") or f"step[{index}]")
        for match in _EXPRESSION.finditer(step["run"]):
            body = match.group("body")
            if any(family in body for family in _ATTACKER_OWNED):
                found.append((job_name, label, body.strip()))
    return found


def test_the_workflow_directory_is_actually_being_measured():
    """حارسٌ يقيس صفراً من الملفّات يمرّ دائماً. هذه تمنع ذلك الصمت."""
    files = _workflow_files()
    assert files, "لم يُقَس أيّ workflow — صارت الحزمةُ صامتةً"
    assert any(path.name == "ci.yml" for path in files), "ملفّ ci.yml ليس ضمن القياس"


def test_no_workflow_interpolates_a_foreign_owned_value_into_a_shell_body():
    """الشرطُ نفسُه الذي أغلقه #964، مقيساً محلّيّاً بلا أداةٍ ولا شبكة."""
    offences: list[str] = []
    for path in _workflow_files():
        for job_name, label, body in _offences(path.read_text(encoding="utf-8")):
            offences.append(f"{path.name} · {job_name} · {label} · ${{{{ {body} }}}}")
    assert not offences, (
        "استبدالٌ نصّيٌّ لقيمةٍ يملكها غيرُنا داخل جسم `run:` — انقلها إلى `env:` على "
        'الخطوة واستعملها بـ"$NAME" مُقتبَسة (المثال: runtime-image-provenance.yml '
        "وSOURCE_SHA):\n  - " + "\n  - ".join(offences)
    )


def test_the_rule_catches_the_shape_that_actually_shipped():
    """تكذيبٌ داخليّ: لولاه لكانت الحالةُ أعلاه خضراءَ لأنّها لا تقيس شيئاً.

    النصُّ هنا منسوخُ البنية عن `runtime-image-provenance.yml` قبل #964.
    """
    vulnerable = """
name: probe
on:
  workflow_dispatch:
    inputs:
      source_sha:
        required: true
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - name: Validate exact checkout
        run: test "$(git rev-parse HEAD)" = "${{ inputs.source_sha }}"
"""
    assert _offences(vulnerable), "القاعدةُ لا تلتقط الشكلَ الذي شُحِن فعلاً — فهي لا تحرس شيئاً"


def test_the_rule_accepts_the_remedy_that_shipped():
    """ومقابلُه: العلاجُ القانونيّ يجب أن يمرّ، وإلّا كانت القاعدةُ تعاقب الإصلاح."""
    remedied = """
name: probe
on:
  workflow_dispatch:
    inputs:
      source_sha:
        required: true
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - name: Validate exact checkout
        env:
          SOURCE_SHA: ${{ inputs.source_sha }}
        run: test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
      - name: Non-shell contexts stay legitimate
        uses: actions/checkout@v4
        with:
          ref: ${{ inputs.source_sha }}
"""
    assert not _offences(remedied), "القاعدةُ تحمرّ على العلاج — فهي تدفع نحو العطل لا بعيداً عنه"
