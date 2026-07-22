#!/usr/bin/env python3
"""branch_funeral.py — سياسة جنازة الفروع البعيدة (BRANCH-GRAVEYARD-POLICY).

يُصنّف فروع `origin` ويقترح الحذف بأمان، **بلا حذف تلقائيّ**. القاعدة (من gaps/registry):
  • محميّ (main/develop + استثناءات) ⇒ يُبقى دائماً.
  • مدموج عبر PR **أو** 0-ahead على main ⇒ آمن الحذف (محتواه ⊆ main).
  • نشط < recent-days ⇒ لا يُمسّ.
  • خامد ≥ stale-days وغير مدموج ⇒ يُؤرشَف SHA ثمّ يُحذَف على دفعات.
  • بين ذلك (غير مدموج، لا خامد بعد) ⇒ يُترَك للمراجعة اليدويّة.

**صدق:** «متقدّم على main» ≠ «غير مدموج» — main يُعاد بناؤه/squash، فالفرع المدموج بـsquash
يظهر متقدّماً. التصنيف الآمن للحذف يعتمد **حالة دمج الـPR** (لا git-diff). لذا يجلب رؤوس فروع
الـPRs المدموجة عبر `gh` (أو ملفّ مُمرَّر بـ--merged-file). بلا هذه البيانات لا يُصنَّف أيّ فرع
«merged-pr» (fail-safe: لا حذف بناءً على تخمين).

الأمان:
  • DRY-RUN افتراضيّ: يطبع الخطّة، لا يحذف شيئاً. الحذف يتطلّب --apply صراحةً.
  • أرشفة SHA قبل الحذف: كلّ فرع مُرشَّح يُكتَب (اسم/SHA/تاريخ) إلى ledger — الاسترجاع بالـSHA
    يبقى ممكناً (الحذف لا يمحو الـobjects ما دام مرجع/لقطة يحملها). لا حذف قبل نجاح الأرشفة.
  • --limit N: دفعات (الافتراضيّ 30/تشغيل) كي لا يُحذَف كلّ شيء مرّة واحدة.
  • --apply يطلب تأكيداً تفاعليّاً ما لم يُمرَّر --yes.

الحذف نفسه عبر `gh api -X DELETE` (يحترم صلاحيّات الويب حيث يفشل git protocol بـ403).

أمثلة:
  python3 scripts/ops/branch_funeral.py                      # dry-run، تصنيف + خطّة
  gh pr list --state merged --limit 2000 --json headRefName --jq '.[].headRefName' > /tmp/merged.txt
  python3 scripts/ops/branch_funeral.py --merged-file /tmp/merged.txt
  python3 scripts/ops/branch_funeral.py --merged-file /tmp/merged.txt --category merged-pr --apply --limit 30
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime

# فروع لا تُحذَف أبداً (قانونيّة/مرجعيّة). أضِف استثناءاتك هنا.
PROTECTED = {"main", "develop", "master", "HEAD"}

# الفئات القابلة للحذف الآليّ (بعد --apply). "stale-unmerged" يتطلّب أرشفة SHA.
DELETABLE = {"merged-pr", "zero-ahead", "stale-unmerged"}


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (subprocess.SubprocessError, OSError) as exc:  # noqa: BLE001
        return 1, str(exc)


def _remote_branches() -> list[str]:
    rc, out = _run(["git", "for-each-ref", "refs/remotes/origin", "--format=%(refname:short)"])
    if rc != 0:
        sys.exit(f"git for-each-ref فشل: {out}")
    names = []
    for line in out.splitlines():
        b = line.strip()
        if b.startswith("origin/"):
            b = b[len("origin/") :]
        if b and b not in PROTECTED:
            names.append(b)
    return names


def _merged_pr_branches(merged_file: str | None) -> set[str] | None:
    """رؤوس فروع الـPRs المدموجة. None ⇒ البيانات غير متاحة (لا يُصنَّف merged-pr)."""
    if merged_file:
        try:
            with open(merged_file, encoding="utf-8") as fh:
                return {ln.strip() for ln in fh if ln.strip()}
        except OSError as exc:
            sys.exit(f"تعذّر قراءة --merged-file: {exc}")
    # جرّب gh (بيئة المالك عادةً)
    rc, out = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            "2000",
            "--json",
            "headRefName",
            "--jq",
            ".[].headRefName",
        ]
    )
    if rc == 0:
        return {ln.strip() for ln in out.splitlines() if ln.strip()}
    print(
        "⚠ gh غير متاح ولا --merged-file — لن يُصنَّف أيّ فرع 'merged-pr' (fail-safe).", file=sys.stderr
    )
    return None


def _tip(branch: str) -> str:
    rc, out = _run(["git", "rev-parse", f"origin/{branch}"])
    return out.strip() if rc == 0 else ""


def _age_days(branch: str, now_ts: int) -> int:
    rc, out = _run(["git", "log", "-1", "--format=%ct", f"origin/{branch}"])
    if rc != 0 or not out.strip().isdigit():
        return -1
    return (now_ts - int(out.strip())) // 86400


def _is_ancestor(branch: str, base: str) -> bool:
    return _run(["git", "merge-base", "--is-ancestor", f"origin/{branch}", base])[0] == 0


def classify(branches, merged_set, base_sha, now_ts, recent_days, stale_days):
    rows = []
    for b in sorted(branches):
        tip = _tip(b)
        age = _age_days(b, now_ts)
        rc, ahead_out = _run(["git", "rev-list", "--count", f"{base_sha}..origin/{b}"])
        ahead = int(ahead_out.strip()) if rc == 0 and ahead_out.strip().isdigit() else -1
        if merged_set is not None and b in merged_set:
            cat = "merged-pr"
        elif ahead == 0 or _is_ancestor(b, base_sha):
            cat = "zero-ahead"
        elif 0 <= age < recent_days:
            cat = "recent-keep"
        elif age >= stale_days:
            cat = "stale-unmerged"
        else:
            cat = "review-manual"
        rows.append({"branch": b, "cat": cat, "age": age, "ahead": ahead, "tip": tip})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Branch funeral — classify + safe-delete stale remote branches."
    )
    ap.add_argument(
        "--merged-file", help="ملفّ يحوي رؤوس فروع الـPRs المدموجة (سطر لكلّ فرع). بلا هذا يُجرَّب gh."
    )
    ap.add_argument(
        "--recent-days", type=int, default=7, help="فرع أحدث من هذا لا يُمسّ (افتراضيّ 7)."
    )
    ap.add_argument(
        "--stale-days",
        type=int,
        default=30,
        help="فرع أخمد من هذا يُرشَّح للأرشفة+الحذف (افتراضيّ 30).",
    )
    ap.add_argument("--category", choices=sorted(DELETABLE), help="مع --apply: احذف هذه الفئة فقط.")
    ap.add_argument(
        "--limit", type=int, default=30, help="أقصى عدد يُحذف في التشغيل (دفعات، افتراضيّ 30)."
    )
    ap.add_argument("--owner", default="kafaat")
    ap.add_argument("--repo", default="ai_platform_complete_v2.0.0_enhanced")
    ap.add_argument(
        "--archive", default="sahool-brain/branch_funeral_archive.tsv", help="ledger أرشفة SHA."
    )
    ap.add_argument("--tsv", help="اكتب التصنيف الكامل إلى TSV.")
    ap.add_argument("--apply", action="store_true", help="نفّذ الحذف فعليّاً (بلا هذا: dry-run).")
    ap.add_argument("--yes", action="store_true", help="لا تسأل تأكيداً مع --apply.")
    args = ap.parse_args()

    _rc, _out = _run(["git", "rev-parse", "origin/main"])
    if _rc != 0 or not _out.strip():
        sys.exit("تعذّر تحديد origin/main — شغّل git fetch origin أوّلاً.")
    base_sha = _out.strip()
    now_ts = int(datetime.now(UTC).timestamp())

    branches = _remote_branches()
    merged_set = _merged_pr_branches(args.merged_file)
    rows = classify(branches, merged_set, base_sha, now_ts, args.recent_days, args.stale_days)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["cat"]] = counts.get(r["cat"], 0) + 1
    print(f"origin/main = {base_sha[:9]} · فروع (عدا المحميّة): {len(branches)}")
    print("التصنيف:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"محميّ (لا يُحذَف): {', '.join(sorted(PROTECTED))}")

    if args.tsv:
        with open(args.tsv, "w", encoding="utf-8") as fh:
            fh.write("category\tage_days\tahead\ttip\tbranch\n")
            for r in rows:
                fh.write(f"{r['cat']}\t{r['age']}\t{r['ahead']}\t{r['tip']}\t{r['branch']}\n")
        print(f"TSV كُتِب: {args.tsv}")

    if not args.apply:
        print("\n— DRY-RUN — لا حذف. مُرشَّحون للحذف الآمن (merged-pr + zero-ahead):")
        for r in rows:
            if r["cat"] in ("merged-pr", "zero-ahead"):
                print(f"  [{r['cat']:12}] {r['branch']}")
        print(
            "\nلِلتنفيذ: أعِد بـ--apply --category merged-pr (و/أو zero-ahead / stale-unmerged) --limit N."
        )
        return 0

    if not args.category:
        sys.exit("--apply يتطلّب --category (merged-pr | zero-ahead | stale-unmerged).")
    targets = [r for r in rows if r["cat"] == args.category][: args.limit]
    if not targets:
        print(f"لا فروع في الفئة {args.category}.")
        return 0

    print(f"\nسيُحذَف {len(targets)} فرعاً من '{args.category}' (limit={args.limit}):")
    for r in targets:
        print(f"  {r['branch']}  (tip {r['tip'][:9]}, عمر {r['age']}d)")
    if not args.yes:
        if input("تأكيد الحذف؟ اكتب 'yes': ").strip().lower() != "yes":
            print("أُلغِي.")
            return 0

    # أرشفة SHA قبل أيّ حذف (fail-closed: لا حذف إن فشلت)
    try:
        with open(args.archive, "a", encoding="utf-8") as fh:
            stamp = datetime.now(UTC).strftime("%Y-%m-%d")
            for r in targets:
                fh.write(f"{stamp}\t{args.category}\t{r['tip']}\t{r['branch']}\n")
    except OSError as exc:
        sys.exit(f"فشلت الأرشفة — لا حذف: {exc}")
    print(f"أُرشِفت {len(targets)} SHA في {args.archive} (استرجاع بالـSHA ممكن).")

    deleted = 0
    for r in targets:
        ref = f"repos/{args.owner}/{args.repo}/git/refs/heads/{r['branch']}"
        rc, out = _run(["gh", "api", "-X", "DELETE", ref])
        if rc == 0:
            print(f"  ✓ حُذِف {r['branch']}")
            deleted += 1
        else:
            print(f"  ✗ فشل {r['branch']}: {out.strip()[:120]}")
    print(
        f"\nتمّ: حُذِف {deleted}/{len(targets)}. الاسترجاع: git push origin <SHA>:refs/heads/<branch> من الأرشيف."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
