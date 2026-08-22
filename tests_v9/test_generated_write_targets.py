"""`CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01` — «يكتبه» لا «يذكره».

الصنفُ ارتدّ مرّتين بعد أوّل علاجه، وفي المرّتين بالآليّة نفسها: قائمةٌ مُنتقاة
تُغلِق الحالات المعروفة وتترك الصنف مفتوحاً. آخرُها `docs/runbooks/GUARD_CATALOGUE.md`
في دمج #881 — مصنوعةٌ يقول رأسُها «لا تُحرَّر يدويّاً»، صنّفها المُصنِّف **مصدراً**
فأوقف نفسه وطلب إنساناً.

**والاشتقاق النصّيّ ليس العلاج** — قِيس ضارّاً: «أيّ مسارٍ يُذكَر في سكربت» يعطي
**٢١٩** مساراً، منها `guard_mutation_registry.json` وهو وثيقةُ سياسةٍ **بخطّ اليد**
يقرؤها المحرّك ولا يكتبها. تصنيفُها مولَّدةً يعني «خُذ جانب main ثمّ أعِد التوليد»،
أي **إتلاف طفراتٍ مكتوبة** — عطلٌ أسوأ من الوقوف الذي جاء ليُصلحه.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "architecture" / "generated_write_targets.json"


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_w_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"_w_{name}"] = module
    spec.loader.exec_module(module)
    return module


resolver = _load("resolve_merge_conflicts")
tool = _load("generated_write_targets")


# ── المعيار نفسه: كتابةٌ لا ذِكر ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "expected", "why"),
    [
        ('OUT = ROOT / "docs/x.md"\nOUT.write_text("hi")', {"docs/x.md"}, "كتابةٌ عبر ثابت"),
        ('(ROOT / "docs/y.json").write_text("{}")', {"docs/y.json"}, "كتابةٌ مباشرة"),
        ('P = ROOT / "docs/z.md"\njson.dump(d, open(P, "w"))', {"docs/z.md"}, "open بوضع w"),
        ('P = ROOT / "docs/a.md"\nP.open("a")', {"docs/a.md"}, "إلحاقٌ كتابة"),
        ('P = ROOT / "docs/b.md"\nP.read_text()', set(), "**قراءةٌ ليست كتابة**"),
        ('P = ROOT / "docs/c.md"\nopen(P)', set(), "فتحُ قراءةٍ ليس كتابة"),
        ('PATH = "docs/d.json"\nprint(PATH)', set(), "**ذِكرٌ ليس كتابة**"),
    ],
)
def test_only_a_write_counts_not_a_mention(source, expected, why):
    """الفرقُ الذي يقوم عليه العقد كلُّه — ولولاه لكان الذِّكرُ كافياً.

    و`read_text` هي الحالة الحاسمة: وثيقةُ السياسة تُقرأ في محرّكٍ ولا تُكتَب،
    فلو عُدَّت القراءةُ كتابةً لدخلت البيان ولأُتلِفت في أوّل تعارض.
    """
    assert tool.write_targets_of(source) == expected, why


def test_the_catalogue_that_halted_the_last_merge_is_now_generated():
    """الحالة التي أوقفت دمج #881 — مقيسةٌ لا مُدَّعاة."""
    assert resolver.classify("docs/runbooks/GUARD_CATALOGUE.md") == "generated"


@pytest.mark.parametrize("path", resolver.HAND_WRITTEN_POLICY)
def test_a_hand_written_policy_document_stays_source(path):
    """الاتّجاه الذي يُتلِف عملاً: «مولَّدة» تعني محوَ طفراتٍ مكتوبة."""
    assert resolver.classify(path) == "source"


def test_the_deny_list_and_the_manifest_are_disjoint():
    """المنعُ يعلو البيان **ولا يتقاطع معه** — يُكشَف الانحراف قبل شبكة الأمان."""
    overlap = set(resolver.HAND_WRITTEN_POLICY) & set(tool.targets())
    assert not overlap, f"وثيقةُ سياسةٍ دخلت بيانَ الكتابة: {sorted(overlap)}"


def test_the_manifest_declares_its_criterion_and_its_limit():
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert document["schema"] == "sahool.generated_write_targets"
    assert document["criterion"], "بيانٌ لا يقول كيف قِيس يصير قائمةً منتقاةً أخرى"
    assert document["not_the_criterion"], "النقيض يبقى مكتوباً — الذِّكرُ ليس كتابةً"
    assert document["honesty_limit"], "الاشتقاق ساكن، وحدُّه يُعلَن لا يُخفى"
    assert document["count"] == len(document["targets"])


def test_every_declared_target_is_tracked_in_git():
    tracked = set(
        subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
        ).stdout.split()
    )
    assert not (set(tool.targets()) - tracked)


def test_the_check_re_derives_and_does_not_merely_describe():
    """`--check` يُعيد الاشتقاق فعلاً — رخيصٌ، فلا عذر لوصفٍ بلا قياس."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ci" / "generated_write_targets.py"), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_missing_manifest_degrades_to_source_not_to_chaos(monkeypatch, tmp_path):
    """غيابُ البيان يفشل في **الاتّجاه الآمن**.

    «مصدر» يُوقِف الأداة ويطلب إنساناً؛ «مولَّد» يأخذ جانباً ويكتب فوق عمل.
    فالاعتمادُ على ملفٍّ قد يغيب يجب أن يسقط إلى الأوّل.
    """
    monkeypatch.setattr(resolver, "WRITE_TARGETS", tmp_path / "ghost.json")
    assert resolver.classify("docs/runbooks/GUARD_CATALOGUE.md") == "source"
    assert resolver.classify("release/FILE_CHECKSUMS.sha256") == "generated"
    for path in resolver.HAND_WRITTEN_POLICY:
        assert resolver.classify(path) == "source"
