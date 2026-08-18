"""عقد مُطلِقات `ci.yml` — `CI-DUPLICATE-PUSH-RUN-BLOCKS-THE-PR-01`.

**العطل، مقيساً في يومٍ واحد على فرعٍ واحد.** كانت `on: [push, pull_request]`، فكلّ
دفعةٍ تُنشئ تشغيلين على الرأس نفسه. وتشغيل `push` لا يُلغى أبداً: مجموعة التزامن
تحوي `run_id` فهي فريدة لكلّ تشغيل — وذلك **مقصودٌ على main** (لكلّ التزامٍ سجلُّه،
لأنّ `certify-run` يستهلكه)، لكنّه طُبِّق على كلّ مرجع.

**والضرر ليس الكلفة بل الحجب.** GitHub يقرأ **أحدث** سجلٍّ لكلّ اسم فحص. فتشغيل
`push` يُلغى أو يسقط بعد أن اخضرّ تشغيل الـPR ⇒ نتيجته الحمراء تعلو على الخضراء،
ويبقى الـPR محجوباً بلا شيء يُصلَح. سجلّ 2026-08-18 على `claude/claude-md-docs-p6qqir`:
`6400` failure · `6402` عالق ٨٠+ دقيقة · `6404` failure · `6406` cancelled بعد ٦٥
دقيقة. أربعة تشغيلات، صفر فائدة، وحجبٌ مرّتين.

**والقصر لا يُنقِص مستهلِكاً واحداً** — وهذا مقيسٌ لا مُرجَّح، ويُفرَض هنا: المستهلك
الوحيد هو `certify-run.yml`، ويشترط `event == 'push' && head_branch == 'main'`. فلو
عاد أحدٌ فوسّع القصر بحسن نيّة، أو غيّر `certify-run` شرطه ليقرأ فروعاً أخرى، سقط
اختبارٌ يقول له لماذا.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
CERTIFY = ROOT / ".github/workflows/certify-run.yml"


def _on(path: Path) -> dict:
    """`on` يُحلّله PyYAML مفتاحاً منطقيّاً `True` — وهو فخّ YAML 1.1 المعروف."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("on", doc.get(True)) or {}


def test_push_runs_are_restricted_to_main():
    on = _on(CI)
    assert isinstance(on, dict), "الشكل المختصر `on: [push, pull_request]` يُعيد التكرار"
    assert "pull_request" in on, "فروع الشرائح تُغطّى بتشغيل الـPR — وهو ما يبرّر القصر"
    assert (on.get("push") or {}).get("branches") == ["main"], (
        "تشغيل push على غير main يُنشئ نسخةً ثانية من ٦٨ فحصاً لا تُلغى، "
        "وأيّ إلغاءٍ لها يكتب نتيجةً أحدثَ تعلو على خضرة تشغيل الـPR فتحجبه"
    )


def test_the_only_consumer_of_push_runs_still_asks_for_main_only():
    """القصر مبنيٌّ على شرطٍ في ملفٍّ آخر — فيُقاس، لا يُفترَض بقاؤه.

    هذا هو الفرق بين تعليقٍ يشرح قراراً وبين عقدٍ يحرسه: لو خُفِّف شرط `certify-run`
    ليقرأ فروعاً غير main، صار القصر يُسقِط مستهلِكاً حقيقيّاً — وهذا الاختبار يُحمِرّ
    قبل أن يحدث ذلك صامتاً.
    """
    certify = CERTIFY.read_text(encoding="utf-8")
    assert "workflow_run.event == 'push'" in certify
    assert "workflow_run.head_branch == 'main'" in certify, (
        "لو صار الاعتماد يقرأ فروعاً أخرى فقصرُ push على main يُسقِط مستهلِكاً"
    )


def test_pull_request_runs_still_cancel_the_stale_one():
    """القصر يُزيل التكرار؛ ولا يجوز أن يُزيل معه إلغاءَ الجولة البائتة.

    دفعةٌ فوق دفعةٍ على PR تُلغي الأقدم — قياسُها لا يعني شيئاً بعد أن تجاوزها الرأس.
    """
    doc = yaml.safe_load(CI.read_text(encoding="utf-8")) or {}
    conc = doc.get("concurrency") or {}
    assert "pull_request" in str(conc.get("cancel-in-progress", "")), (
        "إلغاء الجولة البائتة على الـPR شرطٌ قائم — لا يسقط مع هذا التغيير"
    )
    assert "run_id" in str(conc.get("group", "")), (
        "تشغيلات main تبقى بمجموعةٍ فريدة فلا تُلغى: لكلّ التزامٍ سجلُّه المُعتمَد"
    )
