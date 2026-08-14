"""وظيفةُ «Production Closure» تُعلِن حدّ ادّعائها في ملخّص جولتها.

`CI-JOB-NAME-CLAIMS-MORE-THAN-IT-MEASURES-01`. اسم الوظيفة يقول «إغلاق الإنتاج»،
والمقيس فيها **عقودٌ ساكنة** لا غير: تحقّق أنواع، وبناء واجهة، وميزانية حزمة،
وبوّابات نصّيّة، واختبارات حرّاس. ولا بيئة حيّة في أيّ خطوة — لا قاعدة، ولا وسيط،
ولا واجهة منشورة، ولا طلبٌ واحد إلى خدمةٍ تعمل.

**والفارق ليس تسميةً:** «العقود متماسكة» و«النظام يعمل» جوابان عن سؤالين، وأخضرٌ
واحد يحملهما معاً هو **خضرةٌ عن سؤالٍ لم يُطرَح** — الصنف المتكرّر في هذا المستودع.
والعلاج المُتاح بلا بيئة حيّة أن **تقول الجولة ما قاسته وما لم تقِسه**، في ملخّصها
نفسه لا في وثيقةٍ جانبيّة يقرؤها من يبحث أصلاً.

**ولماذا يُحرَس هذا باختبار:** حدٌّ مكتوب في YAML يُحذَف بسطرٍ واحد ولا يُحمِرّ شيء —
فيعود الاسم يدّعي وحده. وهذه أرخص طريقة لفقدان الحدّ: لا أحد يقصدها.

**وحدّ هذا الاختبار نفسه:** يقيس أنّ الحدّ **مكتوبٌ ومربوط**، لا أنّ نصّه صادق —
صدقُه يُقاس بقراءة الخطوات، وهي مُعدَّدة هنا كي يُلاحَظ اختلافُها إن تغيّرت.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_WF = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "field-workspace-production-closure.yml"
)
_TEXT = _WF.read_text(encoding="utf-8")


def test_the_workflow_writes_a_claim_boundary_to_the_run_summary() -> None:
    assert "GITHUB_STEP_SUMMARY" in _TEXT, "لا ملخّص ⇒ الحدّ لا يبلغ قارئ الجولة"
    assert "CONTRACT_CLOSURE_ONLY" in _TEXT, "لا وسم يفصل إغلاق العقود عن إغلاق الإنتاج"


def test_the_boundary_names_what_is_not_measured_not_only_what_is() -> None:
    """«قِستُ كذا» بلا «ولم أقِس كذا» تُقرأ تغطيةً كاملة — وهي الصيغة المعطوبة."""
    for absent in ("لا قاعدة بيانات حيّة", "لا وسيط", "لا واجهة منشورة"):
        assert absent in _TEXT, f"الحدّ لا يذكر: {absent}"
    assert "runtime_verified" in _TEXT and "production_certified" in _TEXT, (
        "الحدّ لا يقول إنّ شهادتَي التشغيل لا تتحرّكان بهذه الجولة"
    )


def test_the_boundary_is_written_on_failure_too() -> None:
    """حدٌّ يظهر عند النجاح وحده يُقرأ تهنئةً — وأوان الحاجة إليه الفشل."""
    summary_step = _TEXT.split("Claim boundary", 1)[1]
    assert "if: always()" in summary_step.split("run:", 1)[0], "الحدّ مشروطٌ بالنجاح"


def test_the_job_declares_least_privilege_and_a_ceiling() -> None:
    """سعةٌ لا تُستعمَل تبقى سطحاً قائماً، ووظيفةٌ بلا سقف تُعلَّق ستّ ساعات."""
    assert "permissions:" in _TEXT and "contents: read" in _TEXT
    assert "timeout-minutes:" in _TEXT
    assert "concurrency:" in _TEXT


def test_superseded_runs_are_cancelled_only_on_pull_requests() -> None:
    """على main يبقى لكلّ التزامٍ مدموج سجلٌّ خاصّ به — وإلغاؤه يُفقِد دليلاً هبط فعلاً."""
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in _TEXT


def test_the_boundary_did_not_replace_any_measured_step() -> None:
    """حدُّ الادّعاء يُضاف ولا يُقايَض: وثيقةٌ أصدق مع فحصٍ أقلّ صفقةٌ خاسرة.

    وخمس بوّابات وخمسة اختبارات حرّاس تقرأ نصّ هذا الملفّ وتشترط حضور أسمائها فيه،
    فحذفُ خطوةٍ هنا يُحمِرّ هناك — لكنّ الاعتماد على ذلك وحده يترك الواجهة بلا مرساة.
    """
    for step in (
        "npm run typecheck:field-workspace-contract",
        "npm run build",
        "npm run verify:bundle-budget",
        "field_workspace_production_closure_gate.py",
        "edge_inference_service_contract_gate.py",
        "weather_service_real_contract_gate.py",
        "decision_sor_cutover_readiness_gate.py",
        "decision_sor_shadow_promotion_gate.py",
        "decision_sor_staging_probe_gate.py",
        "decision_sor_final_certification_gate.py",
    ):
        assert step in _TEXT, f"خطوةٌ مقيسة اختفت: {step}"


def test_npm_ci_stays_deterministic_and_scriptless() -> None:
    """مرساةٌ ثانية لـ`frontend_reproducibility_guard`: الرايات الثلاث تُقاس هنا أيضاً.

    الحارس يعدّ التثبيتات عبر ملفَّين ويشترط ثلاثاً — فحذفُ التثبيت من هنا يُحمِرّه
    برسالة عدد، وهذه تقول أيّ راية سقطت.
    """
    for flag in ("--ignore-scripts", "--no-audit", "--no-fund"):
        assert flag in _TEXT, f"npm ci بلا {flag}"
    assert "npm install" not in _TEXT, "npm install غير حتميّ"
