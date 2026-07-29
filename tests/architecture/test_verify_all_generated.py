"""حارس ``GENERATED-ARTIFACT-SWEEP-01``: مكنسة المصنوعات تكتشف ما ينفّذه CI فعلاً.

قيمة الأداة كلّها في **اكتمال** القائمة. قائمة مكتوبة يدويّاً تبيت عند إضافة مولّد
جديد، فتُعيد إنتاج العيب داخل الأداة التي تعالجه — ولذلك تُكتشَف من الـworkflows.
هذه الاختبارات تحرس ذلك الاكتشاف نفسه:

  * لا خطوة `--check` في أيّ workflow خارج ما تكتشفه الأداة (وإلّا عادت الانتقائيّة).
  * كلّ ما تكتشفه سكربت موجود فعلاً (لا أسماء بائتة تُعطي طمأنينة كاذبة).
  * المطابقة **مقصورة على السطر** — أوّل نسخة عبرت الأسطر فابتلعت كتلة YAML وأنتجت
    «خطوة» وهميّة تمرّ خضراء بلا تنفيذ شيء. هذا الحارس يمنع عودته.
  * الترتيب حقيقة تبعيّة: ما يبصم غيره يأتي بعده.

وللاكتشاف حدّ بحدّ تعريفه: مولّد لا يذكره أيّ workflow خارج المدى تماماً. تلك الزاوية
تُغلَق بأساس تصنيف مُلتزَم، وهذه الاختبارات تحرسه كما تحرس الاكتشاف: لا مولّد بلا تصنيف،
ولا مدخل بلا دليل وشرط إغلاق، ولا نموّ صامت للأساس.
"""

from __future__ import annotations

import importlib.util
import json
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


# ── الزاوية العمياء: مولّد لا يذكره أيّ workflow ──────────────────────────────

_BASELINE = ROOT / "docs" / "architecture" / "generated_chain_known_drift.json"

# سقف راتشِت لا هدف: الأساس يتقلّص بإغلاق الأسباب. رفعه لتمرير CI يُبطل معناه.
# نزل 4 ⇒ 1 بإغلاق RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01 (2026-07-29):
# الأثر صار يسجّل قدرةً لا هويّة آلة، فخرج من المنحرفين. بقي capability_linker وحده.
_MAX_DRIFTING = 1


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["uncovered"]


def test_every_uncovered_generator_in_the_tree_is_classified():
    """الثابت: لا مولّد خارج كلّ workflow وخارج الأساس معاً — وإلّا اتّسع الثقب صامتاً."""
    assert not MOD.classify_uncovered()


def test_the_classifier_actually_finds_the_uncovered_set():
    """أرضيّة تمنع كشفاً منهاراً يمرّ خضراء بلا تصنيف شيء."""
    found = MOD.uncovered()
    # الأرضيّة نزلت 5 ⇒ 4 بإغلاق PATH3-READINESS-CLAIM-UNBACKED-01 (2026-07-29):
    # `compose_runtime_target_resolver` و`path3_runtime_readiness_closure` خرجا من
    # غير المُغطّى بإدراج اختباريهما. النزول **مكسوب** لا انهيار — والأرضيّة تُخفَّض
    # بسبب مكتوب لا لتمرير اختبار.
    # الأرضيّة 4 ⇒ 3: خرج runtime_environment_preflight من غير المُغطّى بإدراج
    # اختباره في capability-governance.yml. نزول **مكسوب** بسبب مكتوب.
    assert len(found) >= 3, f"كشف مُنهار: {found}"
    for script in found:
        assert (ROOT / script).is_file(), f"مصنَّف غير موجود: {script}"


def test_each_baseline_entry_carries_evidence_and_a_closing_condition():
    """«معروف» بلا سبب ودليل وشرط إغلاق ليس معرفةً بل قائمة تجاهُل."""
    for script, entry in _baseline().items():
        for field in (
            "drifts",
            "kind",
            "watcher",
            "why_the_watcher_is_silent",
            "evidence",
            "why_not_regenerate",
            "to_close",
            "check_flag",
        ):
            assert field in entry, f"{script}: ينقصه {field}"
        assert isinstance(entry["drifts"], bool), f"{script}: drifts ليس منطقيّاً"
        for field in ("evidence", "why_the_watcher_is_silent", "to_close"):
            assert len(entry[field].strip()) >= 30, f"{script}: {field} أقصر من أن يكون تفسيراً"
        assert entry["check_flag"].startswith("--check"), f"{script}: علم فحص غير مُصرَّح"


def test_the_baseline_never_silently_grows():
    """راتشِت: عدد المنحرفين لا يتجاوز السقف المُثبَّت — يُخفَض بالإغلاق لا يُرفَع بالتمرير."""
    drifting = [s for s, e in _baseline().items() if e["drifts"]]
    assert len(drifting) <= _MAX_DRIFTING, f"نما الأساس: {sorted(drifting)}"


def test_a_silent_watcher_is_named_not_hidden():
    """قيمة المدخل في تسمية **سبب** الصمت: حارس غائب أو غير مجموع أو غير موسوم."""
    for script, entry in _baseline().items():
        watcher = entry["watcher"]
        reason = entry["why_the_watcher_is_silent"]
        if watcher is None:
            assert "لا حارس" in reason, f"{script}: بلا حارس وبلا تصريح بذلك"
        else:
            assert (ROOT / watcher).is_file(), f"{script}: حارس مُعلَن غير موجود — {watcher}"


def test_the_default_sweep_does_not_execute_the_uncovered_generators():
    """أكثرها يكتب ملفّات متعقَّبة أثناء --check؛ تشغيلها افتراضيّاً يُوسّخ شجرة المستخدم."""
    source = _SCRIPT.read_text(encoding="utf-8")
    body = source[source.index("def main()") :]
    assert "if args.uncovered:" in body, "التنفيذ غير مشروط بعلم صريح"
    assert body.index("classify_uncovered()") < body.index("if args.uncovered:")


def test_a_guard_that_repairs_during_check_is_caught_not_trusted():
    """`CHECK-STEPS-MUTATE-THE-TREE-01` صار **مُنفَذاً** لا مُسجَّلاً فقط.

    ستّة حرّاس يكتبون في وضع «فحص فقط»: يُصلحون الانحراف صامتاً ويُعيدون صفراً.
    مُثبَت على المكنسة نفسها قبل هذا التعديل: إفساد ``service_inventory.csv`` ثمّ
    الفحص ⇒ اختفى الإفساد وأُعلنت السلامة. فالاعتماد على رموز الخروج أخضر كاذب.

    الحدّ الصادق هنا: حالة الشجرة قبل الفحص = حالتها بعده — إشارة لا يملك الحارس
    تزييفها لأنّها ليست مخرَجه.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("v", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "tree_state"), "أُزيلت إشارة حالة الشجرة — يعود الأخضر الكاذب"
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "before = tree_state()" in body and "after = tree_state()" in body, (
        "الإشارة معرَّفة ولا تُستدعى حول الفحص — وجودها بلا استدعاء لا يحرس شيئاً"
    )
    # وتُقاس على المتتبَّع فقط: ملفّ جديد غير مُدرَج ليس كتابةَ حارس.
    assert "--untracked-files=no" in body


def test_generators_no_workflow_mentions_are_reported_not_hidden():
    """حدّ الاكتشاف مُعلَن: ما لا يذكره workflow لا تراه المكنسة.

    الاكتشاف من الـworkflows يرى ما يُشغّله CI بدقّة، ويعمى عمّا **نسيه**. والقياس
    يقول إنّ ذلك ليس نظريّاً: أربعة مولِّدات خارج كلّ workflow، ثلاثة منها منحرفة
    على ``main`` — وفيها `PATH3-READINESS-CLAIM-UNBACKED-01`.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("v", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    blind = mod.unreferenced_generators()
    # كان التوقّع على `path3_runtime_readiness_closure`؛ أُغلِق سببه
    # (PATH3-READINESS-CLAIM-UNBACKED-01) وأُدرِج اختباره، فحُدِّث التوقّع بوعي بدل
    # حذفه — الكشف نفسه ما زال مطلوباً، والعيّنة تغيّرت لا القاعدة.
    assert "scripts/ci/runtime_environment_preflight.py" in blind, (
        "إمّا صار مذكوراً في workflow — فاحذف هذا التوقّع بوعي — أو كُسر الكشف"
    )
    for script in blind:
        assert (ROOT / script).exists()
