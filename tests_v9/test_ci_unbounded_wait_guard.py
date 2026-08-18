"""القاعدتان لـ`CI-UNBOUNDED-PROVISIONING-WAIT-01` — كلٌّ مُكذَّبةٌ وحدها.

قِيس في تشغيل 32073296568 أنّ `Integration Tests` علقت 112 دقيقة ثمّ بقيت معلَّقة،
والحصرُ يضع التعليق داخل `apt-get`: السحب اكتمل ومعرّفا الحاويتين طُبِعا، ولم يظهر
سطرُ جاهزيّةٍ واحد — والحلقة مسقوفة فلا تُفسّره.

**ولماذا حالتان لا واحدة:** القاعدتان تسقطان لأسبابٍ مختلفة وتُصلَح كلٌّ وحدها.
اختبارٌ يجمعهما كان سيمرّ على نكوصِ إحداهما ما دامت الأخرى قائمة — وهو صنف
«حارسٌ يُبلِغ عن سؤالٍ لم يطرحه».

يُنسَخ `.github/workflows` إلى مستودعٍ اصطناعيّ ويُزرَع العطل فيه، فلا تُمَسّ الشجرة
القانونيّة ولا يُقاس الحارسُ بشجرةٍ أُصلِحت سلفاً.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/ci/ci_unbounded_wait_guard.py"
spec = importlib.util.spec_from_file_location("ci_unbounded_wait_guard", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def _sandbox(tmp_path, monkeypatch):
    dst = tmp_path / ".github/workflows"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / ".github/workflows", dst)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "WORKFLOWS", dst)
    return dst


def test_the_current_tree_has_no_unbounded_provisioning_wait():
    assert mod.findings() == []


def test_an_unbounded_apt_get_is_blocked(tmp_path, monkeypatch):
    """يُزرَع الشكل الذي كان قائماً قبل `#868` حرفيّاً — لا شكلاً مصطنعاً."""
    wf = _sandbox(tmp_path, monkeypatch) / "ci.yml"
    wf.write_text(
        wf.read_text(encoding="utf-8").replace(
            "sudo timeout -k 10 240 apt-get update -qq "
            "&& sudo timeout -k 10 240 apt-get install -y -qq postgresql-client && break",
            "sudo apt-get update -qq && sudo apt-get install -y -qq postgresql-client && break",
            1,
        ),
        encoding="utf-8",
    )
    assert any("apt-get بلا `timeout`" in x for x in mod.findings()), mod.findings()


def test_a_db_job_without_a_job_timeout_is_blocked(tmp_path, monkeypatch):
    wf = _sandbox(tmp_path, monkeypatch) / "ci.yml"
    text = wf.read_text(encoding="utf-8")
    marker = (
        "  integration-tests:\n"
        "    name: Integration Tests\n"
        "    runs-on: ubuntu-24.04\n"
        "    # سقف صارم: المدّة الطبيعيّة دقائق قليلة؛ "
        "بلاه يحترق runner ستّ ساعات على أيّ تجمّد (مقيس).\n"
        "    timeout-minutes: 30\n"
    )
    assert marker in text, "المرساة انحرفت — أعد قراءة ترويسة الوظيفة"
    wf.write_text(
        text.replace(
            marker,
            "  integration-tests:\n    name: Integration Tests\n    runs-on: ubuntu-24.04\n",
            1,
        ),
        encoding="utf-8",
    )
    assert any("بلا `timeout-minutes`" in x for x in mod.findings()), mod.findings()


def test_an_unreadable_workflow_fails_closed_instead_of_being_skipped(tmp_path, monkeypatch):
    wf = _sandbox(tmp_path, monkeypatch) / "ci.yml"
    wf.write_text("jobs: [ this is not: valid yaml", encoding="utf-8")
    assert any("تعذّرت قراءة الـYAML" in x for x in mod.findings()), (
        "وثيقةٌ لا تُقرأ تُخرِج وظائفها من القياس كلّه — و«لم يُقَس» ليس «مرّ»"
    )


def test_the_host_side_readiness_probe_is_deliberately_not_forbidden():
    """حدٌّ مُعلَن: القاعدة الثالثة حُذِفت لأنّ القياس كذّبها، لا لأنّها نُسيت.

    فرضتُ أوّلاً «اسأل الجاهزيّة داخل الحاوية»، فسقط التجهيز في تشغيل 32125050692:
    `pg_isready` عبر مقبس يونكس يقول «accepting connections» أثناء طور التهيئة —
    نقطةُ دخول صورة postgres تُشغّل خادماً مؤقّتاً ثمّ تُعيد تشغيله — فكسرت الحلقة
    وسقط الفحص النهائيّ. والاستجواب من المضيف عبر TCP هو المقياس الصحيح.

    هذا الاختبار يمنع إعادة القاعدة بحسن نيّة: من يُضيفها يجب أن يُبطِله عمداً،
    فيقرأ السبب قبل أن يُعيد العطل.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pg_isready -h localhost" in ci, "الاستجواب من المضيف هو العقد المقيس"
    assert mod.findings() == [], "الحارس لا يجوز أن يُدين الاستجواب من المضيف"
