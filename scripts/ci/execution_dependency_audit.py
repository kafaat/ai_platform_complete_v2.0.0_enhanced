#!/usr/bin/env python3
"""Generate a conservative static execution/dead-code audit.

Repository evidence only: candidates are not automatically deleted and do not prove runtime reachability.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "execution-audit" / "generated"
SCAN = [ROOT / "services", ROOT / "sahool-platform", ROOT / "shared"]
SKIP = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"}
ROUTE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "websocket",
    "api_route",
}
EXEMPT_NAMES = {
    "main",
    "app",
    "create_app",
    "health",
    "healthz",
    "ready",
    "readyz",
    "startup",
    "shutdown",
}


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def _tracked_files() -> set[str]:
    """git-tracked repo-relative paths. rglob counts transient/untracked ``*.py``
    that exist on a dev machine but not on a clean CI checkout, so ``python_files_parsed``
    (and this audit's drift digest) diverges local-vs-CI. Tracked files ARE the repo."""
    import subprocess

    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {r for r in out.split("\0") if r}


def files():
    # sorted(): rglob order is filesystem-dependent; sort for deterministic output.
    tracked = _tracked_files()
    for base in SCAN:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            if any(part in SKIP for part in p.parts):
                continue
            if p.relative_to(ROOT).as_posix() not in tracked:
                continue
            yield p


def parse(p):
    try:
        return ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError):
        return None


def owner(p: Path) -> str:
    parts = p.relative_to(ROOT).parts
    if parts[0] == "services" and len(parts) > 1:
        return parts[1].replace("_", "-")
    if parts[0] == "sahool-platform":
        return "platform"
    return "shared"


def decorator_route(node):
    for d in getattr(node, "decorator_list", []):
        call = d if isinstance(d, ast.Call) else None
        fn = call.func if call else d
        if isinstance(fn, ast.Attribute) and fn.attr in ROUTE_METHODS:
            path = None
            if (
                call
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
            ):
                path = call.args[0].value
            return fn.attr.upper(), path or "<dynamic>"
    return None


def symbol_index(parsed):
    defs, refs, routes, imports, call_edges = [], Counter(), [], [], []
    for p, tree in parsed.items():
        module = rel(p)
        local_defs = {}
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(n, ast.ClassDef) else "function"
                local_defs[n.name] = n
                defs.append(
                    {
                        "symbol": n.name,
                        "kind": kind,
                        "file": module,
                        "line": n.lineno,
                        "owner": owner(p),
                        "decorated_route": bool(decorator_route(n)),
                    }
                )
                r = decorator_route(n)
                if r:
                    routes.append(
                        {
                            "owner": owner(p),
                            "file": module,
                            "line": n.lineno,
                            "handler": n.name,
                            "method": r[0],
                            "path": r[1],
                        }
                    )
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                refs[n.id] += 1
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
                refs[n.attr] += 1
            elif isinstance(n, ast.Import):
                imports.extend((module, a.name) for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module:
                imports.append((module, n.module))
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                src = n.name
                for c in ast.walk(n):
                    if isinstance(c, ast.Call):
                        if isinstance(c.func, ast.Name):
                            dst = c.func.id
                        elif isinstance(c.func, ast.Attribute):
                            dst = c.func.attr
                        else:
                            continue
                        if dst != src:
                            call_edges.append(
                                {
                                    "owner": owner(p),
                                    "file": module,
                                    "source": src,
                                    "target": dst,
                                    "line": c.lineno,
                                }
                            )
    return defs, refs, routes, imports, call_edges


# Fields that exist only on some Python minor/patch versions (e.g. type_params was
# added to FunctionDef in 3.12) or that ast.dump renders differently across patch
# releases. Excluding them keeps the fingerprint identical across interpreters so the
# --check drift gate is deterministic regardless of the runner's Python version.
_VOLATILE_AST_FIELDS = {"type_params", "type_comment"}


def _canonical(node) -> str:
    """Interpreter-independent structural serialization of an AST fragment.

    Uses only grammar-defined field names (via ast.iter_fields) and repr of scalars;
    it never calls ast.dump, so its output does not depend on the Python version.
    Positional attributes (lineno/col) are excluded by construction.
    """
    if isinstance(node, ast.AST):
        fields = [
            f"{name}={_canonical(value)}"
            for name, value in ast.iter_fields(node)
            if name not in _VOLATILE_AST_FIELDS
        ]
        return f"{type(node).__name__}({','.join(fields)})"
    if isinstance(node, list):
        return "[" + ",".join(_canonical(item) for item in node) + "]"
    return repr(node)


def duplicate_blocks(parsed):
    buckets = defaultdict(list)
    for p, tree in parsed.items():
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(n.body) >= 3:
                signature = _canonical([n.args, n.returns, n.body])
                if len(signature) >= 300:
                    h = hashlib.sha256(signature.encode()).hexdigest()[:16]
                    buckets[h].append(
                        {"file": rel(p), "symbol": n.name, "line": n.lineno, "owner": owner(p)}
                    )
    return [
        {
            "fingerprint": h,
            "occurrences": sorted(v, key=lambda o: (o["file"], o["line"], o["symbol"])),
        }
        for h, v in sorted(buckets.items())
        if len(v) > 1
    ]


def generate():
    parsed = {p: t for p in files() if (t := parse(p)) is not None}
    defs, refs, routes, imports, calls = symbol_index(parsed)
    dead = []
    for d in defs:
        name = d["symbol"]
        if (
            d["decorated_route"]
            or name in EXEMPT_NAMES
            or name.startswith("test_")
            or name.startswith("__")
        ):
            continue
        # Definition itself is not counted as a Load, so zero refs is a conservative candidate.
        if refs[name] == 0:
            confidence = "high" if name.startswith("_") else "medium"
            dead.append(
                {
                    **d,
                    "reference_count": 0,
                    "confidence": confidence,
                    "action": "review_before_delete",
                }
            )
    duplicates = duplicate_blocks(parsed)
    owners = sorted({r["owner"] for r in routes})
    summary = {
        "schema_version": 1,
        "evidence_scope": "static_repository_only",
        "runtime_verified": False,
        "python_files_parsed": len(parsed),
        "route_handlers": len(routes),
        "call_edges": len(calls),
        "dead_code_candidates": len(dead),
        "duplicate_function_groups": len(duplicates),
        "route_owners": len(owners),
        "automatic_deletions": 0,
    }
    payload = {
        "summary": summary,
        "routes": sorted(routes, key=lambda x: (x["owner"], x["file"], x["line"])),
        "call_edges": sorted(calls, key=lambda x: (x["file"], x["line"], x["source"], x["target"])),
        "dead_code_candidates": sorted(dead, key=lambda x: (x["confidence"], x["file"], x["line"])),
        "duplicate_function_groups": duplicates,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "execution_dependency_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "execution_audit_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    with (OUT / "route_handlers.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["owner", "method", "path", "handler", "file", "line"])
        w.writeheader()
        w.writerows(payload["routes"])
    with (OUT / "dead_code_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "confidence",
            "owner",
            "kind",
            "symbol",
            "file",
            "line",
            "reference_count",
            "action",
            "decorated_route",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([{k: x[k] for k in fields} for x in payload["dead_code_candidates"]])
    md = [
        "# Static Execution Dependency and Dead-Code Audit",
        "",
        "> Repository evidence only. This report does not prove runtime reachability and performs no automatic deletion.",
        "",
        "## Summary",
        "",
        f"- Python files parsed: **{summary['python_files_parsed']}**",
        f"- FastAPI-style route handlers: **{summary['route_handlers']}**",
        f"- Static function-call edges: **{summary['call_edges']}**",
        f"- Dead-code candidates: **{summary['dead_code_candidates']}**",
        f"- Duplicate function groups: **{summary['duplicate_function_groups']}**",
        "- Automatic deletions: **0**",
        "",
        "## Highest-confidence dead-code candidates",
        "",
        "| Owner | Symbol | Kind | File | Line |",
        "|---|---|---|---|---:|",
    ]
    for x in [d for d in payload["dead_code_candidates"] if d["confidence"] == "high"][:50]:
        md.append(
            f"| `{x['owner']}` | `{x['symbol']}` | {x['kind']} | `{x['file']}` | {x['line']} |"
        )
    md += [
        "",
        "## Duplicate implementation groups",
        "",
        "| Fingerprint | Occurrences |",
        "|---|---:|",
    ]
    for g in duplicates[:50]:
        md.append(f"| `{g['fingerprint']}` | {len(g['occurrences'])} |")
    md += [
        "",
        "## Interpretation",
        "",
        "A candidate can be invoked dynamically through dependency injection, framework registration, reflection, plugins, task queues, or external entrypoints. Review and focused tests are mandatory before deletion.",
    ]
    (OUT / "EXECUTION_DEPENDENCY_AUDIT_REPORT.md").write_text("\n".join(md) + "\n")
    return payload


def digest():
    h = hashlib.sha256()
    for p in sorted(OUT.glob("*")):
        if p.name == ".audit.sha256":
            continue
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        before = (
            (OUT / ".audit.sha256").read_text().strip() if (OUT / ".audit.sha256").exists() else ""
        )
        generate()
        after = digest()
        if before != after:
            raise SystemExit("execution dependency audit drift detected; run --generate")
        print("execution dependency audit: PASS")
    else:
        generate()
        (OUT / ".audit.sha256").write_text(digest() + "\n")
        print("execution dependency audit generated")


if __name__ == "__main__":
    main()
