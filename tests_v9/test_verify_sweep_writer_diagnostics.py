"""تكذيب تشخيص المكنسة — VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01.

كانت `verify_all_generated --fix` تقول «لم تثبت المصنوعات بعد الحدّ الأقصى للدورات»
وحدها. الرسالة تُقرأ **دورة تبعيّات**، فيذهب القارئ يبحث عن حلقة غير موجودة — بينما
السبب الفعليّ في الحادثة التي كشفتها أنّ ثلاثة كتّاب **لم يُستدعوا أصلاً**: غائبون عن
`_GENERATE_FLAG` رغم أنّ كلّاً منهم يُعلن علم كتابة في مصدره (`--apply`/`--write`).
فتمرّ الدورات الثلاث بلا تغيير، ويُبلَّغ عدم الثبات.

وكانت طباعة الصدق الموجودة أصلاً — «فُحِصت ولا تُولَّد آليّاً» — **غير قابلة للوصول
على مسار الفشل**: تقع بعد الحلقة، والفشل يعود `return 1` قبلها. أي أنّ المعلومة كانت
محسوبة ثمّ تُرمى في اللحظة التي تُحتاج فيها.

هذا الاختبار يقفل الأمرين: الخريطة تحمل الثلاثة بعلمهم الحقيقيّ، والكاشف يفرّق بين
«كاتب لم يُستدعَ» و«فحص بلا مولّد» — وهو التفريق الذي تقوم عليه رسالة التشخيص.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "verify_all_generated", ROOT / "scripts/ci/verify_all_generated.py"
)
sweep = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(sweep)

# الثلاثة الذين انحرفوا فعليّاً وكانوا غائبين عن الخريطة.
# وخمسة آخرون كشفتهم مراجعة الفرع الرئيسيّ لاحقاً — نفس الشكل بالضبط: يُعلن كلٌّ منهم
# `--generate`، والمكنسة تُشغّل `--check` عليه فيُبلِّغ انحرافاً، و`--fix` لا تستدعيه،
# ولا هو مُصنَّف «فحص بلا مولّد». أي انحراف بلا سبيل آليّ لإغلاقه.
#
# وهم سلسلة تحقّق تشغيليّ واحدة (خطّة الفحص ⇒ أهداف compose ⇒ إغلاق حوكمة التكامل ⇒
# جاهزيّة Path-3 ⇒ ابتلاع الأدلّة)، فغيابهم لا يظهر إلّا عند تغيير يمسّ عقود التشغيل —
# وعندها يظهر خمستهم دفعةً واحدة. هذا سبب وجيه لتثبيتهم بالاسم لا بالعدّ.
_REGRESSION = {
    "capability_linker.py": "--apply",
    "health_readiness_schema_guard.py": "--write",
    "route_residual_classification_guard.py": "--write",
    "runtime_verification_harness.py": "--generate",
    "compose_runtime_target_resolver.py": "--generate",
    "integration_runtime_governance_closure.py": "--generate",
    "path3_runtime_readiness_closure.py": "--generate",
    "runtime_evidence_ingestion.py": "--generate",
}


@pytest.mark.parametrize(("script", "flag"), sorted(_REGRESSION.items()))
def test_drifted_writers_are_in_the_map_with_their_real_flag(script: str, flag: str):
    """بعلمهم المُعلَن لا بعلم مُوحَّد — `--apply` ليست مرادفاً لـ`--generate`."""
    assert sweep._GENERATE_FLAG.get(script) == flag, (
        f"{script} يجب أن يُستدعى بـ{flag}؛ غيابه عن الخريطة يعني أنّه لا يُستدعى إطلاقاً "
        "فتُبلَّغ «لم تثبت» بلا سبب مفهوم."
    )


def test_detector_names_a_writer_that_declares_a_flag():
    """كاتب يُعلن علم كتابة ⇒ يُرصَد، فتقول الرسالة «أضِفه إلى الخريطة»."""
    assert sweep._declared_write_flags("scripts/ci/capability_linker.py") == ["--apply"]
    assert "--write" in sweep._declared_write_flags("scripts/ci/health_readiness_schema_guard.py")


def test_detector_stays_silent_for_a_check_only_guard():
    """فحص بلا مولّد ⇒ صفر علامات: انحرافه يدويّ بالتصميم، لا خلل في الأداة.

    بلا هذا التمييز تتحوّل رسالة التشخيص إلى اتّهام كلّ فحص بأنّه كاتب مفقود.
    """
    assert sweep._declared_write_flags("scripts/ci/assertion_presence_guard.py") == []


def test_detector_is_safe_on_a_missing_path():
    """مسار غير موجود ⇒ قائمة فارغة لا استثناء — التشخيص لا يُسقِط المكنسة نفسها."""
    assert sweep._declared_write_flags("scripts/ci/does_not_exist_at_all.py") == []


def test_every_mapped_writer_actually_declares_its_flag():
    """إنفاذ عكسيّ: إدخال في الخريطة بعلم لا يُعلنه السكربت ⇒ استدعاء فاشل صامت.

    العلم الفارغ مقصود (تشغيل عارٍ يكتب)، فيُستثنى صراحةً.
    """
    mismatched = []
    for script, flag in sweep._GENERATE_FLAG.items():
        if not flag:
            continue
        rel = next(
            (f"{d}/{script}" for d in sweep._SCRIPT_DIRS if (ROOT / d / script).exists()),
            None,
        )
        if rel is None:
            continue
        if flag not in sweep._declared_write_flags(rel):
            mismatched.append(f"{rel}: الخريطة تقول {flag} والمصدر لا يُعلنه")
    assert not mismatched, "علم في الخريطة لا يطابق مصدر السكربت:\n  " + "\n  ".join(mismatched)
