#!/usr/bin/env python3
"""A positive text anchor must hold on live code, not on a dead binding or a mandated escape.

TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01.

A text guard reads an anchor in a file and passes while the anchor is present. #824
(``fc88d494``) measured two independent ways that pass for the wrong reason:

* **dead binding** — ``assert "./sections/FieldWorkspaceMapCard" in app`` read ``App.tsx``,
  where the only occurrence was ``const FieldWorkspaceMapCard = lazy(() => import(...))``
  with no consumer. The property ("the shell reuses the card") lived in
  ``FieldWorkspaceRouteShell.tsx``; the anchor held on an unused import, and went red on
  whoever deleted that dead line.
* **mandated escape** — ``toMatch(/if \\(!isPivot\\) \\(poly as any\\)\\.editing.../)``
  required the ``as any`` cast verbatim, so narrowing the type broke the guard. An
  anchor that *requires* a type/lint escape punishes the improvement it should welcome.

Both are decidable from text, so both are measured here over every positive anchor —
``expect(X).toContain(...)`` / ``expect(X).toMatch(...)`` in frontend tests, and
``assert "..." in X`` in Python tests where ``X`` is a statically resolvable file read:

* ``dead_binding`` — every occurrence of the anchor in the read file sits inside an
  ``import`` / ``lazy(() => import(...))`` / ``from ... import`` statement, and none of the
  names those statements bind is used anywhere else in the file;
* ``mandated_escape`` — the anchor text itself contains ``as any`` · ``: any`` ·
  ``@ts-ignore`` · ``@ts-expect-error`` · ``eslint-disable`` · ``# type: ignore`` · ``# noqa``.

**Honesty limit:** the general case — "the property lives in another file" — is not
decidable from text; an anchor on a *live* binding in the wrong file still passes. Only
the two mechanical shapes above are caught. Negative anchors (``not in`` /
``.not.toContain``) are prohibitions, not anchors, and are out of scope.

    python scripts/ci/text_anchor_liveness_guard.py           # gate
    python scripts/ci/text_anchor_liveness_guard.py --stats   # inventory counts
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"}

ESCAPES = (
    "as any",
    ": any",
    "@ts-ignore",
    "@ts-expect-error",
    "eslint-disable",
    "# type: ignore",
    "# noqa",
)


def _shown(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:  # a synthetic tree outside the repository (tests)
        return path.as_posix()


@dataclass(frozen=True)
class Anchor:
    test: str  # repo-relative test file
    line: int
    text: str  # literal text, or regex source for toMatch(/.../)
    target: Path  # the file the anchor is read against
    regex: bool = False


# ── the read file: where does an anchor actually occur? ─────────────────────

_TS_IMPORT = re.compile(
    r"^[ \t]*import\s+(?!\()(?P<clause>[^;'\"]*?)\s*from\s*['\"][^'\"]+['\"]\s*;?"
    r"|^[ \t]*import\s*['\"][^'\"]+['\"]\s*;?",
    re.MULTILINE | re.DOTALL,
)
_TS_LAZY = re.compile(
    r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*(?:React\.)?lazy\s*\("
    r"[^;]*?import\s*\(\s*['\"][^'\"]+['\"]\s*\)[^;]*?\)\s*\)?\s*;?",
    re.MULTILINE | re.DOTALL,
)


def _ts_clause_names(clause: str) -> set[str]:
    clause = re.sub(r"^\s*type\s+", "", clause)
    names: set[str] = set()
    braces = re.search(r"\{([^}]*)\}", clause)
    if braces:
        for part in braces.group(1).split(","):
            part = re.sub(r"^\s*type\s+", "", part.strip())
            if part:
                names.add(part.split(" as ")[-1].strip())
        clause = clause[: braces.start()] + clause[braces.end() :]
    star = re.search(r"\*\s+as\s+(\w+)", clause)
    if star:
        names.add(star.group(1))
        clause = clause.replace(star.group(0), "")
    for part in clause.split(","):
        if re.fullmatch(r"\s*\w+\s*", part):
            names.add(part.strip())
    return names


def binding_spans(path: Path, text: str) -> list[tuple[int, int, set[str]]]:
    """``(start, end, bound names)`` for every import-like statement in the file."""
    spans: list[tuple[int, int, set[str]]] = []
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return spans
        offsets = [0]
        for line in text.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = {(a.asname or a.name).split(".")[0] for a in node.names}
                start = offsets[node.lineno - 1] + node.col_offset
                end = offsets[node.end_lineno - 1] + node.end_col_offset
                spans.append((start, end, names))
        return spans
    for match in _TS_IMPORT.finditer(text):
        clause = match.group("clause")
        spans.append((match.start(), match.end(), _ts_clause_names(clause) if clause else set()))
    for match in _TS_LAZY.finditer(text):
        spans.append((match.start(), match.end(), {match.group("name")}))
    return spans


def _occurrences(anchor: Anchor, text: str) -> list[int]:
    if anchor.regex:
        try:
            return [m.start() for m in re.finditer(anchor.text, text)]
        except re.error:
            return []
    return [m.start() for m in re.finditer(re.escape(anchor.text), text)]


_SPANS: dict[Path, tuple[list[tuple[int, int, set[str]]], str]] = {}


def _spans_and_blanked(path: Path, text: str) -> tuple[list[tuple[int, int, set[str]]], str]:
    """Import-like spans of a file, and its text with those spans blanked — once per file."""
    cached = _SPANS.get(path)
    if cached is None or len(cached[1]) != len(text):
        spans = binding_spans(path, text)
        chars = list(text)
        for start, end, _ in spans:
            chars[start:end] = " " * (end - start)
        cached = (spans, "".join(chars))
        _SPANS[path] = cached
    return cached


def dead_binding(anchor: Anchor, text: str) -> bool:
    """Every occurrence inside import-like statements whose names nothing else uses."""
    positions = _occurrences(anchor, text)
    if not positions:
        return False
    spans, blanked = _spans_and_blanked(anchor.target, text)
    holding: list[tuple[int, int, set[str]]] = []
    for position in positions:
        span = next((s for s in spans if s[0] <= position < s[1]), None)
        if span is None:
            return False
        holding.append(span)
    names = set().union(*(s[2] for s in holding))
    if not names:
        return False  # a side-effect import is live by construction
    return not any(re.search(rf"(?<![\w$]){re.escape(n)}(?![\w$])", blanked) for n in names)


def mandated_escape(anchor: Anchor) -> str | None:
    text = anchor.text.replace("\\", "") if anchor.regex else anchor.text
    return next((escape for escape in ESCAPES if escape in text), None)


# ── Python tests: assert "..." in X, X a statically resolvable file read ────


class _PathEval:
    def __init__(self, test: Path) -> None:
        self.test = test

    def value(self, node: ast.AST, env: dict[str, object]) -> object:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return self.test
            return env.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left, right = self.value(node.left, env), self.value(node.right, env)
            if isinstance(left, Path) and isinstance(right, (str, Path)):
                return left / right
            return None
        if isinstance(node, ast.Attribute):
            base = self.value(node.value, env)
            if isinstance(base, Path) and node.attr == "parent":
                return base.parent
            return None
        if isinstance(node, ast.Subscript):
            base = node.value
            if isinstance(base, ast.Attribute) and base.attr == "parents":
                path = self.value(base.value, env)
                index = node.slice
                if isinstance(path, Path) and isinstance(index, ast.Constant):
                    try:
                        return path.parents[int(index.value)]
                    except (IndexError, ValueError, TypeError):
                        return None
            return None
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Path" and len(node.args) == 1:
                inner = self.value(node.args[0], env)
                return Path(inner) if isinstance(inner, (str, Path)) else None
            if isinstance(func, ast.Attribute):
                base = self.value(func.value, env)
                if isinstance(base, Path) and func.attr in ("resolve", "absolute"):
                    return base.resolve()
                if isinstance(base, Path) and func.attr == "joinpath":
                    parts = [self.value(a, env) for a in node.args]
                    if all(isinstance(p, (str, Path)) for p in parts):
                        return base.joinpath(*parts)
        return None


def _readers(tree: ast.Module) -> set[str]:
    """Module-level functions whose body reads a file from their first argument."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.args.args:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and sub.attr in ("read_text", "read_bytes"):
                    names.add(node.name)
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "open":
                    names.add(node.name)
    return names


def _read_target(
    node: ast.AST, env: dict[str, object], evaluator: _PathEval, readers: set[str]
) -> Path | None:
    """The file whose text this expression is (or is derived from), else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name) and func.id in readers and node.args:
        target = evaluator.value(node.args[0], env)
        return target if isinstance(target, Path) else None
    if isinstance(func, ast.Attribute):
        if func.attr == "read_text":
            target = evaluator.value(func.value, env)
            return target if isinstance(target, Path) else None
        if func.attr == "read" and isinstance(func.value, ast.Call):
            opener = func.value
            if getattr(opener.func, "id", None) == "open" and opener.args:
                target = evaluator.value(opener.args[0], env)
                return target if isinstance(target, Path) else None
        # ``read(p).lower()`` and similar: derived text of the same file.
        return _read_target(func.value, env, evaluator, readers)
    return None


def _bind(statements: list[ast.stmt], env: dict[str, object], evaluator, readers) -> None:
    for statement in statements:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if not isinstance(target, ast.Name):
                continue
            read = _read_target(statement.value, env, evaluator, readers)
            if read is not None:
                env[target.id] = ("read", read)
                continue
            value = evaluator.value(statement.value, env)
            if value is not None:
                env[target.id] = value


def python_anchors(test: Path) -> Iterator[Anchor]:
    try:
        source = test.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if "assert" not in source or not ("read_text" in source or "open(" in source):
        return  # no file read, so no resolvable anchor — skip the parse
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    evaluator = _PathEval(test)
    readers = _readers(tree)
    module_env: dict[str, object] = {}
    _bind(tree.body, module_env, evaluator, readers)
    relative = _shown(test)
    functions = [
        node
        for top in tree.body
        for node in ([top] if not isinstance(top, ast.ClassDef) else top.body)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for function in functions:
        nodes = list(ast.walk(function))
        env = dict(module_env)
        _bind([n for n in nodes if isinstance(n, ast.Assign)], env, evaluator, readers)
        asserted = {id(sub) for n in nodes if isinstance(n, ast.Assert) for sub in ast.walk(n.test)}
        for compare in nodes:
            if id(compare) not in asserted or not (
                isinstance(compare, ast.Compare)
                and len(compare.ops) == 1
                and isinstance(compare.ops[0], ast.In)
                and isinstance(compare.left, ast.Constant)
                and isinstance(compare.left.value, str)
                and isinstance(compare.comparators[0], ast.Name)
            ):
                continue
            bound = env.get(compare.comparators[0].id)
            if isinstance(bound, tuple) and bound[0] == "read":
                yield Anchor(relative, compare.lineno, compare.left.value, bound[1])


# ── frontend tests: expect(X).toContain / toMatch, X a readFileSync binding ─

_TS_CONST = re.compile(r"\b(?:const|let)\s+(\w+)\s*=\s*", re.MULTILINE)
_TS_EXPECT = re.compile(
    r"expect\(\s*(\w+)\s*\)\s*\.(toContain|toMatch)\(\s*"
    r"(?:'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\$]|\\.)*)`|/((?:[^/\\\n]|\\.)+)/[a-z]*)"
    r"\s*\)"
)


def _ts_unquote(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _ts_expression_end(text: str, start: int) -> int:
    depth = 0
    quote = ""
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if char == "\\":
                continue
            if char == quote:
                quote = ""
            continue
        if char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char in ";\n" and depth <= 0:
            return index
    return len(text)


class _TsEval:
    def __init__(self, test: Path) -> None:
        self.test = test
        self.env: dict[str, object] = {}

    def path(self, expression: str) -> Path | str | None:
        expression = expression.strip()
        literal = re.fullmatch(r"'([^']*)'|\"([^\"]*)\"", expression)
        if literal:
            return literal.group(1) if literal.group(1) is not None else literal.group(2)
        if expression in ("__dirname", "here"):
            return self.env.get(expression, self.test.parent)
        if re.fullmatch(r"process\.cwd\(\)", expression):
            return FRONTEND
        if "import.meta.url" in expression and re.fullmatch(
            r"(?:dirname\(fileURLToPath\(import\.meta\.url\)\)|fileURLToPath\(new URL\('\.\/?'\s*,\s*import\.meta\.url\)\))",
            expression,
        ):
            return self.test.parent
        if re.fullmatch(r"\w+", expression):
            value = self.env.get(expression)
            return value if isinstance(value, (Path, str)) else None
        call = re.fullmatch(r"(?:path\.)?(join|resolve)\((.*)\)", expression, re.DOTALL)
        if call:
            parts = [self.path(p) for p in _split_args(call.group(2))]
            if not parts or any(p is None for p in parts) or not isinstance(parts[0], Path):
                return None
            result = parts[0]
            for part in parts[1:]:
                result = result / part
            return Path(str(result)).resolve() if isinstance(result, Path) else None
        return None

    def read(self, expression: str) -> Path | None:
        call = re.fullmatch(
            r"(?:fs\.)?readFileSync\((.*)\)(?:\.\w+\([^()]*\))*", expression.strip(), re.DOTALL
        )
        if call:
            args = _split_args(call.group(1))
            target = self.path(args[0]) if args else None
            return target if isinstance(target, Path) else None
        helper = re.fullmatch(r"(\w+)\((.*)\)", expression.strip(), re.DOTALL)
        if helper and isinstance(self.env.get(helper.group(1)), tuple):
            _, parameter, body = self.env[helper.group(1)]
            args = _split_args(helper.group(2))
            if len(args) == 1:
                return self.read(re.sub(rf"\b{parameter}\b", args[0], body))
        derived = re.fullmatch(r"(\w+)\s*\.\s*\w+[\s\S]*", expression.strip())
        if derived and isinstance(self.env.get(derived.group(1)), list):
            return self.env[derived.group(1)][0]
        return None


def _split_args(text: str) -> list[str]:
    parts, depth, quote, current = [], 0, "", ""
    for char in text:
        if quote:
            current += char
            if char == quote:
                quote = ""
            continue
        if char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def frontend_anchors(test: Path) -> Iterator[Anchor]:
    try:
        text = test.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    yield from frontend_anchors_from_text(test, text)


def frontend_anchors_from_text(test: Path, text: str) -> Iterator[Anchor]:
    """Anchors of a frontend test whose source is ``text`` (``test`` fixes its directory)."""
    evaluator = _TsEval(test)
    for match in _TS_CONST.finditer(text):
        name = match.group(1)
        end = _ts_expression_end(text, match.end())
        expression = text[match.end() : end].strip()
        helper = re.fullmatch(
            r"\(\s*(\w+)(?:\s*:\s*\w+)?\s*\)\s*(?::\s*\w+\s*)?=>\s*(.*)", expression, re.DOTALL
        )
        if helper and "readFileSync" in helper.group(2):
            evaluator.env[name] = ("helper", helper.group(1), helper.group(2))
            continue
        read = evaluator.read(expression)
        if read is not None:
            evaluator.env[name] = [read]
            continue
        value = evaluator.path(expression)
        if value is not None:
            evaluator.env[name] = value
    relative = _shown(test)
    for match in _TS_EXPECT.finditer(text):
        bound = evaluator.env.get(match.group(1))
        if not isinstance(bound, list):
            continue
        literal = next((g for g in match.groups()[2:6] if g is not None), None)
        regex = match.group(6) is not None
        anchor_text = match.group(6) if regex else _ts_unquote(literal or "")
        if not anchor_text:
            continue
        line = text.count("\n", 0, match.start()) + 1
        yield Anchor(relative, line, anchor_text, bound[0], regex)


# ── inventory and verdict ───────────────────────────────────────────────────


def _walk(base: Path, suffixes: tuple[str, ...], prefix: str = "") -> Iterator[Path]:
    """Files under ``base`` ending in one of ``suffixes`` — pruning vendored trees."""
    for directory, subdirectories, files in os.walk(base):
        subdirectories[:] = sorted(d for d in subdirectories if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.startswith(prefix) and name.endswith(suffixes):
                yield Path(directory) / name


def collect_anchors(root: Path = ROOT) -> list[Anchor]:
    anchors: list[Anchor] = []
    for test in _walk(root, (".py",), prefix="test_"):
        anchors.extend(python_anchors(test))
    frontend = root / "frontend"
    if frontend.is_dir():
        for test in _walk(frontend, (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
            anchors.extend(frontend_anchors(test))
    return anchors


def findings(anchors: list[Anchor]) -> list[str]:
    out: list[str] = []
    cache: dict[Path, str | None] = {}
    for anchor in anchors:
        escape = mandated_escape(anchor)
        if escape:
            out.append(
                f"{anchor.test}:{anchor.line}: mandated_escape — the anchor requires "
                f"`{escape}` verbatim, so removing the escape (narrowing the type, "
                "fixing the lint) turns it red. Anchor the property, not the escape."
            )
            continue
        if anchor.target not in cache:
            try:
                cache[anchor.target] = anchor.target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                cache[anchor.target] = None
        text = cache[anchor.target]
        if text is not None and dead_binding(anchor, text):
            shown = _shown(anchor.target)
            out.append(
                f"{anchor.test}:{anchor.line}: dead_binding — `{anchor.text}` occurs in "
                f"{shown} only inside an import whose bound names nothing uses. The anchor "
                "holds on a dead line; read it where the property lives."
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stats", action="store_true", help="print inventory counts too")
    args = parser.parse_args(argv)
    anchors = collect_anchors()
    tests = len({a.test for a in anchors})
    found = findings(anchors)
    if args.stats:
        print(f"anchors={len(anchors)} test_files={tests}")
    if found:
        print("text_anchor_liveness_guard_failed")
        for line in found:
            print(f"- {line}")
        return 1
    print(f"text_anchor_liveness_guard_ok ({len(anchors)} positive anchors in {tests} test files)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
