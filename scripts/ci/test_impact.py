#!/usr/bin/env python3
"""Select the tests a local change touches — by asking the impact engine, not a second model.

Re-running 4300 tests after a two-line edit is waste; re-running only what *seems* related
is worse, because a selector that quietly misses a test is indistinguishable from a green
run. This tool sits between the two by refusing to invent anything: every capability comes
from ``pr_capability_impact_gate.impact`` — the same engine the blocking gate uses — and
every reason printed is that engine's own ``sources`` field.

It owns **no impact logic**. That is not a style preference: this repository measured two
engines answering the same capability question and returning 0 and 12 on identical input
(``CAPABILITY-IMPACT-TOOLS-DISAGREE-01``). A second traversal here would be a third.

**What it can and cannot narrow, measured 2026-08-05.** Of 4123 collected unit cases, 1982
(48%) live in files the engine binds to *no* capability — tree-wide guards whose input is
the whole repository. No cone can reach them, so they are not "unselected"; they are the
floor, and they always run. The ceiling of this tool is therefore roughly halving the local
suite, never eliminating it. That number is printed on every run so a narrowed selection is
never read as full coverage.

**It is an accelerator, not a gate.** Its green means "what was selected passed". CI decides.

**An audit sample measures what the selection drops.** In selected mode a seeded random
sample of the *excluded* tests runs too (the method and formula of Unified Local Lab
``portable_ci_lab.change_selection``: ``max(1, ceil(n * percent / 100))``, seeded by base,
head and the changed paths, so the same change draws the same sample). A failure there is a
measured miss of the cone, not noise. The plan also records the resolved commits, a decision
for every tracked test (selected · floor · audit · excluded-not-run) and its own digest, so
"what was planned" can be checked against "what ran" without trusting either alone.

    bash scripts/ci/test_impact.sh                 # select against origin/main, then run
    python scripts/ci/test_impact.py --plan-only    # print the plan, run nothing
    python scripts/ci/test_impact.py --json         # the plan as data
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا السكربت عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نتيجته (UnicodeEncodeError) ⇒ خروجٌ بغير صفر يُقرَأ حجباً وهو قد مرّ.
# **عند التحميل لا داخل `main()`** — بعضُ المخرَج يُطبَع من جسد الوحدة قبل أيّ نداء.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "docs/architecture/test_impact_policy.json"
GATE_PATH = Path(__file__).resolve().parent / "pr_capability_impact_gate.py"


def _engine():
    """Load the blocking gate as the single source of impact truth.

    Imported by path rather than by package name so this tool works from any working
    directory, and so there is exactly one copy of the traversal in the process.
    """
    spec = importlib.util.spec_from_file_location("_pr_capability_impact_gate", GATE_PATH)
    if not spec or not spec.loader:  # pragma: no cover - a missing engine is fail-closed
        raise SystemExit(f"✗ impact engine not found at {GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_test_files(root: Path = ROOT) -> list[str]:
    """Every tracked test file. Derived from git so a new test is seen the moment it lands."""
    out = subprocess.run(
        ["git", "ls-files", "*/test_*.py", "test_*.py", "*_test.py"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return sorted(line for line in out.stdout.splitlines() if line.strip())


def escalation_reasons(
    changed: list[str],
    policy: dict[str, Any],
    *,
    governance_wide: bool,
    unbound: set[str] | None = None,
) -> list[str]:
    """Why partial selection must be refused. Patterns are policy data, never lines here.

    Three grounds, and the third is the one that costs:

    1. the engine itself flagged a governance-wide reference;
    2. the change alters *how* tests run or *what* CI invokes — no cone reaches that;
    3. a changed **source** file the engine cannot bind to any capability. We do not know
       which tests cover it, so narrowing would be a guess, and the one unrecoverable
       failure mode of a selector is the silent skip. Measured: only 42% of non-test source
       files are bindable, so this fires on roughly 58% of source changes. That is the
       honest price, not a defect.

    Documentation, brain prose and generated artifacts do not escalate merely for being
    unbound — they change no behaviour a test measures, and the ones that matter are caught
    by the path patterns and by the sweep.
    """
    reasons: list[str] = []
    if governance_wide:
        reasons.append("the engine flagged a governance-wide reference")

    triggers = policy["escalation_triggers"]["paths"]
    source_suffixes = tuple(policy["escalation_triggers"]["unbound_source_extensions"])
    for path in changed:
        matched = next((t for t in triggers if t in path), None)
        if matched:
            reasons.append(f"{path} matches the escalation pattern {matched!r}")
            continue
        if unbound and path in unbound and path.endswith(source_suffixes):
            reasons.append(
                f"{path} is a source file the engine binds to no capability — "
                "which tests cover it is unknown, so narrowing would be a guess"
            )
    return reasons


def working_tree_paths(root: Path = ROOT) -> list[str]:
    """Staged, unstaged and untracked paths.

    Found by falsifying this tool against itself: the first version asked the engine only
    for the committed diff, so editing a file and running it reported "0 changed paths, 0
    selected" and exited 0. A local accelerator that is blind to the edit you just made is
    the same shape as everything else this session chased — it ran, and it measured
    nothing.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    paths: list[str] = []
    fields = [f for f in out.stdout.split("\0") if f]
    index = 0
    while index < len(fields):
        entry = fields[index]
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            index += 1  # a rename carries its source in the following field
        index += 1
    return sorted(set(paths))


def ref_exists(ref: str, root: Path = ROOT) -> bool:
    """Whether a git ref resolves here. A shallow CI checkout has no ``origin/main``."""
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )


def select(
    snapshot: Any, affected: set[str], tests: list[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Split the test corpus into what this cone reaches and the floor it can never reach.

    A file the engine binds to no capability is not "unselected" — no cone can reach it, so
    it always runs. Tree-wide guards live there, which is why the measured ceiling is about
    half the suite rather than a small slice of it.
    """
    selected: dict[str, dict[str, Any]] = {}
    floor: list[str] = []
    for path in tests:
        reference = snapshot.references.get(path)
        capabilities = set(reference.capabilities) if reference else set()
        if not capabilities:
            floor.append(path)
            continue
        hit = sorted(capabilities & affected)
        if hit:
            selected[path] = {"capabilities": hit, "sources": sorted(reference.sources)}
    return selected, floor


def audit_sample(excluded: list[str], percent: float, seed: str) -> list[str]:
    """A reproducible sample of excluded tests (Unified Local Lab ``_audit_sample``).

    Empty only when nothing was excluded; otherwise at least one test, so a selection
    that drops anything always spends a little to check what it dropped.
    """
    if not excluded:
        return []
    if not (isinstance(percent, (int, float)) and math.isfinite(percent) and 0 < percent <= 100):
        raise ValueError("audit percent must be in (0, 100]")
    count = min(len(excluded), max(1, math.ceil(len(excluded) * percent / 100.0)))
    return sorted(random.Random(seed).sample(sorted(excluded), count))


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def decide(
    tests: list[str],
    selected: dict[str, Any],
    floor: list[str],
    *,
    mode: str,
    percent: float,
    seed: str,
) -> tuple[list[str], dict[str, int]]:
    """Every tracked test gets exactly one decision; return the audit sample and the counts.

    In full mode everything runs, so nothing is excluded and no audit is drawn.
    """
    if mode == "full":
        return [], {
            "selected": 0,
            "floor": 0,
            "audit": 0,
            "excluded_not_run": 0,
            "full_suite": len(tests),
            "total": len(tests),
        }
    chosen = set(selected) | set(floor)
    excluded = [path for path in tests if path not in chosen]
    audit = audit_sample(excluded, percent, seed)
    return audit, {
        "selected": len(selected),
        "floor": len(floor),
        "audit": len(audit),
        "excluded_not_run": len(excluded) - len(audit),
        "full_suite": 0,
        "total": len(tests),
    }


def resolve_commit(ref: str, root: Path = ROOT) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return out.stdout.strip()


def plan(
    base: str,
    head: str,
    *,
    root: Path = ROOT,
    policy: dict[str, Any] | None = None,
    include_working_tree: bool = True,
) -> dict[str, Any]:
    engine = _engine()
    active = policy or load_policy()
    snapshot = engine.current_snapshot(root=root)

    resolved_base, committed = engine.git_changed_paths(base, head, root=root)
    working = working_tree_paths(root) if include_working_tree else []
    changed = sorted(set(committed) | set(working))
    result = engine.impact(changed, snapshot)
    affected = set(result["affected"])

    tests = discover_test_files(root)
    selected, floor = select(snapshot, affected, tests)

    undecided = [p for p in changed if not _is_bound(snapshot, p)]
    reasons = escalation_reasons(
        changed,
        active,
        governance_wide=result["governance_wide"],
        unbound=set(undecided),
    )

    mode = "full" if reasons else "selected"
    head_commit = resolve_commit(head, root)
    percent = active["audit_sample"]["percent"]
    seed = _digest({"base": resolved_base, "head": head_commit, "changed": changed})
    audit, counts = decide(tests, selected, floor, mode=mode, percent=percent, seed=seed)

    result_plan = {
        "schema": "sahool.test_impact_plan",
        "version": 2,
        "base": resolved_base,
        "head": head,
        "head_commit": head_commit,
        "changed_paths": changed,
        "committed_paths": committed,
        "working_tree_paths": working,
        "affected_capabilities": sorted(affected),
        "direct_capabilities": result["direct"],
        "mode": mode,
        "escalation_reasons": reasons,
        "selected": selected,
        "floor": floor,
        "undecided_changed_paths": undecided,
        "ceiling": active["measured_ceiling"],
        "audit": {
            "percent": percent,
            "seed": seed,
            "population": counts["audit"] + counts["excluded_not_run"],
            "test_paths": audit,
        },
        "decision_counts": counts,
        "authority": "plan-only: what was planned, not what ran or passed",
    }
    result_plan["plan_sha256"] = _digest(result_plan)
    return result_plan


def _is_bound(snapshot: Any, path: str) -> bool:
    for reference_path, reference in snapshot.references.items():
        if path == reference_path:
            return True
        if reference.recursive and path.startswith(reference_path.rstrip("/") + "/"):
            return True
    return False


def paths_to_run(result: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    """Selection ∪ floor ∪ audit — or every tracked test when escalated. The floor is never dropped."""
    if result["mode"] == "full":
        return discover_test_files(root)
    audit = (result.get("audit") or {}).get("test_paths", [])  # absent in a v1 plan
    return sorted(set(result["floor"]) | set(result["selected"]) | set(audit))


def render(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"test_impact: {result['base'][:12]}..{result['head'][:12]}")
    lines.append(
        f"  الملفّات المتغيّرة: {len(result['changed_paths'])} "
        f"(مُلتزَمة {len(result['committed_paths'])} · شجرة العمل {len(result['working_tree_paths'])})"
    )
    lines.append(
        f"  القدرات المتأثّرة: {len(result['affected_capabilities'])} "
        f"(مباشرة {len(result['direct_capabilities'])})"
    )

    if result["mode"] == "full":
        lines.append("  ⚠ الوضع: **الجناح الكامل** — الاختيار الجزئيّ مرفوض:")
        for reason in result["escalation_reasons"]:
            lines.append(f"      · {reason}")
    else:
        lines.append(f"  الوضع: اختيار جزئيّ — {len(result['selected'])} ملفّاً مختاراً")

    for path, why in sorted(result["selected"].items()):
        lines.append(f"    ✓ {path}")
        lines.append(f"        القدرات: {', '.join(why['capabilities'])}")
        lines.append(f"        المصدر : {', '.join(why['sources'])}")

    lines.append(f"  الأرضيّة الثابتة (لا يبلغها مخروط): {len(result['floor'])} ملفّاً")

    counts = result["decision_counts"]
    if result["mode"] != "full":
        audit = result["audit"]
        lines.append(
            f"  عيّنة التدقيق ({audit['percent']}٪ من المستبعَدة، بذرة {audit['seed'][:12]}): "
            f"{counts['audit']} من {audit['population']} — فشلُ أحدها إخفاقٌ مقيس للمخروط"
        )
        for path in audit["test_paths"]:
            lines.append(f"    ◇ {path}")
        lines.append(f"  مستبعَدة لم تُشغَّل: {counts['excluded_not_run']} ملفّاً")

    if result["undecided_changed_paths"]:
        lines.append(
            f"  غير محسوم — المحرّك لا يربط {len(result['undecided_changed_paths'])} "
            "من المسارات المتغيّرة بأيّ قدرة:"
        )
        for path in result["undecided_changed_paths"][:20]:
            lines.append(f"      ? {path}")
        if len(result["undecided_changed_paths"]) > 20:
            lines.append(f"      … و{len(result['undecided_changed_paths']) - 20} غيرها")

    ceiling = result["ceiling"]
    lines.append(
        f"  السقف المقيس ({ceiling['measured_on']}): "
        f"{ceiling['cases_in_the_always_run_floor']} من {ceiling['unit_test_cases']} حالة "
        "تعمل دائماً — الاختيار يُنصِّف ولا يُلغي."
    )
    lines.append(f"  بصمة الخطّة: {result['plan_sha256'][:16]} · رأس {result['head_commit'][:12]}")
    lines.append("  هذه أداة تسريع محلّيّة. القرار النهائيّ لـCI.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--json", action="store_true", help="emit the plan as JSON")
    parser.add_argument(
        "--plan-only", action="store_true", help="print the plan and run nothing (the default)"
    )
    parser.add_argument(
        "--print-paths", action="store_true", help="emit only the test paths, one per line"
    )
    parser.add_argument(
        "--committed-only",
        action="store_true",
        help="ignore the working tree and read only the committed diff",
    )
    args = parser.parse_args(argv)

    if not ref_exists(args.base):
        # Measured on #791: a shallow `actions/checkout` has no `origin/main`, and the
        # first version died with a raw CalledProcessError traceback. The refusal is
        # right — a base that does not resolve cannot produce a delta — but a traceback
        # is not a diagnosis. Name the ref and say what to do.
        print(
            f"✗ لا يُحلّ الأساس {args.base!r} في هذا المستودع.\n"
            f"  استنساخٌ ضحل (`fetch-depth: 1`) لا يحمل `origin/main`. مرّر أساساً قائماً:\n"
            f"      python {Path(__file__).name} --base HEAD~1\n"
            f"  أو اجلب الفرع: git fetch origin main",
            file=sys.stderr,
        )
        return 2

    try:
        result = plan(args.base, args.head, include_working_tree=not args.committed_only)
    except subprocess.CalledProcessError as exc:
        print(f"✗ تعذّر اشتقاق الخطّة: {exc}", file=sys.stderr)
        return 2

    if args.print_paths:
        print("\n".join(paths_to_run(result)))
        return 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
