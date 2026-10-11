"""كلُّ مسارٍ يعمل على الـPR يلغي تشغيلَه الأقدم للـPR نفسه — ولا يلغي شيئاً خارج الـPR.

**لماذا:** قياسُ 2026-10-05: دفعٌ واحد إلى PR يُطلق 31–32 مساراً و64–68 وظيفة، و45 من 50 مساراً
على الـPR بلا ``concurrency``. فكلُّ دفعٍ جديد يترك تشغيلات الدفع السابق تشغل أجهزةَ GitHub المحدودة
بحدّ تزامن الخطّة، حتّى صار الطابورُ عميقاً وأُلغيت وظائفُ بـ«not acquired by Runner».

**الشكلُ المفروض** (نفسُ ما في ci.yml منذ قبل): المجموعةُ على الـPR تحمل اسمَ المسار ورقمَ الـPR،
و``cancel-in-progress`` صحيحٌ على الـPR وحده؛ ولغير الـPR (push إلى main، جدولة، تشغيلٌ يدويّ)
مجموعةٌ فريدة بـ``run_id`` فلا يُلغى دمجٌ ولا يُسلسَل — كلُّ commit على main يُفحص كاملاً.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _events(doc: dict) -> set[str]:
    on = doc.get(True, doc.get("on")) or {}
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    return set(on)


def _pr_workflows() -> list[Path]:
    paths = sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))
    return [p for p in paths if "pull_request" in _events(_load(p))]


#: تصاميمُ سبقت هذا التغيير وتُزيل التكرارَ لكلّ PR فعلاً (المجموعةُ تحمل ``github.ref`` أو رقمَ الـPR)،
#: لكنّ ثلاثةً منها تلغي أيضاً تشغيلاتِ main المتتالية (``cancel-in-progress: true`` ثابت). لم تُمَسّ هنا:
#: تغييرُ دلالتها قرارٌ مستقلّ. والقائمةُ مغلقة — مسارٌ جديد يأخذ الشكلَ القياسيّ لا هذه الاستثناءات.
PREEXISTING = {
    "field-workspace-production-closure.yml",
    "railway-dockerfile-pr-build.yml",
    "sahool-production-gates.yml",
    "secret-history-scan.yml",
}


def test_the_preexisting_designs_still_deduplicate_per_pull_request():
    for name in sorted(PREEXISTING):
        conc = _load(WORKFLOWS / name).get("concurrency")
        assert isinstance(conc, dict), name
        group = str(conc["group"])
        assert "github.ref" in group or "github.event.pull_request.number" in group, name
        assert str(conc["cancel-in-progress"]).replace(" ", "") in (
            "True",
            "${{github.event_name=='pull_request'}}",
        ), name


def test_there_are_pull_request_workflows_to_check():
    assert len(_pr_workflows()) >= 40, "الاكتشافُ لم يجد المسارات — الشاهدُ فارغ"


@pytest.mark.parametrize(
    "path", [p for p in _pr_workflows() if p.name not in PREEXISTING], ids=lambda p: p.name
)
def test_a_pull_request_workflow_cancels_only_its_own_superseded_pr_runs(path: Path):
    conc = _load(path).get("concurrency")
    assert isinstance(conc, dict), f"{path.name}: لا concurrency على مستوى المسار"
    group, cancel = str(conc.get("group", "")), str(conc.get("cancel-in-progress", ""))
    # الإلغاءُ مشروطٌ بحدث الـPR — قيمةٌ ثابتة true كانت ستلغي تشغيلات main المتتالية
    assert cancel.replace(" ", "") == "${{github.event_name=='pull_request'}}", (
        f"{path.name}: cancel-in-progress={cancel!r}"
    )
    assert "github.event.pull_request.number" in group, f"{path.name}: المجموعة لا تخصّ الـPR"
    # ولغير الـPR مجموعةٌ فريدة لكلّ تشغيل
    assert "github.run_id" in group, f"{path.name}: لغير الـPR مجموعةٌ مشتركة تُسلسِل أو تُلغي"
    # ومسارٌ آخر لا يشارك المجموعة (ci.yml يحمل بادئةً ثابتة خاصّةً به)
    assert "github.workflow" in group or "'ci-pr-" in group, f"{path.name}: المجموعة بلا اسم المسار"
