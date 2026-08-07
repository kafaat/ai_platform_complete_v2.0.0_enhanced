"""`TEST-PROBE-LEAKS-INTO-THE-TREE-01` — مِسبار اختبار تسرّب فأنتج تشخيصاً خاطئاً.

**الحادثة، لا فرضيّة.** تقرير اعتماد خارجيّ (SAHOOL v22) أصدر **NO-GO** وعزا **١٩
إخفاقاً** إلى «تغيير غير محكوم أضاف `GET /api/probe-newservice/readyz` في
`compat_gateway.py:145`». وأوصى بحذف المسار أو تقنينه بصلاحية.

**المسار لم يدخل المستودع قطّ** — `git log --all -S` يُعطي التزاماً واحداً، وهو
التزام الاختبار الذي يُعرّف المِسبار. أي أنّ ساعاتٍ من التحليل ذهبت إلى مسارٍ لا وجود
له، والعلاج الموصى به كان سيُحوّل مِسبار اختبار إلى **عقد دائم** في قائمة المسارات
العامّة.

فالتسريب أخطر من شجرة متّسخة: **يُنتج تشخيصاً واثقاً وخاطئاً**. والفشل الصاخب أرحم.

**العلاج شطران، وكلاهما مُختبَر هنا:**
  ① المِسبار في ملفّ **غير متعقَّب** ⇒ لا يُعدَّل مصدر حقيقيّ أبداً.
  ② كاشفٌ يُسمّي ما يبقى (الجرود المولَّدة) بسطر واحد وعلاجه.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "probe_leak_guard.py"
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

from probe_leak_guard import PROBE_MARKERS, leaks  # noqa: E402

_VERSIONING_TEST = _ROOT / "tests_v9" / "test_api_versioning_policy_guard.py"
_ROUTERS = _ROOT / "services" / "sahool-platform" / "api" / "routers"


def _run() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GUARD)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONIOENCODING": "utf-8", "PATH": "/usr/bin:/bin"},
        cwd=_ROOT,
        timeout=180,
    )


def test_the_tree_is_clean_right_now():
    """إنفاذ على الشجرة الحيّة — لا على نموذج."""
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_leaked_probe_module_is_caught(tmp_path):
    """ملفّ المِسبار المؤقّت وحده كافٍ للإدانة — وجوده يعني اختباراً قُوطِع."""
    leaked = _ROUTERS / "_probe_unadjudicated_route.py"
    assert not leaked.exists(), "الشجرة متّسخة قبل الاختبار"
    leaked.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n", encoding="utf-8")
    try:
        found = leaks()
        assert any("_probe_unadjudicated_route" in line for line in found)
    finally:
        leaked.unlink(missing_ok=True)
    assert not leaks(), "الاستعادة يجب أن تُعيد الحارس أخضر"


def test_a_probe_marker_in_a_generated_inventory_is_caught(tmp_path):
    """الجرد المولَّد هو ما يبقى منحرفاً بعد المقاطعة — فهو داخل النطاق.

    **يُقاس على مستودع مؤقّت، لا على الجرد الحيّ.** أوّل صياغة كتبت الرمز في
    `api_versioning_inventory.csv` المتعقَّب ثمّ «استعادته» بـ`write_text` — و
    `read_text` يُترجم `\r\n` إلى `\n`، فعادت الاستعادة بمحتوى مطابق ونهايات أسطر
    مختلفة، ففشلت جزئة الملفّ في `validate_release_package` وأسقطت CI.

    أي أنّ اختبار الحارس وقع في **الصنف الذي بُني الحارس لمنعه**. أمسكته CI لا أنا.
    """
    repo = tmp_path / "r"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, capture_output=True)
    inventory = repo / "sub" / "inventory.csv"
    inventory.write_text("GET,/api/probe-newservice/readyz,x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    found = leaks(root=repo)
    assert any("inventory.csv" in line for line in found), found
    assert not leaks(), "الشجرة الحيّة لم تُمَسّ"


def test_the_guard_does_not_fire_on_the_places_that_legitimately_name_the_probe():
    """**الحدّ الذي يُبقي الحارس حيّاً.**

    رموز المِسبار تظهر شرعيّاً في أربعة مواضع: الاختبار الذي يُعرّفها، وخريطة
    القدرات التي تفهرسه، والدماغ الذي يشرح الحادثة، **وكتالوج الدروس**. حارسٌ يُطلِق
    على توثيق ما يمنعه يُعطَّل في أوّل يوم — وهو عطل تكرّر في هذا المستودع أكثر من مرّة.

    والموضع الرابع لم يكن استباقاً: `#802` أضاف درس «عودة مسار probe-newservice
    المحظور» إلى `docs/runbooks/`، فأطلق الحارس على السرد وصار `main` **أحمر على
    بوّابته الحاجبة نفسها** وعلى `test_the_tree_is_clean_right_now`. أي أنّ التحذير
    المكتوب في docstring الحارس وقع عليه هو.
    """
    assert "probe-newservice" in _VERSIONING_TEST.read_text(encoding="utf-8")
    mapping = _ROOT / "docs" / "capability-registry" / "generated" / "mapping"
    assert any(
        "probe-newservice" in p.read_text(encoding="utf-8", errors="ignore")
        for p in mapping.glob("*.json")
    ), "الخريطة تذكر المِسبار — والحارس لا يُطلِق"
    runbook = _ROOT / "docs" / "runbooks" / "CI_GATES_AND_PRE_PUSH_PROTOCOL.md"
    assert "probe-newservice" in runbook.read_text(encoding="utf-8"), (
        "درس الحادثة اختفى من كتالوج الدروس — الاستثناء صار بلا مُبرّر فيجب نزعه"
    )
    assert not leaks(), "المواضع الشرعيّة يجب ألّا تُدين"


def test_the_documentation_exemption_does_not_blind_the_guard_to_a_real_leak(tmp_path):
    """**تكذيب الاستثناء نفسه.** استثناءٌ يُسكِت الحارس عن تسريبٍ حقيقيّ لا يجوز.

    يُقاس على مستودع مؤقّت: الرمز نفسه في سردٍ تحت `docs/runbooks/` **يمرّ**، وفي
    مصدرٍ تحت `services/` **يُدان** — في الشجرة ذاتها وبالرمز ذاته. فالاستثناء مقصور
    على السرد ولا يتمدّد.
    """
    repo = tmp_path / "r"
    (repo / "docs" / "runbooks").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, capture_output=True)
    (repo / "docs" / "runbooks" / "LESSON.md").write_text(
        "درس: عودة مسار /api/probe-newservice/readyz المحظور\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    assert leaks(root=repo) == [], "سردُ الدرس يجب أن يمرّ"

    (repo / "services").mkdir()
    (repo / "services" / "gateway.py").write_text(
        '@router.get("/api/probe-newservice/readyz")\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    found = leaks(root=repo)
    assert any("gateway.py" in line for line in found), found
    assert not any("LESSON.md" in line for line in found), found


def test_every_marker_the_tests_inject_is_declared():
    """قائمة الرموز تُشتقّ من الواقع: كلّ مسار `probe-`/`decoy-`/`ghost-` يحقنه
    الاختبار يجب أن يكون معلوماً للحارس، وإلّا تسرّب صنفٌ منه بلا كاشف."""
    import re

    source = _VERSIONING_TEST.read_text(encoding="utf-8")
    injected = set(re.findall(r"/api/((?:probe|decoy|ghost)-[a-z0-9-]+)/", source))
    missing = [name for name in injected if not any(m in name for m in PROBE_MARKERS)]
    assert not missing, "رموز مِسبار تحقنها الاختبارات ولا يعرفها الحارس: " + " · ".join(missing)


def test_the_versioning_tests_no_longer_edit_a_tracked_source():
    """**الشطر الأوّل من العلاج، مقيساً على المصدر.**

    قبل الإصلاح كان الاختباران يكتبان في `compat_gateway.py` المتعقَّب. الآن يكتبان
    في ملفّ غير متعقَّب. الفحص على الأسطر التنفيذيّة لا على الملفّ كلّه — التعليق
    يشرح الحادثة ويذكر اسم الملفّ عمداً.
    """
    import ast

    tree = ast.parse(_VERSIONING_TEST.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "compat_gateway.py" not in code, "الاختبار ما زال يمسّ مصدراً متعقَّباً"
