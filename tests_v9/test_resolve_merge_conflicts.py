"""تصنيف حلّ التعارضات — MERGE-RESOLUTION-BY-HAND-LOSES-WORK-01.

الاختبار المحوريّ هنا (`test_resolved_append_only_survives_a_theirs_sweep`) **يُعيد
تمثيل الحادثة نفسها** لا وصفها: يحلّ ملفّاً إلحاقيّاً، ثمّ يُمرّر عليه بيده حلقةَ
``git checkout --theirs`` التي أتلفت العمل، ويؤكّد أنّ الحلّ نجا. فإن نُزِعت الفهرسة
من داخل حلقة الحلّ — وهي **العطل بعينه**: ملفّ محلول غير مُفهرَس يبقى في
``--diff-filter=U`` — تدوس الحلقة على الملفّ ويسقط الاختبار.

وهذا مقصود: فحصٌ يبحث عن ``git add`` في المصدر كان سيمرّ على سكربتٍ يستدعيها **بعد**
الحلقة، أي على العطل الأصليّ حرفيّاً. الخاصّيّة ليست «تُستدعى add» بل «لا يبقى ملفّ
محلول عرضةً لأمرٍ آليّ»، ولا تُقاس إلّا بتشغيل ذلك الأمر.

ويُختبَر انقلاب الجانبين أيضاً: `main` هو ``--theirs`` في الدمج و``--ours`` في إعادة
التأسيس. سكربتٌ يُثبّت جانباً يكون صحيحاً في عمليّة وخاطئاً في الأخرى بلا إبلاغ.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "resolve_merge_conflicts", ROOT / "scripts/ci/resolve_merge_conflicts.py"
)
rmc = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(rmc)

BRAIN_LOG = "sahool-brain/log.md"
GENERATED = "capability-registry/generated/mapping/service_map.json"
SOURCE = "services/sahool-platform/api/imagery_automation.py"


def _run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_repo(tmp_path: Path, base: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-b", "main")
    _run(repo, "config", "user.email", "t@example.com")
    _run(repo, "config", "user.name", "t")
    _run(repo, "config", "commit.gpgsign", "false")
    for rel, text in base.items():
        _write(repo, rel, text)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-m", "base")
    return repo


def _diverge(
    tmp_path: Path,
    base: dict[str, str],
    on_main: dict[str, str],
    on_feature: dict[str, str],
    operation: str = "merge",
) -> Path:
    """يبني تعارضاً حقيقيّاً عبر `merge` أو `rebase`، ويترك المستودع في وسطه."""
    repo = _make_repo(tmp_path, base)
    _run(repo, "checkout", "-b", "feature")
    for rel, text in on_feature.items():
        _write(repo, rel, text)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-m", "feature")

    _run(repo, "checkout", "main")
    for rel, text in on_main.items():
        _write(repo, rel, text)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-m", "main")

    _run(repo, "checkout", "feature")
    res = _run(repo, operation, "main", check=False)
    assert res.returncode != 0, f"كان يُفترَض أن يتعارض {operation}"
    return repo


# نصّ ملفّ إلحاقيّ: كلّ جانب يُلحق **مدخلاً مختلفاً** لا نسخةً من مدخل.
_LOG_BASE = "# سجلّ\n\n- مدخل قديم\n"
_LOG_MAIN = _LOG_BASE + "- مدخل من main\n"
_LOG_FEATURE = _LOG_BASE + "- مدخل من الفرع\n"


# ------------------------------------------------------------------ التصنيف


@pytest.mark.parametrize(
    "path,expected",
    [
        ("sahool-brain/log.md", "append_only"),
        ("sahool-brain/gaps/registry.md", "append_only"),
        ("sahool-brain/decisions/ledger.md", "append_only"),
        ("sahool-brain/hot.md", "append_only"),
        ("capability-registry/generated/mapping/x.json", "generated"),
        ("runtime-contracts/generated/runtime_contracts.json", "generated"),
        ("release/FILE_CHECKSUMS.txt", "generated"),
        ("docs/SERVICE_REGISTRY.md", "generated"),
        ("docs/inventory/route_inventory.csv", "generated"),
        ("something.sha256", "generated"),
        ("services/auth/main.py", "source"),
        ("tests_v9/test_x.py", "source"),
        ("scripts/ci/some_guard.py", "source"),
        # ملفّ دماغ ليس في القائمة ليس إلحاقيّاً — القائمة صريحة لا نمط مجلَّد،
        # لأنّ `sahool-brain/README.md` وثيقة تُحرَّر لا سجلّ يُلحَق.
        ("sahool-brain/README.md", "source"),
        ("sahool-brain/index.md", "source"),
    ],
)
def test_classify(path: str, expected: str) -> None:
    assert rmc.classify(path) == expected


# --------------------------------------------------- إبقاء الجانبين وترتيبهما


def test_merge_keeping_both_puts_main_first_on_merge() -> None:
    text = "head\n<<<<<<< HEAD\n- مدخل الفرع\n=======\n- مدخل main\n>>>>>>> main\ntail\n"
    merged, n = rmc.merge_keeping_both(text, "theirs")
    assert n == 1
    assert "<<<<<<<" not in merged and ">>>>>>>" not in merged and "=======" not in merged
    assert merged.index("مدخل main") < merged.index("مدخل الفرع")


def test_merge_keeping_both_inverts_when_main_is_ours() -> None:
    """في إعادة التأسيس يكون `main` هو ``ours`` — والترتيب ينقلب معه."""
    text = "head\n<<<<<<< HEAD\n- مدخل main\n=======\n- مدخل الفرع\n>>>>>>> x\ntail\n"
    merged, _ = rmc.merge_keeping_both(text, "ours")
    assert merged.index("مدخل main") < merged.index("مدخل الفرع")


def test_merge_keeping_both_resolves_every_block() -> None:
    block = "<<<<<<< HEAD\nأ{i}\n=======\nب{i}\n>>>>>>> main\n"
    text = "".join(block.format(i=i) for i in range(3))
    merged, n = rmc.merge_keeping_both(text, "theirs")
    assert n == 3
    assert "<<<<<<<" not in merged
    for i in range(3):
        assert f"أ{i}" in merged and f"ب{i}" in merged


def test_merge_keeping_both_is_a_noop_without_conflicts() -> None:
    merged, n = rmc.merge_keeping_both("لا تعارض هنا\n", "theirs")
    assert (merged, n) == ("لا تعارض هنا\n", 0)


# ------------------------------------- العلامة في بداية السطر فقط (نصّ ≠ علامة)


# نثرٌ حقيقيّ من `sahool-brain/log.md` — هذا المستودع **يصف حوادث التعارض
# بأسمائها**، فالذكر النصّيّ ليس حالةً نادرة بل مضمون الملفّ الذي يُحلّ.
_PROSE = [
    "- **جلسة موازية تركت علامات تعارض `<<<<<<< HEAD` في السجلّ.**\n",
    "- أُزيلت علامات `<<<<<<<`/`=======`/`>>>>>>>` وأُبقيت القيمة الآمنة.\n",
    "- النمط يطابق `=======` وحدها فيُنذر كاذباً على مسطرة setext.\n",
    "شرحٌ يذكر >>>>>>> origin/main وسط جملة لا في أوّلها.\n",
]


_REAL_BLOCK = "<<<<<<< HEAD\n- مدخل الفرع\n=======\n- مدخل main\n>>>>>>> origin/main\n"


@pytest.mark.parametrize("prose", _PROSE)
def test_prose_alone_is_not_a_conflict(prose: str) -> None:
    merged, n = rmc.merge_keeping_both(prose, "theirs")
    assert (merged, n) == (prose, 0)


@pytest.mark.parametrize("prose", _PROSE)
def test_prose_stays_outside_a_following_block(prose: str) -> None:
    """**هذه** هي التي تُميّز، والسابقة لا.

    النثر وحده لا يُكمِل مطابقةً (لا `=======` بعده) فيمرّ تحت النمط المعطوب
    وتحت السليم سواءً — أي أنّه يوثّق النيّة ولا يقيسها. والقياس أن يليه كتلةٌ
    حقيقيّة: النمط بلا مرساة يبدأ عند الذكر النصّيّ فيبتلع النثر داخل «ours»،
    والسليم يُبقيه **خارج** الكتلة في موضعه.
    """
    merged, n = rmc.merge_keeping_both(prose + _REAL_BLOCK, "theirs")
    assert n == 1
    head = merged.split("- مدخل main")[0]
    assert prose.strip() in head, "ابتُلِع النثر داخل الكتلة"
    assert merged.index("مدخل main") < merged.index("مدخل الفرع")


def test_prose_before_a_real_block_does_not_swallow_it() -> None:
    """الحادثة بعينها: ذكرٌ نصّيّ قبل كتلة حقيقيّة ابتلع ١٣٦٧ سطراً بينهما.

    النمط بلا `^` بدأ المطابقة عند الذكر النصّيّ في `log.md:3404`، فمدّ `.*?`
    إلى أوّل `=======` حقيقيّ على بُعد ٣٤٩ ألف حرف وعدّ كلّ ذلك «جانب ours».
    لم يضِع محتوى، لكنّ الترتيب انقلب و**خرج الملفّ بعلامة حقيقيّة داخله** —
    ولم يمسكها إلّا `conflict_marker_guard` بعد الحلّ، مصادفةً كالمرّة السابقة.
    """
    text = (
        "- شرحٌ قديم يذكر `<<<<<<< HEAD` نصّاً.\n"
        "- سطر لا علاقة له.\n"
        "<<<<<<< HEAD\n"
        "- مدخل الفرع\n"
        "=======\n"
        "- مدخل main\n"
        ">>>>>>> origin/main\n"
        "- ذيل.\n"
    )
    merged, n = rmc.merge_keeping_both(text, "theirs")
    assert n == 1
    assert "<<<<<<<" not in merged.replace("`<<<<<<< HEAD`", "")
    assert ">>>>>>>" not in merged
    # السطران السابقان يبقيان في موضعهما قبل المدخلين، لا يُبتلَعان.
    assert merged.index("شرحٌ قديم") < merged.index("سطر لا علاقة له")
    assert merged.index("سطر لا علاقة له") < merged.index("مدخل main")
    assert merged.index("مدخل main") < merged.index("مدخل الفرع")
    assert merged.index("مدخل الفرع") < merged.index("ذيل")


def test_a_real_block_ending_at_end_of_file_is_resolved() -> None:
    """`>>>>>>>` بلا سطر بعده — يقع حين يكون التعارض في ذيل ملفّ إلحاقيّ."""
    text = "<<<<<<< HEAD\nأ\n=======\nب\n>>>>>>> origin/main"
    merged, n = rmc.merge_keeping_both(text, "theirs")
    assert n == 1
    assert "<<<<<<<" not in merged
    assert merged.index("ب") < merged.index("أ")


# ------------------------------------------------------- السلوك على مستودع حيّ


def test_append_only_keeps_both_entries(tmp_path: Path) -> None:
    repo = _diverge(
        tmp_path, {BRAIN_LOG: _LOG_BASE}, {BRAIN_LOG: _LOG_MAIN}, {BRAIN_LOG: _LOG_FEATURE}
    )
    assert rmc.resolve(root=repo) == 0
    text = (repo / BRAIN_LOG).read_text(encoding="utf-8")
    assert "مدخل من main" in text
    assert "مدخل من الفرع" in text
    assert "<<<<<<<" not in text


def test_append_only_is_staged_in_the_same_iteration(tmp_path: Path) -> None:
    repo = _diverge(
        tmp_path, {BRAIN_LOG: _LOG_BASE}, {BRAIN_LOG: _LOG_MAIN}, {BRAIN_LOG: _LOG_FEATURE}
    )
    rmc.resolve(root=repo)
    assert rmc.conflicted_paths(repo) == []


def test_resolved_append_only_survives_a_theirs_sweep(tmp_path: Path) -> None:
    """الحادثة نفسها، مُعادة: حلٌّ صحيح ثمّ حلقة ``--theirs`` على «المتبقّي».

    الملفّ المُفهرَس خرج من ``--diff-filter=U`` فلم تره الحلقة. ولو أُخِّرت الفهرسة
    إلى ما بعد الحلقة — كما كان — لدهسته وضاع مدخلا الجانبين معاً.
    """
    repo = _diverge(
        tmp_path, {BRAIN_LOG: _LOG_BASE}, {BRAIN_LOG: _LOG_MAIN}, {BRAIN_LOG: _LOG_FEATURE}
    )
    assert rmc.resolve(root=repo) == 0

    # الحلقة المُتلِفة، حرفيّاً كما جرت.
    for path in rmc.conflicted_paths(repo):
        _run(repo, "checkout", "--theirs", "--", path, check=False)

    text = (repo / BRAIN_LOG).read_text(encoding="utf-8")
    assert "مدخل من main" in text, "دهست الحلقة على الحلّ — الفهرسة تأخّرت عن الحلّ"
    assert "مدخل من الفرع" in text, "ضاع مدخل الفرع — وهو ما لا يُبلِّغ عنه git"


def test_interruption_cannot_orphan_a_resolved_file(tmp_path: Path, monkeypatch) -> None:
    """**هذا** هو اختبار «الفهرسة في نفس التكرار» — والسابق ليس كذلك.

    أوّل تكذيب لهذه الخاصّيّة **مرّ أخضر**: نقلُ الفهرسة إلى حلقة تالية داخل الدالّة
    نفسها لم يُسقِط شيئاً، لأنّ كنسة `--theirs` في الاختبار تجري **بعد** عودة الدالّة
    — وعندها يكون كلّ شيء مُفهرَساً في الحالتين. أي أنّ ذلك الاختبار يقيس «هل انتهت
    الدالّة بفهرسة» لا «هل يبقى ملفّ محلول عارياً لحظةً».

    والفرق هو الحادثة بعينها: الخطر يقع **بين** الحلّ والفهرسة. فيُقطَع هنا الحلّ في
    منتصف الدفعة، ويُسأل عمّا حلّ بما سبق: مع الفهرسة داخل التكرار يخرج المُنجَز من
    ``--diff-filter=U`` فيَسلَم؛ ومع تأجيلها يبقى الاثنان عاريين لأيّ أمرٍ تالٍ.
    """
    registry = "sahool-brain/gaps/registry.md"
    repo = _diverge(
        tmp_path,
        {BRAIN_LOG: _LOG_BASE, registry: _LOG_BASE},
        {BRAIN_LOG: _LOG_MAIN, registry: _LOG_MAIN},
        {BRAIN_LOG: _LOG_FEATURE, registry: _LOG_FEATURE},
    )
    assert len(rmc.conflicted_paths(repo)) == 2

    real = rmc.merge_keeping_both
    calls: list[int] = []

    def interrupted(text: str, main_side: str) -> tuple[str, int]:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("انقطاع في منتصف الدفعة")
        return real(text, main_side)

    monkeypatch.setattr(rmc, "merge_keeping_both", interrupted)
    with pytest.raises(RuntimeError):
        rmc.resolve(root=repo)

    remaining = rmc.conflicted_paths(repo)
    assert len(remaining) == 1, (
        "الملفّ الأوّل حُلَّ على القرص وبقي في --diff-filter=U — "
        "أي عارياً لأيّ أمرٍ آليّ تالٍ. هذه هي الحادثة."
    )
    done = ({BRAIN_LOG, registry} - set(remaining)).pop()
    text = (repo / done).read_text(encoding="utf-8")
    assert "مدخل من main" in text and "مدخل من الفرع" in text


def test_source_conflict_halts_before_writing_anything(tmp_path: Path) -> None:
    """المصدر يُوقِف السكربت — و**قبل** أن يمسّ ملفّاً إلحاقيّاً في نفس الدفعة."""
    repo = _diverge(
        tmp_path,
        {BRAIN_LOG: _LOG_BASE, SOURCE: "x = 1\n"},
        {BRAIN_LOG: _LOG_MAIN, SOURCE: "x = 2\n"},
        {BRAIN_LOG: _LOG_FEATURE, SOURCE: "x = 3\n"},
    )
    assert rmc.resolve(root=repo) == 1
    assert "<<<<<<<" in (repo / BRAIN_LOG).read_text(encoding="utf-8")
    assert set(rmc.conflicted_paths(repo)) == {BRAIN_LOG, SOURCE}


def test_generated_takes_main_side(tmp_path: Path) -> None:
    repo = _diverge(
        tmp_path,
        {GENERATED: '{"n": 0}\n'},
        {GENERATED: '{"n": 1}\n'},
        {GENERATED: '{"n": 2}\n'},
    )
    assert rmc.resolve(root=repo) == 0
    assert (repo / GENERATED).read_text(encoding="utf-8") == '{"n": 1}\n'
    assert rmc.conflicted_paths(repo) == []


def test_rebase_inverts_which_side_is_main(tmp_path: Path) -> None:
    """نفس الشجرة، عمليّة أخرى: `main` صار ``ours`` — والمصنوعة تتبعه لا الجانب."""
    repo = _diverge(
        tmp_path,
        {GENERATED: '{"n": 0}\n'},
        {GENERATED: '{"n": 1}\n'},
        {GENERATED: '{"n": 2}\n'},
        operation="rebase",
    )
    assert rmc.in_progress_operation(repo) == "rebase"
    assert rmc.resolve(root=repo) == 0
    assert (repo / GENERATED).read_text(encoding="utf-8") == '{"n": 1}\n'


def test_halts_when_no_operation_is_in_progress(tmp_path: Path, monkeypatch) -> None:
    """تعارضٌ بلا دمج ولا إعادة تأسيس: الجانب مجهول، فالتخمين ممنوع."""
    repo = _make_repo(tmp_path, {BRAIN_LOG: _LOG_BASE})
    monkeypatch.setattr(rmc, "conflicted_paths", lambda root=repo: [BRAIN_LOG])
    assert rmc.resolve(root=repo) == 1
    assert (repo / BRAIN_LOG).read_text(encoding="utf-8") == _LOG_BASE


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    repo = _diverge(
        tmp_path, {BRAIN_LOG: _LOG_BASE}, {BRAIN_LOG: _LOG_MAIN}, {BRAIN_LOG: _LOG_FEATURE}
    )
    before = (repo / BRAIN_LOG).read_text(encoding="utf-8")
    assert rmc.resolve(root=repo, dry_run=True) == 0
    assert (repo / BRAIN_LOG).read_text(encoding="utf-8") == before
    assert rmc.conflicted_paths(repo) == [BRAIN_LOG]


def test_clean_tree_is_not_an_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {BRAIN_LOG: _LOG_BASE})
    assert rmc.resolve(root=repo) == 0


def test_a_sweep_owned_artifact_outside_generated_dirs_is_not_read_as_source():
    """`CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01` — مقيس على دمج #876.

    قائمةُ العلامات تُصنّف بالاسم، فأيّ مصنوعةٍ لا يحمل مسارُها `/generated/` ولا
    `.sha256` تُقرأ **مصدراً**. وثلاثةٌ تحت `docs/architecture/` تُعيد المكنسةُ
    توليدها فعلاً وقعت في ذلك، فأوقفت الأداةُ الدمجَ طالبةً إنساناً — والوقوف صحيح
    ومقصود، لكنّه كان عن سؤالٍ للمكنسة فيه جواب.

    والمقيس هنا **ملكيّة** لا اسم: كلٌّ من الاثنين المُسمَّيين أدناه يجب أن يبقى
    مُسجَّلاً بعلمِ توليدٍ في `verify_all_generated.py`. فإن زال التسجيل يوماً، سقط
    مبرّرُ تصنيفه ووجب مراجعتُه — بدل أن يبقى تصنيفاً بلا سبب.
    """
    import importlib.util
    import sys

    path = ROOT / "scripts/ci/verify_all_generated.py"
    spec = importlib.util.spec_from_file_location("_sweep", path)
    sweep = importlib.util.module_from_spec(spec)
    sys.modules["_sweep"] = sweep
    try:
        spec.loader.exec_module(sweep)
    except SystemExit:
        pass
    flags = getattr(sweep, "_GENERATE_FLAG", {})

    for artifact, owner in rmc.GENERATED_OWNERS.items():
        assert rmc.classify(artifact) == "generated", (
            f"{artifact} تُعيد المكنسة توليدها ويُقرأ مصدراً — الحلّ اليدويّ يُنتِج رقماً لم يحسبه أحد"
        )
        assert owner in flags, (
            f"{owner} لم يعد مُسجَّلاً بعلم توليد في المكنسة — سقط مبرّر تصنيف "
            f"{artifact}، فراجِعه بدل أن يبقى ادّعاءً"
        )


def test_a_hand_written_policy_document_is_never_widened_into_generated():
    """الحدُّ الذي يمنع التوسيع من أن يصير إتلافاً.

    جُرِّب اشتقاقٌ عامّ («أيّ مسار يُذكَر في مُولِّدٍ مُعلَم») فأعطى ١٩ مساراً، ومنها
    `guard_mutation_registry.json` — وثيقةُ سياسةٍ بخطّ اليد **يقرؤها** المحرّك ولا
    يكتبها. تصنيفُها «مولَّدة» يعني أخذَ جانب main ثمّ إعادة التوليد، أي إتلاف
    طفراتٍ مكتوبة بلا أن يُبلِّغ شيء. **الذِّكرُ ليس كتابةً.**

    فهذا الاختبار هو الوجه الآخر لأخيه: ذاك يمنع التصنيفَ الناقص، وهذا يمنع
    التصنيفَ الزائد — ووحدَهما معاً يجعلان التوسيع أماناً.
    """
    for policy in rmc.HAND_WRITTEN_POLICY:
        assert rmc.classify(policy) == "source", (
            f"{policy} وثيقةُ سياسةٍ بخطّ اليد؛ تصنيفُها مولَّدةً يُتلِف محتواها عند أوّل دمجٍ متعارض"
        )
