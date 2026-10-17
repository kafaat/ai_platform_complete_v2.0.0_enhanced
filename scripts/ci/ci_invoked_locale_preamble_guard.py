#!/usr/bin/env python3
"""Every Python file a blocking CI step runs prints non-ASCII only after a UTF-8 preamble.

C-LOCALE-GUARD-SWEEPS-A-NAMING-CONVENTION-NOT-A-CLASS-01.

``guard_locale_survival_guard`` measures the encoding death **by execution**, but its
inventory is a naming convention — ``scripts/ci/*_guard.py``. ``guard_catalogue.py``,
``verify_all_generated.py``, ``tools/sahool_inspector.py`` and every ``*_gate.py`` run in
blocking CI steps and sat outside it because of their names. Widening that sweep to the
class was measured and rejected twice (the gap row): non-guards are generators that
**write the tree** when launched without a flag, and the extra launches cost minutes on
the critical path.

So this guard covers the class **statically** and writes nothing:

* **Inventory** — ``guard_catalogue.discover_script_invocations()``: every Python file
  a blocking step executes, from any directory, via ``python -m``, ``working-directory``,
  literal ``cd`` and one hop into a ``.sh``. The same walk the catalogue uses. A launch
  whose target is not readable off the text **fails closed** — an inventory that drops
  what it cannot read is the naming-convention defect again in another form.
* **Rule** — a script whose source can print non-ASCII text (``print``,
  ``sys.std{out,err}.write``, ``sys.exit(...)``, ``SystemExit(...)``; literal or escaped
  text, and names bound to such text) must reconfigure ``sys.stdout`` **and**
  ``sys.stderr`` to UTF-8 in a module-level statement before its first top-level print —
  **or** be executed by ``guard_locale_survival_guard`` (its ``guard_scripts()``), which
  measures the same property behaviourally.

Why a static rule is honest here, when the gap row rejected a zero ratchet over all of
``scripts/``: that ratchet condemned files no blocking step runs. This one is bounded to
what CI executes, and the preamble is a three-line fix with no behaviour change — while
the death it prevents is measured, not hypothetical: under ``LC_ALL=C`` two scripts in
this inventory died with ``UnicodeEncodeError`` on their **success** path.

    python scripts/ci/ci_invoked_locale_preamble_guard.py           # gate
    python scripts/ci/ci_invoked_locale_preamble_guard.py --list    # inventory only
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from pathlib import Path

# C-LOCALE-GUARD-SWEEPS-A-NAMING-CONVENTION-NOT-A-CLASS-01: the rule applies to itself.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "scripts" / "ci"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, CI / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def inventory() -> tuple[list[str], list[dict]]:
    """(every Python file a blocking step runs, the launches that could not be resolved)."""
    rows = _load("guard_catalogue").discover_script_invocations()
    files = sorted({row["script"] for row in rows if row["status"] == "file"})
    unresolved = [row for row in rows if row["status"] == "unresolved"]
    return files, unresolved


def behaviourally_measured() -> set[str]:
    """What ``guard_locale_survival_guard`` already launches under the C locale."""
    module = _load("guard_locale_survival_guard")
    measured = {p.resolve().relative_to(ROOT).as_posix() for p in module.guard_scripts()}
    measured.add("scripts/ci/guard_locale_survival_guard.py")  # pinned by its own test
    return measured


def _non_ascii(value: object) -> bool:
    return isinstance(value, str) and not value.isascii()


def _bound_names(tree: ast.AST) -> set[str]:
    """Names assigned (anywhere) an expression that contains non-ASCII text — to fixpoint."""
    names: set[str] = set()
    assignments: list[tuple[list[str], ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            assignments.append((targets, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            if isinstance(node.target, ast.Name):
                assignments.append(([node.target.id], node.value))
    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            if set(targets) <= names or not _carries_text(value, names):
                continue
            names.update(targets)
            changed = True
    return names


def _carries_text(node: ast.AST, names: set[str]) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and _non_ascii(sub.value):
            return True
        if isinstance(sub, ast.Name) and sub.id in names:
            return True
    return False


def _is_emission(node: ast.AST) -> bool:
    """A call that writes text to a standard stream when executed."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in ("print", "SystemExit", "exit")
    if isinstance(func, ast.Attribute):
        owner = func.value
        if func.attr == "exit" and isinstance(owner, ast.Name) and owner.id == "sys":
            return True
        if (
            func.attr == "write"
            and isinstance(owner, ast.Attribute)
            and owner.attr in ("stdout", "stderr")
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "sys"
        ):
            return True
    return False


def first_non_ascii_emission(tree: ast.AST) -> int | None:
    """Line of the first emission whose arguments can carry non-ASCII text, else None."""
    names = _bound_names(tree)
    lines = []
    for node in ast.walk(tree):
        if not _is_emission(node):
            continue
        arguments = [*node.args, *(k.value for k in node.keywords if k.arg != "file")]
        if any(_carries_text(argument, names) for argument in arguments):
            lines.append(node.lineno)
    return min(lines) if lines else None


def _reconfigured_streams(statement: ast.stmt) -> set[str]:
    """Which of stdout/stderr this top-level statement reconfigures to UTF-8."""
    streams: set[str] = set()
    loop_streams: set[str] = set()
    if isinstance(statement, ast.For) and isinstance(statement.iter, (ast.Tuple, ast.List)):
        for element in statement.iter.elts:
            if isinstance(element, ast.Attribute) and element.attr in ("stdout", "stderr"):
                loop_streams.add(element.attr)
    for node in ast.walk(statement):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconfigure"
        ):
            continue
        encoding = next((k.value for k in node.keywords if k.arg == "encoding"), None)
        if not (
            isinstance(encoding, ast.Constant)
            and str(encoding.value).lower().replace("-", "") == "utf8"
        ):
            continue
        target = node.func.value
        if isinstance(target, ast.Attribute) and target.attr in ("stdout", "stderr"):
            streams.add(target.attr)
        elif isinstance(target, ast.Name) and loop_streams:
            streams |= loop_streams
    return streams


def _emits_at_top_level(statement: ast.stmt) -> bool:
    """Does executing this top-level statement (not defining a body) emit or run main?"""
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    if isinstance(statement, (ast.Import, ast.ImportFrom)):
        return False
    if isinstance(statement, ast.If):
        test = statement.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            return True
    return any(_is_emission(node) for node in ast.walk(statement))


def has_preamble(tree: ast.Module) -> bool:
    """stdout and stderr both reconfigured to UTF-8 before the first top-level emission."""
    covered: set[str] = set()
    for statement in tree.body:
        covered |= _reconfigured_streams(statement)
        if covered >= {"stdout", "stderr"}:
            return True
        if _emits_at_top_level(statement):
            return False
    return False


def violation(path: Path) -> str | None:
    """Why this script breaks the rule, or None."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return f"unreadable ({type(exc).__name__}) — cannot be measured, so it is not a pass"
    line = first_non_ascii_emission(tree)
    if line is None or has_preamble(tree):
        return None
    return f"prints non-ASCII (line {line}) with no module-level UTF-8 preamble"


def evaluate(files: list[str], unresolved: list[dict], measured: set[str]) -> list[str]:
    findings = [
        f"{row['workflow']} → {row['job']}"
        + (f" (via {row['via']})" if row.get("via") else "")
        + f": unresolved launch `{row['token']}` — the inventory cannot see what it runs"
        for row in unresolved
    ]
    for relative in files:
        if relative in measured:
            continue
        why = violation(ROOT / relative)
        if why:
            findings.append(f"{relative}: {why}")
    return findings


PREAMBLE = (
    "    for _stream in (sys.stdout, sys.stderr):\n"
    '        if hasattr(_stream, "reconfigure"):\n'
    '            _stream.reconfigure(encoding="utf-8")'
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the inventory and exit")
    args = parser.parse_args(argv)

    files, unresolved = inventory()
    measured = behaviourally_measured()
    if args.list:
        for relative in files:
            print(("[executed] " if relative in measured else "[static]   ") + relative)
        return 0

    findings = evaluate(files, unresolved, measured)
    if findings:
        print("ci_invoked_locale_preamble_guard_failed")
        for finding in findings:
            print(f"- {finding}")
        print(
            "\nUnder LC_ALL=C (no PYTHONUTF8) print() encodes ASCII and dies with "
            "UnicodeEncodeError — a correct result reported as a failure. Add at module "
            "level, after the imports and before anything prints:\n" + PREAMBLE
        )
        return 1
    static = len([f for f in files if f not in measured])
    print(
        f"ci_invoked_locale_preamble_guard_ok ({len(files)} Python files run by blocking "
        f"CI steps: {len(files) - static} executed by guard_locale_survival_guard, "
        f"{static} checked statically)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
