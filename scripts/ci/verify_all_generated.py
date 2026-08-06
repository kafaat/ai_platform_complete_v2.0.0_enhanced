#!/usr/bin/env python3
"""يشغّل **كلّ** خطوات ``--check`` المولَّدة بأمر واحد — وبالترتيب الذي تتطلّبه التبعيّات.

``GENERATED-ARTIFACT-SWEEP-01``. «ضريبة التسجيل» موصوفة في `hot.md` بثلاث قفزات
(جرد ⇒ كتالوج ⇒ حزمة)، ومداها الحقيقيّ **٤٧ خطوة موزّعة على ١٨ workflow**. الفارق ليس
تفصيلاً: شريحتان متتاليتان في 2026-07-28 كلّفتا جولة CI كاملة كلّ واحدة لأنّ الفحص
المحلّيّ كان انتقائيّاً — أُصلِح ما سمّاه CI، فظهر التالي في الجولة التي بعدها.

**القائمة تُكتشَف من الـworkflows لا تُكتب هنا.** قائمة مكتوبة يدويّاً تبيت بصمت عند
إضافة مولّد جديد، فتُعيد إنتاج العيب نفسه في الأداة التي تعالجه. المصدر الوحيد للحقيقة
هو ما ينفّذه CI فعلاً.

الترتيب مُصرَّح لأنّه حقيقة تبعيّة لا تفضيلاً:
  ١) المولّدات المستقلّة — كلٌّ يقرأ الشجرة ويكتب مصنوعه.
  ٢) ``static_governance_closure`` — يبصم مخرجات (١)، فينحرف مرّتين لو سبقها.
  ٣) حزمة الإصدار — تبصم كلّ ما سبق، فهي آخِراً دائماً.

و``--fix`` يُكرّر حتّى الثبات (حدّ ٣ دورات): مولّد يجزّئ ملفّات غيّرها مولّد آخر يحتاج
دورة ثانية — رُصِد فعليّاً على ``execution_dependency_audit``.

**fail-closed على المجهول:** خطوة ``--check`` بلا علم بكيفيّة إعادة توليدها تُبلَّغ
كـ«يدويّة» ولا تُتخطّى صامتةً — فلا يُقرأ نجاح الأداة كتغطية لا تملكها.

**والاكتشاف من الـworkflows يترك ثقباً بحدّ تعريفه:** مولّد يدعم ``--check`` ولا يذكره
أيّ workflow خارج المدى تماماً — لا يراه CI ولا تراه هذه المكنسة. تُغلَق الزاوية بتصنيف
صريح: كلّ سكربت في ``scripts/{ci,architecture,release}`` يُعلن علم ``--check`` ولا اسم له
في أيّ workflow **يجب** أن يكون مُدرَجاً في ``docs/architecture/generated_chain_known_drift.json``
بحارسه وسبب صمته ودليله وشرط إغلاقه. مولّد جديد يدخل بلا تصنيف ⇒ فشل.

التصنيف غير المُغطّى لا يُنفَّذ افتراضياً لأنّه خارج عقد workflows المكتشَف، لا لأن
``--check`` مسموح له بالكتابة. أُغلقت ``CHECK-STEPS-MUTATE-THE-TREE-01``: أوضاع الفحص
للحرّاس الستّة أصبحت قراءة فقط، مع بقاء مقارنة حالة الشجرة دفاعاً إضافياً.

    git add -A                                          # ← لازم أوّلاً، انظر أدناه
    python scripts/ci/verify_all_generated.py           # افحص فقط
    python scripts/ci/verify_all_generated.py --fix     # أعد التوليد ثمّ افحص
    python scripts/ci/verify_all_generated.py --uncovered  # شغّل غير المُغطّى (يكتب!)

**`git add` قبل التشغيل ضرورة لا عادة:** المولّدات تمسح `git ls-files` (مُتعقَّب فقط —
قرار #660 لمنع التقاط ملفّات محلّيّة غائبة عن checkout الـCI). فملفّ جديد غير مُدرَج في
الفهرس **لا يراه أيّ مولّد**، وتمرّ المكنسة خضراء بينما CI سيرصد الانحراف بعد الالتزام.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
KNOWN_DRIFT = ROOT / "docs" / "architecture" / "generated_chain_known_drift.json"
UNMAPPED_BASELINE = ROOT / "docs" / "architecture" / "generated_sweep_unmapped_generators.json"

# أدلّة السكربتات التي قد تحمل مولّدات — نفسها التي يطابقها `_STEP` في الـworkflows.
_SCRIPT_DIRS = ("scripts/ci", "scripts/architecture", "scripts/release")

# «يدعم --check» = يُعلن العلم كسلسلة نصّيّة في مصدره (argparse)، لا مجرّد ذكره في شرح.
# التمييز ليس شكليّاً: `verify_all_generated` نفسه يذكر `--check` في docstring ولا يملكه.
_DECLARES_CHECK = re.compile(r"""["']--check[a-z-]*["']""")

# خطوة فحص في workflow: `python scripts/<dir>/<name>.py … --check[-suffix]`
# مقصور على **سطر واحد**: `\s` يبتلع الأسطر الجديدة فيلتهم كتلة YAML كاملة ويُنتج
# «خطوة» وهميّة تمرّ خضراء بلا تنفيذ شيء — رُصِد على أوّل تشغيل.
_STEP = re.compile(
    r"python[ \t]+(scripts/(?:ci|architecture|release)/[a-z_0-9]+\.py)"
    r"((?:[ \t]+(?!\||&)[^\s|&]+)*?[ \t]+--check[a-z-]*)"
)

# علم إعادة التوليد لكلّ سكربت يملكه. الغياب = فحص فقط (يُبلَّغ، لا يُتخطّى).
_GENERATE_FLAG = {
    "generate_service_inventory.py": "--write-registry",
    "capability_mapping_engine.py": "--generate",
    "capability_evidence_maturity_engine.py": "--generate",
    "capability_parity_investment_engine.py": "--generate",
    "capability_release_history.py": "--generate",
    "capability_runtime_evidence.py": "--apply",
    "execution_dependency_audit.py": "--generate",
    "decision_lineage_graph.py": "--generate",
    "database_contract_graph.py": "--generate",
    "event_contract_graph.py": "--generate",
    "architecture_graph.py": "--generate",
    "route_conflict_guard.py": "--generate",
    "router_reachability_guard.py": "--generate",
    "runtime_contract_generator.py": "--generate",
    "generate_indicator_artifacts.py": "",
    "generate_indicators_frontend_manifest.py": "",
    "pr_capability_impact_gate.py": "--generate-index",
    # كتالوج الحرّاس: مصنوعة مولَّدة من الـworkflows + سجلّ الطفرات + توثيق كلّ حارس.
    # علمُ التوليد هو التشغيل العاري؛ `--check` يفشل عند الانحراف.
    "guard_catalogue.py": "",
    "build_platform_catalog.py": "",  # بلا علم — التشغيل العاري يكتب
    "build_service_dependency_bundle.py": "",
    "static_governance_closure.py": "--generate",
    "manifest_registry_guard.py": "",  # بلا علم — التشغيل العاري يولّد,
}

# الثلاثة أدناه انحرفت فعليّاً في شريحة واحدة وكانت غائبة عن الخريطة، فلم تُستدعَ
# ومرّت ثلاث دورات بلا تغيير ⇒ «لم تثبت» (VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01).
# أُضيفت بعلمها الحقيقيّ المُعلَن في مصدرها لا بعلم مُوحَّد مفروض عليها.
_GENERATE_FLAG.update(
    {
        "capability_linker.py": "--apply",
        "health_readiness_schema_guard.py": "--write",
        "route_residual_classification_guard.py": "--write",
    }
)

# العشرة أدناه أُغلِقت بالشرط المُعلَن في generated_sweep_unmapped_generators.json، لا
# بالثقة في وجود العلم: لكلٍّ منها أُفسِدت مصنوعة يملكها ⇒ `--check` رصد الإفساد
# (خرج بغير صفر)، ثمّ شُغِّل العلم ⇒ `--check` عاد بصفر **والملفّ استُعيد بايتاً بايت**.
# وكلّها خاملة على شجرة نظيفة (تشغيل العلم لا يُغيّر شيئاً)، فوصلها لا يُوسّخ الشجرة.
_GENERATE_FLAG.update(
    {
        "capability_roadmap_linker.py": "--generate",
        "compose_runtime_target_resolver.py": "--generate",
        "gateway_reachability_guard.py": "--generate",
        "integration_runtime_governance_closure.py": "--generate",
        "path3_runtime_readiness_closure.py": "--generate",
        "production_evidence_pack_guard.py": "--write",
        "report_index_guard.py": "--write",
        "runtime_certification_gate.py": "--generate",
        "runtime_evidence_ingestion.py": "--generate",
        "runtime_verification_harness.py": "--generate",
    }
)

# الأربعة أدناه كانت **غير مرئيّة للاكتشاف أصلاً** لا مجرّد غائبة عن الخريطة: استدعاؤها
# في `platform-route-budget.yml` مكتوب على أسطر بشرطة مائلة عكسيّة، و`_STEP` مقصور على
# سطر واحد. أُضيفت بعد إغلاق الشرط المُعلَن لكلٍّ منها (أفسِد مصنوعتها ⇒ `--check` يرصد،
# ثمّ شغّل العلم ⇒ `--check` بصفر **والملفّ مُستعاد بايتاً بايت**) — لا بالثقة في وجود العلم.
#
# الترتيب بينها حقيقة تبعيّة لا تفضيل: `attestation` يستدعي جرد الملكيّة ويقرأ جرد
# الميزانيّة، و`release_binding` يبصم الثلاثة. والأبجديّة **لا** تُنتِج هذا الترتيب —
# قِستُه فوجدتُه `budget → attestation → ownership`، أي التصديق قبل أحد مصدرَيه؛ فصار
# صريحاً في `_ORDER_TIER` بدل الاتّكال على أنّ دورة `--fix` الثانية ستُصحّحه مصادفةً.
# و`--write-source` اسمٌ تاريخيّ: يكتب `release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json`
# (مصنوعة مولَّدة) لا كوداً مصدريّاً — تحقّقتُ منه قبل الوصل.
_GENERATE_FLAG.update(
    {
        "platform_route_ownership_guard.py": "--write-generated",
        "platform_route_budget_guard.py": "--write-generated",
        "platform_route_governance_attestation.py": "--write-generated",
        "platform_route_release_binding.py": "--write-source",
    }
)

# والستّة أدناه لم تكن قابلة للإغلاق حتّى أُصلِح ما يمنع قياسها: شرط الإغلاق يبدأ بـ
# «أفسِد مصنوعة ⇒ يجب أن يرصد `--check`»، وهذه الستّة **كانت عمياء عن ١٣ من ١٦ مصنوعة
# تملكها** (GENERATED-CHECK-IGNORES-ITS-OWN-COMPANION-ARTIFACTS-01). فوصلها قبل ذلك كان
# سيُصلح انحرافاً لا يستطيع أحد رصده. بعد توحيدها على `generated_artifact_contract`
# صارت ١٦ من ١٦ راصدة، ومرّ الشرط كاملاً على كلٍّ منها: خمول على شجرة نظيفة · رصد
# الإفساد **مع تسمية الملفّ** · استعادة بايتاً بايت · ولا يمسّ العلم ملفّاً غير الذي
# سمّاه الانحراف.
_GENERATE_FLAG.update(
    {
        "ai_container_contract_guard.py": "--write",
        "capability_registry_v1.py": "--generate",
        "duplicate_definition_guard.py": "--generate",
        "platform_main_subinventory_guard.py": "--write",
        "production_certification_checklist_guard.py": "--write",
        "runtime_container_deep_contract_guard.py": "--write",
    }
)

# والسابع رصدته **شريحة عملٍ عاديّة لا مسحٌ عن الحرّاس**، وهذا وجه الفائدة منه: تغييرٌ في
# محرّك WOFOST أكسب `IRR-004` بُعد `events` (تغطية ٥ ⇒ ٦)، فانحرفت
# `capability_management_matrix.json` — و`--fix` دار ثلاث دورات كاملة (~١٥د) بلا أن
# يستدعيه، فطبع «لم تثبت المصنوعات» بلا سببٍ ظاهر لمن لا يقرأ ذيل التلميحات.
#
# كان مستثنىً في `generated_sweep_unmapped_generators.json` بسببٍ **مقيس آنذاك**: «تشغيل
# العلم على شجرة نظيفة يُغيّر ملفّاً في كلّ مرّة». أُعيد قياس الثلاثة المستثناة فرداً فرداً
# (لا تعميماً من عيّنة): هذا يُخرِج **صفر** ملفّات بعد تشغيلين متتاليين على شجرة نظيفة،
# بينما `capability_registry_guard` و`runtime_environment_preflight` ما زالا يُوسِّخان
# ملفّاً لكلٍّ ⇒ يبقيان مستثنيَين. السبب المُسجَّل صار صحيحاً لاثنين وبائتاً لواحد.
#
# وأُغلِق بالشرط المُعلَن حرفيّاً لا بالقياس أعلاه وحده: أُفسِد
# `capability_management_matrix.json` ⇒ `--check` رصد **وسمّى الملفّ** (خرج بـ1) ⇒
# `--generate` ⇒ `--check` بصفر **والملفّ مُستعاد بايتاً بايت** (`cmp`).
_GENERATE_FLAG.update({"capability_management_engine.py": "--generate"})

# علم كتابة يُعلنه سكربت في مصدره — يُميّز «كاتب لم يُستدعَ» عن «فحص بلا مولّد».
_WRITE_FLAG_DECL = re.compile(r"""["'](--(?:write|apply|generate)[a-z-]*)["']""")

# أعلام الكتابة، **بالعائلة لا بالتعداد** (GENERATED-SWEEP-WRITE-FLAG-FAMILY-BLIND-01).
#
# كانت قائمةً مغلقةً تُفحَص بتطابق تامّ، فغابت عنها عائلة `--write-*` كاملةً: أربعة
# مولّدات تكتب بـ`--write-generated`/`--write-source` بقيت **غير مرئيّة** لـ
# `flag_map_problems()`، فأعلن الحارس نظافةً بينما هي تنحرف. وقياساً على `d4549ef6`:
# `flag_map_problems()` تُرجِع لا شيء بينما `platform_route_ownership_guard` و
# `platform_route_governance_attestation` و`platform_route_budget_guard` غائبة عن
# `_GENERATE_FLAG` — وهي التي عطّلت شريحة #751 حتّى شُغِّلت يدويّاً.
#
# والتناقض كان **داخل هذا الملفّ نفسه**: `_WRITE_FLAG_DECL` أعلاه يطابق `--write-*`
# بالبادئة، فالماسح المصدريّ كان يراها والمُستجوِب لا يراها. فوُحِّد المعياران.
#
# البادئة مقصودة أوسع من التعداد: خطؤها المحتمل «سمِّه في الأساس» — كلفته سطر
# مُعلَّل؛ وخطأ التعداد «لا يُعاد توليده أبداً» — كلفته انحراف صامت.
_WRITE_FLAG_PREFIXES = ("--write", "--generate", "--apply")
_WRITE_FLAG_EXACT = frozenset({"--fix"})


def write_flags_of(flags: set[str]) -> list[str]:
    """أعلام الكتابة ضمن ما يقبله سكربت فعلاً — بعائلة العلم لا بقائمة مغلقة."""
    return sorted(
        flag for flag in flags if flag in _WRITE_FLAG_EXACT or flag.startswith(_WRITE_FLAG_PREFIXES)
    )


def _declared_write_flags(script: str) -> list[str]:
    path = ROOT / script
    try:
        return sorted(set(_WRITE_FLAG_DECL.findall(path.read_text(encoding="utf-8"))))
    except OSError:
        return []


def _accepted_flags(script: str) -> set[str]:
    """الأعلام التي يقبلها ``argparse`` فعلاً — من ``--help`` لا من مسح المصدر.

    ``_declared_write_flags`` أعلاه يمسح النصّ، وهو تقريب رخيص يكفي **للتشخيص بعد
    الفشل**. لكنّه لا يصلح حكماً: أيّ سلسلة نصّيّة مقتبَسة تُحسَب علماً. مُقاس على
    الشجرة (2026-08-01): خمسة سكربتات «تُعلن» علماً لا يقبله argparse، وأطرفها
    ``verify_all_generated.py`` نفسه — يُتَّهم بإعلان الأعلام الخمسة جميعاً لأنّ
    ``_GENERATE_FLAG`` يحوي تلك النصوص. الاستجواب هنا لا يخطئ هذا الخطأ.
    """
    proc = subprocess.run(  # noqa: S603 — مسار مُكتشَف من الـworkflows
        [sys.executable, script, "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=STEP_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        return set()
    return set(re.findall(r"--[a-z][a-z0-9-]*", proc.stdout))


def flag_map_problems(steps) -> list[str]:
    """يستجوب ``_GENERATE_FLAG`` قبل استعماله — وقايةً لا تشخيصاً بعد وقوع الضرر.

    ``VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01`` عولج بتصحيح المداخل الخاطئة،
    وأُضيف إليه تشخيص يميّز «كاتب لم يُستدعَ» عن «دورة تبعيّة». لكنّ ذلك التشخيص
    يعمل **داخل فرع عدم الاستقرار وحده** — أي بعد أن تكون المكنسة قد فشلت ثلاث
    دورات كاملة. والخريطة يدويّة، فستبيت ثانيةً؛ والعيب ساكن لا يحتاج انحرافاً
    لينكشف. هذا يفحصها في الوضع الافتراضيّ وهي خضراء: علم مُعلَن لا يقبله السكربت،
    أو علم كتابة يملكه السكربت ولا تذكره الخريطة ⇒ فشل يسمّي السكربت وعلمه الحقيقيّ.
    """
    problems: list[str] = []
    baseline = json.loads(UNMAPPED_BASELINE.read_text(encoding="utf-8"))["unmapped"]
    seen: set[str] = set()
    for script in sorted({s for s, _ in steps}):
        name = Path(script).name
        flags = _accepted_flags(script)
        if not flags:
            continue  # لا ``--help`` قابلاً للاستجواب ⇒ لا حكم (لا تخمين)
        seen.add(script)
        if name in _GENERATE_FLAG:
            declared = _GENERATE_FLAG[name]
            if declared and declared not in flags:
                usable = write_flags_of(flags) or ["لا علم كتابة — التشغيل العاري"]
                problems.append(
                    f"{script}: العلم المُعلَن `{declared}` لا يقبله السكربت. "
                    f"المقبول: {', '.join(usable)}"
                )
            continue
        usable = write_flags_of(flags)
        if not usable:
            continue
        if script in baseline:
            if baseline[script] not in usable:
                problems.append(
                    f"{script}: الأساس يسجّل `{baseline[script]}` والسكربت يقبل "
                    f"{', '.join(usable)} — حدّث generated_sweep_unmapped_generators.json"
                )
            continue
        problems.append(
            f"{script}: يملك علم كتابة ({', '.join(usable)}) ولا يذكره _GENERATE_FLAG "
            "⇒ لا يُعاد توليده أبداً، وانحرافه يبقى بلا إصلاح. صِلْه بالخريطة، أو "
            "سجّله في generated_sweep_unmapped_generators.json بسبب مقيس."
        )
    for script in sorted(set(baseline) - seen):
        problems.append(
            f"مدخل بائت في أساس غير المُوصَّلين: {script} — لم يعد خطوة --check في أيّ "
            "workflow، أو وُصِل بالخريطة. احذف المدخل (الأساس يتقلّص)."
        )
    return problems


# يبصم مخرجات المولّدات ⇒ بعدها دائماً.
_LATE = ("static_governance_closure.py",)

# طبقات ترتيب صريحة داخل مرحلة المولّدات — تبعيّة مقيسة لا ترتيب أبجديّ.
# `platform_route_governance_attestation` يستدعي `build_ownership_inventory()` ويقرأ
# جرد الميزانيّة، فتشغيله قبل أيّهما يُبقيه بائتاً **بلا خطأ خاصّ به**: الأبجديّة وحدها
# كانت ترتّبه `budget → attestation → ownership`، أي قبل أحد مصدرَيه. الاعتماد على أنّ
# `--fix` سيُصحّح ذلك في دورة ثانية اعتمادٌ على مصادفة، وهو نفس الصمت الذي تعالجه المكنسة.
#
# و`capability_management_engine` يقع في الفخّ نفسه بحدّة أكبر: يقرأ خمس مصنوعات
# (`capability_mapping` · `capability_evidence_matrix` · `capability_parity_matrix` ·
# `capability_investment_matrix` · `capability_registry`)، والأبجديّة تضعه **قبل ثلاث
# منها** لأنّ `man` < `map` و`pa` و`re`. فتشغيله في طبقة صفر كان سيقرأ مدخلات بائتة
# ويحتاج دورةً ثانية دائماً — أي «يستقرّ» بمصادفة الدورات لا بترتيب صحيح.
_ORDER_TIER = {
    "capability_management_engine.py": 1,
    "platform_route_governance_attestation.py": 1,
    "platform_route_release_binding.py": 2,
}

# تبصم كلّ ما سبق ⇒ آخر شيء على الإطلاق.
_RELEASE_BUILD = "scripts/release/build_release_bundle.py"
_RELEASE_VALIDATE = "scripts/release/validate_release_package.py"

MAX_PASSES = 3
STEP_TIMEOUT_SECONDS = 180


def discover() -> list[tuple[str, list[str]]]:
    """(مسار السكربت، وسائطه) لكلّ خطوة ``--check`` في الـworkflows — مُزالة التكرار.

    **متابعات السطر تُطوى أوّلاً** (`GENERATED-SWEEP-CONTINUATION-BLIND-01`): `_STEP`
    مقصور على سطر واحد عمداً — `\\s` كان يبتلع الأسطر الجديدة فيلتهم كتلة YAML كاملة
    ويُنتج «خطوة» وهميّة. لكنّ القصر بلا طيّ جعل كلّ استدعاء مكتوب على أسطر بشرطة
    مائلة عكسيّة **غير مرئيّ للاكتشاف أصلاً**، لا مُصنَّفاً ولا مُبلَّغاً عنه.

    القياس على `d4549ef6`: **ثلاث** خطوات فحص في `platform-route-budget.yml`
    (`platform_route_ownership_guard` · `platform_route_budget_guard` ·
    `platform_route_governance_attestation`) خارج المدى تماماً — وهي التي عطّلت #751
    ولم يُظهرها أيّ حارس، لأنّ ما لا يُكتشَف لا يُصنَّف.

    الطيّ يقتصر على `\\` في نهاية السطر (متابعة صدفة صريحة)، فلا يُعيد فتح ثغرة `\\s`:
    سطر YAML عاديّ بلا شرطة مائلة يبقى منفصلاً.
    """
    seen: dict[tuple[str, tuple[str, ...]], None] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = re.sub(r"\\\n[ \t]*", " ", wf.read_text(encoding="utf-8"))
        for script, args in _STEP.findall(text):
            argv = tuple(a for a in args.split() if a)
            seen.setdefault((script, argv), None)
    return [(s, list(a)) for (s, a) in seen]


def uncovered() -> list[str]:
    """السكربتات التي تُعلن ``--check`` ولا يذكرها أيّ workflow — خارج مدى CI والمكنسة."""
    named = "\n".join(wf.read_text(encoding="utf-8") for wf in WORKFLOWS.glob("*.yml"))
    found: list[str] = []
    for directory in _SCRIPT_DIRS:
        for path in sorted((ROOT / directory).glob("*.py")):
            if not _DECLARES_CHECK.search(path.read_text(encoding="utf-8")):
                continue
            if path.name in named:
                continue
            found.append(f"{directory}/{path.name}")
    return found


def load_known_drift() -> dict[str, dict]:
    """أساس التصنيف. غيابه ليس «لا شيء معروف» بل عطب — لا يُقرأ كخضرة."""
    if not KNOWN_DRIFT.exists():
        raise FileNotFoundError(f"أساس التصنيف مفقود: {KNOWN_DRIFT.relative_to(ROOT)}")
    return json.loads(KNOWN_DRIFT.read_text(encoding="utf-8"))["uncovered"]


def classify_uncovered() -> list[str]:
    """يُطابق ما في الشجرة بما في الأساس. يُعيد أسطر الأخطاء (فارغة = متّسق).

    الاتّجاهان يفشلان: مولّد جديد بلا تصنيف (ثقب يتّسع صامتاً)، ومدخل بائت في الأساس
    (سكربت وُصِل بـworkflow أو حُذِف — «معروف» صار وصفاً لماضٍ). القائمة تتقلّص ولا تنمو.
    """
    in_tree = set(uncovered())
    in_baseline = set(load_known_drift())
    problems: list[str] = []
    for script in sorted(in_tree - in_baseline):
        problems.append(
            f"مولّد يدعم --check ولا يذكره workflow ولا يصنّفه الأساس: {script}"
            f" — صنّفه في {KNOWN_DRIFT.relative_to(ROOT)} أو صِله بـworkflow."
        )
    for script in sorted(in_baseline - in_tree):
        problems.append(f"مدخل بائت في الأساس: {script} — لم يعد غير مُغطّى (أو حُذِف). احذف المدخل.")
    return problems


def run_uncovered(entries: dict[str, dict]) -> list[tuple[str, str]]:
    """يشغّل غير المُغطّى بعلمه المُصرَّح ويقارن النتيجة بالمُعلَن في الأساس.

    يكتب ملفّات متعقَّبة (``CHECK-STEPS-MUTATE-THE-TREE-01``) — ولذلك لا يعمل افتراضيّاً.
    الفشل هنا ليس «انحرف» بل «انحرافه غير ما يقوله الأساس»: سليم صار منحرفاً (انحدار
    جديد)، أو منحرف صار سليماً (شرط إغلاقه تحقّق ⇒ يُحذف مدخله).
    """
    surprises: list[tuple[str, str]] = []
    for script, entry in sorted(entries.items()):
        code, out = _run([script, entry["check_flag"]])
        drifted = code != 0
        tail = out.splitlines()[-1] if out.splitlines() else f"exit {code}"
        if drifted == bool(entry["drifts"]):
            state = "منحرف كما هو مُعلَن" if drifted else "سليم كما هو مُعلَن"
            print(f"  ✓ {script} — {state}")
            continue
        note = (
            "الأساس يقول سليم وقد انحرف — انحدار جديد"
            if drifted
            else "الأساس يقول منحرف وقد سلُم — تحقّق شرط الإغلاق، احذف المدخل"
        )
        surprises.append((script, f"{note}: {tail}"))
        print(f"  ✗ {script}\n      {note}\n      {tail}")
    return surprises


def _run(argv: list[str]) -> tuple[int, str]:
    """Run one discovered step with a hard, diagnosable deadline.

    A generated-artifact guard must not be able to consume an entire CI job without naming
    the stalled step. Each command runs in its own process group so descendants are also
    terminated on timeout.
    """
    cmd = [sys.executable, *argv]
    proc = subprocess.Popen(  # noqa: S603 — أوامر من الـworkflows لا من مُدخَل مستخدم
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=STEP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        stdout, stderr = proc.communicate()
        partial = ((stdout or "") + (stderr or "")).strip()
        detail = f"TIMEOUT after {STEP_TIMEOUT_SECONDS}s: {' '.join(argv)}"
        return 124, (partial + "\n" + detail).strip()
    return proc.returncode, ((stdout or "") + (stderr or "")).strip()


def _sort_key(step: tuple[str, list[str]]) -> tuple[int, int, str]:
    name = Path(step[0]).name
    return (1 if name in _LATE else 0, _ORDER_TIER.get(name, 0), step[0])


def unindexed_files() -> list[str]:
    """ملفّات غير متعقَّبة وغير مُتجاهَلة — أي غير مرئيّة لأيّ مولّد.

    `GENERATED-SWEEP-UNINDEXED-FILES-INVISIBLE-01`. المولّدات تمسح `git ls-files`
    (متعقَّب فقط — قرار #660 لمنع التقاط ملفّات محلّيّة غائبة عن checkout الـCI)، مثال
    حيّ: `capability_mapping_engine.py:203`. فملفّ جديد لم يُضَف إلى الفهرس **لا يراه
    أيّ مولّد**، وتخرج المكنسة بصفر بينما CI يرصد الانحراف بعد الالتزام.

    القاعدة كانت مكتوبة في docstring هذا الملفّ («`git add` قبل التشغيل ضرورة لا
    عادة») **ولا تفرضها الأداة**. وقاعدة بلا إنفاذ ليست قاعدة: نصّها لا يمنع أحداً،
    وخضرة الأداة تُقرأ تصديقاً لتشغيلٍ لم يرَ نصف المُدخَل.

    و`tree_state()` لا يسدّ هذه الثغرة: يستعمل `--untracked-files=no` عمداً — يقيس
    **تغيّر** الملفّات المتعقَّبة، لا اكتمال المُدخَل. فالسؤالان مختلفان.

    المُتجاهَلة (`.gitignore`) مستثناة: لا يراها المولّد ولا يُفترَض أن يراها.
    """
    proc = subprocess.run(  # noqa: S603 — أمر ثابت
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []  # لا git ⇒ `tree_state()` يرفع الاستثناء المفصَّل بعد قليل
    return sorted(line[3:] for line in proc.stdout.splitlines() if line.startswith("?? "))


def tree_state() -> str:
    """حالة الملفّات المتتبَّعة — الإشارة الوحيدة التي لا يملك الحارس تزييفها.

    وهي إشارة **مشروطة بوجود git**: على أرشيف مفكوك بلا ``.git`` كان الأمر يفشل
    و``stdout`` يعود فارغاً، فيتساوى «قبل» و«بعد» **دائماً** ويصير كاشف الكتابة-
    أثناء-الفحص أعمى بلا أن يقول ذلك — مُقاس على لقطة: اثنا عشر ملفّاً أُصلِحت
    ذاتيّاً وأُعلِنت السلامة. الغياب يُرفَع الآن استثناءً: عمى الأداة يجب أن يُعلن
    نفسه، لا أن يُنتج خضرة.
    """
    proc = subprocess.run(  # noqa: S603 — أمر ثابت
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "تعذّر قراءة حالة الشجرة عبر git — كاشف «حارس كتب أثناء الفحص» يعتمد "
            "عليها كليّاً، وبلا git يُعطي خضرة كاذبة. شغّل المكنسة داخل checkout "
            f"حقيقيّ. رمز git={proc.returncode}: {proc.stderr.strip()[:200]}"
        )
    return "\n".join(sorted(proc.stdout.splitlines()))


def unreferenced_generators() -> list[str]:
    """مولِّدات في الشجرة **لا يذكرها أيّ workflow** — عمياء عن الاكتشاف.

    الاكتشاف من الـworkflows يرى ما يُشغّله CI بدقّة، ويعمى بالتعريف عمّا **نسيه**.
    والقياس يقول إنّ هذه ليست حالة نظريّة: أربعة مولِّدات خارج كلّ workflow، وثلاثة
    منها منحرفة على `main` — وفيها `path3_runtime_readiness_closure` الذي يُعلن
    جاهزيّةً لا تسندها الشجرة (`PATH3-READINESS-CLAIM-UNBACKED-01`).

    تُذكر ولا تُشغَّل: تشغيلها هنا يوسّع العقد بلا قرار، وكتمانها يجعل الأداة تدّعي
    شمولاً لا تملكه.
    """
    writes = re.compile(r'"(--(?:generate|write)[a-z-]*)"')
    referenced: set[str] = set()
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        referenced.update(
            re.findall(r"(scripts/(?:ci|release)/[a-z0-9_]+\.py)", wf.read_text(encoding="utf-8"))
        )
    found: set[str] = set()
    for folder in ("scripts/ci", "scripts/release"):
        for script in sorted((ROOT / folder).glob("*.py")):
            if writes.search(script.read_text(encoding="utf-8", errors="ignore")):
                found.add(f"{folder}/{script.name}")
    return sorted(found - referenced)


def check_all(steps) -> list[tuple[str, str]]:
    """يُعيد قائمة (الخطوة، آخر سطر) لكلّ فحص فاشل."""
    failures: list[tuple[str, str]] = []
    for script, args in sorted(steps, key=_sort_key):
        code, out = _run([script, *args])
        label = f"{script} {' '.join(args)}".strip()
        if code != 0:
            tail = out.splitlines()[-1] if out.splitlines() else f"exit {code}"
            failures.append((label, tail))
            print(f"  ✗ {label}\n      {tail}")
        else:
            print(f"  ✓ {label}")
    return failures


def regenerate(steps) -> list[str]:
    """يُعيد توليد ما يُعرَف توليده؛ يُعيد أسماء الخطوات **غير** القابلة للتوليد آليّاً."""
    manual: list[str] = []
    for script, _args in sorted(steps, key=_sort_key):
        name = Path(script).name
        if name not in _GENERATE_FLAG:
            manual.append(script)
            continue
        flag = _GENERATE_FLAG[name]
        code, out = _run([script, flag] if flag else [script])
        if code != 0:
            tail = out.splitlines()[-1] if out.splitlines() else f"exit {code}"
            print(f"  ! تعذّر توليد {script}: {tail}")
    # حزمة الإصدار آخِراً — تبصم كلّ ما سبق. لكن **بشرط الحاجة**: البناء يكتب
    # ``generated_at`` جديداً في كلّ مرّة، فبناؤه بلا داعٍ يُوسّخ الشجرة بفرق طابع زمنيّ
    # لا يقابله تغيير محتوى (``file_count`` ثابت) — ضجيج يُخفي الفرق الحقيقيّ في المراجعة.
    if _run([_RELEASE_VALIDATE])[0] != 0:
        _run([_RELEASE_BUILD])
    return manual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="أعد التوليد حتّى الثبات ثمّ افحص")
    # ``--check`` مرادف صريح للسلوك الافتراضيّ، أُضيف لا ليغيّر شيئاً بل ليجعل نيّة
    # المُستدعي **مكتوبة**. مستدعٍ يكتب `verify_all_generated.py` بلا راية يتّكل على
    # افتراض: لو تغيّر الافتراضيّ يوماً تغيّر معنى استدعائه بلا تعديل سطر واحد عنده.
    # الاتّكال على الافتراضات هو صنف «أخضر عن سؤال لم يُطرَح» بشكله الأخفّ.
    parser.add_argument(
        "--check",
        action="store_true",
        help="افحص فقط (السلوك الافتراضيّ) — رايةٌ صريحة تجعل نيّة المُستدعي مكتوبة",
    )
    parser.add_argument(
        "--uncovered",
        action="store_true",
        help="شغّل المولّدات غير المُغطّاة وقارنها بالأساس (يكتب ملفّات متعقَّبة — شجرة نظيفة)",
    )
    args = parser.parse_args()

    steps = discover()
    print(f"اكتُشفت {len(steps)} خطوة --check من {len(list(WORKFLOWS.glob('*.yml')))} workflow\n")

    # اكتمال المُدخَل قبل أيّ قياس عليه: ملفّ غير مُفهرَس لا يراه أيّ مولّد، فنتيجة
    # المكنسة عنه لا معنى لها — لا «سليم» ولا «منحرف»، بل **غير مقيس**. الإعلان أوّلاً
    # لأنّ كلّ ما يليه مبنيّ عليه.
    pending = unindexed_files()
    if pending:
        print("ملفّات غير مُفهرَسة — لا يراها أيّ مولّد، فنتيجة المكنسة عنها غير مقيسة:")
        for path in pending[:20]:
            print(f"  ✗ {path}")
        if len(pending) > 20:
            print(f"  … و{len(pending) - 20} غيرها")
        print(
            "\n  شغّل `git add -A` ثمّ أعِد المكنسة. الخضرة قبل الفهرسة تصديقٌ لتشغيلٍ\n"
            "  لم يرَ نصف المُدخَل، وCI سيرصد الانحراف بعد الالتزام (مثال: مصنوعة\n"
            "  capability_mapping تنحرف بملفّ اختبار جديد لم يُضَف)."
        )
        return 1

    # التصنيف أوّلاً: يقيس مدى الأداة نفسها. مولّد خارج كلّ workflow لا يظهر في أيّ فحص
    # أدناه، فالسكوت عنه يُحوّل نجاح المكنسة إلى ادّعاء تغطية لا تملكها.
    unclassified = classify_uncovered()
    if unclassified:
        print("خلل في تصنيف المولّدات غير المُغطّاة:")
        for line in unclassified:
            print(f"  ✗ {line}")
        return 1
    # خريطة أعلام التوليد تُستجوَب قبل استعمالها. علم خاطئ أو غائب يتنكّر في هيئة
    # انحراف مصنوعات لا ينقضي، فيُطارَد الوهم بدل السطر. والفحص يعمل في الوضع
    # الافتراضيّ عمداً: العيب ساكن، ولا يحتاج `--fix` لينكشف.
    flag_problems = flag_map_problems(steps)
    if flag_problems:
        print("خريطة أعلام إعادة التوليد لا تطابق السكربتات:")
        for line in flag_problems:
            print(f"  ✗ {line}")
        return 1

    entries = load_known_drift()
    drifting = [s for s, e in entries.items() if e["drifts"]]
    print(
        f"غير مُغطّى بأيّ workflow: {len(entries)} مولّد "
        f"({len(drifting)} منها منحرف بأساس موثَّق) — خارج مدى هذه المكنسة بالتصميم.\n"
    )

    manual: list[str] = []
    if args.fix:
        stabilized = False
        for attempt in range(1, MAX_PASSES + 1):
            print(f"— دورة توليد {attempt}/{MAX_PASSES}")
            manual = regenerate(steps)
            if not check_all(steps):
                stabilized = True
                break
            print()
        if not stabilized:
            # VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01: «لم تثبت» وحدها تُقرأ
            # دورة تبعيّات، فتُرسِل القارئ خلف حلقة غير موجودة. السبب الغالب أنّ
            # كاتباً **لم يُستدعَ أصلاً** لغيابه عن `_GENERATE_FLAG` رغم إعلانه علم
            # كتابة في مصدره. التمييز بين الأسباب الثلاثة هو المعلومة المفيدة.
            print("\nلم تثبت المصنوعات بعد الحدّ الأقصى للدورات.")
            invokable = [s for s in manual if _declared_write_flags(s)]
            if invokable:
                print(
                    "\n  (١) كتّاب يُعلنون علم كتابة في مصدرهم ولم تستدعِهم المكنسة "
                    "— أضِفهم إلى _GENERATE_FLAG (سبب مُرجَّح لعدم الثبات):"
                )
                for script in invokable:
                    print(f"      · {script} ⇐ يدعم {', '.join(_declared_write_flags(script))}")
            blind_only = [s for s in manual if not _declared_write_flags(s)]
            if blind_only:
                print("\n  (٢) فحوص بلا مولّد مُعلَن — انحرافها يدويّ بالتصميم لا خلل أداة:")
                for script in blind_only:
                    print(f"      · {script}")
            if not manual:
                print(
                    "\n  (٣) كلّ الكتّاب استُدعوا ومع ذلك لم تثبت الشجرة ⇒ "
                    "دورة تبعيّات حقيقيّة أو مخرَج غير حتميّ — شخِّصها يدويّاً."
                )
            return 1
    else:
        # دفاع إضافي بعد إغلاق CHECK-STEPS-MUTATE-THE-TREE-01: الحرّاس المعروفة
        # صارت قراءة فقط، لكن مقارنة حالة الشجرة تمنع أي حارس مستقبلي من إعادة العيب.
        before = tree_state()
        failed = bool(check_all(steps))
        after = tree_state()
        if before != after:
            print("\n  ✗ حارس كتب أثناء الفحص — الشجرة تغيّرت بين بدايته ونهايته:")
            for line in sorted(set(after.splitlines()) ^ set(before.splitlines())):
                print(f"      {line}")
            print("      انحراف أُصلِح صامتاً وضاع دليله قبل أن يُقرأ في git diff.")
            failed = True
        if failed:
            print("\nانحراف في المصنوعات المولَّدة — شغّل --fix ثمّ راجع الفرق قبل الالتزام.")
            return 1

    code, out = _run([_RELEASE_VALIDATE])
    print(f"\n{out.splitlines()[-1] if out.splitlines() else ''}")
    if code != 0:
        return 1

    if manual:
        # صدق: الأداة لا تدّعي تغطية لا تملكها.
        print("\nفُحِصت ولا تُولَّد آليّاً (تحتاج يداً إن انحرفت):")
        for script in manual:
            print(f"  · {script}")

    # التقاء شريحتين على الزاوية نفسها (#693 و#690). وكان النصّ المطبوع هنا يقول إنّ
    # كلّ عضو في هذه المجموعة «مُصنَّف في الأساس» ويحيل إلى `classify_uncovered`
    # كفارضٍ له — وهو **غير صحيح**، لأنّ المجموعتين ليستا واحدة: `uncovered()` يجمع من
    # يُعلن `--check`، و`unreferenced_generators()` يجمع من يُعلن علم كتابة. مُقاس:
    # أعضاء هذه المجموعة، **واحد** منها في الأساس والباقي في لا شيء. فكانت الأداة
    # تطبع ادّعاء تغطية لا تملكه — وهو بالضبط العيب الذي بُنيت لتمنعه. التصنيف الآن
    # يُشتَقّ لا يُدَّعى، والمجهول يُسمّى مجهولاً.
    blind = unreferenced_generators()
    if blind:
        classified = set(load_known_drift())
        known = [s for s in blind if s in classified]
        unknown = [s for s in blind if s not in classified]
        print("\nمولِّدات لا يذكرها أيّ workflow ⇒ خارج الاكتشاف (لا تُنفَّذ هنا):")
        for script in known:
            print(f"  · {script} — مُصنَّف في generated_chain_known_drift.json")
        for script in unknown:
            print(f"  · {script} — **بلا تصنيف**: يُعلن علم كتابة ولا `--check` له")
        if unknown:
            print(
                f"  {len(unknown)} من {len(blind)} بلا تصنيف. لا يمسكها "
                "`classify_uncovered` لأنّه يفرض على من يُعلن `--check` وحدهم: "
                "مولّد بلا وضع فحص لا يستطيع الإبلاغ عن انحرافه أصلاً "
                "(GENERATED-WRITE-ONLY-GENERATORS-UNCLASSIFIED-01)."
            )

    if args.uncovered:
        print("\n— المولّدات غير المُغطّاة (تنفيذ صريح؛ راجع `git status` بعده):")
        if run_uncovered(entries):
            print("\nحالة مولّد غير مُغطّى تخالف الأساس — حدِّث الأساس أو أصلح السبب.")
            return 1

    print("\n✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
