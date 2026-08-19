#!/usr/bin/env python3
"""Detect duplicate Python definitions in the same lexical scope.

This guard is deliberately scope-aware: methods with the same name in different
classes are valid and must not be reported. Repeated ``@overload`` declarations
are also permitted.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generated_artifact_contract import (  # noqa: E402
    Artifact,
    enforce,
    render_json,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "execution-audit" / "generated" / "duplicate_definitions.json"
SCAN = [ROOT / "services", ROOT / "sahool-platform", ROOT / "shared"]
SKIP = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"}


def _release_manifest_entries() -> dict[str, str]:
    """Fail-closed repository membership for extracted release ZIPs.

    Delivery archives intentionally contain no ``.git``. In that mode the signed
    release checksum manifest is the only accepted membership source; raw ``rglob``
    would admit arbitrary local files and make this generated artifact non-reproducible.
    """
    manifest = ROOT / "release" / "FILE_CHECKSUMS.sha256"
    if not manifest.exists():
        return {}
    if manifest.is_symlink() or not manifest.is_file():
        raise RuntimeError("release checksum manifest must be a regular non-symlink file")
    entries: dict[str, str] = {}
    for lineno, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        parts = raw.split(None, 1)
        if len(parts) != 2:
            raise RuntimeError(f"malformed release checksum manifest line {lineno}")
        digest, rel = parts[0].lower(), parts[1].strip()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise RuntimeError(f"malformed SHA-256 on release checksum manifest line {lineno}")
        rp = Path(rel)
        if rp.is_absolute() or ".." in rp.parts:
            raise RuntimeError(f"unsafe path on release checksum manifest line {lineno}: {rel!r}")
        if rel in entries:
            raise RuntimeError(f"duplicate path on release checksum manifest line {lineno}: {rel}")
        entries[rel] = digest
    return entries


def _tracked_inventory() -> tuple[set[str], dict[str, str] | None]:
    """Repository membership from Git, or digest-bound release membership in ZIP mode."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        tracked = {rel for rel in out.split("\0") if rel}
        if tracked:
            return tracked, None
    except (OSError, subprocess.CalledProcessError):
        pass
    entries = _release_manifest_entries()
    if entries:
        return set(entries), entries
    raise RuntimeError(
        "no git worktree and no release checksum manifest; refusing raw filesystem scan (fail-closed)"
    )


def _verify_manifest_member(path: Path, rel: str, expected: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"manifest member is not a regular file: {rel}")
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError(f"manifest member escapes repository root: {rel}") from exc
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != expected:
        raise RuntimeError(f"release checksum mismatch for scanned file: {rel}")


@dataclass(frozen=True)
class Finding:
    file: str
    scope: str
    symbol: str
    kind: str
    lines: tuple[int, ...]


def iter_files():
    tracked, manifest_entries = _tracked_inventory()
    for base in SCAN:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in SKIP for part in path.parts):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel not in tracked:
                continue
            if manifest_entries is not None:
                _verify_manifest_member(path, rel, manifest_entries[rel])
            yield path


def decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    return ""


def is_overload(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        decorator_name(d) == "overload" for d in node.decorator_list
    )


def scope_findings(path: Path, tree: ast.Module) -> list[Finding]:
    findings: list[Finding] = []

    def visit_body(body: list[ast.stmt], scope: str) -> None:
        by_name: dict[str, list[ast.AST]] = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                by_name.setdefault(node.name, []).append(node)

        for name, nodes in by_name.items():
            if len(nodes) < 2:
                continue
            # Multiple overload declarations are intentional. A concrete implementation
            # plus overloads is also valid; more than one concrete definition is not.
            concrete = [n for n in nodes if not is_overload(n)]
            if len(concrete) <= 1:
                continue
            kinds = {"class" if isinstance(n, ast.ClassDef) else "function" for n in concrete}
            findings.append(
                Finding(
                    file=str(path.relative_to(ROOT)),
                    scope=scope,
                    symbol=name,
                    kind="/".join(sorted(kinds)),
                    lines=tuple(n.lineno for n in concrete),
                )
            )

        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                child_scope = f"{scope}.{node.name}" if scope else node.name
                visit_body(node.body, child_scope)

    visit_body(tree.body, "<module>")
    return findings


def build_payload() -> dict:
    findings: list[Finding] = []
    parsed = 0
    parse_errors: list[str] = []
    for path in iter_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            parse_errors.append(str(path.relative_to(ROOT)))
            continue
        parsed += 1
        findings.extend(scope_findings(path, tree))

    payload = {
        "schema_version": 1,
        "scope_semantics": "same_lexical_scope_only",
        "python_files_parsed": parsed,
        "parse_errors": sorted(parse_errors),
        "duplicate_definitions": [
            asdict(f) for f in sorted(findings, key=lambda x: (x.file, x.scope, x.symbol))
        ],
        "finding_count": len(findings),
    }
    return payload


def artifacts(payload: dict) -> list[Artifact]:
    """المصنوعة الوحيدة التي يملكها هذا الحارس."""
    return [Artifact(OUT, render_json(payload))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    # `--check` كان يستدعي التوليد الكاتب بلا شرط، فيمحو أيّ إفساد قبل أن يقرأه ثمّ
    # «يفحص» ما كتبه للتوّ. الفحص الآن يقارن ولا يكتب.
    enforce(artifacts(payload), write=args.generate, label="duplicate definition guard")
    if args.check and payload["finding_count"]:
        for finding in payload["duplicate_definitions"]:
            print(f"{finding['file']}:{finding['lines']} {finding['scope']}.{finding['symbol']}")
        raise SystemExit(f"duplicate definitions in same lexical scope: {payload['finding_count']}")
    print(f"duplicate definition guard: PASS ({payload['python_files_parsed']} files)")


if __name__ == "__main__":
    main()
