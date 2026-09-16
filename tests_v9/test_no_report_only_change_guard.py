import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.unit


def _run(*paths):
    return subprocess.run(
        [sys.executable, "scripts/ci/no_report_only_change_guard.py", *paths],
        text=True,
        capture_output=True,
    )


def test_report_only_change_is_blocked():
    result = _run("FOO_REPORT_20260709.md", "route_inventory.generated.json")
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_report_with_guard_change_is_allowed():
    result = _run("FOO_REPORT_20260709.md", "scripts/ci/example_guard.py")
    assert result.returncode == 0, result.stderr


def test_runbook_only_is_substantive_for_certification_path():
    result = _run("docs/runbooks/PRODUCTION_EVIDENCE_PACK.md")
    assert result.returncode == 0, result.stderr


def test_migration_change_is_substantive():
    # A migration fix (e.g. making DDL idempotent) accompanied only by the
    # regenerated release bundle must NOT be blocked as report-only — migrations
    # are schema/data code. Regression guard for the v205 idempotency fix PR.
    result = _run(
        "migrations/v205_irrigation_reservation_runtime_hardening.sql",
        "release/FILE_CHECKSUMS.sha256",
        "sahool-brain/gaps/registry.md",
    )
    assert result.returncode == 0, result.stderr


def test_architecture_test_change_is_substantive():
    # Architecture tests live under tests/ (not tests_v9/). Adding a real test plus
    # the regenerated mapping report must NOT be blocked as report-only.
    result = _run(
        "tests/architecture/test_runtime_identity_bridge.py",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr


def test_runtime_verification_spec_change_is_substantive():
    # A functional probe plan / identity-bridge map is a behavioural governance spec,
    # not a report; changing it alongside the regenerated bundle must be allowed.
    result = _run(
        "runtime-verification/functional_probes/sahool-platform.json",
        "runtime-verification/service_identity_map.json",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr


def test_brain_maintenance_is_docs_not_report_only():
    # The mandated end-of-session brain update — even the brain's own gaps/registry.md
    # (whose name matches the REGISTRY hint) plus the regenerated release manifest — is
    # documentation, not a certification report, and must NOT be blocked.
    result = _run(
        "sahool-brain/log.md",
        "sahool-brain/gaps/registry.md",
        "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
    )
    assert result.returncode == 0, result.stderr


def test_a_gate01_adjudication_seal_is_substantive_not_a_report():
    # Sealing a spent one-time GATE-01 grant `CONSUMED` after its merge is a step the
    # adjudication file itself calls mandatory — yet it touches only that JSON plus the
    # brain and regenerated artifacts. Without this prefix EVERY seal is report-only by
    # classification and therefore unlandable, which is how the one-shot lifecycle gap
    # stays open forever. Measured on #959.
    result = _run(
        "docs/architecture/gates/adjudications/GATE01-ADJ-2026-08-28-001.json",
        "sahool-brain/log.md",
        "docs/architecture/source_text_assertion_inventory.json",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr


def test_a_codeowners_identity_change_is_substantive_not_a_report():
    # `.github/CODEOWNERS` أداةُ تفويضٍ لا تقريرُ تقدّم. وإضافةُ هويّةٍ ثانيةٍ فيه هي
    # حرفيّاً العلاجُ الذي يطلبه `branch_protection_contract_guard` في رسالته — ومع
    # ذلك كانت تسقط هنا «تقريراً فقط»، لأنّها تمسّ هذا الملفَّ والمصنوعاتِ المولَّدة
    # وحدَها. أي أنّ حارساً كان يمنع علاجَ حارسٍ آخر. مقيسٌ على #976.
    result = _run(
        ".github/CODEOWNERS",
        "docs/architecture/source_text_assertion_inventory.json",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr


def test_the_codeowners_exemption_is_exact_not_a_prefix():
    # الاستثناءُ على **الاسم الكامل** لا على `.github/`: ملفٌّ آخرُ تحت `.github/`
    # لا يصير جوهريّاً بالمصادفة. وهو نفسُ تمييز `CVE-LIKE-BUT-NOT` في حارس
    # الادّعاءات — البادئةُ تبتلع ما لم يُقصَد.
    result = _run(
        ".github/CODEOWNERS_BACKUP.md",
        "docs/architecture/source_text_assertion_inventory.json",
    )
    assert result.returncode != 0, "ابتلع الاستثناءُ ملفّاً غيرَ مقصود"


def test_the_gate01_prefix_does_not_launder_an_unrelated_report():
    # The prefix is scoped to docs/architecture/gates/ — it must not turn a generated
    # capability report into a substantive change just because some other governance
    # file rode along. A report-only diff stays blocked.
    result = _run(
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
        "docs/architecture/source_text_assertion_inventory.json",
    )
    assert result.returncode != 0, "لُوندِر تقريرٌ مولَّد عبر البادئة الجديدة"


def test_capabilities_registry_report_still_blocked():
    # The exemption is scoped to sahool-brain/: the capabilities/ certification registry
    # and generated mapping reports remain report-like and blocked without substantive code.
    result = _run(
        "capabilities/registry/capabilities.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_frontend_code_with_generated_report_is_substantive():
    # False positive مقيس على PR #857: إصلاح UI حقيقيّ (TSX) + مصنوعات مولَّدة
    # حُجب «report-only» لأنّ التصنيف الأوّل لم يعرف frontend/ ككود.
    result = _run(
        "frontend/src/hooks/useApi.ts",
        "frontend/src/components/ds/theme.tsx",
        "release/FILE_CHECKSUMS.sha256",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr


def test_mobile_code_with_generated_report_is_substantive():
    # نفس العيب كان سيصيب PR يعدّل Flutter/mobile مع تقرير مولَّد فقط.
    result = _run(
        "mobile/lib/screens/field_ranking.dart",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr


def test_service_code_with_generated_report_is_substantive():
    result = _run(
        "services/sahool-platform/api/routers/nl_sql.py",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr


def test_plain_docs_outside_certification_path_pass():
    # وثيقة عاديّة بلا تلميح تقرير خارج مسار الاعتماد ليست report-like أصلاً.
    result = _run("docs/adr/0001-topology.md")
    assert result.returncode == 0, result.stderr


def test_a_plain_doc_with_regenerated_artifacts_is_docs_only():
    # DOCS-ONLY-SLICE-UNLANDABLE-UNDER-MANDATORY-REGENERATION-01 — مقيسٌ على #1012 حرفيّاً:
    # وثيقةُ تدقيقٍ بخطّ اليد + الدماغ + ما أعاد `regenerate_all_generated.sh` ختمَه.
    # الرأسُ يَعِد بـ«docs-only allowed»، والتصنيفُ كان يحجبها لأنّ الوثيقة لا تُرى
    # والمصنوعاتُ المولَّدة وحدها هي ما يُرى.
    result = _run(
        "docs/audits/DECISION_FABRIC_EXTERNAL_SOURCE_VERIFICATION_20260916.md",
        "sahool-brain/hot.md",
        "docs/architecture/source_text_assertion_inventory.json",
        "docs/capability-registry/generated/impact/impact_index_summary.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr
    assert "docs_with_regenerated_artifacts" in result.stdout


def test_a_hand_edited_report_beside_a_doc_stays_blocked():
    # الاستثناءُ للمصنوعات المولَّدة وحدها: تقريرٌ بخطّ اليد باسمٍ تقريريّ بجوار وثيقةٍ
    # عاديّة ليس مصنوعَ توليد — فالوثيقةُ لا تُلوندِره.
    result = _run("docs/adr/0002-notes.md", "FOO_REPORT_20260916.md")
    assert result.returncode != 0, "لُوندِر تقريرٌ بخطّ اليد عبر وثيقةٍ مرافِقة"
    assert "report-only" in result.stderr


def test_the_certification_registry_beside_a_doc_stays_blocked():
    # سجلُّ الاعتماد ليس مصنوعَ إعادة توليد — وإن عدّه `generated_write_targets.json`
    # هدفَ كتابة، لأنّه يُكتَب **جزئيّاً** (حقولٌ قانونيّة بخطّ اليد). وثيقةٌ مرافِقة
    # لا تجعله وثائقيّاً؛ ولذلك القائمةُ صريحة لا مشتقّة من ذلك الجرد.
    result = _run(
        "docs/adr/0002-notes.md",
        "capabilities/registry/capabilities.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_every_exact_regeneration_artifact_lands_with_a_doc_and_is_blocked_alone():
    """كلُّ مدخلٍ في `REGENERATION_ARTIFACT_EXACT` مُختبَرٌ بعينه في الاتّجاهين.

    مراجعة Copilot ٤ على #1012: القائمةُ كانت تُختبَر بعيّنةٍ منها، ونزعُ أيّ مدخلٍ
    غيرِ مُختبَر يُعيد الشريحةَ الوثائقيّة إلى «غيرِ قابلةٍ للهبوط» **صامتاً**. ولأنّ
    الحاجزَ صار يشمل المصنوعات (`gated`)، يُقاس الاتّجاهُ الثاني أيضاً: المدخلُ وحده
    محجوب. فالجدولُ يُقرَأ من المصدر لا يُنسَخ، فمدخلٌ جديد يدخل الاختبارَ تلقائيّاً.
    """
    import importlib.util as ilu

    spec = ilu.spec_from_file_location(
        "guard_under_test", ROOT / "scripts/ci/no_report_only_change_guard.py"
    )
    assert spec is not None and spec.loader is not None
    guard = ilu.module_from_spec(spec)
    spec.loader.exec_module(guard)

    entries = sorted(guard.REGENERATION_ARTIFACT_EXACT)
    assert entries, "قائمةُ المصنوعات فارغة — الاختبارُ يمرّ بلا قياس"
    for artifact in entries:
        with_doc = _run("docs/adr/0002-notes.md", artifact)
        assert with_doc.returncode == 0, f"{artifact} لا يهبط مع وثيقة: {with_doc.stderr}"
        alone = _run(artifact)
        assert alone.returncode != 0, f"{artifact} عبر وحده بلا وثيقة ولا شيفرة"
        assert "report-only" in alone.stderr


def test_an_artifact_riding_with_an_unapproved_path_is_blocked():
    # مراجعة Copilot ٥ على #1012: `artifacts_only` يشترط أن يكون **كلُّ** مسارٍ مصنوعاً،
    # فملفٌّ بخطّ اليد خارج `docs/` (ولا تلميحَ تقريرٍ في اسمه) يركب مع مصنوعٍ ويعبر.
    # المقيس: `RELEASE_NOTES_20260626.md` — مطلوبةٌ بعينها في `validate_release_package.py` —
    # مع `release/FILE_CHECKSUMS.sha256` كانت rc=0.
    result = _run("RELEASE_NOTES_20260626.md", "release/FILE_CHECKSUMS.sha256")
    assert result.returncode != 0, "مصنوعٌ عبر خلف ملفٍّ غيرِ مُقرّ"
    assert "report-only" in result.stderr


def test_substantive_code_still_lands_with_artifacts_after_the_third_arm():
    # الذراعُ الثالثة تُطلِق الحاجزَ لكنّ `substantive` تُخرِج التغييرَ — وإلّا صارت
    # البوّابةُ تحجب شيفرةً حقيقيّة أعادت توليدَ حزمتها.
    result = _run("services/sahool-platform/api/routers/fields.py", "release/FILE_CHECKSUMS.sha256")
    assert result.returncode == 0, result.stderr


def test_a_lone_generated_artifact_is_blocked_even_without_a_report_name():
    # مراجعة Copilot ٤ على #1012: `is_report_like` أسماءٌ ولاحقات، فهذان لا يطابقانها
    # وكانا يمرّان منفردَين بينما يَعِد العقدُ بحجبهما. المقياسُ صار واحداً.
    for artifact in ("release/FILE_CHECKSUMS.sha256", "release/SBOM_MINIMAL.json"):
        result = _run(artifact)
        assert result.returncode != 0, f"{artifact} عبر وحده"
        assert "report-only" in result.stderr


def test_regenerated_artifacts_without_a_doc_stay_blocked():
    # «exclusively generated reports» كما ينصّ رأسُ الحارس — بلا وثيقةٍ بخطّ اليد
    # تبقى المصنوعاتُ وحدها محجوبة (وهو ما تُثبِّته الحالاتُ الأقدم أيضاً).
    result = _run(
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
        "docs/architecture/source_text_assertion_inventory.json",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_a_brain_file_alone_does_not_launder_regenerated_artifacts_as_a_doc():
    # الدماغُ مُعفًى بذاته (`test_brain_maintenance_is_docs_not_report_only`) لكنّه ليس
    # «وثيقةً بخطّ اليد» بمعنى هذا الاستثناء — وإلّا صار كلُّ سطرٍ في `log.md` مفتاحاً
    # يفتح المصنوعاتِ المولَّدة. الحالةُ القائمة تمرّ بالإعفاء القديم لا بالجديد.
    result = _run(
        "sahool-brain/log.md",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    # مراجعة Copilot على #1012: غيابُ التشخيص الجديد وحده لا يُثبِت شيئاً — تنفيذٌ معطوب
    # يُرجِع `_ok` كان سيمرّ. الإثباتُ هو الحجبُ نفسه: رمزُ خروجٍ غيرُ صفريّ ورسالتُه.
    assert result.returncode != 0, "الدماغُ وحده لَوندَر تقريراً مولَّداً"
    assert "report-only" in result.stderr
    assert "docs_with_regenerated_artifacts" not in result.stdout


def test_a_hand_maintained_release_checklist_is_not_a_regeneration_artifact():
    # مراجعة Copilot على #1012: بادئةُ `release/` كانت تجعل كلَّ ملفٍّ تقريريّ هناك مصنوعَ
    # توليد — و`DEPLOYMENT_READINESS_CHECKLIST.md` قائمةٌ بخطّ اليد يطلبها
    # `validate_release_package.py` بعينها. وثيقةٌ مرافِقة لا تُلوندِرها.
    result = _run(
        "docs/adr/0002-notes.md",
        "release/DEPLOYMENT_READINESS_CHECKLIST.md",
    )
    assert result.returncode != 0, "لُوندِرت قائمةُ إصدارٍ بخطّ اليد عبر بادئة release/"
    assert "report-only" in result.stderr


def test_generator_written_release_files_are_regeneration_artifacts():
    # ما يكتبه `build_release_bundle.py` فعلاً (لا كلُّ `release/`) يبقى مصنوعَ توليد.
    result = _run(
        "docs/adr/0002-notes.md",
        "release/FILE_CHECKSUMS.sha256",
        "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode == 0, result.stderr
    assert "docs_with_regenerated_artifacts" in result.stdout


def test_runtime_config_code_with_regenerated_artifacts_is_substantive():
    # RUNTIME-CONFIG-TREE-NOT-SUBSTANTIVE-01 — قائمةُ ملفّات #1011 بعد علاجها الإلزاميّ حرفيّاً:
    # شيفرةُ تشغيلٍ تحت `config/` (يستوردها runtime_guardrail_adapter وinternal_orchestrator)
    # + وثيقةُ المقارنة + ما تُعيد `regenerate_all_generated.sh` ختمَه. كانت تُحجَب «report-only»
    # لأنّ `config/` لم تكن كوداً في التصنيف — وتمرّ عبر الجوهريّة لا عبر استثناء الوثائق.
    result = _run(
        "config/guardrail_feature_flags.py",
        "docs/architecture/DECISION_FABRIC_SOURCE_COMPARISON_20260916.md",
        "docs/architecture/source_text_assertion_inventory.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
        "release/FILE_CHECKSUMS.sha256",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "no_report_only_change_guard_ok"


def test_runtime_service_config_with_release_bundle_is_substantive():
    # إعدادُ تشغيلٍ غيرُ بايثونيّ تحت `config/` + الحزمة. المسارُ هنا **افتراضيّ** عمداً:
    # اسمُ ملفٍّ حقيقيّ كان يُدخِل كلمةَ نطاقٍ في شاهدِ حوكمةٍ فيصير دليلاً معجميّاً
    # لقدرةٍ لا يخدمها — والصنفُ مُغلَقٌ من جذره بتسمية هذا الملفّ شاهدَ حوكمة في
    # `capability_mapping_engine.META_GOVERNANCE_FILES`، وهذه الصياغةُ حزامٌ ثانٍ.
    result = _run("config/example_runtime_source.yml", "release/FILE_CHECKSUMS.sha256")
    assert result.returncode == 0, result.stderr


def test_a_baseline_carrying_a_hand_adjudicated_field_is_not_a_regeneration_artifact():
    # مراجعة Copilot ٣ على #1012: `fake_connection_debt.json` يحمل `proven_live` —
    # «قرارٌ مقيس لا مُشتقّ» يحمله المولِّد كما هو. لو عُدَّ مصنوعاً لَمرّ ادّعاءُ
    # إثباتٍ حيٍّ خلف وثيقةٍ ومصنوعات. وكذلك `brain_deferral_baseline.json` بـ`exempt_lines`
    # التي «تُقلَّص يدويّاً» ويثق بها `load_baseline`.
    for baseline in (
        "docs/architecture/fake_connection_debt.json",
        "docs/architecture/brain_deferral_baseline.json",
    ):
        result = _run(
            "docs/adr/0002-notes.md",
            baseline,
            "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
        )
        assert result.returncode != 0, f"لُوندِر حقلٌ مُحكَّمٌ بخطّ اليد عبر {baseline}"
        assert "report-only" in result.stderr


def test_a_non_markdown_file_under_the_brain_does_not_launder_artifacts():
    # مراجعة Copilot ٣ على #1012: البادئةُ الخام كانت تُمرِّر أيّ ملفّ تحت `sahool-brain/`.
    # عقدُ الدماغ Markdown، فشيفرةٌ هناك ليست «وثائقيّة».
    #
    # والوثيقةُ في القائمة **شرطُ تكذيب** لا زينة: بدونها يكون `plain_docs` فارغاً فلا
    # يُطرَق استثناءُ الوثائق أصلاً، فيمرّ الاختبارُ أخضرَ مع البادئة الخام وبدونها —
    # اختبارٌ لا يُكذِّب. مع الوثيقة يصير الفرقُ مرئيّاً: خامٌّ ⇒ يعبر، بلاحقةٍ ⇒ يُحجَب.
    result = _run(
        "docs/adr/0002-notes.md",
        "sahool-brain/extra.py",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode != 0, "شيفرةٌ تحت الدماغ عبرت بوصفها وثائقيّة"
    assert "report-only" in result.stderr


def test_a_report_named_config_file_stays_report_like():
    # البادئةُ لا تُلوندِر ملفّاً تقريريّاً بالاسم داخلها: `indicators_registry.json` يحمل
    # تلميح REGISTRY فيبقى تقريراً، والجوهريُّ يُستبعَد منه ما هو report-like قبل البادئة.
    result = _run(
        "config/indicators_registry.json",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode != 0, "لُوندِر تقريرٌ مُسمًّى عبر بادئة config/"
    assert "report-only" in result.stderr


def test_a_report_named_doc_is_not_a_plain_doc():
    # وثيقةٌ بخطّ اليد لكن باسمٍ تقريريّ تقريرٌ لا وثيقة — لا تفتح الاستثناء لنفسها.
    result = _run(
        "docs/audits/SOMETHING_REPORT_20260916.md",
        "docs/capability-registry/generated/mapping/CAPABILITY_MAPPING_REPORT.md",
    )
    assert result.returncode != 0
    assert "report-only" in result.stderr
