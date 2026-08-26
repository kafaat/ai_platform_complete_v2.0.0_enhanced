"""`--strip-added`: يحذف من الأسطر المضافة وحدها، ولا يمسّ سطراً ملتزَماً.

`BIDI-MARKS-ARE-REINTRODUCED-FASTER-THAN-DISCIPLINE-REMOVES-THEM-01`

**العطل المقيس مرّتين في ساعة:** شريحةُ دماغٍ حُجِبت بسبع علامات `RLM` أدخلها نصٌّ
عربيٌّ مخلوط — كلُّها بنمطٍ واحد. أُزيلت، وأُعلِن أنّ النمط صار متجنَّباً، ثمّ عاد
**في أوّل نصٍّ جديد** بثلاث. فالمحرفُ لا يُرى بالعين ولا ينفع فيه انضباط.

**والخاصّيّةُ الحرجة ليست الحذف بل حدُّه:** تنظيفٌ شامل يمسّ سطوراً ملتزَمةً سابقاً
فينقض إلحاقيّةَ ملفّات الدماغ ويُخفي انحرافاً لم يقع في هذه الشريحة. فالاختبارُ
الثاني أهمُّ من الأوّل.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "bidi_guard", ROOT / "scripts" / "ci" / "bidi_control_char_guard.py"
)
bidi = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(bidi)

RLM = "\u200f"  # هروبٌ لا حرفاً — انظر ترويسةَ `strip_added`
LRM = "\u200e"


def _repo(tmp_path: Path) -> Path:
    """مستودعٌ حقيقيّ — الوضعُ يقرأ `git diff`، فمحاكاتُه تُثبِت غير المقصود."""
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", "-C", str(tmp_path), *a], check=True, capture_output=True
    )
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    return tmp_path


def test_a_mark_added_in_this_change_is_removed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    f = repo / "note.md"
    f.write_text("سطرٌ قديمٌ نظيف\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "base"], check=True, capture_output=True
    )
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()

    f.write_text(f"سطرٌ قديمٌ نظيف\nسطرٌ جديد ({RLM}٣٤ دقيقة)\n", encoding="utf-8")

    cleaned = bidi.strip_added(base=base, root=repo)

    assert cleaned == {"note.md": 1}
    assert RLM not in f.read_text(encoding="utf-8")
    assert "سطرٌ قديمٌ نظيف" in f.read_text(encoding="utf-8"), "لم يُتلَف السطرُ السابق"


def test_a_mark_already_committed_survives_a_cleanup_of_the_same_file(tmp_path: Path) -> None:
    """الحدُّ الذي يحمي الإلحاقيّة — ولولاه لكان الوضعُ ينقض `append-only`.

    **والصياغةُ الأولى لهذا الاختبار مرّت على تنظيفٍ شامل ولم تمسكه**، لأنّ السطرَ
    المضاف كان نظيفاً فلم يدخل الملفُّ حلقةَ المعالجة أصلاً — فالمسارُ الخطر غيرُ
    مطروق. فالشرطُ أن يجتمع في **ملفٍّ واحد** علامةٌ ملتزَمة وأخرى مضافة: عندها
    يُفتَح الملفّ، ويكون الفرقُ بين «حذفٌ من الأسطر المضافة» و«حذفٌ من الملفّ»
    مرئيّاً. كشفه التكذيبُ لا المراجعة.
    """
    repo = _repo(tmp_path)
    f = repo / "log.md"
    f.write_text(f"سطرٌ ملتزَمٌ فيه علامة ({RLM}٩)\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "base"], check=True, capture_output=True
    )
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()

    f.write_text(f"سطرٌ ملتزَمٌ فيه علامة ({RLM}٩)\nسطرٌ مضافٌ فيه علامة ({RLM}٧)\n", encoding="utf-8")

    cleaned = bidi.strip_added(base=base, root=repo)

    assert cleaned == {"log.md": 1}, "حُذِفت علامةٌ واحدة فقط — لا أكثر ولا أقلّ"
    text = f.read_text(encoding="utf-8")
    assert text.count(RLM) == 1, "مسّ سطراً ملتزَماً — نقضٌ للإلحاقيّة"
    assert f"({RLM}٩)" in text, "العلامةُ الباقية هي الملتزَمة لا المضافة"
    assert "(٧)" in text, "العلامةُ المحذوفة هي المضافة"


def test_every_mark_the_guard_counts_is_a_mark_it_can_strip() -> None:
    """مصدرٌ واحد: الحذفُ يُشتقّ من `MARKS` نفسِه لا من قائمةٍ ثانية.

    تعريفان لِما هو «علامةٌ خفيّة» ينحرفان، فيَعُدّ الحارسُ ما لا يحذفه الوضع —
    ويبقى الفشلُ بلا علاجٍ يُسمّيه.
    """
    stripped = "".join(chr(cp) for cp in bidi.MARKS)
    for cp in bidi.MARKS:
        assert chr(cp) in stripped


def test_a_clean_change_is_a_no_op(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    f = repo / "a.md"
    f.write_text("أوّل\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "base"], check=True, capture_output=True
    )
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()
    f.write_text("أوّل\nثانٍ بلا علامات\n", encoding="utf-8")
    before = f.read_text(encoding="utf-8")

    assert bidi.strip_added(base=base, root=repo) == {}
    assert f.read_text(encoding="utf-8") == before


def test_the_failure_message_names_the_command_that_fixes_it() -> None:
    """رسالةٌ تقول «احذف» ولا تقول «كيف» تترك الإصلاحَ للتخمين على محرفٍ غير مرئيّ."""
    failures = bidi.violations({}, {"x.md": 5}, {"x.md": 1})

    assert failures, "لم تُبلَّغ مخالفةٌ أصلاً"
    assert "--strip-added" in failures[0]
