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
# نزل 4 ⇒ 1 بإغلاق RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01، ثم 1 ⇒ 0
# بإغلاق capability_linker: --check صار نقيّاً ومتماثلاً وموصولاً بالـworkflow.
_MAX_DRIFTING = 0


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["uncovered"]


def test_every_uncovered_generator_in_the_tree_is_classified():
    """الثابت: لا مولّد خارج كلّ workflow وخارج الأساس معاً — وإلّا اتّسع الثقب صامتاً."""
    assert not MOD.classify_uncovered()


def test_the_uncovered_detector_catches_a_new_unwired_generator():
    """صفر غير مُغطّى نتيجة صحيحة؛ نحرس الكاشف بمسبار اصطناعي لا بأرضية تاريخية.

    فرض حد أدنى دائم لمولدات غير موصولة يحوّل الدين المغلق إلى شرط نجاح. بدل ذلك
    ننشئ سكربتًا مؤقتًا يعلن ``--check`` ولا يذكره أي workflow، ونثبت أن الاكتشاف
    يلتقطه، ثم نحذفه حتمياً.
    """
    probe = ROOT / "scripts" / "ci" / "_uncovered_detector_probe.py"
    assert not probe.exists()
    probe.write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--check", action="store_true")\n',
        encoding="utf-8",
    )
    try:
        found = MOD.uncovered()
        assert "scripts/ci/_uncovered_detector_probe.py" in found
    finally:
        probe.unlink(missing_ok=True)

    assert MOD.uncovered() == [], "الشجرة الملتزمة يجب أن تبقى بلا مولدات غير موصولة"


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


def test_a_guard_that_mutates_during_check_is_still_caught_as_defense_in_depth():
    """The sweep retains a repository-state backstop even after the six guards became pure.

    Individual regression tests now prove their owned outputs are immutable during
    ``--check``.  The outer tree-state comparison remains defense in depth for a future
    guard that violates the same contract.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("v", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "tree_state")
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "before = tree_state()" in body and "after = tree_state()" in body
    assert "--untracked-files=no" in body


def test_generators_no_workflow_mentions_are_reported_not_hidden():
    """الصفر حالة صحيّة؛ نحرس كاشف مولّدات الكتابة بمسبار غير موصول.

    لا ينبغي إبقاء سكربت معروف خارج workflow كي يظل الاختبار أخضر. ننشئ مولّدًا
    مؤقتًا يعلن علم كتابة ولا نذكره في أي workflow، ونثبت أن الكاشف يراه، ثم نحذفه.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("v", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    probe = ROOT / "scripts" / "ci" / "_unreferenced_generator_probe.py"
    assert not probe.exists()
    probe.write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--generate", action="store_true")\n',
        encoding="utf-8",
    )
    try:
        blind = mod.unreferenced_generators()
        assert "scripts/ci/_unreferenced_generator_probe.py" in blind
    finally:
        probe.unlink(missing_ok=True)

    assert mod.unreferenced_generators() == [], "كل مولّد كتابة ملتزم يجب أن يكون مذكورًا في workflow"


def test_regeneration_flags_match_the_generator_clis():
    """The sweep must call each writer through the flag it actually exposes."""
    assert MOD._GENERATE_FLAG["build_service_dependency_bundle.py"] == ""
    assert MOD._GENERATE_FLAG["capability_runtime_evidence.py"] == "--apply"
    assert MOD._GENERATE_FLAG["generate_indicator_artifacts.py"] == ""
    assert MOD._GENERATE_FLAG["generate_indicators_frontend_manifest.py"] == ""


def test_each_step_has_a_diagnosable_timeout(monkeypatch, tmp_path):
    """A hung guard fails by name instead of consuming the whole workflow silently."""
    probe = ROOT / "scripts" / "ci" / "_generated_sweep_timeout_probe.py"
    probe.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    monkeypatch.setattr(MOD, "STEP_TIMEOUT_SECONDS", 0.05)
    try:
        code, output = MOD._run([str(probe.relative_to(ROOT))])
    finally:
        probe.unlink(missing_ok=True)
    assert code == 124
    assert "TIMEOUT after" in output
    assert "_generated_sweep_timeout_probe.py" in output


def test_the_flag_map_is_interrogated_against_argparse_not_trusted():
    """خريطة أعلام التوليد تُفحَص وهي خضراء — لا بعد أن تفشل ثلاث دورات.

    ``VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01`` أُصلحت مداخله وأُضيف تشخيص
    يميّز «كاتب لم يُستدعَ» عن «دورة تبعيّة» — لكنّه يعمل داخل فرع عدم الاستقرار
    وحده. والخريطة يدويّة فستبيت ثانيةً. هنا تُستجوَب في الوضع الافتراضيّ.

    التكذيب بالاتّجاهات الأربعة، وكلٌّ منها عيب وقع فعلاً أو يمكن أن يقع:
    علم مُعلَن لا يقبله argparse · سكربت كاتب سقط من الخريطة · مدخل أساس ببائت ·
    مدخل أساس بعلم خاطئ.
    """
    steps = MOD.discover()
    assert MOD.flag_map_problems(steps) == [], "الخريطة الحاليّة لا تطابق السكربتات"

    saved = dict(MOD._GENERATE_FLAG)
    try:
        MOD._GENERATE_FLAG["capability_runtime_evidence.py"] = "--generate"
        problems = MOD.flag_map_problems(steps)
        assert any("capability_runtime_evidence.py" in p and "--apply" in p for p in problems), (
            f"علم مُعلَن غير مقبول لم يُرصَد: {problems}"
        )
    finally:
        MOD._GENERATE_FLAG.clear()
        MOD._GENERATE_FLAG.update(saved)

    saved = dict(MOD._GENERATE_FLAG)
    try:
        MOD._GENERATE_FLAG.pop("capability_linker.py")
        problems = MOD.flag_map_problems(steps)
        assert any("capability_linker.py" in p and "--apply" in p for p in problems), (
            f"سكربت كاتب غائب عن الخريطة لم يُرصَد: {problems}"
        )
    finally:
        MOD._GENERATE_FLAG.clear()
        MOD._GENERATE_FLAG.update(saved)


def test_the_unmapped_baseline_is_itself_held_to_the_truth(tmp_path):
    """الأساس ليس إعفاءً: مدخله يُقاس هو أيضاً، فلا يصير ملاذاً لادّعاء بائت."""
    steps = MOD.discover()
    real = json.loads(MOD.UNMAPPED_BASELINE.read_text(encoding="utf-8"))
    original = MOD.UNMAPPED_BASELINE
    try:
        stale = dict(real)
        stale["unmapped"] = {**real["unmapped"], "scripts/ci/_gone_forever.py": "--write"}
        path = tmp_path / "stale.json"
        path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        MOD.UNMAPPED_BASELINE = path
        assert any("_gone_forever.py" in p for p in MOD.flag_map_problems(steps)), (
            "مدخل بائت في الأساس لم يُرصَد"
        )

        # الهدف يُختار **من الأساس الحيّ** لا بالاسم: الصيغة السابقة ثبّتت
        # `report_index_guard.py`، فلمّا أُغلِق ذلك المدخل وخرج من الأساس صار المسبار
        # يفسد مدخلاً لا وجود له ⇒ لا شيء يُرصَد، وسقط الاختبار. وهذا سقوط **صحيح**:
        # أمسك بياتَ نفسه. الاختيار الحيّ يُبقيه صادقاً كلّما تقلّص الأساس.
        victim = next(iter(sorted(real["unmapped"])))
        opposite = "--generate" if real["unmapped"][victim] != "--generate" else "--write"
        wrong = dict(real)
        wrong["unmapped"] = {**real["unmapped"], victim: opposite}
        path2 = tmp_path / "wrong.json"
        path2.write_text(json.dumps(wrong, ensure_ascii=False), encoding="utf-8")
        MOD.UNMAPPED_BASELINE = path2
        assert any(victim in p for p in MOD.flag_map_problems(steps)), (
            f"علم خاطئ مُسجَّل في الأساس لم يُرصَد ({victim})"
        )
    finally:
        MOD.UNMAPPED_BASELINE = original


def test_the_source_scan_is_a_diagnostic_not_a_verdict():
    """يُثبِّت سبب وجود ``_accepted_flags`` بجانب ``_declared_write_flags``.

    مسح المصدر يعدّ أيّ سلسلة مقتبَسة علماً. أوضح شاهد: المكنسة نفسها — قاموسها
    يحوي نصوص الأعلام، فيتّهمها مسحُها بإعلانها جميعاً بينما ``argparse`` لا يقبل
    منها شيئاً. لو تساوى الاثنان يوماً لصار أحدهما زائداً؛ وهذا الاختبار هو ما
    يُبقي التمييز مقيساً بدل أن يكون رأياً في تعليق.
    """
    script = "scripts/ci/verify_all_generated.py"
    declared = set(MOD._declared_write_flags(script))
    accepted = MOD._accepted_flags(script)
    assert declared, "مسح المصدر لم يجد شيئاً — تغيّرت بنية الخريطة"
    assert not set(MOD.write_flags_of(declared & accepted)), (
        "المكنسة صارت تقبل علم كتابة فعليّاً — راجع الفرضيّة"
    )
    assert declared - accepted, "مسح المصدر لم يعد يُنتج إيجابيّة كاذبة هنا"


def test_a_generator_whose_only_write_flag_is_fix_is_not_invisible():
    """‏``--fix`` ثغرة مقيسة في مسح المصدر، لا احتمال نظريّ.

    نمط ``_WRITE_FLAG_DECL`` يطابق ``--write|--apply|--generate`` فقط. فمولّد علمه
    الوحيد ``--fix`` **لا يراه التشخيص إطلاقاً** — ولا حتّى بعد أن تفشل المكنسة في
    الاستقرار، وهي اللحظة الوحيدة التي يعمل فيها ذلك التشخيص. أي أنّ صنفاً كاملاً
    من الكُتّاب يسقط من التقرير الذي وُضع ليسمّي الكُتّاب الساقطين.

    ``write_flags_of`` يشمله، والاستجواب عبر ``argparse`` لا يعتمد على النمط أصلاً.
    """
    probe = ROOT / "scripts" / "ci" / "_fix_only_write_flag_probe.py"
    assert not probe.exists()
    probe.write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        'p.add_argument("--check", action="store_true")\n'
        'p.add_argument("--fix", action="store_true")\n'
        "p.parse_args()\n",
        encoding="utf-8",
    )
    try:
        relative = "scripts/ci/_fix_only_write_flag_probe.py"
        assert MOD._declared_write_flags(relative) == [], (
            "تغيّر نمط مسح المصدر — أعد قياس الفرضيّة بدل الاعتماد على هذا الاختبار"
        )
        assert MOD.write_flags_of(MOD._accepted_flags(relative)) == ["--fix"], (
            "الاستجواب لم يرَ --fix — الثغرة صارت مفتوحة في الاتّجاهين"
        )
    finally:
        probe.unlink(missing_ok=True)


def test_write_flag_families_are_matched_not_enumerated():
    """‏``GENERATED-SWEEP-WRITE-FLAG-FAMILY-BLIND-01`` — قائمة مغلقة تبيت بصمت.

    كانت أعلام الكتابة تُفحَص بعضويّة في سلسلة ثابتة، فغابت عنها عائلة ``--write-*``
    كاملةً: أربعة مولّدات تكتب بـ``--write-generated``/``--write-source`` بقيت **غير
    مرئيّة** للحارس الوقائيّ نفسه، فأعلن نظافةً بينما هي خارج الخريطة تماماً.

    والتناقض كان داخل الملفّ الواحد: ``_WRITE_FLAG_DECL`` يطابق ``--write-*`` بالبادئة،
    فالماسح المصدريّ يراها والمُستجوِب لا يراه. المعياران مُوحَّدان الآن.
    """
    assert MOD.write_flags_of({"--write-generated", "--check-generated"}) == ["--write-generated"]
    assert MOD.write_flags_of({"--write-source", "--check-source"}) == ["--write-source"]
    assert MOD.write_flags_of({"--generate-index"}) == ["--generate-index"]
    assert MOD.write_flags_of({"--apply"}) == ["--apply"]
    assert MOD.write_flags_of({"--fix"}) == ["--fix"]
    # لا يُصنَّف الفحص كتابةً — وإلّا صار كلّ حارس «مولّداً» والتقرير ضجيجاً
    assert MOD.write_flags_of({"--check", "--check-generated", "--json-output"}) == []


def test_a_step_written_across_continuation_lines_is_discovered():
    r"""‏``GENERATED-SWEEP-CONTINUATION-BLIND-01`` — ما لا يُكتشَف لا يُصنَّف.

    ``_STEP`` مقصور على سطر واحد عمداً (``\s`` كان يبتلع كتلة YAML)، لكنّ القصر بلا
    طيّ متابعات السطر جعل كلّ استدعاء مكتوب بشرطة مائلة عكسيّة خارج المدى **تماماً**:
    لا يراه الاكتشاف، فلا يُصنَّف ولا يُبلَّغ عنه ولا يُعاد توليده. مُقاس: ثلاث خطوات في
    ``platform-route-budget.yml`` — وهي التي عطّلت شريحة #751.
    """
    discovered = {script for script, _ in MOD.discover()}
    for script in (
        "scripts/ci/platform_route_ownership_guard.py",
        "scripts/ci/platform_route_budget_guard.py",
        "scripts/ci/platform_route_governance_attestation.py",
    ):
        assert script in discovered, f"{script} خارج الاكتشاف — عادت ثغرة متابعة السطر"


def test_the_attestation_runs_after_both_inventories_it_reads():
    """الترتيب تبعيّة مقيسة لا أبجديّة.

    ``platform_route_governance_attestation`` يستدعي جرد الملكيّة ويقرأ جرد الميزانيّة،
    و``platform_route_release_binding`` يبصم الثلاثة. الترتيب الأبجديّ وحده كان يضع
    التصديق **قبل** أحد مصدرَيه، فيبقى بائتاً بلا خطأ خاصّ به — والاتّكال على دورة
    ``--fix`` ثانية لتصحيحه اتّكالٌ على مصادفة.
    """
    order = [script for script, _ in sorted(MOD.discover(), key=MOD._sort_key)]
    position = {script: index for index, script in enumerate(order)}
    ownership = position["scripts/ci/platform_route_ownership_guard.py"]
    budget = position["scripts/ci/platform_route_budget_guard.py"]
    attestation = position["scripts/ci/platform_route_governance_attestation.py"]
    binding = position["scripts/release/platform_route_release_binding.py"]
    assert attestation > ownership and attestation > budget
    assert binding > attestation
    assert position["scripts/ci/static_governance_closure.py"] > binding


def test_unindexed_files_are_reported_because_no_generator_can_see_them(tmp_path):
    """‏`GENERATED-SWEEP-UNINDEXED-FILES-INVISIBLE-01` — قاعدة كانت نصّاً بلا إنفاذ.

    المولّدات تمسح ``git ls-files`` (مثال حيّ: ``capability_mapping_engine.py:203``)،
    فملفّ لم يُضَف إلى الفهرس **لا يراه أيّ مولّد**. كانت القاعدة مكتوبة في docstring
    المكنسة («`git add` قبل التشغيل ضرورة لا عادة») ولا تفرضها الأداة — فتخرج بصفر
    بينما CI يرصد الانحراف بعد الالتزام. حدث ذلك فعليّاً على ``fe44832a``: انحرفت
    مصنوعة ``capability_mapping`` بملفّ اختبار جديد لم يُضَف، والمكنسة كانت خضراء.

    الفحص هنا على سلوك ``unindexed_files()`` في مستودع حقيقيّ مؤقّت — لا على نصّ
    المكنسة، لأنّ الادّعاء أنّ الأداة **ترصد**، لا أنّها تذكر الكلمة.
    """
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )
    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (repo / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "base")

    original_root = MOD.ROOT
    try:
        MOD.ROOT = repo
        assert MOD.unindexed_files() == [], "شجرة نظيفة أُبلِغ عنها كناقصة"

        (repo / "new_test.py").write_text("y = 2\n", encoding="utf-8")
        assert MOD.unindexed_files() == ["new_test.py"], "ملفّ غير مُفهرَس لم يُرصَد"

        (repo / "ignored").mkdir()
        (repo / "ignored" / "scratch.py").write_text("z = 3\n", encoding="utf-8")
        assert MOD.unindexed_files() == ["new_test.py"], (
            "المُتجاهَل أُبلِغ عنه — المولّد لا يراه ولا يُفترَض أن يراه، فالإبلاغ عنه ضجيج"
        )

        run("add", "-A")
        assert MOD.unindexed_files() == [], "الفهرسة لم تُسكِت الإبلاغ"
    finally:
        MOD.ROOT = original_root


def test_the_completeness_question_is_not_the_change_question():
    """‏``tree_state()`` لا يسدّ هذه الثغرة، والخلط بينهما هو سبب بقائها مفتوحة.

    ``tree_state`` يستعمل ``--untracked-files=no`` **عمداً**: يقيس *تغيّر* المتعقَّب
    أثناء الفحص. و``unindexed_files`` يقيس *اكتمال المُدخَل* قبله. سؤالان مختلفان،
    وعلمٌ واحد لا يجيبهما.
    """
    import inspect

    assert "--untracked-files=no" in inspect.getsource(MOD.tree_state)
    assert "--untracked-files=normal" in inspect.getsource(MOD.unindexed_files)
