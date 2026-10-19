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

The sole shrink exception is a proven, lossless removal of byte-identical duplicate
active rows in the duplicate guard's globally unique registry. It preserves the first
row and every other byte, allows appends only at a line boundary, and does not select between
conflicting evidence. Both guards can therefore accept the same repair without padding
or rewriting Git history. Other journals and all non-redundant content remain protected.

The second exception is archival, and it is as narrow
(``BRAIN-HOT-MD-UNBOUNDED-NO-ARCHIVE-PATH-01``). Measured 2026-10-19 on ``2a759d06``:
``hot.md`` was 896,670 bytes, is read at the start of every session (CLAUDE.md), and grew
194,608 bytes in thirty days — and this guard blocked every reduction, so it could never
be compacted. The retention rule (UWRP Professional v4.3, approved by the owner) is a size
cap, then approved archival, never silent removal. So:

* a journal listed in ``resolve_merge_conflicts.ARCHIVES`` (only ``hot.md``) may shrink
  when every removed line block appears **verbatim and in order** in bytes ADDED to files
  under its archive directory **in the same commit** — a new file, or an append to an
  existing one. Old archive content is not a credit; anything else stays ``JOURNAL_SHRANK``;
* an archive file is append-only in the strict sense: it may not be deleted, shrunk or
  edited — its old bytes must remain a prefix;
* the journal has a committed byte budget (``BUDGET``) that is a ratchet: the journal may
  not exceed it at the head, and the budget at the head may not exceed the budget at the
  base. The remedy for a full snapshot is archival, never a higher number.

The file list is not written here: it is imported from ``resolve_merge_conflicts``, which
already owns that classification. A second list is a second thing to keep in step.

Fails closed. An unreadable history, an unresolvable ref, or a deleted journal is a
failure — "there is nothing to compare against" is never a pass. So is a missing or
unreadable budget at the head.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from difflib import SequenceMatcher
from functools import cache
from pathlib import Path
from types import ModuleType

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
# The byte budget is an owner decision (``claim_base_registry.json`` → ``decided``), read at
# the base and at the head of the range — never from the working tree.
BUDGET = "docs/architecture/brain_hot_budget.json"


def _load_resolver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_resolve_merge_conflicts", RESOLVER)
    if not spec or not spec.loader:
        raise SystemExit(f"✗ لا يمكن قراءة تصنيف append_only من {RESOLVER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def append_only_files() -> tuple[str, ...]:
    """The classification, imported rather than copied.

    ``resolve_merge_conflicts.APPEND_ONLY`` already decides which files are journals.
    Restating it here would create the drift this repository keeps measuring.
    """
    module = _load_resolver()
    return tuple(module.APPEND_ONLY)


def archive_dirs() -> dict[str, str]:
    """Journal → its archive directory, imported from the same classifier as the list."""
    return dict(_load_resolver().ARCHIVES)


@cache
def _row_identity_policy() -> ModuleType:
    """Use the duplicate guard's scope, full identity and fence rules, not a second parser."""
    path = Path(__file__).resolve().with_name("brain_duplicate_gap_identity_guard.py")
    spec = importlib.util.spec_from_file_location("_brain_row_identity_policy", path)
    if not spec or not spec.loader:
        raise SystemExit(f"Cannot load duplicate-row policy: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_lossless_row_deduplication(path: str, before: bytes, after: bytes) -> bool:
    """Prove a shrink removes only redundant, byte-identical active registry rows.

    APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01: keep the first occurrence of
    each identity and every other byte in its original order. A conflicting row
    (same ID, different evidence/status/whitespace) is NOT redundant. Its resolution
    must preserve both versions in an explicit audit entry, not silently discard one.
    The candidate must contain that exact retained prefix and be globally unique;
    new content may be appended at a line boundary. Fenced examples cannot fund a shrink.
    This is a narrow exception to size monotonicity, not a file-wide exemption.
    """
    policy = _row_identity_policy()
    if path not in policy.GLOBAL_ROW_UNIQUENESS_TARGETS:
        return False
    try:
        parent_text = before.decode("utf-8")
        child_text = after.decode("utf-8")
    except UnicodeDecodeError:
        return False

    kept: list[str] = []
    seen: dict[str, str] = {}
    removed = 0
    raw_lines = parent_text.splitlines(keepends=True)
    active_lines = policy._strip_fenced_blocks(parent_text.splitlines())
    for raw, active in zip(raw_lines, active_lines, strict=True):
        match = policy.ROW_FULL_ID_RE.match(active) if active is not None else None
        if match:
            identity = match.group("gap_id")
            if identity in seen:
                if raw != seen[identity]:
                    return False
                removed += 1
                continue
            seen[identity] = raw
        kept.append(raw)

    if removed == 0:
        return False
    retained = "".join(kept).encode("utf-8")
    if not after.startswith(retained):
        return False
    # Do not let a suffix modify the unterminated final row or prose line.
    if after != retained and not retained.endswith((b"\n", b"\r")):
        return False
    return not policy.global_duplicate_row_identities(child_text)


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


def archive_files(ref: str, folders: list[str], *, root: Path = ROOT) -> list[str]:
    """Every file under the archive directories at ``ref``, sorted (an empty list if none)."""
    if not folders:
        return []
    result = _git("ls-tree", "-r", "-z", "--name-only", ref, "--", *folders, root=root)
    if result.returncode != 0:
        raise SystemExit(f"✗ تعذّرت قراءة شجرة الأرشيف عند {ref} — يفشل مُغلَقاً.")
    return sorted(p for p in result.stdout.decode("utf-8").split("\0") if p)


def archive_additions(
    parent: str, commit: str, folder: str, *, root: Path = ROOT
) -> list[tuple[str, bytes]]:
    """Bytes this commit ADDED under ``folder``: a new file whole, an append its suffix.

    Content that was already archived at the parent is not a credit: it moved in another
    commit, and letting it fund a second shrink would let one archive excuse any deletion
    of text it happens to contain. A rewritten archive contributes nothing; the archive
    rule below blocks it on its own.
    """
    added: list[tuple[str, bytes]] = []
    for archive in archive_files(commit, [folder], root=root):
        now = blob(commit, archive, root=root) or b""
        kept = blob(parent, archive, root=root)
        if kept is None:
            added.append((archive, now))
        elif now.startswith(kept) and len(now) > len(kept):
            added.append((archive, now[len(kept) :]))
    return added


def _cannot_anchor(line: bytes) -> bool:
    """A blank or a lone ``>`` separates entries; it says nothing about which entry it is."""
    return line.strip() in (b"", b">")


def removed_blocks(before: bytes, after: bytes) -> list[tuple[int, bytes]]:
    """Runs of parent lines the child does not keep: (1-based parent line, bytes).

    Line-level and deterministic. Separator lines may not ANCHOR the alignment — measured on
    the first real compaction (2026-10-19): with a blank allowed to anchor, the blank between
    two kept lines matched a blank inside a cut and a KEPT line was read as removed, so a
    lossless move was refused. Separators still join the run they sit in (``SequenceMatcher``
    extends a match through equal junk at its ends). ``autojunk`` stays off: its popularity
    heuristic would drop frequent lines that do carry content.
    """
    old = before.splitlines(keepends=True)
    new = after.splitlines(keepends=True)
    matcher = SequenceMatcher(_cannot_anchor, old, new, autojunk=False)
    return [
        (i1 + 1, b"".join(old[i1:i2]))
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes()
        if tag in ("delete", "replace")
    ]


def _find_from(
    segments: list[tuple[str, bytes]], block: bytes, cursor: tuple[int, int]
) -> tuple[int, int] | None:
    """The first occurrence of ``block`` at or after ``cursor`` inside ONE archive file."""
    seg, pos = cursor
    while seg < len(segments):
        at = segments[seg][1].find(block, pos)
        if at >= 0:
            return seg, at + len(block)
        seg, pos = seg + 1, 0
    return None


def verbatim_archival(
    path: str, before: bytes, after: bytes, additions: list[tuple[str, bytes]], folder: str
) -> tuple[bool, str]:
    """Prove a shrink of ``path`` is a move: each removed block, verbatim, in order, archived.

    The blocks are searched left to right in the archive bytes added by this commit (files
    in path order, a block never spanning two files). Greedy leftmost matching is complete
    for ordered, non-overlapping substrings, so a refusal means these blocks have no such
    placement. Stated limit: the blocks come from one deterministic line alignment; when
    identical lines (a blank, a lone ``>``) sit on both sides of a cut, another alignment is
    not tried — cut on the boundary the alignment keeps and the proof follows the bytes.
    """
    if not additions:
        return False, (
            f"\n      لا أرشفة: لم يُضَف ولم يُلحَق أيُّ ملفٍّ تحت {folder} في هذا الالتزام."
            f"\n      المحذوف من {path} يُنقَل حرفيّاً إلى أرشيفٍ في الالتزام نفسه، لا يُمحى."
        )
    blocks = removed_blocks(before, after)
    cursor = (0, 0)
    for k, (line, block) in enumerate(blocks, 1):
        found = _find_from(additions, block, cursor)
        if found is None:
            seen = any(block in data for _name, data in additions)
            why = (
                "موجودةٌ في الأرشيف لكن قبل الكتلة السابقة (out of order)"
                if seen
                else f"غيرُ موجودةٍ حرفيّاً فيما أُضيف تحت {folder} (not verbatim)"
            )
            return False, (
                f"\n      الكتلة {k} من {len(blocks)} ({len(block):,} بايت، السطر {line} عند الوالد) {why}"
            )
        cursor = found
    moved = sum(len(block) for _line, block in blocks)
    names = " · ".join(name for name, _data in additions)
    return True, (f"{moved:,} بايت في {len(blocks)} كتلة نُقلت حرفيّاً وبترتيبها إلى {names}")


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
    base: str | None,
    head: str,
    *,
    files: tuple[str, ...] | None = None,
    archives: dict[str, str] | None = None,
    root: Path = ROOT,
) -> tuple[list[Finding], list[Finding], int]:
    """Return (blocking, advisory, pairs_examined)."""
    targets = files if files is not None else append_only_files()
    archives = archives if archives is not None else archive_dirs()
    folders = sorted(set(archives.values()))
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
                # Keep the shrink-to-advisory mutation anchored to the blocking rule.
                # The lossless exception is proved before that rule, not inserted into it.
                if len(after) < len(before) and is_lossless_row_deduplication(path, before, after):
                    advisory.append(
                        Finding(
                            "DUPLICATE_ROWS_DEDUPLICATED",
                            path,
                            parent,
                            commit,
                            f"{len(before):,} -> {len(after):,} bytes: removed only "
                            "byte-identical duplicate rows; retained content is unchanged",
                        )
                    )
                    continue
                # BRAIN-HOT-MD-UNBOUNDED-NO-ARCHIVE-PATH-01: the archival exception, proved
                # before the blocking rule like the one above, never folded into it.
                reason = ""
                folder = archives.get(path)
                if len(after) < len(before) and folder:
                    additions = archive_additions(parent, commit, folder, root=root)
                    moved, reason = verbatim_archival(path, before, after, additions, folder)
                    if moved:
                        advisory.append(
                            Finding(
                                "JOURNAL_ARCHIVED",
                                path,
                                parent,
                                commit,
                                f"{len(before):,} -> {len(after):,} bytes: {reason}",
                            )
                        )
                        continue
                if len(after) < len(before):
                    blocking.append(
                        Finding(
                            "JOURNAL_SHRANK",
                            path,
                            parent,
                            commit,
                            f"{len(before):,} ← {len(after):,} بايت "
                            f"(فُقِد {len(before) - len(after):,})" + reason,
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
            # An archive is the strict form of append-only: what moved there is never
            # edited, so the parent's bytes must stay a prefix — no shrink, no rewrite,
            # no deletion. Listed at the PARENT, so a deleted archive is still examined.
            for archive in archive_files(parent, folders, root=root):
                pairs += 1
                kept = blob(parent, archive, root=root) or b""
                now = blob(commit, archive, root=root)
                if now is None or not now.startswith(kept):
                    code = "ARCHIVE_DELETED" if now is None else "ARCHIVE_REWRITTEN"
                    size = "محذوف" if now is None else f"{len(now):,} بايت"
                    blocking.append(
                        Finding(
                            code,
                            archive,
                            parent,
                            commit,
                            f"أرشيفٌ إلحاقيٌّ صارم: {len(kept):,} ← {size}، "
                            "ومحتوى الوالد لم يبقَ بادئةً — ما نُقِل إليه لا يُحرَّر ولا يُحذَف",
                        )
                    )
    return blocking, advisory, pairs


def _budget_at(ref: str, *, root: Path, path: str) -> tuple[dict[str, int] | None, str | None]:
    """(journal → max bytes, error). ``(None, None)`` when the budget file is absent at ``ref``."""
    raw = blob(ref, path, root=root)
    if raw is None:
        return None, None
    try:
        doc = json.loads(raw.decode("utf-8"))
        return {journal: int(spec["max_bytes"]) for journal, spec in doc["budgets"].items()}, None
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def check_budget(
    base: str | None,
    head: str,
    *,
    root: Path = ROOT,
    path: str = BUDGET,
    archives: dict[str, str] | None = None,
) -> tuple[list[Finding], list[Finding]]:
    """The size cap as a ratchet: under budget at the head, and no budget above the base's.

    Read from the two ends of the range, not from every pair: the cap is a property of the
    tree that lands, and the ratchet compares what lands with what it replaces. A journal
    the base budgets and the head does not is a raise to infinity, and blocks as one.
    """
    archives = archives if archives is not None else archive_dirs()
    blocking: list[Finding] = []
    advisory: list[Finding] = []
    head_budgets, head_error = _budget_at(head, root=root, path=path)
    if head_error:
        blocking.append(Finding("BUDGET_UNREADABLE", path, "—", head, head_error))
        return blocking, advisory
    if head_budgets is None:
        blocking.append(
            Finding(
                "BUDGET_ABSENT_AT_HEAD",
                path,
                "—",
                head,
                "ميزانيّةُ الحجم غائبةٌ عند الرأس — سقفٌ لا يُقاس ليس سقفاً، والغيابُ ليس نجاحاً",
            )
        )
        return blocking, advisory
    base_budgets, base_error = _budget_at(base, root=root, path=path) if base else (None, None)
    if base_error:
        blocking.append(Finding("BUDGET_UNREADABLE", path, base or "—", "—", base_error))
    elif base_budgets is None:
        advisory.append(
            Finding("BUDGET_INTRODUCED", path, "—", head, "الميزانيّةُ تدخل في هذا المدى")
        )
    else:
        for journal, limit in sorted(base_budgets.items()):
            raised = head_budgets.get(journal)
            if raised is None or raised > limit:
                shown = "∞ (أُزيلت)" if raised is None else f"{raised:,}"
                blocking.append(
                    Finding(
                        "BUDGET_RAISED",
                        journal,
                        base or "—",
                        head,
                        f"الميزانيّة {limit:,} ← {shown} بايت — راتشِت يهبط ولا يرتفع",
                    )
                )
    for journal, limit in sorted(head_budgets.items()):
        content = blob(head, journal, root=root)
        if content is None:
            blocking.append(
                Finding("BUDGET_TARGET_ABSENT", journal, "—", head, "دفترٌ مُوازَنٌ غائبٌ عند الرأس")
            )
        elif len(content) > limit:
            folder = archives.get(journal, "?")
            blocking.append(
                Finding(
                    "BUDGET_EXCEEDED",
                    journal,
                    "—",
                    head,
                    f"{len(content):,} > {limit:,} بايت (+{len(content) - limit:,}). العلاج أرشفةٌ"
                    f" حرفيّة لأقدم المداخل إلى {folder} (sahool-brain/README.md)، لا رفعُ الرقم",
                )
            )
    return blocking, advisory


_TIP_REMEDY = (
    "\n  سجلّ إلحاقيّ لا يتقلّص ولا يُحذَف. إن كان هذا دمجاً، فالأرجح أنّه أخذ\n"
    "  الجانب الفارغ: أعِد بناء المحتوى من **كلا** الوالدَين، لا من أحدهما."
)


def shrink_remedy(blocking: list[Finding], head: str) -> str:
    """نصُّ العلاج — **مشتقٌّ من موضع الانخفاض** لا ثابتاً.

    ``A-HISTORICAL-DIP-IS-NOT-REPAIRABLE-BY-A-LATER-COMMIT-01``. قِيس على #1036
    (2026-09-19): رأسُ الفرع كان **أكبرَ** من الأساس في السجلّات الأربعة كلِّها، ومع ذلك
    بقي الحجبُ قائماً — لأنّ حلَّ التعارض جرى على خطوتَين، فأنزل التزامٌ وسيطٌ الملفَّين
    إلى مقاس ``main`` ثمّ استعادهما التزامٌ لاحق. والحارسُ يفحص **كلّ** زوج (التزام،
    والد) لا الرأسَ وحده، فالانخفاضُ محفورٌ في الزوج.

    والرسالةُ الثابتة كانت تصف علاجَ الرأس وحده («أعِد البناء من كلا الوالدَين»)، وهو
    علاجٌ صحيحٌ **لدمجٍ يُكتب الآن** وعديمُ الأثر لانخفاضٍ هبط أمس: أيُّ التزامٍ فوقه
    يترك الزوجَ كما هو. فقارئُها يُعيد البناء، ويبقى أحمر، ويستنتج أنّ الحارسَ معطوب.
    رسالةٌ تصف علاجاً لا يعمل في الحالة المعروضة صنفُ عطلٍ مسجَّلٌ هنا باسم «رسالةٌ بلا
    علاج»، وهذا فرعُه الثاني: علاجٌ حاضرٌ لكنّه لغير الحالة.
    """
    historical = sorted(
        {f.commit for f in blocking if f.code == "JOURNAL_SHRANK" and f.commit != head}
    )
    if not historical:
        return _TIP_REMEDY
    return (
        _TIP_REMEDY + "\n\n"
        "  وهذا الانخفاضُ **محفورٌ في التاريخ لا في الرأس**: رأسُك قد يكون أكبرَ من\n"
        "  الأساس في كلّ سجلّ ويبقى الحجبُ قائماً، فالفحصُ على الأزواج لا على الرأس.\n"
        "  التزامٌ إصلاحيٌّ فوقه لا يُزيله — أعِد تشكيلَ النافذة نفسِها (ادمج التزامَ\n"
        "  التجهيز مع التزام الاستعادة في التزامٍ واحد، أو أعِد بناءَ الضمّ من والدَيه)\n"
        "  ثمّ ادفع بـ`--force-with-lease`.\n"
        "  الالتزاماتُ المعنيّة: " + " · ".join(commit[:8] for commit in historical)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # GUARD-RUN-WITHOUT-THE-ARGUMENTS-CI-PASSES-01: بلا `--base` كان الحارس يفحص HEAD
    # وحده ويطبع `_ok` — خضرةٌ عن سؤالٍ لم يُطرَح، بينما CI تمشي على كلّ أزواج المدى.
    # فالمدى إلزاميّ: غيابُه خطأُ استدعاءٍ (رمز 2) لا قياساً فارغاً يُقرأ نجاحاً.
    parser.add_argument(
        "--base",
        required=True,
        help="بداية المدى base..head — إلزاميّة؛ الحارس يرفض أن يخضرّ على HEAD وحده",
    )
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
    budget_blocking, budget_advisory = check_budget(args.base, args.head)
    blocking += budget_blocking
    advisory += budget_advisory

    targets = append_only_files()
    print(
        f"brain_append_only_guard: {len(targets)} سجلّاً إلحاقيّاً · {pairs} زوج (التزام، والد) مفحوصاً"
    )
    budgets, _error = _budget_at(args.head, root=ROOT, path=BUDGET)
    for journal, limit in sorted((budgets or {}).items()):
        size = len(blob(args.head, journal) or b"")
        print(f"  ميزانيّة {journal}: {size:,} / {limit:,} بايت (المتبقّي {limit - size:,})")
    for finding in advisory:
        print(str(finding).replace("✗", "•"))
    if blocking:
        print("\nbrain_append_only_guard: FAIL", file=sys.stderr)
        for finding in blocking:
            print(finding, file=sys.stderr)
        if any(not f.code.startswith("BUDGET_") for f in blocking):
            head_sha = _git("rev-parse", args.head).stdout.strip()
            print(shrink_remedy(blocking, head_sha), file=sys.stderr)
        return 1

    print("brain_append_only_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
