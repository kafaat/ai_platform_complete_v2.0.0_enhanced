#!/usr/bin/env python3
"""Guard against report-only certification/progress changes in CI.

Usage in CI:
  git diff --name-only origin/main...HEAD | python scripts/ci/no_report_only_change_guard.py --stdin

Local static check only verifies the policy file itself. The guard allows docs-only
changes, but blocks changes that are exclusively generated reports/csv/json under
release-report patterns unless a code, test, guard, inventory, workflow, or runbook
change accompanies them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPORT_SUFFIXES = (".md", ".csv", ".json")

# DOCS-ONLY-SLICE-UNLANDABLE-UNDER-MANDATORY-REGENERATION-01 — **مقيسٌ على #1012.**
#
# الحارس يَعِد في رأسه بأنّ «docs-only changes» مسموحة، والتصنيفُ يُصدِّق ذلك لوثيقةٍ
# **وحدها** (`test_plain_docs_outside_certification_path_pass`). لكنّ CLAUDE.md يُلزِم
# بإعادة توليد المصنوعات بعد أيّ إضافة، وإعادةُ التوليد تُعيد ختمَ ملفّاتٍ تحمل تلميحاتِ
# التقارير في أسمائها (`CAPABILITY_MAPPING_REPORT.md` · `*_inventory.json` ·
# `*_summary.json`). فوثيقةُ تدقيقٍ مكتوبةٌ بخطّ اليد + المصنوعاتُ التي أوجبها المستودعُ
# نفسُه = «report-only» بالتصنيف، **وغيرُ قابلةٍ للهبوط أبداً** — لأنّ الوثيقة لا تُرى
# (ليست جوهريّة ولا تقريراً) والمصنوعاتُ وحدها هي ما يُرى.
#
# صنفُ «بوّابةٌ لا تُغلَق بعملٍ صحيح» للمرّة الرابعة في هذا الملفّ (بعد `sahool-brain/`
# و`docs/architecture/gates/` و`.github/CODEOWNERS`)، والعلاجُ على نمطها: يُعرَّف
# **مصنوعُ إعادة التوليد** تعريفاً صريحاً ضيّقاً — دليلُ التوليد، وملفّاتُ الإصدار التي
# يكتبها مولِّد، وملفّاتُ القياس التي يُعيد `verify_all_generated.py --fix` ختمَ `measured_on` فيها —
# فإذا لم يكن في التغيير شيءٌ سوى وثائق بخطّ اليد + الدماغ + هذه المصنوعات، فالتغييرُ
# وثائقيّ كما يَعِد الرأس. المصنوعاتُ تابعةٌ لِما ولّدها.
#
# **ولماذا قائمةٌ صريحة لا `generated_write_targets.json`:** ذلك الجردُ يعدّ كلَّ ما
# يكتبه سكربت، ومنه ما يُكتَب **جزئيّاً** (سجلُّ الاعتماد تحت `capabilities/registry/`:
# حقولٌ قانونيّة بخطّ اليد وحقولُ إسقاطٍ مولَّدة). اعتبارُه مصنوعاً يجعل تعديلَ حقلِ
# اعتمادٍ يدويّاً يمرّ خلف وثيقة — وهو بعينه ما وُجِد الحارسُ ليحجبه.
# (اسمُ الملفّ لا يُكتَب هنا كاملاً عمداً: `capability_legacy_access_guard` يبحث عنه
# نصّيّاً ويعدّ ذكرَه في تعليقٍ «وصولاً مباشراً» — مقيسٌ على #1012.)
#
# وما **لا** يفتحه: تقريرٌ مكتوبٌ بخطّ اليد باسمٍ تقريريّ (`FOO_REPORT.md`) أو سجلُّ
# الاعتماد بجوار وثيقة — ليس مصنوعَ إعادة توليد فيبقى محجوباً؛ ومصنوعاتٌ مولَّدة **بلا**
# وثيقة — تبقى «exclusively generated» كما ينصّ الرأس.
REGENERATION_ARTIFACT_PREFIXES = ("docs/capability-registry/generated/",)
# `release/` **ليست** بادئةً هنا (مراجعة Copilot على #1012): تحتها `DEPLOYMENT_READINESS_CHECKLIST.md`
# بخطّ اليد ويطلبها `validate_release_package.py` بعينها — بادئةٌ كانت ستجعلها مصنوعاً
# يُلوندَر خلف وثيقة. تُعدَّد ملفّاتُ الإصدار التي يكتبها مولِّدٌ فعلاً (`build_release_bundle.py`
# · `platform_route_release_binding.py` · `generate_dependency_sbom.py`) لا غير.
#
# **المعيارُ المُلزِم للعضويّة هنا (مراجعة Copilot ٣ على #1012، مقيسةٌ في المولِّدات):**
# ملفٌّ يحمل **حقلاً مُحكَّماً بخطّ اليد** ليس مصنوعَ إعادة توليد ولو أعاد المولِّدُ كتابتَه —
# لأنّ المولِّد **يحمله كما هو** ولا يشتقّه، فإدراجُه يفتح ذلك الحقلَ خلف وثيقة. مُستبعَدان
# بهذا المعيار، وكلاهما كان هنا فأُخرِج:
#   · `fake_connection_debt.json` — `proven_live` «قرارٌ مقيس لا مُشتقّ»، يُحمَل عبر
#     إعادة التوليد (`fake_connection_debt_guard.py` في `_generate`: `carried = …`).
#     إدراجُه كان يسمح بادّعاء إثباتٍ حيٍّ خلف وثيقةٍ ومصنوعات.
#   · `brain_deferral_baseline.json` — `exempt_lines` «يُستدعى مرّة … ثمّ يُقلَّص يدويّاً»
#     (`brain_deferral_registry_guard.py` في `write_baseline`)، و`load_baseline` يثق به.
#     إدراجُه كان يسمح بإضافة إعفاءٍ يتخطّى حارسَ التأجيلات.
# والباقي مفحوصٌ بالمعيار نفسه: لا مفتاحَ إعفاءٍ/إثباتٍ/تحكيمٍ في أيٍّ منها، ومولِّداتُها
# لا تحمل شيئاً قُدُماً.
REGENERATION_ARTIFACT_EXACT = {
    "release/FILE_CHECKSUMS.sha256",
    "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
    "release/SBOM_MINIMAL.json",
    "release/SBOM_DEPENDENCIES.cdx.json",
    "release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json",
    "docs/architecture/assertion_presence_baseline.json",
    "docs/architecture/db_writer_ownership_baseline.json",
    "docs/architecture/generated_write_targets.json",
    "docs/architecture/manifest_registry.json",
    "docs/architecture/s4_kg_consumer_freeze.json",
    "docs/architecture/s5_exec_01_edge_freeze.json",
    "docs/architecture/source_text_assertion_inventory.json",
    "docs/architecture/tenant_guc_scope_baseline.json",
    "REPORT_INDEX.md",
}
REPORT_NAME_HINTS = (
    "REPORT",
    "INVENTORY",
    "CHECKLIST",
    "SUMMARY",
    "MATRIX",
    "REGISTRY",
)
SUBSTANTIVE_PREFIXES = (
    "services/",
    "bots/",
    # Frontend/mobile application code IS code — the guard's own message invites
    # "code/test/guard" changes, but the first implementation only recognised
    # backend trees. A real UI fix (TSX/Dart) + regenerated release checksums was
    # wrongly blocked as "report-only" (measured on PR #857). Any runtime tree
    # added later needs a prefix here AND a regression test below.
    "frontend/",
    "mobile/",
    "scripts/ci/",
    "tests_v9/",
    # Architecture/guard tests live under tests/ (not tests_v9/). A test is exactly
    # the "test" category this guard's own message invites; without this prefix a PR
    # that adds real tests here + regenerates the bundle is wrongly blocked.
    "tests/",
    ".github/workflows/",
    "docs/runbooks/",
    "certification/evidence/",
    # runtime-verification/ holds functional probe PLANS and the identity-bridge map —
    # behavioural governance specs (what gets verified, how evidence propagates), not
    # reports. Changing them is substantive. (Live evidence under
    # runtime-verification/functional_evidence/ is gitignored and never committed.)
    "runtime-verification/",
    # SQL migrations are schema/data code — a migration-only fix (e.g. making a
    # DDL statement idempotent) is substantive, not a report. Without this, any
    # PR that only touches migrations/ + regenerates the release bundle would be
    # wrongly blocked as "report-only".
    "migrations/",
    # GATE-01 adjudications and policy are AUTHORIZATION INSTRUMENTS, not progress
    # reports: `gate01_frozen_path_guard` reads them to decide PASS/BLOCK on
    # physical-actuation code, so editing one changes what CI permits. This is the
    # same category as runtime-verification/ above — behavioural governance, not a
    # report — and the same reasoning the sahool-brain/ exemption already applies:
    # a MANDATED step must be landable without contriving an unrelated code change.
    #
    # Measured on #959: sealing a spent one-time grant `CONSUMED` after its merge is
    # a step the adjudication file itself calls "لازمة لا تحسينيّة", yet it touches
    # only that JSON + the brain + regenerated artifacts — so every seal was
    # report-only by classification and therefore unlandable. An unlandable mandated
    # step is how `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01` stays open forever.
    #
    # This does NOT weaken the control that matters: `branch_protection_contract_guard`
    # still demands code-owner review on this exact path, and it is a separate gate.
    "docs/architecture/gates/",
    # RUNTIME-CONFIG-TREE-NOT-SUBSTANTIVE-01 — **مقيسٌ على #1011:** `config/guardrail_feature_flags.py`
    # شيفرةُ تشغيلٍ يستوردها `services/ai_agronomist/runtime_guardrail_adapter.py` و
    # `services/sahool-platform/core/internal_orchestrator.py`، وتعديلُها + المصنوعاتُ التي
    # يُوجِبها المستودعُ (إعادة التوليد) كان يُصنَّف «report-only» — فالـPR تمرّ ما دامت
    # **لم تُصلِح** حزمتَها، وتُحجَب لحظةَ إصلاحها. صنفُ #857 بعينه (frontend «ليس كوداً»).
    #
    # الشجرةُ مجرودة لا مظنونة (12 ملفّاً): شيفرةُ تشغيلٍ وإعداداتُه (`.py` · `terrain_sources.yml`
    # لخدمة raster · `ai-model-runtimes/`) ومدخلاتُ حرّاسٍ سلوكيّة (تغطيةُ الواجهات وإعفاءاتُها ·
    # عقودُ الميزات · استثناءاتُ الأمن التي يقرؤها `waiver_expiry_guard`) — الصنفُ نفسه الذي
    # يُعفي `runtime-verification/` و`docs/architecture/gates/` أعلاه. وملفّاها المُسمَّيان
    # تقريراً (`evidence_lab_matrix.json` · `indicators_registry.json`) يبقيان تقريرَين:
    # `check_changed_files` يستبعد ما هو report-like من الجوهريّ **قبل** النظر إلى البادئة،
    # مُثبَتاً بـ`test_a_report_named_config_file_stays_report_like`.
    "config/",
)
SUBSTANTIVE_EXACT = {
    "requirements.services.direct.lock",
    # `REPORT_INDEX.md` **كان هنا وهو إعلانٌ ميّت** — مقيسٌ أثناء معالجة مراجعة Copilot ٣
    # على #1012: `check_changed_files` يستبعد ما هو report-like من الجوهريّ **قبل** أيّ
    # نظرٍ إلى هذه المجموعة، والاسمُ يحمل التلميح `REPORT` فـ`is_substantive` تُرجِع True
    # ولا يُستعمَل ذلك قطّ. إعلانٌ يصف حكماً لا يقع هو الصنفُ الذي يُطارَد في هذا
    # المستودع، فنُقِل إلى موضعه العامل: `REGENERATION_ARTIFACT_EXACT` أعلاه (يكتبه
    # `report_index_guard.py --write`)، وأُزيل من هنا بدل أن يبقى زينةً.
    # `.github/CODEOWNERS` هو **أداةُ التفويض** لا تقريرَ تقدّم — نفسُ صنف
    # `docs/architecture/gates/` أعلاه وبالحجّة عينها: خطوةٌ **واجبة** يجب أن تكون
    # قابلةً للهبوط بلا اختلاق تغييرٍ لا صلةَ له.
    #
    # ورسالةُ `branch_protection_contract_guard` تسمّيه بنفسها علاجاً:
    # «و`.github/CODEOWNERS` يُسمّي مالك `docs/architecture/gates/adjudications/**`».
    #
    # **مقيسٌ على #976:** إضافةُ هويّةٍ ثانيةٍ فيه — وهي ما يفكّ قفلَ
    # `GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01` — تمسّ هذا الملفَّ والمصنوعاتِ
    # المولَّدة وحدَها، فصُنِّفت «تقريراً فقط» و**سقطت**. أي أنّ العلاجَ الذي يطلبه
    # حارسٌ كان يمنعه حارسٌ آخر: قفلٌ لا يُفتَح بعملٍ صحيح، وهو الصنفُ الذي أُغلِق
    # هنا مرّتين قبله (`sahool-brain/` ثمّ `docs/architecture/gates/`).
    #
    # **وموضعُه هنا لا في `SUBSTANTIVE_PREFIXES` قصدٌ:** بادئةُ `.github/` كانت
    # ستجعل كلَّ ملفٍّ تحتها جوهريّاً بالمصادفة — قوالبَ ووسومَ إصدارٍ وغيرَها.
    # الاسمُ الكامل يُعفي ما قُصِد وحدَه.
    #
    # ولا يُضعِف هذا ما يهمّ: `branch_protection_contract_guard` ما زال يطلب مراجعةَ
    # مالكي الكود على مسار التفويضات، وهو بوّابةٌ منفصلة.
    ".github/CODEOWNERS",
}


def is_report_like(path: str) -> bool:
    p = Path(path)
    if p.suffix not in REPORT_SUFFIXES:
        return False
    # The sahool-brain/ knowledge base is mandated documentation (CLAUDE.md contributor
    # protocol, strict per-fact sourcing), NOT a certification/progress report — even when
    # a file name matches a report hint (e.g. the brain's own gaps/registry.md). Treating
    # it as docs lets the required end-of-session brain maintenance land without contriving
    # an unrelated code change; the guard still blocks the capabilities/ certification
    # registry and generated release reports.
    if path.startswith("sahool-brain/"):
        return False
    upper = p.name.upper()
    if any(hint in upper for hint in REPORT_NAME_HINTS):
        return True
    if path.startswith("certification/evidence/") or path.startswith("docs/runbooks/"):
        return False
    return p.suffix in {".csv", ".json"} and "generated" in p.name


def is_substantive(path: str) -> bool:
    if path in SUBSTANTIVE_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in SUBSTANTIVE_PREFIXES):
        return True
    return False


def is_regeneration_artifact(path: str) -> bool:
    if path in REGENERATION_ARTIFACT_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in REGENERATION_ARTIFACT_PREFIXES)


def is_plain_doc(path: str) -> bool:
    """وثيقةٌ بخطّ اليد: Markdown تحت `docs/` ليس تقريراً بالاسم، ولا جوهريّاً، ولا
    مصنوعَ توليد. الدماغُ ليس منها (مُعفًى بذاته ولا يُلوندِر غيرَه)، و`.md` خارج
    `docs/` ليس منها — الاستثناءُ على الدليل المقصود لا على اللاحقة."""
    if not path.startswith("docs/") or Path(path).suffix != ".md":
        return False
    if is_report_like(path) or is_substantive(path) or is_regeneration_artifact(path):
        return False
    return True


def check_changed_files(paths: list[str]) -> None:
    clean = [p.strip() for p in paths if p.strip()]
    if not clean:
        print("no_report_only_change_guard_no_changes")
        return
    substantive = [p for p in clean if is_substantive(p) and not is_report_like(p)]
    report_like = [p for p in clean if is_report_like(p)]
    plain_docs = [p for p in clean if is_plain_doc(p)]
    # «وثائقيّ فقط» حرفيّاً: لا شيء في التغيير سوى وثائق + الدماغ + مصنوعات إعادة
    # التوليد. أيُّ ملفٍّ آخر — تقريرٌ بخطّ اليد، سجلُّ اعتماد، `.md` خارج `docs/` —
    # يُخرِج التغييرَ من الاستثناء إلى الحكم القديم.
    #
    # والدماغُ **بلاحقته لا ببادئته** (مراجعة Copilot ٣ على #1012): البادئةُ الخام كانت
    # تُمرِّر `sahool-brain/extra.py` مع تقريرٍ مولَّد فيصير `outside_docs_only` فارغاً —
    # أي شيفرةٌ تحت الدماغ تعبر «وثائقيّاً». وعقدُ الدماغ في `sahool-brain/README.md`
    # يصفه قاعدةَ معرفةٍ Markdown، فالحدُّ يطابق العقدَ المُعلَن.
    outside_docs_only = [
        p
        for p in clean
        if not (
            is_plain_doc(p)
            or (p.startswith("sahool-brain/") and Path(p).suffix == ".md")
            or is_regeneration_artifact(p)
        )
    ]
    if report_like and not substantive:
        if plain_docs and not outside_docs_only:
            print("no_report_only_change_guard_docs_with_regenerated_artifacts")
            return
        raise SystemExit(
            "report-only change detected; include code/test/guard/workflow/runbook/evidence changes or mark as docs-only outside certification path"
        )
    print("no_report_only_change_guard_ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdin", action="store_true", help="read changed paths from stdin")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    if args.stdin:
        paths = sys.stdin.read().splitlines()
    else:
        paths = args.paths
    check_changed_files(paths)


if __name__ == "__main__":
    main()
