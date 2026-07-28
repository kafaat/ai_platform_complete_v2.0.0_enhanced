"""حارس ``GENERATED-ARTIFACT-SWEEP-01``: مكنسة المصنوعات تكتشف ما ينفّذه CI فعلاً.

قيمة الأداة كلّها في **اكتمال** القائمة. قائمة مكتوبة يدويّاً تبيت عند إضافة مولّد
جديد، فتُعيد إنتاج العيب داخل الأداة التي تعالجه — ولذلك تُكتشَف من الـworkflows.
هذه الاختبارات تحرس ذلك الاكتشاف نفسه:

  * لا خطوة `--check` في أيّ workflow خارج ما تكتشفه الأداة (وإلّا عادت الانتقائيّة).
  * كلّ ما تكتشفه سكربت موجود فعلاً (لا أسماء بائتة تُعطي طمأنينة كاذبة).
  * المطابقة **مقصورة على السطر** — أوّل نسخة عبرت الأسطر فابتلعت كتلة YAML وأنتجت
    «خطوة» وهميّة تمرّ خضراء بلا تنفيذ شيء. هذا الحارس يمنع عودته.
  * الترتيب حقيقة تبعيّة: ما يبصم غيره يأتي بعده.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "ci" / "verify_all_generated.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_all_generated", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def test_every_check_step_in_the_workflows_is_discovered():
    """الثابت الجوهريّ: لا خطوة فحص خارج المكنسة."""
    discovered = {script for script, _args in MOD.discover()}
    pattern = re.compile(
        r"python[ \t]+(scripts/(?:ci|architecture|release)/[a-z_0-9]+\.py)"
        r"[^\n|&]*?--check[a-z-]*"
    )
    in_workflows = set()
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        in_workflows.update(pattern.findall(wf.read_text(encoding="utf-8")))

    missing = in_workflows - discovered
    assert not missing, f"خطوات فحص لا تكتشفها المكنسة: {sorted(missing)}"


def test_discovery_finds_a_substantial_set_not_a_handful():
    """أرضيّة تمنع انهياراً صامتاً للتعبير النمطيّ إلى نتيجة شبه فارغة."""
    assert len(MOD.discover()) >= 40


def test_every_discovered_script_exists_on_disk():
    """اسم بائت يُعطي طمأنينة كاذبة — يُمسَك هنا لا في CI."""
    for script, _args in MOD.discover():
        assert (ROOT / script).is_file(), f"سكربت مكتشَف غير موجود: {script}"


def test_no_discovered_step_swallowed_a_yaml_block():
    """المطابقة مقصورة على السطر: لا وسيط يحمل مسافة بيضاء عبر الأسطر.

    الانحدار الملموس: `\\s` بدل `[ \\t]` جعل المطابقة تعبر الأسطر فابتلعت كتلة YAML
    كاملة كـ«وسائط»، فصارت الخطوة تمرّ خضراء بلا تنفيذ شيء.
    """
    for script, args in MOD.discover():
        for arg in args:
            assert "\n" not in arg, f"وسيط يعبر الأسطر في {script}: {arg!r}"
        assert len(args) <= 4, f"وسائط كثيرة على نحو مريب في {script}: {args}"


def test_fingerprinting_steps_are_ordered_after_the_generators():
    """`static_governance_closure` يبصم مخرجات المولّدات ⇒ يجب أن يليها."""
    ordered = sorted(MOD.discover(), key=MOD._sort_key)
    names = [Path(script).name for script, _ in ordered]
    late = names.index("static_governance_closure.py")
    generators = [n for n in names[:late] if n in MOD._GENERATE_FLAG]
    assert generators, "لا مولّد قبل خطوة البصم — الترتيب انقلب"
    assert "static_governance_closure.py" not in names[:late]


def test_release_bundle_is_rebuilt_only_when_validation_fails():
    """البناء يكتب طابعاً زمنيّاً جديداً؛ بناؤه بلا داعٍ يُوسّخ الشجرة بفرق بلا محتوى."""
    source = _SCRIPT.read_text(encoding="utf-8")
    build_at = source.index("_run([_RELEASE_BUILD])")
    guard_at = source.index("if _run([_RELEASE_VALIDATE])[0] != 0:")
    assert guard_at < build_at, "بناء الحزمة غير مشروط بفشل التحقّق"


def test_unknown_steps_are_reported_not_skipped():
    """صدق: ما لا تعرف الأداة توليده يُبلَّغ كيدويّ — لا يُقرأ النجاح كتغطية غير مملوكة."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "manual.append(script)" in source
    assert "ولا تُولَّد آليّاً" in source
