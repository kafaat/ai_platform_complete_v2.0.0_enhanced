#!/usr/bin/env python3
"""An append-only journal may not shrink — and a merge must preserve **both** parents.

``BRAIN-APPEND-ONLY-TRUNCATION-GUARD-01``. Measured 2026-08-05: ``sahool-brain/log.md``
went from 1,383,368 bytes to **0** in ``cb6598fe`` and stayed empty on ``main`` for about
five hours. Every gate was green throughout. Nothing here was broken — the file simply
had no guard:

* the three brain guards check *claims* and *state transitions*, not journal size;
* ``resolve_merge_conflicts`` knows the file is ``append_only``, but it runs only when
  git reports a conflict — and a merge that silently takes the empty side has none;
* the checksum generators re-stamp whatever they find, and **an empty file has a
  perfectly valid checksum**.

**Merge-awareness is the whole point, and the incident proves it.** The truncation
survived because one parent (the branch) held the file and the other (main) did not.
A guard that compares a merge to *a* base passes; one that compares it to *every*
parent catches it. This checks every commit in the range against each of its parents.

**The rule is "must not shrink", not "must be a byte-prefix", and that is measured.**
Over 202 commit-parent pairs in this repository:

    file                       pairs   shrinks   deletions   worst shrink
    sahool-brain/log.md          202         1           0   1,383,368  <- the incident
    sahool-brain/gaps/registry   202         1           0          57
    sahool-brain/decisions/…     202         0           0           0
    sahool-brain/hot.md          202         1           0         432

A byte-prefix rule would have blocked **141** of those pairs, because ``registry.md``
carries status edits (``مفتوحة`` → ``مُغلَقة``, mandated by CLAUDE.md) and ``hot.md`` is a
snapshot that is rewritten by design. A guard that fires on normal work trains its reader
to bypass it, so prefix loss is **reported** and size loss **blocks**.

The file list is not written here: it is imported from ``resolve_merge_conflicts``, which
already owns that classification. A second list is a second thing to keep in step.

**One shrink is not a loss, and it took a blocked merge to learn it.**
``APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01``: ``brain_duplicate_gap_identity_guard``
requires **one governing row per gap identity** in ``gaps/registry.md``, so reconciling a
``merge=union`` duplicate means one of the two rows must stop existing. Measured on #985:
folding the two ``SOIL-MOISTURE-UNIT-IDENTITY-01`` rows cost 1,090 bytes and this guard
answered ``JOURNAL_SHRANK`` — two blocking guards demanding opposite things about the same
edit, satisfiable only by rewriting history. Neither is wrong; the rule was simply stated
in bytes when what it protects is **content**.

So the exception is narrow and **proven per pair**, never asserted: on the one file whose
rows are unique declarations by design, a shrink passes only when *every line that vanished
was a row carrying an identity that was declared more than once at the parent*. The proof
is a multiset difference over the parent's own lines, and the surviving duplicate row may
be rewritten to absorb both texts. Truncation removes lines that are not duplicate rows, so
it still blocks — including truncation of a file that happens to contain duplicates. What
the exception bounds is **which lines may disappear**; whether the surviving row still says
what both said is a review question, not a measurable one, and is not claimed here.

Fails closed. An unreadable history, an unresolvable ref, or a deleted journal is a
failure — "there is nothing to compare against" is never a pass.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = Path(__file__).resolve().parent / "resolve_merge_conflicts.py"
DUPLICATE_GUARD = Path(__file__).resolve().parent / "brain_duplicate_gap_identity_guard.py"


def append_only_files() -> tuple[str, ...]:
    """The classification, imported rather than copied.

    ``resolve_merge_conflicts.APPEND_ONLY`` already decides which files are journals.
    Restating it here would create the drift this repository keeps measuring.
    """
    spec = importlib.util.spec_from_file_location("_resolve_merge_conflicts", RESOLVER)
    if not spec or not spec.loader:
        raise SystemExit(f"✗ لا يمكن قراءة تصنيف append_only من {RESOLVER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return tuple(module.APPEND_ONLY)


@lru_cache(maxsize=1)
def _duplicate_guard():
    """The sibling guard, loaded rather than re-implemented.

    It owns what "a row declaring a duplicated identity" means — the fenced-block
    exclusion and the dotted-identity anchor were both corrected there by measurement.
    Re-deriving either here would make the two guards disagree about the same line.
    """
    spec = importlib.util.spec_from_file_location(
        "_brain_duplicate_gap_identity_guard", DUPLICATE_GUARD
    )
    if not spec or not spec.loader:
        raise SystemExit(f"✗ لا يمكن قراءة حارس الهويّات المكرَّرة من {DUPLICATE_GUARD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def duplicate_row_reconciliation(path: str, before: bytes, after: bytes) -> str | None:
    """A proof string when the shrink is exactly the removal of duplicate-identity rows.

    Returns ``None`` — meaning "block" — for every other shrink, including a shrink in a
    file that merely *contains* duplicates. The bound is the parent's own lines: whatever
    disappeared must be one of the rows whose identity the sibling guard would refuse to
    leave duplicated.
    """
    module = _duplicate_guard()
    if path not in module.GLOBAL_ROW_UNIQUENESS_TARGETS:
        return None
    try:
        before_text = before.decode("utf-8")
        after_text = after.decode("utf-8")
    except UnicodeDecodeError:
        return None  # unreadable content is never proof of anything

    duplicated = module.duplicate_row_lines(before_text)
    if not duplicated:
        return None

    allowed: Counter[str] = Counter()
    for rows in duplicated.values():
        allowed.update(rows)
    removed = Counter(before_text.splitlines()) - Counter(after_text.splitlines())
    if not removed or removed - allowed:
        return None

    touched = sorted(
        gap_id for gap_id, rows in duplicated.items() if any(row in removed for row in rows)
    )
    return (
        f"نقصٌ مبرهَن أنّه ضمُّ صفوفٍ مكرَّرة الهويّة: "
        f"{sum(removed.values())} صفّاً أُزيل، كلُّه مُعلَنٌ مرّتين فأكثر عند الوالد "
        f"({', '.join(touched)}) — ولا سطرَ آخر اختفى"
    )


def _git(*args: str, root: Path = ROOT) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True)


def blob(ref: str, path: str, *, root: Path = ROOT) -> bytes | None:
    """File content at a ref, or None when the file does not exist there."""
    result = _git("show", f"{ref}:{path}", root=root)
    return result.stdout if result.returncode == 0 else None


def commits_in_range(base: str | None, head: str, *, root: Path = ROOT) -> list[str]:
    args = ["rev-list", f"{base}..{head}"] if base else ["rev-list", "--max-count=1", head]
    result = _git(*args, root=root)
    if result.returncode != 0:
        raise SystemExit(
            f"✗ تعذّرت قراءة تاريخ git ({' '.join(args)}) — يفشل مُغلَقاً.\n"
            f"  {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout.decode("utf-8").split()


def parents_of(commit: str, *, root: Path = ROOT) -> list[str]:
    result = _git("rev-list", "--parents", "-n", "1", commit, root=root)
    if result.returncode != 0:
        raise SystemExit(f"✗ تعذّر تحديد والدَي {commit} — يفشل مُغلَقاً.")
    return result.stdout.decode("utf-8").split()[1:]


class Finding:
    def __init__(self, code: str, path: str, parent: str, commit: str, detail: str) -> None:
        self.code, self.path, self.parent, self.commit, self.detail = (
            code,
            path,
            parent,
            commit,
            detail,
        )

    def __str__(self) -> str:
        return f"  ✗ [{self.code}] {self.path}\n      {self.parent[:8]} → {self.commit[:8]}: {self.detail}"


def check_range(
    base: str | None, head: str, *, files: tuple[str, ...] | None = None, root: Path = ROOT
) -> tuple[list[Finding], list[Finding], int]:
    """Return (blocking, advisory, pairs_examined)."""
    targets = files if files is not None else append_only_files()
    blocking: list[Finding] = []
    advisory: list[Finding] = []
    pairs = 0

    # Fail closed on absence, before comparing anything. Every pair below is skipped when
    # the journal is missing at the parent, so a tree where the journals no longer exist
    # would examine zero pairs and report "ok" — the exact silent zero this guard exists
    # to catch, reappearing inside the guard. A journal must exist at the head, full stop.
    for path in targets:
        if blob(head, path, root=root) is None:
            blocking.append(
                Finding(
                    "JOURNAL_ABSENT_AT_HEAD",
                    path,
                    "—",
                    head,
                    "سجلّ إلحاقيّ مفقود عند الرأس — «لا شيء للمقارنة» ليس نجاحاً",
                )
            )

    for commit in commits_in_range(base, head, root=root):
        for parent in parents_of(commit, root=root):
            for path in targets:
                before = blob(parent, path, root=root)
                if before is None:
                    continue  # the journal did not exist yet on this side
                pairs += 1
                after = blob(commit, path, root=root)
                if after is None:
                    blocking.append(
                        Finding(
                            "JOURNAL_DELETED",
                            path,
                            parent,
                            commit,
                            f"موجود عند الوالد ({len(before):,} بايت) ومحذوف عند الابن",
                        )
                    )
                    continue
                if len(after) < len(before):
                    proof = duplicate_row_reconciliation(path, before, after)
                    if proof is None:
                        blocking.append(
                            Finding(
                                "JOURNAL_SHRANK",
                                path,
                                parent,
                                commit,
                                f"{len(before):,} ← {len(after):,} بايت "
                                f"(فُقِد {len(before) - len(after):,})",
                            )
                        )
                    else:
                        advisory.append(
                            Finding(
                                "DUPLICATE_ROW_RECONCILED",
                                path,
                                parent,
                                commit,
                                f"{len(before):,} ← {len(after):,} بايت — {proof}",
                            )
                        )
                elif not after.startswith(before):
                    advisory.append(
                        Finding(
                            "PREFIX_NOT_PRESERVED",
                            path,
                            parent,
                            commit,
                            f"نما إلى {len(after):,} بايت لكنّ محتوى الوالد ليس بادئةً له "
                            "— تحرير وسط الملفّ (إرشاديّ: مقيس أنّه طبيعيّ لسجلّ الحالات واللقطة)",
                        )
                    )
    return blocking, advisory, pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=None, help="فحص base..head؛ بدونه يُفحص HEAD وحده")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--check", action="store_true", help="الوضع الافتراضي؛ الراية تجعل النيّة صريحة"
    )
    args = parser.parse_args(argv)

    for ref in filter(None, (args.base, args.head)):
        if _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
            print(
                f"✗ لا يُحلّ المرجع {ref!r} — يفشل مُغلَقاً بدل أن يُبلِغ عن مدى فارغ.\n"
                f"  في CI: اجلب الأساس أوّلاً (`git fetch --no-tags origin <sha>`).",
                file=sys.stderr,
            )
            return 2

    blocking, advisory, pairs = check_range(args.base, args.head)

    targets = append_only_files()
    print(
        f"brain_append_only_guard: {len(targets)} سجلّاً إلحاقيّاً · {pairs} زوج (التزام، والد) مفحوصاً"
    )
    for finding in advisory:
        print(str(finding).replace("✗", "•"))
    if blocking:
        print("\nbrain_append_only_guard: FAIL", file=sys.stderr)
        for finding in blocking:
            print(finding, file=sys.stderr)
        print(
            "\n  سجلّ إلحاقيّ لا يتقلّص ولا يُحذَف. إن كان هذا دمجاً، فالأرجح أنّه أخذ\n"
            "  الجانب الفارغ: أعِد بناء المحتوى من **كلا** الوالدَين، لا من أحدهما.",
            file=sys.stderr,
        )
        return 1

    print("brain_append_only_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
