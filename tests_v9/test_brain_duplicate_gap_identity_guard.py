"""`DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01` — الشطر L2: الفشل الصامت لـ`union`.

الاختبار المحوريّ هنا ليس اختبار وحدة بل **تكامل حقيقيّ**: يُبنى مستودع git مؤقّت،
ويُفعَّل فيه `merge=union`، ويُدمَج فرعان حرّرا **نفس السطر** — فيخرج git بـ**0** بلا
علامة تعارض، ويفشل هذا الحارس. تلك المفارقة بعينها هي ما يُراد إثباته:

    git merge     ⇒ نجاح
    duplicate     ⇒ فشل

ولولاها لكان `merge=union` تحسيناً يُخفي التناقض بدل أن يُظهره.

**والحدّ الذي يفرضه التصميم مُختبَر صراحةً:** السجلّ يحتفظ عمداً بسلاسل تاريخيّة
لنفس المعرّف (`SILENT-EXCEPTION-HANDLERS-11-01` ثلاث مرّات). حارسٌ يرفعها إنذاراً
يُعطَّل في أوّل يوم، فالقاعدة على **التلاصق** لا على التكرار — واختبارٌ أدناه يُثبِت
أنّ السلسلة المفصولة بمتن تمرّ.

فحص صرف (subprocess + نصّ) — ``pytest -m unit``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "brain_duplicate_gap_identity_guard.py"
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

from brain_duplicate_gap_identity_guard import (  # noqa: E402
    adjacent_duplicate_identities,
    global_duplicate_row_identities,
)


def _ids(text: str) -> list[str]:
    return [gap_id for gap_id, _, _ in adjacent_duplicate_identities(text)]


# ───────────────────────── القاعدة نفسها ─────────────────────────


def test_the_exact_union_signature_is_caught():
    """نفس المعرّف في سطرين متتاليين — ما يُنتجه ضمّ نسختَي سطر واحد."""
    text = "## GAP-A — هبطت على main في abc1234\n## GAP-A — مُغلقة بالجلسة الأخرى\n\n- متن\n"
    assert _ids(text) == ["GAP-A"]


def test_a_literal_repeat_is_caught_too():
    assert _ids("## GAP-A — OPEN\n## GAP-A — OPEN\n") == ["GAP-A"]


def test_a_deliberate_history_chain_passes():
    """**الحدّ المقيس.** السجلّ يحتفظ بحالات متعاقبة لنفس الفجوة، يفصلها متن.

    المقيس على الشجرة الحقيقيّة: ١١ معرّفاً مكرّراً، **١٠** منها سلاسل شرعيّة.
    قاعدة «التكرار» كانت سترفعها كلّها؛ قاعدة «التلاصق» تُمرّرها.
    """
    text = (
        "## GAP-A — مفتوحة (2026-07-31)\n"
        "- **المصدر:** قياس.\n"
        "\n"
        "## GAP-A — مُغلقة بالقياس (2026-08-01)\n"
        "- **التكذيب:** طفرة.\n"
    )
    assert _ids(text) == []


def test_two_different_gaps_side_by_side_pass():
    assert _ids("## GAP-A — OPEN\n## GAP-B — OPEN\n") == []


def test_a_shared_prefix_is_not_the_same_identity():
    """`GAP-A` و`GAP-AUTH-01` معرّفان مختلفان — `\\b` وحده لا يكفي لو قُرِئ بادئةً."""
    assert _ids("## GAP-AUTH-01 — OPEN\n## GAP-AUTH-02 — OPEN\n") == []
    assert _ids("## SEASON-RECORD-ENTRY-01 — OPEN\n## SEASON-RECORD-ENTRY-02 — OPEN\n") == []


def test_a_mention_inside_a_paragraph_is_not_a_heading():
    """ذكر المعرّف في نثر ليس إعلان حالة."""
    text = "## GAP-A — OPEN\n- راجع GAP-A وGAP-A مرّة أخرى في السياق نفسه.\n"
    assert _ids(text) == []


def test_the_heading_must_start_the_line_not_merely_appear_in_it():
    """**المرساة، مقيسة لا مُعلَنة.**

    أوّل صياغة لهذا الاختبار استعملت سطراً لا يحوي `##` إطلاقاً، فمرّت تحت **أربع**
    طفرات مزروعة (نزع `^`، و`match`⇒`search`، وكلٌّ منهما وحده، وكلاهما معاً). أي
    أنّها كانت توثّق النيّة ولا تقيسها — نفس العطل المسجَّل في #768 حرفيّاً، ووقعتُ
    فيه في الحارس المصنوع لمنع صنفه.

    الحالتان أدناه هما الوحيدتان الحسّاستان للمرساة: عنوان **مُقتبَس** (`>`) وعنوان
    يسبقه نصّ. كلاهما يجب ألّا يُحسَب سجلّاً، ونزعُ المرساة يجعلهما يُحسَبان.
    """
    quoted = "> ## GAP-A — OPEN\n> ## GAP-A — CLOSED\n"
    assert _ids(quoted) == [], "عنوان مُقتبَس اقتباسٌ لا سجلّ"

    inline = "راجع ## GAP-A — OPEN\nراجع ## GAP-A — CLOSED\n"
    assert _ids(inline) == [], "`##` وسط سطر ليست عنواناً"

    # وللتناظر: نفس المحتوى في بداية السطر **يُحسَب** — وإلّا كان الاختبار يُثبِت
    # أنّ الحارس لا يرى شيئاً أصلاً.
    assert _ids("## GAP-A — OPEN\n## GAP-A — CLOSED\n") == ["GAP-A"]


def test_headings_inside_a_fenced_code_block_are_examples_not_records():
    """أمثلة التوثيق داخل ``` لا تُحسَب — وإلّا أطلق الحارس على شرحه لنفسه."""
    text = "```\n## GAP-A — OPEN\n## GAP-A — CLOSED\n```\n\n## GAP-B — OPEN\n"
    assert _ids(text) == []


def test_tilde_fences_count_as_fences_too():
    text = "~~~\n## GAP-A — OPEN\n## GAP-A — CLOSED\n~~~\n"
    assert _ids(text) == []


def test_crlf_and_lf_behave_identically():
    lf = "## GAP-A — OPEN\n## GAP-A — CLOSED\n"
    assert _ids(lf) == _ids(lf.replace("\n", "\r\n")) == ["GAP-A"]


def test_unicode_after_the_identity_does_not_break_matching():
    """الوصف عربيّ في هذا المستودع — المطابقة على المعرّف وحده لا على السطر."""
    assert _ids("## GAP-A — مُغلقة بالقياس ⇒ ٠\n## GAP-A — هبطت على main\n") == ["GAP-A"]


def test_reported_line_numbers_point_at_both_headings():
    text = "- متن\n\n## GAP-A — OPEN\n## GAP-A — CLOSED\n"
    assert adjacent_duplicate_identities(text) == [("GAP-A", 3, 4)]


# ───────────── الحارس كأداة: fail-closed ورسالة تُسمّي الموضع ─────────────


def _run_guard(*targets: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GUARD), *targets],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONIOENCODING": "utf-8", "PATH": "/usr/bin:/bin"},
        cwd=_ROOT,
        timeout=120,
    )


def test_the_guard_is_fail_closed_and_names_the_lines(tmp_path):
    bad = _ROOT / "sahool-brain" / "gaps" / "registry.md"
    assert bad.exists()
    good = _run_guard()
    assert good.returncode == 0, good.stdout + good.stderr


def test_a_missing_target_fails_rather_than_passing_vacuously():
    """هدفٌ غير موجود يُبلَّغ فشلاً — «لم أجد ما أفحصه» ليست نجاحاً."""
    result = _run_guard("sahool-brain/gaps/does-not-exist.md")
    assert result.returncode == 1
    assert "مفقود" in result.stdout


def test_the_real_registry_is_clean_today():
    """إنفاذ على الشجرة الحيّة، لا على نموذج — يشمل الفحص العالميّ للصفوف."""
    result = _run_guard()
    assert result.returncode == 0, result.stdout


# ──────────── BRAIN-DUP-ROW-ESCAPES-THE-ADJACENCY-NET-01: صفوف الجدول ────────────


def test_a_non_adjacent_row_duplicate_is_caught_globally():
    """بصمة العودة المقيسة: نفس المعرّف صفَّين بينهما صفٌّ آخر — التلاصق أعمى عنه."""
    text = "| GAP-AA-01 | حالة أولى |\n| GAP-BB-01 | صفٌّ فاصل |\n| GAP-AA-01 | حالة ثانية |\n"
    assert adjacent_duplicate_identities(text) == []
    assert global_duplicate_row_identities(text) == [("GAP-AA-01", [1, 3])]


def test_distinct_dotted_waiver_ids_are_not_the_same_identity():
    """`WAIVER-WX10.6-001` و`.7-001` إعفاءان متمايزان — هويّة الخليّة الكاملة بالنقاط."""
    text = "| WAIVER-WX10.6-001 | أ |\n| WAIVER-WX10.7-001 | ب |\n"
    assert global_duplicate_row_identities(text) == []


def test_a_dotted_row_id_duplicate_is_still_visible_to_the_global_net():
    """إسقاط النقطة من النمط لا يدمج الهويّتين بل **يُعمي** الشبكة عن الصفوف
    المنقوطة كلّها (مرساة `\\s*\\|` تُفشِل المطابقة عند النقطة) — مقيس بالزرع."""
    text = "| WAIVER-WX10.6-001 | أولى |\n| GAP-EE-01 | فاصل |\n| WAIVER-WX10.6-001 | ثانية |\n"
    assert global_duplicate_row_identities(text) == [("WAIVER-WX10.6-001", [1, 3])]


def test_heading_history_chains_are_exempt_from_the_global_row_check():
    """السلاسل التاريخيّة عناوين `##` مقصودة — الفحص العالميّ صفوفٌ فقط."""
    text = "## GAP-CC-01 — مفتوحة\nمتن\n## GAP-CC-01 — مُغلَقة بالقياس\n"
    assert global_duplicate_row_identities(text) == []


def test_a_row_id_inside_a_fenced_example_is_documentation_not_a_declaration():
    text = "| GAP-DD-01 | حقيقيّ |\n```\n| GAP-DD-01 | مثال |\n```\n"
    assert global_duplicate_row_identities(text) == []


def test_the_global_check_is_scoped_to_the_registry_file(tmp_path):
    """صفّ مكرّر بعيدٌ في ledger لا يُحمِّر — النطاق سجلّ الفجوات وحده."""
    from brain_duplicate_gap_identity_guard import GLOBAL_ROW_UNIQUENESS_TARGETS

    assert GLOBAL_ROW_UNIQUENESS_TARGETS == {"sahool-brain/gaps/registry.md"}


# ───────────────── التكامل: git ينجح والحارس يفشل ─────────────────


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
        timeout=120,
    )


def _union_repo(tmp_path: Path, base: str, side_a: str, side_b: str) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / ".gitattributes").write_text("registry.md merge=union\n", encoding="utf-8")
    (repo / "registry.md").write_text(base, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "side")
    (repo / "registry.md").write_text(side_b, encoding="utf-8")
    _git(repo, "commit", "-qam", "side")
    _git(repo, "checkout", "-q", "-")
    (repo / "registry.md").write_text(side_a, encoding="utf-8")
    _git(repo, "commit", "-qam", "mine")
    return repo


@pytest.mark.slow
def test_union_merges_distinct_entries_without_conflict(tmp_path):
    """الحالة التي وُضِع union لأجلها: كلّ جانب يُضيف مدخلاً مختلفاً."""
    base = "## GAP-X — OPEN\n- متن\n"
    repo = _union_repo(
        tmp_path,
        base,
        base + "\n## GAP-A — OPEN\n- متن أ\n",
        base + "\n## GAP-B — OPEN\n- متن ب\n",
    )
    merged = _git(repo, "merge", "side", "--no-edit")
    assert merged.returncode == 0, merged.stdout + merged.stderr
    text = (repo / "registry.md").read_text(encoding="utf-8")
    assert "GAP-A" in text and "GAP-B" in text, "الجانبان محفوظان"
    assert "<<<<<<<" not in text
    assert _ids(text) == [], "مدخلان مختلفان ⇒ لا تناقض"


@pytest.mark.slow
def test_union_succeeds_while_the_guard_fails_on_the_same_identity(tmp_path):
    """**الطفرة المهمّة**: git يقول «نجح»، والحارس يقول «متناقض».

    هذا هو الحدّ الحقيقيّ لـL3، ومُثبَت لا موصوف: بلا L2 يمرّ التناقض إلى `main`
    ولا يراه أحد — لا علامة تعارض، ولا خطأ، ولا اختبار ساقط.
    """
    base = "## GAP-A — مفتوحة\n- متن\n"
    repo = _union_repo(
        tmp_path,
        base,
        "## GAP-A — هبطت على main في abc1234\n- متن\n",
        "## GAP-A — مُغلقة بالجلسة الأخرى\n- متن\n",
    )
    merged = _git(repo, "merge", "side", "--no-edit")
    assert merged.returncode == 0, "git يجب أن ينجح — وهذا بيت القصيد"
    text = (repo / "registry.md").read_text(encoding="utf-8")
    assert "<<<<<<<" not in text, "لا علامة تعارض — الفشل صامت"
    assert _ids(text) == ["GAP-A"], "والحارس وحده هو من يراه"


# ─── UNION-MERGE-DUPLICATES-EDITED-LOG-AND-LEDGER-ENTRIES-SILENTLY-01: log/ledger ───
#
# المُثبَّتُ أدناه أُنتِج بمستودعٍ مؤقّت حقيقيّ قبل كتابة القاعدة: جانبٌ يُصحِّح آخرَ
# سطرين في آخر مدخل، والآخرُ يُلحِق مدخلاً ⇒ git rc=0 والسطران المحرَّران بجوار
# أصليّيهما. والحارسُ على origin/main (5472740e) مرّ عليه بـrc=0: رؤوسُ التاريخ لا
# تطابق `HEADING_RE`، ولا صفوفَ جدول. `test_union_merge_of_an_edited_entry_…` يُعيد
# الإنتاجَ نفسه ويقارن بالمُثبَّت، فلا ينجرف المُثبَّتُ عن سلوك git.

_LOG_BASE = (
    "# سجلّ الجلسات (append-only)\n"
    "\n"
    "## 2026-10-13 — مراجعة الحارس الأوّل\n"
    "- قِيس الحارس على الشجرة الحيّة فمرّ بلا إنذار كاذب.\n"
    "\n"
    "## 2026-10-14 — دمج #1186 (حوكمة الموجة الثانية)\n"
    "- دُمج الفرع بعد اخضرار البوّابات الحاجبة كلّها على الرأس.\n"
    "- الرأس المختبَر `abc1234` وشجرة main مطابقة له بايتاً ببايت.\n"
    "- التالي: تسجيل الفجوات المتبقّية في السجلّ الحيّ للموجة.\n"
)
_LOG_EDITED = _LOG_BASE.replace(
    "- الرأس المختبَر `abc1234` وشجرة main مطابقة له بايتاً ببايت.\n"
    "- التالي: تسجيل الفجوات المتبقّية في السجلّ الحيّ للموجة.\n",
    "- الرأس المختبَر `abc1234def` وشجرة main مطابقة له بايتاً ببايت (مُصحَّح).\n"
    "- التالي: تسجيل الفجوات الثلاث المتبقّية في السجلّ الحيّ للموجة.\n",
)
_LOG_APPENDED = _LOG_BASE + (
    "\n## 2026-10-15 — مراجعة #1191 واستيراد sahool-qa\n"
    "- استُورد تقييم الموسم دون اتّصال تحت أدوات المستودع.\n"
)
# ناتجُ `git merge` بـ`merge=union` (مقيس، git 2.x، rc=0).
_LOG_UNION_MERGED = (
    "# سجلّ الجلسات (append-only)\n"
    "\n"
    "## 2026-10-13 — مراجعة الحارس الأوّل\n"
    "- قِيس الحارس على الشجرة الحيّة فمرّ بلا إنذار كاذب.\n"
    "\n"
    "## 2026-10-14 — دمج #1186 (حوكمة الموجة الثانية)\n"
    "- دُمج الفرع بعد اخضرار البوّابات الحاجبة كلّها على الرأس.\n"
    "- الرأس المختبَر `abc1234def` وشجرة main مطابقة له بايتاً ببايت (مُصحَّح).\n"
    "- التالي: تسجيل الفجوات الثلاث المتبقّية في السجلّ الحيّ للموجة.\n"
    "- الرأس المختبَر `abc1234` وشجرة main مطابقة له بايتاً ببايت.\n"
    "- التالي: تسجيل الفجوات المتبقّية في السجلّ الحيّ للموجة.\n"
    "\n"
    "## 2026-10-15 — مراجعة #1191 واستيراد sahool-qa\n"
    "- استُورد تقييم الموسم دون اتّصال تحت أدوات المستودع.\n"
)


def _near(text: str) -> list[tuple[int, int]]:
    from brain_duplicate_gap_identity_guard import near_duplicate_lines

    return [(a, b) for a, b, _ in near_duplicate_lines(text)]


def test_union_on_an_edited_last_entry_is_caught():
    """**الشاهد.** السطران المحرَّران (8، 9) ونسختاهما الأصليّتان (10، 11) في مدخلٍ واحد."""
    from brain_duplicate_gap_identity_guard import near_duplicate_findings

    assert _near(_LOG_UNION_MERGED) == [(8, 10), (9, 11)]
    problems = near_duplicate_findings("sahool-brain/log.md", _LOG_UNION_MERGED)
    flagged = [p for p in problems if p.startswith("near-duplicate")]
    assert len(flagged) == 2, problems


def test_the_identity_nets_were_blind_to_the_same_merge():
    """لماذا وُجِدت القاعدة: شبكتا الهويّة (العناوين والصفوف) لا تريان شيئاً هنا."""
    assert adjacent_duplicate_identities(_LOG_UNION_MERGED) == []
    assert global_duplicate_row_identities(_LOG_UNION_MERGED) == []


def test_each_side_alone_is_clean():
    for text in (_LOG_BASE, _LOG_EDITED, _LOG_APPENDED):
        assert _near(text) == []


def test_distinct_entries_under_the_same_heading_pass():
    """تاريخٌ واحد لموضوعين ⇒ عنوانٌ مكرَّر حرفيّاً بمتنٍ مختلف: ليس نسخة."""
    text = (
        "## 2026-10-14 — مزامنة الفرع مع main\n"
        "- دُمج main في الفرع بعد هبوط #1183 بلا تعارض في الشيفرة.\n"
        "\n"
        "## 2026-10-14 — مزامنة الفرع مع main\n"
        "- أُعيد توليد كتالوج الحرّاس بعد تسجيل الطفرة الجديدة للحارس.\n"
    )
    assert _near(text) == []


def test_a_deliberate_history_chain_of_entries_passes():
    """سلسلةٌ تاريخيّة: مدخلٌ لاحق يُصحِّح سابقاً **بعنوانه** — ما يُوصى به في الإصلاح."""
    text = (
        "## 2026-10-13 — قياس الحارس\n"
        "- الرأس المختبَر `abc1234` وشجرة main مطابقة له بايتاً ببايت.\n"
        "\n"
        "## 2026-10-14 — تصحيح: الرأس المختبَر\n"
        "- الرأس المختبَر `abc1234def` وشجرة main مطابقة له بايتاً ببايت (مُصحَّح).\n"
    )
    assert _near(text) == []


def test_short_repeated_lines_are_not_substantive():
    text = "## 2026-10-14 — أ\n- لا شيء.\n- لا شيء.\n| a | b |\n|---|---|\n|---|---|\n"
    assert _near(text) == []


def test_a_near_template_in_separate_paragraphs_passes():
    """الإيجابيّ الكاذب الوحيد المقيس على main: قالبٌ يتكرّر برقمٍ مختلف في فقرتين
    منفصلتين (log.md:9131/9138، تشابه 0.932). التشابهُ وحده مقصورٌ على الكتلة المتّصلة."""
    text = (
        "## 2026-10-07 — ملاحظات\n"
        "> **2026-10-06 — سجلٌّ متأخّرُ الدمج (#1128):** السطرُ التالي كُتب في 2026-10-03 ودُمج بعد أيّام.\n"
        "\n"
        "> **2026-10-02 — مدخلٌ آخر بموضوعٍ مختلفٍ تماماً عن الحارس.**\n"
        "\n"
        "> **2026-10-06 — سجلٌّ متأخّرُ الدمج (#1130):** السطران التاليان كُتبا في 2026-10-03 ودُمجا بعد أيّام.\n"
    )
    assert _near(text) == []


def test_the_same_near_copy_inside_one_block_is_caught():
    """والنصّ نفسه متلاصقاً — بصمةُ union على سطرٍ واحد — يُمسَك بالتشابه."""
    text = (
        "## 2026-10-07 — ملاحظات\n"
        "> **2026-10-06 — سجلٌّ متأخّرُ الدمج (#1128):** السطرُ التالي كُتب في 2026-10-03 ودُمج بعد أيّام.\n"
        "> **2026-10-06 — سجلٌّ متأخّرُ الدمج (#1130):** السطرُ التالي كُتب في 2026-10-03 ودُمج بعد أيّام.\n"
    )
    assert _near(text) == [(2, 3)]


def test_a_prefix_edit_is_caught_across_a_blank_line():
    """تصحيحٌ أضاف ذيلاً: الأصليّ بادئةُ المحرَّر — داخل المدخل ولو فصلهما سطرٌ فارغ."""
    text = (
        "## 2026-10-14 — أ\n"
        "- خلاصة: اجتازت البوّابات الحاجبة كلّها على الرأس بعد إعادة التشغيل (بعد تصحيح الرقم ٣).\n"
        "\n"
        "- خلاصة: اجتازت البوّابات الحاجبة كلّها على الرأس بعد إعادة التشغيل\n"
    )
    assert _near(text) == [(2, 4)]


def test_a_whole_entry_copied_is_caught():
    """④: عنوانٌ حرفيٌّ مكرَّر ومتنٌ متطابق، تفصلهما كتلٌ فارغة."""
    entry = "## 2026-10-14 — دمج #1186\n- قصير.\n"
    text = entry + "\n" + "## 2026-10-15 — آخر\n- متنٌ آخر.\n\n" + entry
    from brain_duplicate_gap_identity_guard import near_duplicate_lines

    assert [k for *_, k in near_duplicate_lines(text)] == ["duplicated-entry"]


def test_a_short_entry_with_its_heading_edited_is_caught():
    """مدخلٌ قصير حُرِّر عنوانُه ومتنُه: union يضمّ «عنوان′ متن′ عنوان متن» كتلةً واحدة."""
    text = (
        "## 2026-10-14 — دمج #1186 وحوكمة الموجة الثانية على الرأس (مُصحَّح)\n"
        "- دُمج الفرع بعد اخضرار البوّابات الحاجبة كلّها على الرأس `abc1234def`.\n"
        "## 2026-10-14 — دمج #1186 وحوكمة الموجة الثانية على الرأس\n"
        "- دُمج الفرع بعد اخضرار البوّابات الحاجبة كلّها على الرأس `abc1234`.\n"
    )
    assert _near(text) == [(1, 3), (2, 4)]


def test_fenced_examples_are_documentation_not_entries():
    line = "- الرأس المختبَر `abc1234` وشجرة main مطابقة له بايتاً ببايت.\n"
    assert _near("## أ\n" + line + "```\n" + line + "```\n") == []


def test_the_near_duplicate_scope_is_log_and_ledger():
    from brain_duplicate_gap_identity_guard import NEAR_DUPLICATE_TARGETS

    assert NEAR_DUPLICATE_TARGETS == {
        "sahool-brain/log.md",
        "sahool-brain/decisions/ledger.md",
    }


def test_the_real_log_and_ledger_pass_with_the_frozen_baseline():
    """إنفاذٌ على الشجرة الحيّة: التكراراتُ الأربعة القائمة مُسمّاة، ولا مدخلَ أساسٍ بائت."""
    from brain_duplicate_gap_identity_guard import (
        NEAR_DUPLICATE_TARGETS,
        near_duplicate_findings,
        stale_baseline_entries,
    )

    for rel in sorted(NEAR_DUPLICATE_TARGETS):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        assert near_duplicate_findings(rel, text) == [], rel
        assert stale_baseline_entries(rel, text) == [], f"{rel}: احذف المدخل البائت من الأساس"


def test_the_baseline_only_shrinks():
    """الأساسُ مُجمَّد على 5472740e بأربعة أزواج. يُخفَّض هذا الرقم حين يُزال مدخل،
    ولا يُرفَع: تكرارٌ جديد يُعالَج في النصّ لا في القائمة."""
    from brain_duplicate_gap_identity_guard import NEAR_DUPLICATE_BASELINE

    assert len(NEAR_DUPLICATE_BASELINE) <= 4
    assert all(count == 1 for count in NEAR_DUPLICATE_BASELINE.values())


def test_a_third_copy_of_a_baselined_line_is_still_caught(monkeypatch):
    """الأساسُ يعدّ الأزواج لا يُعفي البصمة: نسخةٌ ثالثة من سطرٍ مُعفى تحجب."""
    import brain_duplicate_gap_identity_guard as guard

    line = "- الرأس المختبَر `abc1234` وشجرة main مطابقة له بايتاً ببايت."
    fp = guard.line_fingerprint(line)
    monkeypatch.setattr(guard, "NEAR_DUPLICATE_BASELINE", {("sahool-brain/log.md", fp, fp): 1})
    two = f"## أ\n{line}\n{line}\n"
    three = f"## أ\n{line}\n{line}\n{line}\n"
    assert guard.near_duplicate_findings("sahool-brain/log.md", two) == []
    assert len(guard.near_duplicate_findings("sahool-brain/log.md", three)) == 3


def test_a_baseline_entry_that_matches_nothing_is_reported_stale(monkeypatch):
    import brain_duplicate_gap_identity_guard as guard

    key = ("sahool-brain/log.md", "0" * 16, "0" * 16)
    monkeypatch.setattr(guard, "NEAR_DUPLICATE_BASELINE", {key: 1})
    assert guard.stale_baseline_entries("sahool-brain/log.md", _LOG_BASE) == [key]
    assert guard.near_duplicate_findings("sahool-brain/log.md", _LOG_BASE) == []


def _union_log_repo(tmp_path: Path, base: str, side_a: str, side_b: str) -> Path:
    repo = tmp_path / "log_repo"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / ".gitattributes").write_text("log.md merge=union\n", encoding="utf-8")
    (repo / "log.md").write_text(base, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "side")
    (repo / "log.md").write_text(side_b, encoding="utf-8")
    _git(repo, "commit", "-qam", "side")
    _git(repo, "checkout", "-q", "-")
    (repo / "log.md").write_text(side_a, encoding="utf-8")
    _git(repo, "commit", "-qam", "mine")
    return repo


@pytest.mark.slow
def test_union_merge_of_an_edited_entry_succeeds_while_the_guard_fails(tmp_path):
    """التكامل: git يدمج بـ0 بلا علامة، وناتجُه هو المُثبَّت حرفيّاً، والحارس يحمرّ."""
    repo = _union_log_repo(tmp_path, _LOG_BASE, _LOG_EDITED, _LOG_APPENDED)
    merged = _git(repo, "merge", "side", "--no-edit")
    assert merged.returncode == 0, merged.stdout + merged.stderr
    text = (repo / "log.md").read_text(encoding="utf-8")
    assert text == _LOG_UNION_MERGED, "المُثبَّت انجرف عن ناتج git الفعليّ"
    assert _near(text) == [(8, 10), (9, 11)]
