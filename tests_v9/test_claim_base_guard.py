"""كلّ ادّعاء يحمل أساسه — CLAIMS-WITHOUT-A-MEASURED-BASE-01.

الادّعاء المقيس يَبيت بحركة الشجرة تحته؛ والقرار لا يَبيت بها. وخلطُ الصنفين هو
كيف يصير رقمٌ مقيس عقداً دائماً لا يُعاد قياسه: `platform_extraction_map.json`
يقول `baseline_route_count = 633` وقائمة `routes` فيه تعدّ **635**، ولا قارئ لذلك
الحقل في المستودع كلّه.

يُبنى هنا `docs/architecture/` صناعيّ لكلّ حالة بدل تعديل الحقيقيّ، فالحارس يُقرأ
عبر معاملات جذره — واختبارٌ يقرأ الشجرة الحقيقيّة وحدها يكون قد قاس **حالتها**
لا **قاعدته**، وهو بالضبط عمى التكذيب الذي تكرّر ثلاث مرّات في هذه الجلسة.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "claim_base_guard", ROOT / "scripts/ci/claim_base_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)

REAL_REGISTRY = json.loads(
    (ROOT / "docs/architecture/claim_base_registry.json").read_text(encoding="utf-8")
)


def _debt_keys(section: dict) -> set[str]:
    return {k for k in section if not k.startswith("$")}


# ------------------------------------------------- السجلّ الحقيقيّ على الشجرة


def test_real_tree_passes() -> None:
    assert guard.check(REAL_REGISTRY) == []


def test_every_architecture_artifact_is_classified() -> None:
    classified = set(REAL_REGISTRY["measured"]) | set(REAL_REGISTRY["decided"])
    assert set(guard.declared_artifacts()) == classified


def test_the_two_classes_are_disjoint() -> None:
    assert not set(REAL_REGISTRY["measured"]) & set(REAL_REGISTRY["decided"])


def test_ceilings_are_tight_against_the_declared_debt() -> None:
    """سقفٌ فيه فسحة يسمح بمصنوعةٍ جديدة بلا أساس — وهو ما يُفترَض منعه."""
    assert len(_debt_keys(REAL_REGISTRY["unbased_debt"])) == (REAL_REGISTRY["unbased_debt_ceiling"])
    assert len(_debt_keys(REAL_REGISTRY["undated_debt"])) == (REAL_REGISTRY["undated_debt_ceiling"])


def test_debt_entries_are_classified_in_their_own_class() -> None:
    assert _debt_keys(REAL_REGISTRY["unbased_debt"]) <= set(REAL_REGISTRY["measured"])
    assert _debt_keys(REAL_REGISTRY["undated_debt"]) <= set(REAL_REGISTRY["decided"])


def test_the_registry_dates_its_own_judgement() -> None:
    """السجلّ نفسه قرارٌ، فيلزمه ما يلزم غيره — وإلّا استثنى نفسه من قاعدته."""
    assert "claim_base_registry.json" in REAL_REGISTRY["decided"]
    assert REAL_REGISTRY["adjudicated_on"]
    assert "claim_base_registry.json" not in _debt_keys(REAL_REGISTRY["undated_debt"])


# --------------------------------------------------------- مطابقة المفاتيح


def test_a_count_is_not_a_base() -> None:
    """`baseline_route_count` بادئته `baseline` — والمطابقة تامّة لا بادئة.

    لو قُبِلت البادئة لكان أكثر ملفّ في هذا المستودع دلالةً على العطل
    (`platform_extraction_map.json`) هو أوّل من يمرّ بوصفه مؤرَّخاً.
    """
    assert not guard._has_base({"baseline_route_count": 633}, ["measured_on", "baseline"])
    assert guard._has_base({"baseline": "fbe6048"}, ["measured_on", "baseline"])


def test_an_empty_stamp_is_not_a_base() -> None:
    assert not guard._has_base({"measured_on": "   "}, ["measured_on"])
    assert not guard._has_base({"measured_on": ""}, ["measured_on"])


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("9b0399d8 (على fde6f955، 2026-08-01)", "9b0399d8"),
        ("fbe6048+programmatic-closure-20260723", "fbe6048"),
        ("6c966bab + deterministic linker", "6c966bab"),
        ("branched from origin/main after PR #734", None),
        ("2026-07-31", None),  # تاريخ لا شجرة
        ("abc", None),  # أقصر من رمز
    ],
)
def test_extract_sha(stamp: str, expected: str | None) -> None:
    assert guard.extract_sha(stamp) == expected


def test_an_unknown_sha_reports_unresolvable_not_zero(tmp_path: Path) -> None:
    """رمزٌ ضاع بدمج squash يجب أن يُقال عنه «غير قابل للحلّ» لا «صفر التزام»."""
    assert guard.commits_since("0000000000000000000000000000000000000000") is None


# ------------------------------------------------- التكذيب على شجرة صناعيّة


def _fake_arch(tmp_path: Path, files: dict[str, dict]) -> Path:
    arch = tmp_path / "architecture"
    arch.mkdir()
    for name, data in files.items():
        (arch / name).write_text(json.dumps(data), encoding="utf-8")
    return arch


def _registry(**over) -> dict:
    base = {
        "measured": [],
        "decided": [],
        "measured_base_keys": ["measured_on", "baseline"],
        "decided_base_keys": ["adjudicated_on"],
        "unbased_debt": {},
        "undated_debt": {},
        "unbased_debt_ceiling": 0,
        "undated_debt_ceiling": 0,
    }
    base.update(over)
    return base


def test_unclassified_artifact_is_blocked(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"newcomer.json": {"measured_on": "abc1234"}})
    failures = guard.check(_registry(), arch)
    assert any("غير مصنَّفة" in f and "newcomer.json" in f for f in failures)


def test_measured_without_a_base_is_blocked(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"m.json": {"count": 207}})
    failures = guard.check(_registry(measured=["m.json"]), arch)
    assert any("قياس بلا أساس" in f for f in failures)


def test_measured_with_a_base_passes(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"m.json": {"measured_on": "abc1234", "count": 1}})
    assert guard.check(_registry(measured=["m.json"]), arch) == []


def test_declared_debt_excuses_a_missing_base(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"m.json": {"count": 207}})
    reg = _registry(measured=["m.json"], unbased_debt={"m.json": "سبب"}, unbased_debt_ceiling=1)
    assert guard.check(reg, arch) == []


def test_debt_that_gained_a_base_must_leave_the_list(tmp_path: Path) -> None:
    """الإنفاذ العكسيّ: قائمة دَين لا تتقلّص تُطيل نفسها بمداخل بائتة."""
    arch = _fake_arch(tmp_path, {"m.json": {"measured_on": "abc1234"}})
    reg = _registry(measured=["m.json"], unbased_debt={"m.json": "سبب"}, unbased_debt_ceiling=1)
    failures = guard.check(reg, arch)
    assert any("اكتسب ختم أساس" in f for f in failures)


def test_debt_growth_is_blocked_by_the_ceiling(tmp_path: Path) -> None:
    """بلا سقف، تُضاف المصنوعة الجديدة إلى الدَّين ويمرّ الحارس."""
    arch = _fake_arch(tmp_path, {"a.json": {"n": 1}, "b.json": {"n": 2}})
    reg = _registry(
        measured=["a.json", "b.json"],
        unbased_debt={"a.json": "سبب", "b.json": "جديد"},
        unbased_debt_ceiling=1,
    )
    failures = guard.check(reg, arch)
    assert any("والسقف" in f for f in failures)


def test_stale_debt_entry_is_blocked(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {})
    reg = _registry(unbased_debt={"gone.json": "سبب"}, unbased_debt_ceiling=1)
    failures = guard.check(reg, arch)
    assert any("مدخل بائت" in f for f in failures)


def test_classified_but_absent_artifact_is_blocked(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {})
    failures = guard.check(_registry(measured=["ghost.json"]), arch)
    assert any("لا وجود لها على القرص" in f for f in failures)


def test_a_file_cannot_be_both_measured_and_decided(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"x.json": {"measured_on": "abc1234"}})
    failures = guard.check(_registry(measured=["x.json"], decided=["x.json"]), arch)
    assert any("متنافيان" in f for f in failures)


def test_decided_without_an_adjudication_date_is_blocked(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"c.json": {"rule": "..."}})
    failures = guard.check(_registry(decided=["c.json"]), arch)
    assert any("قرار بلا تاريخ حكم" in f for f in failures)


def test_a_measured_stamp_does_not_satisfy_a_decision(tmp_path: Path) -> None:
    """الختمان ليسا مترادفين: «قِسته» ليست «حكمتُ فيه»."""
    arch = _fake_arch(tmp_path, {"c.json": {"measured_on": "abc1234"}})
    failures = guard.check(_registry(decided=["c.json"]), arch)
    assert any("قرار بلا تاريخ حكم" in f for f in failures)


def test_a_decision_stamp_does_not_satisfy_a_measurement(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"m.json": {"adjudicated_on": "2026-08-02"}})
    failures = guard.check(_registry(measured=["m.json"]), arch)
    assert any("قياس بلا أساس" in f for f in failures)


def test_dollar_comment_keys_are_not_treated_as_debt_entries(tmp_path: Path) -> None:
    arch = _fake_arch(tmp_path, {"m.json": {"measured_on": "abc1234"}})
    reg = _registry(measured=["m.json"], unbased_debt={"$comment": "شرح"})
    assert guard.check(reg, arch) == []


# ── GOV-01 · MEASURED-ON-SQUASH-FRESHNESS-01 ────────────────────────────────
# عقدُ دلالةٍ لا عقدُ سلوكٍ جديد: `measured_on` **إشارةُ إسناد** تقول «أيّ شجرةٍ
# قِيس عليها هذا الرقم»، وليست شهادةَ أنّ المصنوعة طازجة على الشجرة المنشورة.
#
# **والفرق ليس نظريّاً.** مع الدمج بـsquash يستحيل أن يحمل الختم الالتزامَ الناتج:
# الرقم يُقاس داخل الـPR، والالتزام النهائيّ لا يوجد بعد. فأساسُ `tenant_guc` قِيس
# على SHA فرعٍ ابتلعه الـsquash، والشجرة نظيفة و`verify_all_generated --check` يخرج
# بصفر في الحالين. أي أنّ الختم **قديمٌ بالبناء**، لا منحرفٌ بإهمال — ولذلك لا
# يُثبَّت هنا رقمُ SHA بعينه: قيمةٌ تتبدّل بكلّ دمج تكون هي نفسها ادّعاءً بلا أساس.
#
# **ولمَ لا يُحجَب على قِدَمه:** الحجب يجعل كلّ التزامٍ عاديّ يُبيت كلّ القياسات،
# فتتحوّل الـPRات إلى churn في مصنوعاتٍ لم يتغيّر معناها — وهو ما يُدرّب القارئ على
# تجاهل الحارس. والسجلّ يقولها في `staleness_is_reported_not_blocked`.
#
# **وسلطةُ الطزاجة قائمةٌ فعلاً وأقوى من أيّ ختم:** الحارس المالك **يُعيد الاشتقاق**
# من الشجرة الحاضرة ثمّ يقارن الناتج بالأساس المخزون. وهذا يشمل ما لا تشمله بصمةُ
# مدخلات: تغيُّرَ المولّد نفسه بمدخلاتٍ ثابتة.
#
# فالمرفوض ثلاثة: اشتراطُ `measured_on == HEAD` · تدويرُ SHA بعد كلّ squash ·
# وبصمةُ مدخلاتٍ مستقلّة **تُستخدَم سلطةَ طزاجةٍ موازيةً** لإعادة الاشتقاق (محرّكٌ
# ثانٍ للحقيقة، والأضعف منهما). والمرفوض هو **ذلك الدور** لا الإسنادُ المُعنوَن
# بالمحتوى في ذاته: بصمةٌ تُسجَّل إسناداً بجانب إعادةِ اشتقاقٍ تبقى هي الحاكمة
# مقبولةٌ متى أفادت — والقاعدةُ المحروسة هنا واحدة: **الحاكمُ إعادةُ الاشتقاق**.


def test_the_registry_declares_staleness_reported_not_blocked() -> None:
    """الدلالة مُعلَنة في السجلّ لا في نثرٍ خارجه — فتُقرأ حيث تُقرأ الأرقام."""
    registry = guard.load_registry()
    note = registry.get("staleness_is_reported_not_blocked")
    assert note, "دلالةُ البيات غير مُعلَنة في السجلّ"
    assert "ولا يحجب" in note


def test_a_stale_stamp_alone_is_not_a_failure(tmp_path: Path) -> None:
    """ختمٌ يشير إلى التزامٍ لا يوجد في هذه الشجرة **ليس** إخفاقاً.

    هذا هو العقد حرفيّاً: `check()` يحجب غياب الأساس لا قِدَمه. ولو انقلب يوماً،
    لصار كلّ دمجٍ بـsquash يُحمِّر المستودع بلا تغيّرٍ دلاليّ واحد.
    """
    arch = _fake_arch(tmp_path, {"m.json": {"measured_on": "0" * 40}})
    assert guard.check(_registry(measured=["m.json"]), arch) == []


def test_reporting_staleness_never_decides(tmp_path: Path) -> None:
    """`report_staleness` تطبع ولا تُرجِع حكماً — فلا يمكن ترقيتها إلى بوّابة سهواً."""
    arch = _fake_arch(tmp_path, {"m.json": {"measured_on": "0" * 40}})
    assert guard.report_staleness(_registry(measured=["m.json"]), arch, tmp_path) is None


def _tenant_guc_module():
    """حارسٌ **حقيقيّ** يُعيد الاشتقاق — لا محاكاةٌ تختبر نفسها."""
    spec = importlib.util.spec_from_file_location(
        "tenant_guc_for_gov01", ROOT / "scripts/ci/tenant_guc_scope_guard.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_stale_stamp_passes_when_re_derivation_still_matches(tmp_path, monkeypatch, capsys):
    """(أ) ختمٌ بائت + اشتقاقٌ مطابق ⇒ **PASS**.

    يُثبِت أنّ قِدَم الختم لا يُسقِط شيئاً ما دام الناتج المُعاد اشتقاقه هو نفسه —
    وهو الشرط الذي يجعل الدمج بـsquash ممكناً بلا churn.
    """
    module = _tenant_guc_module()
    offenders, _ = module.scan()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"measured_on": "0" * 40, "offenders": sorted(module._key(o) for o in offenders)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "BASELINE", baseline)
    monkeypatch.setattr(sys, "argv", ["tenant_guc_scope_guard.py", "--check"])
    assert module.main() == 0
    assert "tenant_guc_scope_ok" in capsys.readouterr().out


def test_a_stale_stamp_fails_when_re_derivation_diverges(tmp_path, monkeypatch, capsys):
    """(ب) ختمٌ بائت + اشتقاقٌ **مختلف** ⇒ **FAIL**.

    ونفسُ الختم في الحالتين — فالمتغيّر الوحيد هو الناتج. وهذا يفصل الخاصّيّتين:
    قِدَمُ الختم ليس سلطة، وإعادةُ الاشتقاق هي السلطة.
    """
    module = _tenant_guc_module()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"measured_on": "0" * 40, "offenders": ["ملفٌّ لا وجود له::سطر"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "BASELINE", baseline)
    monkeypatch.setattr(sys, "argv", ["tenant_guc_scope_guard.py", "--check"])
    assert module.main() == 1
    out = capsys.readouterr().out
    # الأساسُ هنا يخالف المشتقَّ في **الاتّجاهين**: يُدرِج موضعاً لا وجود له، ويُغفِل
    # المواضع القائمة. والحارس يعود من فرع «الجديد» أوّلاً — فالمرساة عليه لا على
    # «أساسٌ بائت» (فرع `settled` الذي لا يُبلَغ). وأوّل صياغةٍ هنا رست على الثاني فسقطت.
    assert "مواضع جديدة" in out, out
    # والسببُ المطبوع يسمّي المواضع، لا الختم: الختمُ إشارةُ إسناد لا حُجّة حجب.
    assert "0" * 40 not in out


def test_freshness_authority_is_re_derivation_not_the_stamp() -> None:
    """الشاهد السلوكيّ: حارسٌ مالكٌ يُعيد المسح في مسار الفحص، لا يقرأ الأساس وحده.

    `tenant_guc_scope_guard` نموذجٌ للصنف: `main()` يستدعي `scan()` **قبل** أن يتفرّع
    إلى `--check`، فيقارن المشتقَّ من الشجرة بالمخزون. ولو حُذِف ذلك النداء لصار
    الحارس يقارن الأساس بنفسه — فيمرّ أبداً، ويصير `measured_on` كلَّ ما يملكه
    القارئ. وهذا بالضبط ما يجعل الختم يُقرأ شهادةً وهو ليس كذلك.
    """
    source = (ROOT / "scripts/ci/tenant_guc_scope_guard.py").read_text(encoding="utf-8")
    main_at = source.index("def main(")
    # المرساة على **استهلاك** الراية (`args.check` / `args.generate`) لا على إعلانها:
    # `add_argument("--check")` يسبق `scan()` دائماً، فمرساةٌ عليه تقيس ترتيب argparse
    # لا ترتيب الاشتقاق — وكانت أوّل صياغةٍ هنا تسقط لهذا السبب بالضبط.
    # وأوّل استهلاكٍ هنا هو `args.generate`: هذا الحارس لا يقرأ `args.check` إطلاقاً —
    # الفحص هو الفرع الآخر. فمرساةٌ على `args.check` ترفع `ValueError` لا فشلاً مقروءاً،
    # وكانت الصياغة الثانية تفعل ذلك. المقيس هو **سبقُ الاشتقاق لأيّ تفرّع**.
    branch_at = source.index("args.generate", main_at)
    assert "scan()" in source[main_at:branch_at], (
        "مسارُ الفحص لم يعد يُعيد الاشتقاق من الشجرة — فالطزاجة صارت بلا سلطة، "
        "ولا يسدّ `measured_on` مكانها: إشارةُ إسناد لا شهادةُ تطابق."
    )
