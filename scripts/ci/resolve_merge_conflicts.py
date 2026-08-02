#!/usr/bin/env python3
"""يحلّ تعارضات الدمج **بالتصنيف** لا باليد — MERGE-RESOLUTION-BY-HAND-LOSES-WORK-01.

كلّ ملفّ متعارض في هذا المستودع ينتمي إلى أحد ثلاثة أصناف، ولكلٍّ علاج **مختلف**،
وخلطها يُتلِف عملاً بصمت:

* **إلحاقيّ** (`sahool-brain/*.md`) — الجانبان يُلحقان مدخلات **مختلفة** لا نسختين من
  مدخل. أخذُ جانبٍ يحذف سجلّ جلسة أو فجوة من ملفّ وظيفته الوحيدة أنّ تلك لا تختفي.
  العلاج: **الإبقاء على الاثنين**، ومدخل `main` أوّلاً.
* **مولَّد** — بصمة أو جرد يُنتِجه مولّد. حلُّه يدويّاً يُنتِج رقماً **لم يحسبه أحد**.
  العلاج: خُذ جانب `main` ثمّ **أعِد التوليد** (`verify_all_generated.py --fix`).
* **مصدر** — كود أو اختبار. لا قاعدة آليّة تصلح هنا؛ الدمج الخاطئ يُغيّر سلوكاً.
  العلاج: **يتوقّف السكربت** ويطلب إنساناً.

**لماذا سكربت لا قاعدة في الرأس:** هذه القواعد الثلاث كانت معروفة ومكتوبة ومُطبَّقة
يدويّاً **خمس مرّات** في جلسة واحدة، ثمّ نُقِضت في السادسة: حُلَّت أربعة ملفّات إلحاقيّة
صحيحاً، ثمّ مرّت حلقة ``git checkout --theirs`` على «المتبقّي» — والملفّات المحلولة لم
تكن مُفهرَسة بعد، فبقيت في ``--diff-filter=U`` **فداست الحلقة على الحلّ كلّه**. ضاع
مدخلا سجلّ وتصحيح سطر كاذب وقرار دفتر وختم لقطة ومدخل فجوة. **وgit أبلغ دمجاً نظيفاً**،
ولم يمسك الضياع إلّا حارس ادّعاء المعرّفات مصادفةً — لأنّ رسالة الالتزام ذكرت معرّفاً
لم يعد في السجلّ.

الدرس المُرمَّز هنا: **الفهرسة تجري في نفس اللحظة التي يُحلّ فيها الملفّ**، قبل أن
يلمس أيّ أمر آليّ شيئاً. معرفةُ القاعدة وترميزُها في ترتيب العمليّات شيئان مختلفان.

**وأيّ الجانبين هو `main` ليس ثابتاً:** في ``git merge origin/main`` يكون `main`
هو ``--theirs``، وفي ``git rebase origin/main`` ينقلب فيصير ``--ours`` — لأنّ HEAD
أثناء الإعادة هو المُنبَع. سكربتٌ يُثبّت جانباً واحداً يكون صحيحاً في عمليّة وخاطئاً
في الأخرى **بلا أن يُبلِّغ**، وهو بالضبط صنف العطل الذي وُجِد هذا السكربت ليمنعه؛
فالجانب يُقرأ من العمليّة الجارية، وما لا يُعرَف يُوقِف السكربت.

    python scripts/ci/resolve_merge_conflicts.py            # يحلّ ويُفهرِس
    python scripts/ci/resolve_merge_conflicts.py --dry-run  # يُصنّف ولا يكتب
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# سجلّات إلحاقيّة: الجانبان مدخلان مختلفان دائماً، لا نسختان من مدخل واحد.
APPEND_ONLY = (
    "sahool-brain/log.md",
    "sahool-brain/gaps/registry.md",
    "sahool-brain/decisions/ledger.md",
    "sahool-brain/hot.md",
)

# مصنوعات مولَّدة: تُؤخَذ من `main` ثمّ يُعاد توليدها. حلُّها يدويّاً يُنتِج رقماً
# لم يحسبه أحد — والبصمة تحديداً لا تُدمَج، تُحسَب.
GENERATED_MARKERS = (
    "/generated/",
    "generated/",
    ".sha256",
    ".generated.json",
    "release/FILE_CHECKSUMS",
    "release/SAHOOL_RELEASE_MANIFEST",
    "release/SBOM_MINIMAL",
    "SERVICE_REGISTRY.md",
    "service_inventory.csv",
    "route_inventory.csv",
    "api_versioning_inventory.csv",
)

CONFLICT_RE = re.compile(r"<<<<<<< (?:HEAD|[^\n]*)\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]*\n", re.S)

# أيّ جانبٍ يحمل `main` في كلّ عمليّة. الإعادة تقلب المعنى لأنّ HEAD أثناءها هو
# المُنبَع لا الفرع؛ فما لا يرِد هنا يُوقِف السكربت بدل أن يُخمَّن.
MAIN_SIDE = {"merge": "theirs", "rebase": "ours"}


def classify(path: str) -> str:
    """``append_only`` · ``generated`` · ``source``. المصدر يُوقِف السكربت."""
    if path in APPEND_ONLY:
        return "append_only"
    if any(marker in path for marker in GENERATED_MARKERS):
        return "generated"
    return "source"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        cwd=root,
    )


def conflicted_paths(root: Path = ROOT) -> list[str]:
    out = _git(root, "diff", "--name-only", "--diff-filter=U")
    return [p for p in out.stdout.splitlines() if p.strip()]


def in_progress_operation(root: Path = ROOT) -> str | None:
    """``merge`` · ``rebase`` · ``None``. منها يُعرَف أيّ جانبٍ هو `main`."""
    git_dir = Path(_git(root, "rev-parse", "--git-dir").stdout.strip())
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    if (git_dir / "MERGE_HEAD").exists():
        return "merge"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        return "rebase"
    return None


def merge_keeping_both(text: str, main_side: str) -> tuple[str, int]:
    """يُبقي الجانبين، جانبَ `main` أوّلاً. يُرجِع (النصّ، عدد الكتل المحلولة)."""
    resolved = 0
    while True:
        m = CONFLICT_RE.search(text)
        if not m:
            return text, resolved
        ours, theirs = m.group(1), m.group(2)
        first, second = (ours, theirs) if main_side == "ours" else (theirs, ours)
        text = text[: m.start()] + first + "\n\n" + second + "\n" + text[m.end() :]
        resolved += 1


def _stage(root: Path, path: str) -> None:
    _git(root, "add", "--", path)


def resolve(root: Path = ROOT, dry_run: bool = False) -> int:
    paths = conflicted_paths(root)
    if not paths:
        print("resolve_merge_conflicts: لا تعارضات")
        return 0

    operation = in_progress_operation(root)
    if operation not in MAIN_SIDE:
        print(
            "resolve_merge_conflicts: لا دمج ولا إعادة تأسيس جارية — لا يُعرَف أيّ"
            "\nجانبٍ هو main، وتخمينه هنا يقلب الحلّ رأساً على عقب. توقّف.",
            file=sys.stderr,
        )
        return 1
    main_side = MAIN_SIDE[operation]

    buckets: dict[str, list[str]] = {"append_only": [], "generated": [], "source": []}
    for p in paths:
        buckets[classify(p)].append(p)

    # المصدر أوّلاً وقبل أيّ كتابة: لا قاعدة آليّة تصلح لدمج كود، والتوقّف هنا
    # أرخص من اكتشاف سلوك مدموج خطأً بعد الالتزام.
    if buckets["source"]:
        print("resolve_merge_conflicts: تعارض في ملفّات مصدر — يلزم إنسان", file=sys.stderr)
        for p in buckets["source"]:
            print(f"  ✗ {p}", file=sys.stderr)
        print(
            "\nهذه ليست مصنوعات ولا سجلّات إلحاقيّة. حُلَّها بقراءة الجانبين، ولا تُطبَّق"
            "\nعليها قاعدة آليّة — الدمج الخاطئ لكود يُغيّر سلوكاً ولا يُبلِّغ عن نفسه.",
            file=sys.stderr,
        )
        return 1

    print(f"resolve_merge_conflicts: {operation} — جانب main هو --{main_side}")

    # الإلحاقيّة: تُحلّ **وتُفهرَس في نفس التكرار**. الفصل بين الخطوتين هو ما أتلف
    # العمل سابقاً: ملفّ محلول غير مُفهرَس يبقى في `--diff-filter=U` فيُداس عليه.
    for p in buckets["append_only"]:
        f = root / p
        merged, n = merge_keeping_both(f.read_text(encoding="utf-8"), main_side)
        if dry_run:
            print(f"  [append-only] {p}: سيُبقي الجانبين ({n} كتلة)")
            continue
        f.write_text(merged, encoding="utf-8")
        _stage(root, p)
        print(f"  ✓ [append-only] {p}: أُبقي الجانبان ({n} كتلة) + فُهرِس")

    for p in buckets["generated"]:
        if dry_run:
            print(f"  [generated]   {p}: سيأخذ جانب main ثمّ يلزم إعادة توليد")
            continue
        _git(root, "checkout", f"--{main_side}", "--", p)
        _stage(root, p)
        print(f"  ✓ [generated]   {p}: جانب main + فُهرِس")

    if dry_run:
        print("\n(dry-run — لم يُكتَب شيء)")
        return 0

    if buckets["generated"]:
        print(
            "\n⚠ مصنوعات مولَّدة أُخِذت من main — **أعِد التوليد قبل الالتزام**:"
            "\n    python scripts/ci/verify_all_generated.py --fix"
        )
    print("resolve_merge_conflicts_ok")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    return resolve(dry_run=p.parse_args().dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
