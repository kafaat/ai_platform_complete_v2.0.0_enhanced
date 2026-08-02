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
